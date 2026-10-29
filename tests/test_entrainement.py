"""Les données d'entraînement (plan IA, IA3) : le lot, à part de la vraie banque ; la génération de nuit, qui reprend
là où elle s'est arrêtée ; le bilan."""

import copy
import hashlib
import json
import os
import sys
import warnings
from collections import Counter
from datetime import datetime, timedelta

import pytest

from generateur import entrainement, programmes
from generateur.donnees import classes, comptes
from generateur.donnees.base import Base
from generateur.entrainement import __main__ as cli
from generateur.entrainement import bilan, jeu, nuit, relecture
from generateur.moteur import banque, config, contre_verification, generation, registre, securite
from generateur.moteur.fournisseurs import ErreurFournisseur
from generateur.moteur.fournisseurs.base import Fournisseur
from generateur.moteur.fournisseurs.maquette import Maquette

from generateur.interface.api import creer_application, decrire_erreur
from generateur.interface.taches import File

with warnings.catch_warnings():  # starlette signale que son client de test préférera bientôt httpx2
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

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
    assert banque.signalements(exemple) == [1]  # maths : N4 refait les calculs des questions 2 et 3, pas l'égalité de la 1
    francais = json.loads(Modele().generer([], {"properties": {"matiere": {"enum": ["francais"]}, "niveau": {"enum": [
        "6e"]}, "questions": {"minItems": 4}}}))
    assert banque.signalements(francais) == []  # hors maths, aucun calcul n'est refait : ce n'est pas un signalement
    for q in francais["questions"]:
        q["index_correct"], q["propositions"] = 0, [q["propositions"][q["index_correct"]]] + \
            [p for i, p in enumerate(q["propositions"]) if i != q["index_correct"]]
    assert banque.signalements(francais) == [0]  # « la bonne réponse est toujours en position 1 »
    exemple["questions"][1]["index_correct"] = 0  # 3² + 4² = 25 : « 7 cm » est faux
    assert banque.signalements(exemple) == [1, 2]


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


# --- la relecture du lot (étape 2) ------------------------------------------------------------------------

def _ligne(ident, matiere, niveau, heure, statut="genere", origine="modele"):
    return {"id": ident, "matiere": matiere, "niveau": niveau, "date": f"2026-10-29T{heure}", "statut": statut,
            "origine": origine}


def test_l_ordre_de_relecture():
    lignes = [_ligne("m1", "maths", "6e", "22:00"), _ligne("m2", "maths", "6e", "22:01"), _ligne("m3", "maths", "6e", "22:02"),
              _ligne("f1", "francais", "5e", "22:03"), _ligne("p1", "maths", "6e", "21:00", origine="procedural"),
              _ligne("a1", "maths", "5e", "20:00", statut="accepte"), _ligne("r1", "francais", "6e", "20:30", statut="rejete"),
              _ligne("g1", "maths", "5e", "23:00")]
    # les classes en alternance (français 5e, maths 5e, maths 6e), dans l'ordre de la génération ; le procédural ; les relus
    assert [l["id"] for l in relecture.ordonner(lignes)] == ["f1", "g1", "m1", "m2", "m3", "p1", "r1", "a1"]
    assert relecture.ordonner([]) == []


def _lot(dossier):
    _ranger(dossier, "qcm-a", "accepte", decisions=[{"statut": "accepte"}], date="2026-10-29T22:00:00")
    _ranger(dossier, "qcm-b", "rejete", decisions=[{"statut": "rejete", "motifs": ["reponse_fausse"]}],
            date="2026-10-29T22:01:00")
    _ranger(dossier, "qcm-c", regenerations=[{"question": 1}], date="2026-10-29T22:02:00")
    _ranger(dossier, "qcm-d", origine="procedural", date="2026-10-29T21:00:00")
    _ranger(dossier, "qcm-e", date="2026-10-29T22:03:00")


def test_compter_et_l_etat_de_la_relecture(tmp_path):
    _lot(tmp_path / "lot")
    _ranger(tmp_path / "banque", "qcm-f", "accepte")
    e = relecture.etat(tmp_path / "lot", tmp_path / "banque")
    assert (e["lot"], e["relus"], e["acceptes"], e["rejetes"], e["motifs"], e["corrections"], e["a_relire"]) == \
        (5, 2, 1, 1, 1, 1, 3)
    assert e["objectif_relus"] == 150 and e["ordre"] == ["qcm-c", "qcm-e", "qcm-d"]
    assert e["jeu"] == {"acceptes_lot": 1, "proceduraux": 1, "acceptes_banque": 1, "total": 3, "objectif": 300,
                        "paires": 1, "motifs": 1}
    assert [m["code"] for m in e["motifs_de_rejet"]] == list(banque.MOTIFS_DE_REJET)
    assert relecture.etat(tmp_path / "lot", None)["jeu"]["acceptes_banque"] == 0


# --- l'interface du lot (--entrainement) ------------------------------------------------------------------

MOT_DE_PASSE = "un mot de passe de test"


def _client(tmp_path, entrainement):
    app = creer_application(File(decrire_erreur=decrire_erreur), entrainement=entrainement,
                            banque_enseignant=tmp_path / "vraie-banque")
    comptes.creer(app.state.base, "prof", "Professeur Essai", MOT_DE_PASSE, "admin")
    c = TestClient(app, base_url="http://127.0.0.1:8002")
    assert c.post("/api/session", json={"identifiant": "prof", "mot_de_passe": MOT_DE_PASSE}).json()["entrainement"] \
        is entrainement
    return c


@pytest.fixture
def interface_du_lot(tmp_path, monkeypatch):
    """L'interface lancée avec --entrainement : ses dossiers de banque sont ceux du lot (ici, tmp_path/banque)."""
    vrai = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai(nom) if nom == "types" else tmp_path / nom)
    _lot(tmp_path / "banque")
    _ranger(tmp_path / "vraie-banque", "qcm-f", "accepte")
    return _client(tmp_path, True)


def test_l_interface_du_lot_ne_sert_qu_a_relire(interface_du_lot):
    c = interface_du_lot
    assert c.get("/api/session").json()["entrainement"] is True
    for methode, chemin, corps in [("POST", "/api/exercices/qcm-a/publications", {"classe_id": 1}),
                                   ("GET", "/api/exercices/qcm-a/publications", None),
                                   ("POST", "/api/generations", {"notion": "les fractions"}), ("GET", "/api/classes", None),
                                   ("GET", "/api/cours", None), ("GET", "/api/comptes", None), ("GET", "/api/journal", None),
                                   ("GET", "/api/eleves/bloques", None), ("GET", "/api/serveur-classe", None)]:
        reponse = c.request(methode, chemin, json=corps)
        assert reponse.status_code == 404 and "lot d'entraînement" in reponse.json()["detail"], chemin
    for chemin in ("/api/types", "/api/exercices", "/api/exercices/qcm-a", "/api/exercices/qcm-a/apercu",
                   "/api/programmes?matiere=maths&niveau=6e", "/api/generations", "/api/entrainement"):
        assert c.get(chemin).status_code == 200, chemin


def test_l_interface_du_lot_relit_dans_l_ordre(interface_du_lot):
    c = interface_du_lot
    assert [x["id"] for x in c.get("/api/exercices").json()["exercices"]] == ["qcm-c", "qcm-e", "qcm-d", "qcm-b", "qcm-a"]
    assert [x["id"] for x in c.get("/api/exercices?statut=genere").json()["exercices"]] == ["qcm-c", "qcm-e", "qcm-d"]
    etat = c.get("/api/entrainement").json()
    assert etat["ordre"] == ["qcm-c", "qcm-e", "qcm-d"] and etat["jeu"]["acceptes_banque"] == 1
    reponse = c.post("/api/exercices/qcm-e/decision", json={"decision": "rejeter", "motif": "trop facile",
                                                            "motifs": ["distracteurs_faciles"]})
    assert reponse.status_code == 200
    assert banque.charger("qcm-e")["meta"]["decisions"][-1]["motifs"] == ["distracteurs_faciles"]
    assert c.post("/api/exercices/qcm-c/decision", json={"decision": "rejeter", "motifs": ["inconnu"]}).status_code == 422
    etat = c.get("/api/entrainement").json()
    assert (etat["relus"], etat["rejetes"], etat["motifs"], etat["ordre"]) == (3, 2, 2, ["qcm-c", "qcm-d"])


def test_l_interface_habituelle_n_a_pas_de_lot(tmp_path, monkeypatch):
    vrai = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai(nom) if nom == "types" else tmp_path / nom)
    c = _client(tmp_path, False)
    assert c.get("/api/session").json()["entrainement"] is False
    assert c.get("/api/entrainement").status_code == 404
    assert c.get("/api/classes").status_code == 200


# --- le jeu de données (étape 3) --------------------------------------------------------------------------

DEMANDE = {"type": "qcm", "matiere": "maths", "niveau": "4e", "notion": "Pythagore", "nb_questions": 3}


def _exercice(ident, statut="accepte", attendu=None, enonce=None, **meta):
    x = copy.deepcopy(registre.charger("qcm").exemple)
    if enonce:
        x["questions"][0]["enonce"] = enonce
    x["meta"] = {"id": ident, "statut": statut, "fournisseur": "llamacpp", "date": "2026-10-29T22:00:00",
                 "demande": DEMANDE, **({"programme": {"attendus": [attendu]}} if attendu else {}), **meta}
    return x


def _ecrire(dossier, *instances):
    dossier.mkdir(parents=True, exist_ok=True)
    for x in instances:
        (dossier / f"{x['meta']['id']}.json").write_text(json.dumps(x, ensure_ascii=False), encoding="utf-8")


def test_une_conversation_d_entrainement():
    x = _exercice("qcm-a")
    m = jeu.messages(x)
    attendus = generation.construire_messages(registre.charger("qcm"), DEMANDE)
    assert [e["role"] for e in m] == ["system", "user", "assistant"] and m[:2] == attendus  # le vrai prompt
    sortie = json.loads(m[2]["content"])
    assert sortie == {k: v for k, v in x.items() if k != "meta"}  # l'exercice, sans meta
    assert list(sortie)[:4] == ["type", "titre", "matiere", "niveau"]
    assert list(sortie["questions"][0]) == ["enonce", "propositions", "explication", "index_correct", "difficulte"]


def test_un_exercice_tire_d_un_cours_garde_ses_sources():
    x = _exercice("qcm-cours")
    passage = {"id": 1, "cours_id": 1, "cours": "pythagore.pdf", "page": 2, "texte": "Le carré de l'hypoténuse…"}
    x["meta"]["cours"] = {"passages": [passage], "sources": [
        {"numero": n, "source": 1, "empreinte": contre_verification.empreinte(q)} for n, q in enumerate(x["questions"], 1)]}
    m = jeu.messages(x)
    assert "Extraits des cours de l'enseignant" in m[1]["content"] and "Le carré de l'hypoténuse" in m[1]["content"]
    assert [list(q)[0] for q in json.loads(m[2]["content"])["questions"]] == ["source"] * 3
    x["questions"][1]["enonce"] = "Une question modifiée à la main ?"  # sa source n'est plus sûre : appris sans cours
    m = jeu.messages(x)
    assert "Extraits des cours" not in m[1]["content"] and "source" not in m[2]["content"]


def test_separer_par_notion():
    exemples = [jeu.Exemple({"meta": {"id": f"x{i}"}}, "lot", notion=f"n{i % 10}") for i in range(30)]
    jeux = jeu.separer(exemples)
    notions = {nom: {e.notion for e in liste} for nom, liste in jeux.items()}
    assert not notions["train"] & notions["test"] and not notions["train"] & notions["valid"]
    assert not notions["valid"] & notions["test"]
    assert (len(jeux["test"]), len(jeux["valid"]), len(jeux["train"])) == (3, 3, 24)
    assert [e.id for e in jeu.separer(exemples)["test"]] == [e.id for e in jeux["test"]]  # toujours la même
    assert [e.id for e in jeu.separer(exemples, graine=1)["test"]] != [e.id for e in jeux["test"]]
    # une notion trop grosse pour 10 % reste à l'entraînement ; les petites vont au test et à la validation
    gros = [jeu.Exemple({"meta": {"id": f"g{i}"}}, "lot", notion="grosse") for i in range(20)]
    jeux = jeu.separer(gros + exemples[:3])
    assert {e.notion for e in jeux["train"]} == {"grosse"} and len(jeux["test"]) == 2 and len(jeux["valid"]) == 1


def test_les_proceduraux_sont_plafonnes():
    autres = [jeu.Exemple({"meta": {"id": f"a{i}"}}, "lot", notion="a") for i in range(6)]
    proceduraux = [jeu.Exemple({"meta": {"id": f"p{i}"}}, "procedural", notion=f"p{i % 2}") for i in range(10)]
    gardes, de_cote = jeu.plafonner(autres + proceduraux, 1 / 3, 2026)
    retenus = [e for e in gardes if e.source == "procedural"]
    assert len(retenus) == 3 and len(de_cote) == 7 and {e.notion for e in retenus} == {"p0", "p1"}
    assert jeu.plafonner(autres, 1 / 3, 2026) == (autres, [])


def test_les_donnees_personnelles_sont_cherchees():
    noms = [("Zoé", "Lefèvre")]
    assert "Zoé Lefèvre" in jeu.donnee_personnelle("Zoé Lefèvre trace un triangle.", noms)
    assert "Marie DUPONT" in jeu.donnee_personnelle("Marie DUPONT a 12 ans.", ())
    assert "courriel" in jeu.donnee_personnelle("écris à prof@college.fr", ())
    assert "lien" in jeu.donnee_personnelle("voir www.exemple.fr", ())
    assert jeu.donnee_personnelle("Dans un triangle ABC rectangle en A, quelle égalité est vraie ?", noms) is None


def test_le_jeu(tmp_path):
    lot, enseignant, rejets = tmp_path / "lot", tmp_path / "banque", tmp_path / "rejets"
    _ecrire(lot, *[_exercice(f"qcm-a{i}", attendu=f"maths.4e.notion-{i}", enonce=f"Question {i} : quelle égalité est vraie ?")
                   for i in range(8)],
            _exercice("qcm-non-relu", "genere", "maths.4e.x", "Une question que personne n'a relue ?"),
            _exercice("qcm-procedural", "genere", "maths.4e.p", "Une question du programme ?", origine="procedural"),
            _exercice("qcm-rejete", "rejete", enonce="Une question rejetée ?",
                      decisions=[{"statut": "rejete", "motifs": ["reponse_fausse"], "motif": "7 cm"}]),
            _exercice("qcm-nom", enonce="Zoé Lefèvre trace un triangle ABC rectangle en A. Quelle égalité est vraie ?"),
            _exercice("qcm-lien", enonce="Voir www.exemple.fr : quelle égalité est vraie ?"),
            _exercice("qcm-doublon", attendu="maths.4e.notion-0", enonce="Question 0 : quelle égalité est vraie ?"))
    ancienne = copy.deepcopy(registre.charger("qcm").exemple["questions"][0]) | {"enonce": "L'ancienne question ?"}
    _ecrire(enseignant, _exercice("qcm-b", attendu="maths.4e.b", enonce="Une question de l'enseignant ?",
                                  regenerations=[{"question": 1, "date": "2026-10-20T10:00:00", "motif": "trop facile",
                                                  "ancienne": ancienne}]),
            _exercice("qcm-maquette", fournisseur="maquette"))
    rejets.mkdir()
    (rejets / "qcm-rejet-n4.json").write_text(json.dumps({"fournisseur": "llamacpp", "niveau": "N4", "erreurs": ["faux"],
                                                          "demande": DEMANDE, "instance": registre.charger("qcm").exemple}))
    dossier = tmp_path / "jeux" / "1"
    m = jeu.construire(lot, enseignant, [rejets], [("Zoé", "Lefèvre")], dossier)

    retenus = {x["id"]: x["source"] for liste in m["jeux"].values() for x in liste}
    assert set(retenus) == {f"qcm-a{i}" for i in range(8)} | {"qcm-b", "qcm-procedural"}  # jamais un non relu
    assert retenus["qcm-procedural"] == "procedural" and retenus["qcm-b"] == "banque"
    raisons = {e["id"]: e["raison"] for e in m["ecartes"]}
    assert "Zoé Lefèvre" in raisons["qcm-nom"] and "lien" in raisons["qcm-lien"] and "doublon" in raisons["qcm-doublon"]
    assert sum(len(l) for l in m["jeux"].values()) == 10 and m["jeux"]["test"] and m["jeux"]["valid"]
    lignes = [json.loads(l) for f in ("train", "valid", "test") for l in (dossier / f"{f}.jsonl").read_text().splitlines()]
    assert len(lignes) == 10 and all([e["role"] for e in l["messages"]] == ["system", "user", "assistant"] for l in lignes)
    paire = json.loads((dossier / "paires.jsonl").read_text())
    assert (paire["exercice"], paire["motif"], paire["rejete"]["enonce"], paire["choisi"]["enonce"]) == \
        ("qcm-b", "trop facile", "L'ancienne question ?", "Une question de l'enseignant ?")
    a_eviter = [json.loads(l) for l in (dossier / "a_eviter.jsonl").read_text().splitlines()]
    assert [(a["id"], a.get("motifs") or a.get("erreurs")) for a in a_eviter] == [("qcm-rejete", ["reponse_fausse"]),
                                                                                  ("qcm-rejet-n4", ["faux"])]
    for f in jeu.FICHIERS:  # figé : en lecture seule, les empreintes au manifeste
        assert not os.access(dossier / f, os.W_OK)
        assert m["empreintes"][f] == hashlib.sha256((dossier / f).read_bytes()).hexdigest()
    texte = (dossier / "fiche.md").read_text(encoding="utf-8")
    assert "**10 exercices** ; objectif avant d'entraîner : 300 (**il en manque 290**)" in texte
    assert "| Relus et acceptés dans le lot | " in texte and "1 paire(s)" in texte and "qcm-nom" in texte
    assert "part procédurale au plus 33 %" in texte
    with pytest.raises(FileExistsError):  # un jeu figé ne s'écrase pas
        jeu.construire(lot, enseignant, [rejets], [], dossier)


def test_la_commande_jeu(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "_REDIRIGES", {nom: tmp_path / nom for nom in ("banque", "rejets", "entrainement", "base")})
    _ecrire(tmp_path / "entrainement" / "banque" / "instances", *[
        _exercice(f"qcm-a{i}", attendu=f"maths.4e.n{i}", enonce=f"Question {i} : quelle égalité est vraie ?") for i in range(3)])
    monkeypatch.setattr(sys, "argv", ["entrainement", "jeu"])
    cli.main()
    assert "Jeu de données : 3 exercices (entraînement 1, validation 1, test 1)" in capsys.readouterr().out
    assert len(list((tmp_path / "entrainement" / "jeux").glob("*/fiche.md"))) == 1
