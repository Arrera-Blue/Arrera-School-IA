"""E4 : le suivi des élèves (generateur/donnees/suivi.py, simulation.py) — réponses recalculées, profils simulés
retrouvés, règles lisibles, groupes et exercices proposés puis validés par l'enseignant, cloisonnement, export."""

import csv
import io
import json
import re

import pytest

from generateur.donnees import classes, comptes, demo, journal, simulation, suivi
from generateur.donnees.base import Base
from generateur.moteur import banque, config

CLE = b"k" * 32
REGLES = {"questions_min": 6, "a_consolider": 0.5, "en_reussite": 0.85}


@pytest.fixture
def base(tmp_path):
    base = Base(tmp_path / "arrera.sqlite3")
    comptes.creer(base, "prof", "Professeur", "un mot de passe de test", "admin")
    comptes.creer(base, "autre", "Autre professeur", "un autre mot de passe")
    return base


@pytest.fixture
def prof(base):
    return comptes.lire(base, "prof")


@pytest.fixture
def autre(base):
    return comptes.lire(base, "autre")


@pytest.fixture
def demo_simulee(base, prof):
    """La classe de démonstration (24 élèves fictifs), remplie par le simulateur."""
    classe, _ = classes.creer(base, prof, "6e Démo", "6e", "2026-2027",
                              [{"nom": n, "prenom": p} for n, p in demo.ELEVES], CLE)
    simulation.simuler(base, prof, classe["id"])
    return classes.lire(base, prof, classe["id"])


def exercice(attendus=("maths.6e.fractions.09",), choisi=True, questions=4, ident="essai-1"):
    return {"titre": "Essai", "niveau": "6e", "matiere": "maths",
            "questions": [{"enonce": f"Question {i}", "propositions": ["a", "b", "c", "d"], "index_correct": i % 4,
                           "difficulte": "difficile" if i == 0 else None} for i in range(questions)],
            "meta": {"id": ident, "programme": {"attendus": list(attendus), "choisi": choisi}}}


# --- enregistrer une tentative ----------------------------------------------------------------------------

def test_juste_ou_faux_est_recalcule(base, prof):
    _, cartes = classes.creer(base, prof, "6e B", "6e", "2026-2027", [{"nom": "DUPONT", "prenom": "Marie"}], CLE)
    instance = exercice()
    ident = suivi.enregistrer_tentative(base, cartes[0]["eleve_id"], instance, [(1, 0, 12.5), (2, 0, None), (4, 3, 3)],
                                        "simulation")
    with base.lire() as conn:
        lignes = [tuple(r) for r in conn.execute("SELECT question, choix, juste, attendu, difficulte FROM reponse "
                                                 "WHERE tentative_id = ? ORDER BY question", (ident,))]
        tentative = conn.execute("SELECT * FROM tentative WHERE id = ?", (ident,)).fetchone()
    assert lignes == [(1, 0, 1, "maths.6e.fractions.09", "difficile"), (2, 0, 0, "maths.6e.fractions.09", None),
                      (4, 3, 1, "maths.6e.fractions.09", None)]
    assert tentative["exercice"] == "essai-1" and tentative["empreinte"] == suivi.empreinte_exercice(instance)
    case = suivi.fiche(base, prof, cartes[0]["eleve_id"])["attendus"][0]   # la question 1 est marquée difficile
    assert case["explication"] == "2 réussites sur 3 questions, dont 1 sur 1 difficile" and case["etat"] == "pas_assez"
    assert suivi.empreinte_exercice(instance) != suivi.empreinte_exercice(exercice(questions=5))


@pytest.mark.parametrize("reponses, message", [([(0, 1, 1)], "question inconnue"), ([(5, 1, 1)], "question inconnue"),
                                               ([(1, 1, 1), (1, 2, 1)], "en double"), ([(1, 4, 1)], "proposition"),
                                               ([(1, -1, 1)], "proposition"), ([(1, "0", 1)], "proposition"),
                                               ([(1, 0, -1)], "temps"), ([(1, 0, 7200)], "temps")])
def test_reponses_impossibles_refusees(base, prof, reponses, message):
    _, cartes = classes.creer(base, prof, "6e B", "6e", "2026-2027", [{"nom": "DUPONT", "prenom": "Marie"}], CLE)
    with pytest.raises(classes.ClasseInvalide, match=message):
        suivi.enregistrer_tentative(base, cartes[0]["eleve_id"], exercice(), reponses, "simulation")
    with base.lire() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tentative").fetchone()[0] == 0  # rien d'enregistré à moitié


def test_attendu_de_chaque_question():
    assert suivi.attendu_de_question(exercice(), 1) == "maths.6e.fractions.09"           # choisi par l'enseignant
    assert suivi.attendu_de_question(exercice(choisi=False), 1) == "maths.6e.fractions.09"  # le seul rattaché
    assert suivi.attendu_de_question(exercice(("maths.6e.fractions.08", "maths.6e.fractions.09"), choisi=False), 1) is None
    procedural = simulation._exercice("maths.6e.fractions.09", "6e", 0)              # le genre du générateur
    procedural["meta"]["programme"] = {"attendus": [], "choisi": False}
    assert suivi.attendu_de_question(procedural, 1) == "maths.6e.fractions.09"


# --- les règles ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("vues, justes, attendu", [(5, 0, "pas_assez"), (5, 5, "pas_assez"), (6, 2, "a_consolider"),
                                                   (6, 3, "en_cours"), (20, 16, "en_cours"), (20, 17, "en_reussite"),
                                                   (8, 8, "en_reussite"), (0, 0, "pas_assez")])
def test_regles_lisibles(vues, justes, attendu):
    """Sous 50 % : à consolider ; à partir de 85 % : en réussite ; moins de 6 questions : pas assez de réponses."""
    assert suivi.etat(vues, justes, REGLES) == attendu


def test_seuils_dans_la_configuration():
    assert suivi.seuils() == {**REGLES, **(config.charger().get("suivi") or {})}


# --- le simulateur et le tableau de suivi ------------------------------------------------------------------

def test_le_tableau_retrouve_les_profils_simules(base, prof, demo_simulee):
    indic = suivi.indicateurs(base, prof, demo_simulee["id"])
    assert [a["code"] for a in indic["attendus"]] == [f"A{i}" for i in range(1, 8)]
    assert {a["id"] for a in indic["attendus"]} == {a for liste in simulation.ATTENDUS["6e"].values() for a in liste}
    for rang, eleve in enumerate(indic["eleves"]):
        profil = simulation.profil(rang)
        for famille, liste in simulation.ATTENDUS["6e"].items():
            for a in liste:
                assert eleve["cases"][a]["etat"] == simulation.etat_attendu(profil, famille), (rang, a)
    case = indic["eleves"][0]["cases"]["maths.6e.fractions.09"]
    assert case == {"vues": 8, "justes": 2, "difficiles_vues": 0, "difficiles_justes": 0, "taux": 0.25,
                    "etat": "a_consolider", "explication": "2 réussites sur 8 questions"}
    besoin = next(b for b in indic["besoins"] if b["attendu"] == "maths.6e.fractions.09")
    ids = [e["id"] for e in indic["eleves"]]
    assert besoin == {"attendu": "maths.6e.fractions.09", "a_consolider": ids[:6], "en_reussite": ids[10:14]}
    assert indic["rappel"] == suivi.RAPPEL and journal.lire(base)[0]["action"] == "suivi_consulte"


def test_vocabulaire_bienveillant(base, prof, demo_simulee):
    """« à consolider », « en réussite » ; jamais « faible », « lacune », « mauvais » (D1)."""
    texte = json.dumps(suivi.indicateurs(base, prof, demo_simulee["id"]), ensure_ascii=False).lower()
    texte += json.dumps(suivi.proposer_groupes(base, prof, demo_simulee["id"]), ensure_ascii=False).lower()
    assert "à consolider" in texte and "en réussite" in texte
    assert not re.search(r"\b(faibles?|lacunes?|mauvais|nuls?)\b", texte)


def test_simulation_deterministe_et_non_doublee(base, prof, demo_simulee):
    with pytest.raises(classes.ClasseInvalide, match="déjà des réponses simulées"):
        simulation.simuler(base, prof, demo_simulee["id"])
    with base.lire() as conn:
        avant = [tuple(r) for r in conn.execute("SELECT r.question, r.choix, r.juste FROM reponse r ORDER BY r.id")]
    assert simulation.simuler(base, prof, demo_simulee["id"], remplacer=True)["tentatives"] == 24 * 7
    with base.lire() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tentative").fetchone()[0] == 24 * 7
        assert [tuple(r) for r in conn.execute("SELECT r.question, r.choix, r.juste FROM reponse r ORDER BY r.id")] == avant
        assert conn.execute("SELECT COUNT(DISTINCT exercice) FROM tentative").fetchone()[0] == 7
    assert journal.lire(base)[0]["action"] == "simulation"


def test_simulation_hors_6e_et_5e_refusee(base, prof):
    classe, _ = classes.creer(base, prof, "4e A", "4e", "2026-2027", [{"nom": "DUPONT", "prenom": "Marie"}], CLE)
    with pytest.raises(classes.ClasseInvalide, match="6e et en 5e"):
        simulation.simuler(base, prof, classe["id"])


def test_simulation_en_5e(base, prof):
    classe, _ = classes.creer(base, prof, "5e A", "5e", "2026-2027",
                              [{"nom": n, "prenom": p} for n, p in demo.ELEVES[:12]], CLE)
    simulation.simuler(base, prof, classe["id"])
    indic = suivi.indicateurs(base, prof, classe["id"])
    assert len(indic["attendus"]) == 4
    assert indic["eleves"][0]["cases"]["maths.5e.nombres-rationnels.01"]["etat"] == "a_consolider"
    assert indic["eleves"][8]["cases"]["maths.5e.proportionnalite.02"]["etat"] == "a_consolider"
    assert indic["eleves"][11]["cases"]["maths.5e.proportionnalite.02"]["etat"] == "en_reussite"


def test_simulation_en_ligne_de_commande(tmp_path, monkeypatch, capsys):
    vrai = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai(nom) if nom == "types" else tmp_path / nom)
    base = Base(tmp_path / "base")
    comptes.creer(base, "prof", "Professeur", "un mot de passe de test", "admin")
    assert simulation.main(["prof"]) == 1 and "pas de classe" in capsys.readouterr().err
    assert demo.main(["prof"]) == 0
    capsys.readouterr()
    assert simulation.main(["prof"]) == 0
    sortie = capsys.readouterr().out
    assert "168 tentatives simulées pour 24 élèves" in sortie and sortie.count("n° ") == 24
    assert sortie.count("à consolider en fractions") == 6 and sortie.count("en réussite partout") == 4
    assert simulation.main(["prof"]) == 1 and "--remplacer" in capsys.readouterr().err
    assert simulation.main(["prof", "--remplacer"]) == 0
    assert simulation.main(["personne"]) == 1


# --- la fiche d'un élève, annuler une tentative --------------------------------------------------------------

def test_fiche_d_un_eleve(base, prof, demo_simulee):
    eleve = demo_simulee["liste"][0]
    f = suivi.fiche(base, prof, eleve["id"])
    assert f["eleve"]["nom"] == eleve["nom"] and f["eleve"]["classe"] == "6e Démo" and len(f["tentatives"]) == 7
    assert {a["id"]: a["etat"] for a in f["attendus"]}["maths.6e.fractions.08"] == "a_consolider"
    assert all(t["questions"] == 8 and t["origine"] == "simulation" and not t["annulee"] for t in f["tentatives"])
    assert journal.lire(base)[0]["action"] == "eleve_consulte"


def test_annuler_une_tentative(base, prof, demo_simulee):
    """Rectification : une tentative faite par erreur ne compte plus, mais reste visible (et rétablissable)."""
    eleve = demo_simulee["liste"][0]
    tentative = next(t for t in suivi.fiche(base, prof, eleve["id"])["tentatives"]
                     if t["exercice"] == "simulation-maths.6e.fractions.08")
    suivi.annuler_tentative(base, prof, tentative["id"])
    assert journal.lire(base)[0]["action"] == "tentative_annulee"
    f = suivi.fiche(base, prof, eleve["id"])
    assert "maths.6e.fractions.08" not in {a["id"] for a in f["attendus"]}
    assert next(t for t in f["tentatives"] if t["id"] == tentative["id"])["annulee"]
    indic = suivi.indicateurs(base, prof, demo_simulee["id"])
    assert "maths.6e.fractions.08" not in indic["eleves"][0]["cases"]
    suivi.annuler_tentative(base, prof, tentative["id"], annulee=False)
    assert suivi.indicateurs(base, prof, demo_simulee["id"])["eleves"][0]["cases"]["maths.6e.fractions.08"]["etat"] \
        == "a_consolider"


# --- les groupes de besoins ---------------------------------------------------------------------------------

def test_groupes_proposes(base, prof, demo_simulee):
    ids = [e["id"] for e in demo_simulee["liste"]]
    groupes = suivi.proposer_groupes(base, prof, demo_simulee["id"])
    par_attendu = {g["attendu"]: g for g in groupes}
    for a in simulation.ATTENDUS["6e"]["fractions"]:
        assert par_attendu[a]["eleves"] == ids[:6] and par_attendu[a]["nature"] == "consolider"
    for a in simulation.ATTENDUS["6e"]["pourcentages"]:
        assert par_attendu[a]["eleves"] == ids[6:10]
    assert "maths.6e.nombres-decimaux.14" not in par_attendu                       # personne à consolider
    assert par_attendu[None] == {"nom": "Pour aller plus loin", "attendu": None, "nature": "approfondir",
                                 "eleves": ids[10:14]}
    assert suivi.lister_groupes(base, prof, demo_simulee["id"]) == []              # rien d'enregistré


def test_creer_ajuster_supprimer_un_groupe(base, prof, demo_simulee):
    ids = [e["id"] for e in demo_simulee["liste"]]
    g = suivi.creer_groupe(base, prof, demo_simulee["id"], "  Fractions   mardi ", "maths.6e.fractions.09", "consolider",
                           ids[:6] + [ids[0]])
    assert g["nom"] == "Fractions mardi" and g["eleves"] == ids[:6] and g["libelle_attendu"].startswith("Comparer")
    g = suivi.modifier_groupe(base, prof, g["id"], "Fractions jeudi", [ids[7], ids[2]])
    assert g["nom"] == "Fractions jeudi" and g["eleves"] == [ids[2], ids[7]]
    assert suivi.lister_groupes(base, prof, demo_simulee["id"]) == [g]
    suivi.supprimer_groupe(base, prof, g["id"])
    assert suivi.lister_groupes(base, prof, demo_simulee["id"]) == []
    assert [e["action"] for e in journal.lire(base)[:3]] == ["groupe_supprime", "groupe_modifie", "groupe_cree"]


@pytest.mark.parametrize("nom, attendu, nature, message", [("", None, "consolider", "nom"),
                                                           ("G", "maths.6e.inconnu.01", "consolider", "attendu inconnu"),
                                                           ("G", None, "trier", "nature")])
def test_groupe_mal_forme(base, prof, demo_simulee, nom, attendu, nature, message):
    with pytest.raises(classes.ClasseInvalide, match=message):
        suivi.creer_groupe(base, prof, demo_simulee["id"], nom, attendu, nature, [])


def test_un_groupe_ne_prend_que_des_eleves_de_la_classe(base, prof, demo_simulee):
    _, cartes = classes.creer(base, prof, "6e B", "6e", "2026-2027", [{"nom": "DUPONT", "prenom": "Marie"}], CLE)
    with pytest.raises(classes.ClasseInvalide, match="hors de la classe"):
        suivi.creer_groupe(base, prof, demo_simulee["id"], "G", None, "approfondir", [cartes[0]["eleve_id"]])


# --- les exercices à travailler -----------------------------------------------------------------------------

BANQUE = [
    {"id": "f09-moyen", "titre": "Comparer, moyen", "niveau": "6e", "attendus": ["maths.6e.fractions.09"], "difficulte": "moyen"},
    {"id": "f09-facile", "titre": "Comparer, facile", "niveau": "6e", "attendus": ["maths.6e.fractions.09"],
     "difficulte": "facile"},
    {"id": "f09-5e", "titre": "Autre classe", "niveau": "5e", "attendus": ["maths.6e.fractions.09"], "difficulte": "facile"},
    {"id": "f09-difficile", "titre": "Comparer, difficile", "niveau": "6e", "attendus": ["maths.6e.fractions.09"],
     "difficulte": "difficile"},
    {"id": "nd07", "titre": "Décimaux, suite", "niveau": "6e", "attendus": ["maths.6e.nombres-decimaux.07"],
     "difficulte": "moyen"},
]


@pytest.fixture
def banque_fictive(monkeypatch):
    """Une banque en mémoire : la vraie banque n'est jamais lue ni touchée."""
    vus = []
    monkeypatch.setattr(banque, "lister", lambda **filtres: vus.append(filtres) or [dict(x) for x in BANQUE])
    return vus


def test_exercices_proposes(base, prof, demo_simulee, banque_fictive):
    ids = [e["id"] for e in demo_simulee["liste"]]
    props = suivi.proposer_exercices(base, prof, demo_simulee["id"])
    assert banque_fictive == [{"statut_voulu": "accepte"}]                         # les exercices acceptés seulement
    assert len(props) == 6 * 3 + 4 * 3 + 4 * 7                                     # à consolider, puis en réussite
    de = lambda eleve, attendu: next(p for p in props if p["eleve_id"] == eleve and p["attendu"] == attendu)
    assert de(ids[0], "maths.6e.fractions.09")["exercice"] == "f09-facile"         # le plus facile, de la classe
    assert de(ids[0], "maths.6e.fractions.08") | {} == {
        "eleve_id": ids[0], "nature": "retravailler", "attendu": "maths.6e.fractions.08",
        "libelle_attendu": "Établir des égalités de fractions", "exercice": None, "titre": None, "a_generer": True,
        "difficulte": "facile"}
    assert de(ids[10], "maths.6e.fractions.09")["exercice"] == "f09-difficile"     # un difficile, même attendu
    assert de(ids[10], "maths.6e.nombres-decimaux.07")["exercice"] == "nd07"       # sinon l'attendu suivant
    assert de(ids[10], "maths.6e.fractions.17")["a_generer"]                       # sinon : à générer
    assert de(ids[10], "maths.6e.fractions.08")["a_generer"]                       # le suivant (.09) : déjà en réussite
    assert len({(p["eleve_id"], p["attendu"]) for p in props}) == len(props)       # une seule par élève et attendu
    assert not [p for p in props if p["eleve_id"] in ids[14:]]                     # en cours : rien à proposer


def test_un_exercice_deja_fait_n_est_pas_repropose(base, prof, demo_simulee, banque_fictive):
    eleve = demo_simulee["liste"][10]["id"]
    suivi.enregistrer_tentative(base, eleve, exercice(ident="f09-difficile"), [(1, 0, 10)], "simulation")
    props = suivi.proposer_exercices(base, prof, demo_simulee["id"])
    assert not [p for p in props if p["eleve_id"] == eleve and p["exercice"] == "f09-difficile"]
    p = next(p for p in props if p["eleve_id"] == eleve and p["attendu"] == "maths.6e.fractions.10")
    assert p["nature"] == "plus_loin" and p["a_generer"]


def test_un_eleve_desactive_n_a_pas_de_proposition(base, prof, demo_simulee, banque_fictive):
    eleve = demo_simulee["liste"][0]["id"]
    classes.activer(base, prof, eleve, False)
    assert not [p for p in suivi.proposer_exercices(base, prof, demo_simulee["id"]) if p["eleve_id"] == eleve]


def test_valider_les_propositions(base, prof, demo_simulee, banque_fictive):
    props = suivi.proposer_exercices(base, prof, demo_simulee["id"])
    assert suivi.lister_propositions(base, prof, demo_simulee["id"]) == []         # rien avant la validation
    assert suivi.valider_propositions(base, prof, demo_simulee["id"], props[:5]) == 5
    gardees = suivi.lister_propositions(base, prof, demo_simulee["id"])
    assert len(gardees) == 5 and journal.lire(base)[0]["action"] == "propositions_validees"
    suivi.supprimer_proposition(base, prof, gardees[0]["id"])
    assert len(suivi.lister_propositions(base, prof, demo_simulee["id"])) == 4
    suivi.valider_propositions(base, prof, demo_simulee["id"], props[5:7])        # remplace les précédentes
    assert len(suivi.lister_propositions(base, prof, demo_simulee["id"])) == 2


@pytest.mark.parametrize("modif", [{"nature": "imposer"}, {"attendu": "maths.6e.inconnu.01"}, {"attendu": None}])
def test_proposition_mal_formee(base, prof, demo_simulee, modif):
    p = {"eleve_id": demo_simulee["liste"][0]["id"], "nature": "retravailler", "attendu": "maths.6e.fractions.09"}
    with pytest.raises(classes.ClasseInvalide):
        suivi.valider_propositions(base, prof, demo_simulee["id"], [{**p, **modif}])


# --- cloisonnement, effacement, export ----------------------------------------------------------------------

def test_un_enseignant_ne_voit_pas_le_suivi_d_un_autre(base, prof, autre, demo_simulee):
    """M9 : chaque enseignant ne voit que ses classes, y compris dans le suivi."""
    eleve = demo_simulee["liste"][0]["id"]
    g = suivi.creer_groupe(base, prof, demo_simulee["id"], "G", None, "approfondir", [eleve])
    suivi.valider_propositions(base, prof, demo_simulee["id"],
                               [{"eleve_id": eleve, "nature": "retravailler", "attendu": "maths.6e.fractions.09"}])
    proposition = suivi.lister_propositions(base, prof, demo_simulee["id"])[0]["id"]
    tentative = suivi.fiche(base, prof, eleve)["tentatives"][0]["id"]
    for appel in (lambda: suivi.indicateurs(base, autre, demo_simulee["id"]),
                  lambda: suivi.fiche(base, autre, eleve),
                  lambda: suivi.annuler_tentative(base, autre, tentative),
                  lambda: suivi.proposer_groupes(base, autre, demo_simulee["id"]),
                  lambda: suivi.lister_groupes(base, autre, demo_simulee["id"]),
                  lambda: suivi.creer_groupe(base, autre, demo_simulee["id"], "G", None, "approfondir", []),
                  lambda: suivi.modifier_groupe(base, autre, g["id"], "G", []),
                  lambda: suivi.supprimer_groupe(base, autre, g["id"]),
                  lambda: suivi.proposer_exercices(base, autre, demo_simulee["id"]),
                  lambda: suivi.valider_propositions(base, autre, demo_simulee["id"], []),
                  lambda: suivi.lister_propositions(base, autre, demo_simulee["id"]),
                  lambda: suivi.supprimer_proposition(base, autre, proposition)):
        with pytest.raises(classes.Introuvable):
            appel()
    assert len(suivi.lister_groupes(base, prof, demo_simulee["id"])) == 1         # rien n'a bougé


def test_supprimer_un_eleve_efface_ses_reponses(base, prof, demo_simulee):
    eleve = demo_simulee["liste"][0]["id"]
    suivi.creer_groupe(base, prof, demo_simulee["id"], "G", None, "approfondir", [eleve])
    suivi.valider_propositions(base, prof, demo_simulee["id"],
                               [{"eleve_id": eleve, "nature": "retravailler", "attendu": "maths.6e.fractions.09"}])
    classes.supprimer(base, prof, eleve)
    with base.lire() as conn:
        for requete in ("SELECT COUNT(*) FROM tentative WHERE eleve_id = ?",
                        "SELECT COUNT(*) FROM reponse r JOIN tentative t ON t.id = r.tentative_id WHERE t.eleve_id = ?",
                        "SELECT COUNT(*) FROM groupe_eleve WHERE eleve_id = ?",
                        "SELECT COUNT(*) FROM proposition WHERE eleve_id = ?"):
            assert conn.execute(requete, (eleve,)).fetchone()[0] == 0, requete
        assert conn.execute("SELECT COUNT(*) FROM tentative").fetchone()[0] == 23 * 7


def test_la_purge_efface_le_suivi(base, prof):
    classe, _ = classes.creer(base, prof, "6e Démo", "6e", "2025-2026",
                              [{"nom": n, "prenom": p} for n, p in demo.ELEVES[:3]], CLE)
    simulation.simuler(base, prof, classe["id"])
    suivi.creer_groupe(base, prof, classe["id"], "G", None, "approfondir", [])
    from datetime import date
    classes.purger(base, prof, date(2026, 10, 24))
    with base.lire() as conn:
        for table in ("tentative", "reponse", "groupe", "groupe_eleve", "proposition"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


def test_l_export_montre_les_reponses(base, prof, demo_simulee):
    eleve = demo_simulee["liste"][0]["id"]
    tentative = suivi.fiche(base, prof, eleve)["tentatives"][0]["id"]
    suivi.annuler_tentative(base, prof, tentative)
    _, contenu = classes.exporter(base, prof, eleve)
    lignes = list(csv.reader(io.StringIO(contenu.decode("utf-8-sig")), delimiter=";"))
    entete = lignes.index(["Date", "Exercice", "Question", "Réponse choisie", "Juste", "Temps (s)",
                           "Attendu du programme", "Origine", "Compte dans le suivi"])
    reponses = [l for l in lignes[entete + 1:] if len(l) == 9]
    assert len(reponses) == 7 * 8 and ["aucune réponse enregistrée"] not in lignes
    assert {l[3] for l in reponses} <= set("ABCD") and {l[4] for l in reponses} == {"oui", "non"}
    assert {l[7] for l in reponses} == {"simulée (élève fictif)"}
    assert sum(l[8] == "non (annulée)" for l in reponses) == 8
    assert ["Groupes de besoins"] in lignes and ["aucun groupe"] in lignes and ["aucun exercice validé"] in lignes


def test_l_export_montre_groupes_et_exercices_valides(base, prof, demo_simulee):
    eleve = demo_simulee["liste"][0]["id"]
    suivi.creer_groupe(base, prof, demo_simulee["id"], "Fractions mardi", "maths.6e.fractions.09", "consolider", [eleve])
    suivi.valider_propositions(base, prof, demo_simulee["id"], [
        {"eleve_id": eleve, "nature": "retravailler", "attendu": "maths.6e.fractions.09", "exercice": "f09-facile"},
        {"eleve_id": eleve, "nature": "plus_loin", "attendu": "maths.6e.fractions.10"}])
    _, contenu = classes.exporter(base, prof, eleve)
    lignes = list(csv.reader(io.StringIO(contenu.decode("utf-8-sig")), delimiter=";"))
    assert ["Fractions mardi"] in lignes
    assert [l[:3] for l in lignes if l[:1] == ["À retravailler"]] == [["À retravailler", "maths.6e.fractions.09", "f09-facile"]]
    assert [l[:3] for l in lignes if l[:1] == ["Pour aller plus loin"]] == [["Pour aller plus loin", "maths.6e.fractions.10",
                                                                             "à générer"]]
