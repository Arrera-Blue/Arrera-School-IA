"""Outil du point de décision de N4 (docs/etapes/etape-1.3.md §8)."""

import json
from collections import Counter
from pathlib import Path

from generateur.moteur import registre
from generateur.moteur.validation.n4_calcul import A_RELIRE, FAUX, VERIFIE
from generateur.outils.bilan_n4 import Bilan, decision, mesurer, premier_essai, rapport

DONNEES = Path(__file__).parent / "donnees"


def ecrire(chemin: Path, contenu: dict) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")


def test_mesure_acceptes_et_rejetes(tmp_path):
    instances, rejets = tmp_path / "instances", tmp_path / "rejets"
    ecrire(instances / "pythagore.json", registre.charger("qcm").exemple)               # maths, accepté
    ecrire(instances / "histoire.json", {"matiere": "histoire-geo", "questions": []})   # ignoré
    fractions = json.loads((DONNEES / "qcm-fractions-6e-reel.json").read_text(encoding="utf-8"))
    ecrire(rejets / "fractions.json", {"niveau": "N3", "instance": fractions})           # maths, rejeté
    ecrire(rejets / "illisible.json", {"niveau": "N1", "instance": None, "demande": {"notion": "x"}})

    bilan = mesurer(instances, rejets)

    assert (bilan.acceptees, bilan.rejetees, bilan.rejets_non_mesurables) == (1, 1, 1)
    # exemple : à relire, vérifié, vérifié ; fractions : faux, vérifié, faux, faux, faux
    assert bilan.statuts == Counter({VERIFIE: 3, FAUX: 4, A_RELIRE: 1})
    assert "GÉNÉRATEUR PROCÉDURAL" in decision(bilan) and "indicatif" in decision(bilan)
    assert "Questions : 8" in rapport(bilan)


def test_nature_des_questions_fausses(tmp_path):
    # QCM du 25/09 : Q1, Q3, Q4 ont plusieurs bonnes réponses ; Q5 a une réponse annoncée fausse
    ecrire(tmp_path / "instances" / "f.json",
           json.loads((DONNEES / "qcm-fractions-6e-reel.json").read_text(encoding="utf-8")))
    bilan = mesurer(tmp_path / "instances", tmp_path / "rejets")
    assert bilan.faux_par_nature == Counter({"plusieurs bonnes réponses": 3, "réponse annoncée fausse": 1})
    assert "dont plusieurs bonnes réponses : 3" in rapport(bilan)
    assert "remesurer après la reprise" in decision(bilan)


def test_filtre_depuis_une_date(tmp_path):
    instances, rejets = tmp_path / "instances", tmp_path / "rejets"
    ancien = json.loads((DONNEES / "qcm-fractions-6e-reel.json").read_text(encoding="utf-8"))  # meta.date 25/09
    recent = json.loads((DONNEES / "qcm-fractions-6e-20261003-rejete-a-tort.json").read_text(encoding="utf-8"))
    ecrire(instances / "ancien.json", ancien)
    ecrire(rejets / "recent.json", {"date": "2026-10-03T14:09:14", "niveau": "N3", "instance": recent})

    tout = mesurer(instances, rejets)
    assert (tout.acceptees, tout.rejetees, tout.statuts[FAUX]) == (1, 1, 4)

    nouveau_prompt = mesurer(instances, rejets, depuis="2026-10-03")
    assert (nouveau_prompt.acceptees, nouveau_prompt.rejetees) == (0, 1)
    assert nouveau_prompt.statuts == Counter({VERIFIE: 5})


def test_filtre_par_modele(tmp_path):
    # cas réel du 05/10 : un essai de qwen3:4b et un de gemma4 le même jour, à ne pas mélanger
    instances, rejets = tmp_path / "instances", tmp_path / "rejets"
    juste = json.loads((DONNEES / "qcm-fractions-6e-20261003-rejete-a-tort.json").read_text(encoding="utf-8"))
    juste["meta"] = {"date": "2026-10-05T08:45:08", "modele": "gemma4:e4b-it-qat"}
    faux = json.loads((DONNEES / "qcm-fractions-6e-20261003-rejete-a-raison.json").read_text(encoding="utf-8"))
    ecrire(instances / "gemma.json", juste)
    ecrire(rejets / "qwen.json", {"date": "2026-10-05T07:07:19", "modele": "qwen3:4b", "niveau": "N4",
                                  "instance": faux})
    ecrire(rejets / "illisible.json", {"date": "2026-10-05T09:00:00", "modele": "qwen3:4b", "niveau": "N1",
                                       "instance": None, "demande": {}})

    gemma = mesurer(instances, rejets, depuis="2026-10-05", modele="gemma4:e4b-it-qat")
    assert (gemma.acceptees, gemma.rejetees, gemma.rejets_non_mesurables) == (1, 0, 0)
    assert gemma.statuts == Counter({VERIFIE: 5})

    qwen = mesurer(instances, rejets, modele="qwen3:4b")
    assert (qwen.acceptees, qwen.rejetees, qwen.rejets_non_mesurables) == (0, 1, 1)
    assert qwen.statuts == Counter({FAUX: 5})

    assert mesurer(instances, rejets).generations == 2


def test_dossiers_absents(tmp_path):
    bilan = mesurer(tmp_path / "rien", tmp_path / "rien non plus")
    assert bilan.questions == 0 and "aucune question" in decision(bilan)


def test_seuils_de_decision():
    def bilan(verifie: int, faux: int, a_relire: int) -> Bilan:
        return Bilan(acceptees=10, statuts=Counter({VERIFIE: verifie, FAUX: faux, A_RELIRE: a_relire}))

    assert decision(bilan(70, 5, 25)).startswith("garder la chaîne actuelle")
    assert "se trompe trop souvent" in decision(bilan(50, 25, 25))
    assert "ne vérifie pas assez" in decision(bilan(40, 15, 45))
    assert decision(bilan(55, 15, 30)).startswith("zone intermédiaire")


# --- premier essai et après reprise (étape 1.4) --------------------------------------------------

def q(enonce: str, propositions: list[str], index_correct: int) -> dict:
    return {"enonce": enonce, "propositions": propositions, "index_correct": index_correct,
            "explication": "Explication de test, sans importance pour N4."}


JUSTE_1 = q("Quelle fraction est équivalente à 2/3 ?", ["4/5", "6/9", "2/6", "3/6"], 1)
JUSTE_2 = q("Le nombre 0,5 peut s'écrire sous quelle forme de fraction irréductible ?", ["1/5", "5/10", "1/2", "2/1"], 2)
# défaut réel du 05/10 : 1/2, 4/8 et 3/6 valent toutes 2/4
EGALES = q("Quelle est la fraction équivalente à 2/4 ?", ["1/2", "2/8", "4/8", "3/6"], 0)
REMPLACANTE = q("Quelle fraction est équivalente à 1/2 ?", ["2/5", "1/4", "3/6", "2/3"], 2)


def exercice(*questions: dict, **meta) -> dict:
    return {"type": "qcm", "titre": "Les fractions", "matiere": "maths", "niveau": "6e", "notion": "fractions",
            "questions": list(questions), "meta": meta}


def test_premier_essai_defait_les_reprises_de_la_derniere_a_la_premiere():
    autre = q("Quelle fraction est équivalente à 3/4 ?", ["6/8", "3/8", "4/3"], 0)
    final = exercice(JUSTE_1, REMPLACANTE, JUSTE_2)
    reprises = [
        {"tentative": 2, "questions": [2], "resultat": "questions remplacées", "questions_remplacees": [EGALES]},
        {"tentative": 3, "questions": [2], "resultat": "réponse inutilisable (N1)"},
        {"tentative": 4, "questions": [2], "resultat": "questions remplacées", "questions_remplacees": [autre]},
    ]
    assert premier_essai(final, reprises)["questions"] == [JUSTE_1, EGALES, JUSTE_2]
    assert final["questions"] == [JUSTE_1, REMPLACANTE, JUSTE_2]            # l'instance n'est pas modifiée
    assert premier_essai(final, []) is final and premier_essai(final, None) is final


def test_premier_essai_apres_un_exercice_regenere():
    final = exercice(JUSTE_1, JUSTE_2)
    tout = [{"tentative": 2, "questions": "toutes", "resultat": "exercice regénéré",
             "questions_remplacees": [EGALES, JUSTE_2]}]
    assert premier_essai(final, tout)["questions"] == [EGALES, JUSTE_2]
    # premier essai illisible (N1) : rien de bien formé à reconstituer, on garde la première version lisible
    illisible = [{"tentative": 2, "questions": "toutes", "resultat": "exercice regénéré", "questions_remplacees": None}]
    assert premier_essai(final, illisible)["questions"] == [JUSTE_1, JUSTE_2]


def test_bilan_au_premier_essai_et_apres_reprise(tmp_path):
    instances, rejets = tmp_path / "instances", tmp_path / "rejets"
    # cas du 06/10 : question 2 refusée au premier essai, réparée par la reprise
    ecrire(instances / "repare.json", exercice(JUSTE_1, REMPLACANTE, JUSTE_2, reprises=[
        {"tentative": 2, "questions": [2], "resultat": "questions remplacées", "questions_remplacees": [EGALES]}]))
    ecrire(instances / "direct.json", exercice(JUSTE_1, JUSTE_2))
    # abandon après 3 tentatives : la question 1 reste fausse
    ecrire(rejets / "abandon.json", {"niveau": "N4", "instance": exercice(EGALES, JUSTE_2), "reprises": [
        {"tentative": 2, "questions": [1], "resultat": "questions remplacées", "questions_remplacees": [EGALES]},
        {"tentative": 3, "questions": [1], "resultat": "questions remplacées", "questions_remplacees": [EGALES]}]})

    bilan = mesurer(instances, rejets)

    assert (bilan.acceptees, bilan.rejetees, bilan.reprises, bilan.questions_remplacees) == (2, 1, 1, 1)
    assert bilan.statuts == Counter({VERIFIE: 5, FAUX: 2})                # le modèle : 2 fausses sur 7
    assert bilan.statuts_finaux == Counter({VERIFIE: 6, FAUX: 1})         # l'enseignant : 1, dans un rejet
    texte = rapport(bilan)
    assert "Questions : 7, au premier essai" in texte
    assert "Après reprise (1 génération(s) reprise(s), 1 question(s) remplacée(s)) :" in texte
    assert "  fausses   :   1  (14%)" in texte
    assert "ne les corrige pas assez" in decision(bilan)                   # 14 % de fausses après reprise


def test_sans_reprise_le_rapport_ne_change_pas(tmp_path):
    ecrire(tmp_path / "instances" / "direct.json", exercice(JUSTE_1, JUSTE_2))
    texte = rapport(mesurer(tmp_path / "instances", tmp_path / "rejets"))
    assert "Questions : 2\n" in texte and "Après reprise" not in texte


def test_decision_quand_la_reprise_corrige_les_plusieurs_bonnes_reponses():
    def bilan(faux_final: int) -> Bilan:
        return Bilan(acceptees=10, reprises=4, statuts=Counter({VERIFIE: 60, FAUX: 25, A_RELIRE: 15}),
                     faux_par_nature=Counter({"plusieurs bonnes réponses": 25}),
                     statuts_finaux=Counter({VERIFIE: 85 - faux_final, FAUX: faux_final, A_RELIRE: 15}))

    assert "la reprise sur erreur (1.4) les corrige" in decision(bilan(0))
    assert "ne les corrige pas assez" in decision(bilan(20))               # la reprise ne suffit pas
    assert "GÉNÉRATEUR PROCÉDURAL" in decision(bilan(20))
