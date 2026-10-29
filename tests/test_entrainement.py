"""Les données d'entraînement (plan IA, IA3) : le lot, à part de la vraie banque ; la génération de nuit, qui reprend
là où elle s'est arrêtée ; le bilan."""

import copy
import json
import sys
from collections import Counter
from datetime import datetime, timedelta

import pytest

from generateur import entrainement, programmes
from generateur.donnees import classes, comptes
from generateur.donnees.base import Base
from generateur.entrainement import __main__ as cli
from generateur.entrainement import bilan, nuit
from generateur.moteur import banque, config, generation, registre, securite
from generateur.moteur.fournisseurs import ErreurFournisseur
from generateur.moteur.fournisseurs.base import Fournisseur
from generateur.moteur.fournisseurs.maquette import Maquette

CLE = b"k" * 32
QUESTIONS = [
    ("Quel mot est un nom commun ?", ["maison", "rapide", "courir", "très"], "« maison » désigne une chose."),
    ("Quel mot est un verbe ?", ["chanter", "table", "joli", "sous"], "« chanter » exprime une action."),
    ("Quel mot est un adjectif ?", ["grand", "pomme", "partir", "avec"], "« grand » qualifie un nom."),
    ("Quel mot est un déterminant ?", ["le", "chat", "dormir", "vite"], "« le » précède le nom."),
    ("Quel mot est une préposition ?", ["dans", "arbre", "manger", "bleu"], "« dans » introduit un complément."),
    ("Quel mot est un adverbe ?", ["lentement", "fleur", "venir", "petit"], "« lentement » modifie un verbe."),
]


class Modele(Fournisseur):
    """Le faux modèle : un QCM de grammaire, à la matière, à la classe et au nombre de questions demandés."""
    nom, modele = "faux", "faux-modele"

    def generer(self, messages, schema):
        p = schema["properties"]
        exercice = copy.deepcopy(registre.charger("qcm").exemple)
        exercice |= {"matiere": p["matiere"]["enum"][0], "niveau": p["niveau"]["enum"][0], "titre": "Les classes de mots",
                     "notion": "les classes de mots"}
        exercice["questions"] = []
        for i in range(p["questions"]["minItems"]):
            enonce, propositions, explication = QUESTIONS[i]
            rang = i % 4
            propositions = propositions[1:rang + 1] + [propositions[0]] + propositions[rang + 1:]
            exercice["questions"].append({"enonce": enonce, "propositions": propositions, "explication": explication,
                                          "index_correct": rang, "difficulte": "facile"})
        return json.dumps(exercice, ensure_ascii=False)


@pytest.fixture
def lot(tmp_path, monkeypatch):
    """Les dossiers de la banque, de la base et du lot dans tmp_path (redirigés comme le fait `entrainement.utiliser`),
    et le faux modèle (ou la maquette, si on la demande)."""
    monkeypatch.setattr(config, "_REDIRIGES", {nom: tmp_path / nom for nom in
                                              ("banque", "rejets", "supprimes", "sortie", "base", "entrainement")})
    monkeypatch.setattr(generation, "creer", lambda nom, reglages: Maquette() if nom == "maquette" else Modele())
    return tmp_path


def commande(attendu: str, passe: int = 1, questions: int = 4) -> nuit.Commande:
    a = programmes.attendu(attendu)
    return nuit.Commande(passe, {"type": "qcm", "matiere": a.matiere, "niveau": a.niveau,
                                 "notion": programmes.notion_de(attendu), "attendu": attendu, "nb_questions": questions})


FRANCAIS = [a.id for a in programmes.lister("francais", "6e", qcm=True)][:3]
FRACTIONS = next(a.id for a in programmes.lister("maths", "6e", qcm=True)
                 if generation.procedural.aiguiller({"matiere": "maths", "niveau": "6e", "attendu": a.id}) == "fractions")


# --- le plan ----------------------------------------------------------------------------------------------

def test_le_plan_couvre_chaque_attendu_a_chaque_passe():
    attendus = {a.id for a in programmes.lister(qcm=True) if a.matiere in ("maths", "francais")
                and a.niveau in ("6e", "5e")}
    commandes = nuit.plan()
    assert len(attendus) == 239 and len(commandes) == 3 * 239
    for passe in (1, 2, 3):
        assert sorted(c.demande["attendu"] for c in commandes if c.passe == passe) == sorted(attendus)
    assert len({c.cle for c in commandes}) == len(commandes)
    premiers = [[c.demande["attendu"] for c in commandes if c.passe == p][:20] for p in (1, 2)]
    assert premiers[0] != premiers[1]  # un ordre tiré au sort à chaque passe
    # une nuit interrompue tôt couvre déjà les deux matières et les deux classes
    assert {(c.demande["matiere"], c.demande["niveau"]) for c in commandes[:30]} == \
        {("maths", "6e"), ("maths", "5e"), ("francais", "6e"), ("francais", "5e")}


def test_le_plan_est_toujours_le_meme_et_varie_les_demandes():
    assert [c.demande for c in nuit.plan()] == [c.demande for c in nuit.plan()]  # une nuit reprend la précédente
    assert [c.demande for c in nuit.plan(graine=1)] != [c.demande for c in nuit.plan()]
    demandes = [c.demande for c in nuit.plan()]
    assert set(Counter(d["nb_questions"] for d in demandes)) == set(nuit.QUESTIONS)
    assert set(Counter(d.get("difficulte") for d in demandes)) == set(nuit.DIFFICULTES)


def test_les_demandes_du_plan_sont_valables():
    for c in nuit.plan(passes=1):
        d = c.demande
        assert d["matiere"] == programmes.attendu(d["attendu"]).matiere and len(d["notion"]) <= 120
        propre = securite.controler_demande(d, ())  # aucune n'est refusée par les contrôles de sécurité (IA1)
        assert propre["attendu"] == d["attendu"] and propre["notion"] == securite.nettoyer(d["notion"])


def test_la_notion_d_un_attendu_tient_dans_le_schema():
    long = max(programmes.lister(), key=lambda a: len(a.libelle))
    assert len(long.libelle) > 120
    notion = programmes.notion_de(long.id)
    assert len(notion) <= 120 and notion.endswith("…")
    theme = programmes.attendu(FRANCAIS[0]).theme_id
    assert programmes.notion_de(theme) == programmes.theme(theme)["theme"]


def test_l_heure_de_fin_est_la_prochaine():
    soir = datetime(2026, 10, 29, 22, 0)
    assert nuit.heure_de_fin("07:30", soir) == datetime(2026, 10, 30, 7, 30)
    assert nuit.heure_de_fin("23:15", soir) == datetime(2026, 10, 29, 23, 15)


# --- le lot, à part de la vraie banque --------------------------------------------------------------------

def test_rediriger_range_ailleurs_pour_tout_le_processus(tmp_path):
    vraie = config.chemin("banque")
    config.rediriger({"entrainement": tmp_path / "lot"})
    assert config.chemin("banque") == vraie
    entrainement.utiliser()
    assert config.chemin("banque") == tmp_path / "lot" / "banque" / "instances"
    assert config.chemin("rejets") == tmp_path / "lot" / "banque" / "rejets"
    assert config.chemin("sortie") == tmp_path / "lot" / "sortie"
    assert config.chemin("types") == config.RACINE / "generateur" / "types"  # le reste ne bouge pas


def test_le_lot_n_est_jamais_versionne():
    ignore = (config.RACINE / ".gitignore").read_text(encoding="utf-8").split()
    assert "/donnees/" in ignore and config.charger()["chemins"]["entrainement"].startswith("donnees/")


# --- la génération de nuit --------------------------------------------------------------------------------

def test_la_nuit_range_les_exercices_dans_le_lot_et_reprend(lot):
    lignes = []
    resultats = nuit.nuit([commande(a) for a in FRANCAIS[:2]], afficher=lignes.append)
    assert resultats == Counter(genere=2)
    du_lot = list((lot / "entrainement" / "banque" / "instances").glob("*.json"))
    assert len(du_lot) == 2 and not (lot / "banque").exists()  # rien dans la banque de l'enseignant
    instance = json.loads(du_lot[0].read_text(encoding="utf-8"))
    assert instance["meta"]["entrainement"]["passe"] == 1 and instance["meta"]["statut"] == banque.GENERE
    assert instance["meta"]["programme"]["attendus"][0] in FRANCAIS
    assert list((lot / "entrainement" / "sortie").glob("*.html"))
    journal = nuit.lire_journal()
    assert [e["resultat"] for e in journal] == ["genere", "genere"] and journal[0]["id"]
    assert "[1/2] francais 6e" in lignes[1] and "✓ gardé (modele" in lignes[1]

    lignes.clear()
    assert nuit.nuit([commande(a) for a in FRANCAIS], afficher=lignes.append) == Counter(genere=1)
    assert "1 demande(s) à faire sur 3" in lignes[0]
    assert len(nuit.lire_journal()) == 3


def test_procedural_et_rejet(lot):
    resultats = nuit.nuit([commande(FRACTIONS, questions=5), commande(FRANCAIS[0])], fournisseur="maquette",
                          afficher=lambda _: None)
    assert resultats == Counter(genere=1, rejete=1)  # la maquette renvoie l'exemple (maths, 4e) : N2 le refuse
    gardee, rejetee = nuit.lire_journal()
    assert gardee["origine"] == "procedural"
    assert rejetee["niveau"] == "N2" and rejetee["rejet"]
    assert (lot / "entrainement" / "banque" / "rejets" / rejetee["rejet"]).is_file()
    assert not (lot / "rejets").exists()
    assert nuit.nuit([commande(FRACTIONS, questions=5), commande(FRANCAIS[0])], afficher=lambda _: None) == Counter()


def test_trois_erreurs_de_suite_arretent_la_nuit_et_seront_refaites(lot, monkeypatch):
    def panne(*a, **k):
        raise ErreurFournisseur("le modèle ne se charge pas")

    vraie = generation.generer
    monkeypatch.setattr(generation, "generer", panne)
    lignes = []
    assert nuit.nuit([commande(a, passe=p) for p in (1, 2) for a in FRANCAIS], afficher=lignes.append) == \
        Counter(erreur=3)
    assert "Arrêt : 3 erreurs de suite" in lignes[-2]
    monkeypatch.setattr(generation, "generer", vraie)
    assert nuit.nuit([commande(a) for a in FRANCAIS], afficher=lambda _: None) == Counter(genere=3)


def test_une_erreur_isolee_n_arrete_pas_la_nuit(lot, monkeypatch):
    vraie = generation.generer
    appels = []

    def parfois(demande, **k):
        appels.append(demande["attendu"])
        if len(appels) == 1:
            raise RuntimeError("un défaut du code")
        return vraie(demande, **k)

    monkeypatch.setattr(generation, "generer", parfois)
    assert nuit.nuit([commande(a) for a in FRANCAIS], afficher=lambda _: None) == Counter(erreur=1, genere=2)
    assert "RuntimeError : un défaut du code" in nuit.lire_journal()[0]["erreur"]


def test_l_heure_de_fin_et_le_nombre(lot):
    passee = datetime.now() - timedelta(minutes=1)
    assert nuit.nuit([commande(a) for a in FRANCAIS], fin=passee, afficher=lambda _: None) == Counter()
    assert nuit.nuit([commande(a) for a in FRANCAIS], nombre=1, afficher=lambda _: None) == Counter(genere=1)


def test_les_noms_de_tous_les_eleves_sont_proteges(lot, monkeypatch):
    base = Base(config.chemin("base"))
    for identifiant in ("prof", "autre"):
        comptes.creer(base, identifiant, "Professeur", "un mot de passe de test")
    prof, autre = (comptes.lire(base, i) for i in ("prof", "autre"))
    classes.creer(base, prof, "6e B", "6e", "2026-2027", [{"nom": "Lefèvre", "prenom": "Zoé"}], CLE)
    classes.creer(base, autre, "5e A", "5e", "2026-2027", [{"nom": "Durand", "prenom": "Jade"}], CLE)
    vus = []
    vraie = generation.generer
    monkeypatch.setattr(generation, "generer", lambda d, **k: vus.append(k["noms_proteges"]) or vraie(d, **k))
    nuit.nuit([commande(FRANCAIS[0])], afficher=lambda _: None)
    assert sorted(vus[0]) == [("Jade", "Durand"), ("Zoé", "Lefèvre")]


def test_les_signalements():
    exemple = copy.deepcopy(registre.charger("qcm").exemple)
    assert nuit.signalements(exemple) == [1]  # maths : N4 refait les calculs des questions 2 et 3, pas l'égalité de la 1
    francais = json.loads(Modele().generer([], {"properties": {"matiere": {"enum": ["francais"]}, "niveau": {"enum": [
        "6e"]}, "questions": {"minItems": 4}}}))
    assert nuit.signalements(francais) == []  # hors maths, aucun calcul n'est refait : ce n'est pas un signalement
    for q in francais["questions"]:
        q["index_correct"], q["propositions"] = 0, [q["propositions"][q["index_correct"]]] + \
            [p for i, p in enumerate(q["propositions"]) if i != q["index_correct"]]
    assert nuit.signalements(francais) == [0]  # « la bonne réponse est toujours en position 1 »
    exemple["questions"][1]["index_correct"] = 0  # 3² + 4² = 25 : « 7 cm » est faux
    assert nuit.signalements(exemple) == [1, 2]


# --- le bilan ---------------------------------------------------------------------------------------------

def _ranger(dossier, ident, statut="genere", origine=None, fournisseur="llamacpp", **meta):
    instance = copy.deepcopy(registre.charger("qcm").exemple)
    instance["meta"] = {"id": ident, "statut": statut, "fournisseur": fournisseur, "date": "2026-10-29T22:00:00",
                        **({"origine": origine} if origine else {}), **meta}
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"{ident}.json").write_text(json.dumps(instance, ensure_ascii=False), encoding="utf-8")


def test_le_bilan(tmp_path):
    lot, enseignant = tmp_path / "lot", tmp_path / "banque"
    _ranger(lot, "a", "accepte", decisions=[{"statut": "accepte"}])
    _ranger(lot, "b", "rejete", decisions=[{"statut": "rejete", "motif": "trop facile"}])
    _ranger(lot, "c", "accepte", decisions=[{"statut": "accepte"}], modifications=[{"question": 1}])
    _ranger(lot, "d", origine="procedural")
    _ranger(lot, "e")
    _ranger(enseignant, "f", "accepte", regenerations=[{"question": 2}])
    _ranger(enseignant, "g", "accepte", fournisseur="maquette")  # l'exemple, pas un exercice
    journal = [{"cle": "1:x", "passe": 1, "resultat": "erreur", "duree_s": 3, "demande": {"matiere": "maths", "niveau": "6e"}},
               {"cle": "1:x", "passe": 1, "resultat": "genere", "duree_s": 60, "demande": {"matiere": "maths", "niveau": "6e"}},
               {"cle": "1:y", "passe": 1, "resultat": "rejete", "duree_s": 90, "demande": {"matiere": "francais", "niveau": "5e"}},
               {"cle": "2:x", "passe": 2, "resultat": "genere", "duree_s": 50, "demande": {"matiere": "maths", "niveau": "6e"}}]
    texte = bilan.bilan(lot, journal, enseignant)
    assert "Demandes faites : 3 (passe 1 : 2, passe 2 : 1)" in texte
    assert "Exercices gardés : 2 ; rejetés par N1 → N4 : 1 ; demandes refusées : 0 ; erreurs, à refaire : 0" in texte
    assert "| maths | 6e | 2 | 0 | 0 |" in texte and "| francais | 5e | 0 | 1 | 0 |" in texte
    assert "Relus : 3 sur 150 visés ; acceptés 2, rejetés 1 (dont 1 motif(s) de rejet écrit(s))" in texte
    assert "Corrections (questions corrigées à la main ou régénérées) : 1." in texte
    assert "| Lot : procéduraux sans erreur, non relus (calculs justes par construction) | 1 |" in texte
    assert "| Banque de l'enseignant : exercices acceptés | 1 |" in texte
    assert "| Paires avant → après (lot et banque) | 2 |" in texte
    assert "Exercices acceptés (relus, procéduraux, banque) : **4**" in texte


def test_le_bilan_sans_rien(tmp_path):
    assert "Aucune demande faite" in bilan.bilan(tmp_path / "lot", [], tmp_path / "banque")


def test_la_commande_bilan(lot, monkeypatch, capsys):
    nuit.nuit([commande(FRANCAIS[0])], afficher=lambda _: None)
    monkeypatch.setattr(config, "_REDIRIGES", {nom: lot / nom for nom in ("banque", "entrainement")})
    monkeypatch.setattr(sys, "argv", ["entrainement", "bilan", "--sortie", str(lot / "bilan.md")])
    cli.main()
    assert "Exercices gardés : 1" in capsys.readouterr().out
    assert "Exercices dans le lot : 1." in (lot / "bilan.md").read_text(encoding="utf-8")
