"""N4 — recalcul des questions de maths : les cas de docs/etapes/etape-1.3.md, section 7."""

import json
import time
from fractions import Fraction
from pathlib import Path

import pytest

from generateur.moteur import registre
from generateur.moteur.validation import ErreurValidation
from generateur.moteur.validation.n4_calcul import (A_RELIRE, FAUX, VERIFIE, Incalculable, evaluer, formater,
                                                   valider, verifier, verifier_question)

DONNEES = Path(__file__).parent / "donnees"


def question(enonce: str, propositions: list[str], index_correct: int) -> dict:
    return {"enonce": enonce, "propositions": propositions, "index_correct": index_correct,
            "explication": "Explication de test, sans importance pour N4."}


def statut(enonce: str, propositions: list[str], index_correct: int) -> str:
    return verifier_question(1, question(enonce, propositions, index_correct)).statut


def message(enonce: str, propositions: list[str], index_correct: int) -> str:
    return verifier_question(1, question(enonce, propositions, index_correct)).message


def qcm(*questions: dict, matiere: str = "maths") -> dict:
    return {"type": "qcm", "titre": "Test", "matiere": matiere, "niveau": "6e", "notion": "test",
            "questions": list(questions)}


# --- le critère de fin de plan.md 4.3 et les cas réels --------------------------------------------

def test_critere_du_plan_3_carre_plus_4_carre_ne_donne_pas_7():
    q = question("Combien font 3² + 4² ?", ["7", "25", "14"], 0)
    with pytest.raises(ErreurValidation) as e:
        valider(qcm(q))
    assert e.value.niveau == "N4" and e.value.questions == (1,)
    assert e.value.erreurs == ["question 1 : 3² + 4² = 25, mais la réponse annoncée est « 7 » au lieu de « 25 »"]


def test_qcm_des_fractions_reel():
    instance = json.loads((DONNEES / "qcm-fractions-6e-reel.json").read_text(encoding="utf-8"))
    verdicts = verifier(instance)
    # Q1 et Q4 : deux propositions justes ; Q3 : « simplifiée » admet 2/4 et 1/2 ; Q5 : 2/5 annoncé > 3/7
    assert [v.statut for v in verdicts] == [FAUX, VERIFIE, FAUX, FAUX, FAUX]
    assert verdicts[4].message == ("question 5 : la plus grande valeur est 3/7, "
                                   "mais la réponse annoncée est « 2/5 » au lieu de « 3/7 »")
    assert "« 2/4 », « 1/2 »" in verdicts[2].message


def test_qcm_reel_du_3_octobre_entierement_verifie():
    # premier QCM généré avec le nouveau prompt : les 5 calculs sont justes et reconnus
    instance = json.loads((DONNEES / "qcm-fractions-6e-20261003-rejete-a-tort.json").read_text(encoding="utf-8"))
    assert valider(instance) == {"n4": VERIFIE, "n4_questions": [VERIFIE] * 5}


def test_l_exemple_de_reference_n_est_jamais_marque_faux():
    statuts = [v.statut for v in verifier(registre.charger("qcm").exemple)]
    # Q1 « quelle égalité est vraie ? » n'est pas un calcul ; Q2 hypoténuse ; Q3 réciproque
    assert statuts == [A_RELIRE, VERIFIE, VERIFIE]


# --- calcul direct --------------------------------------------------------------------------------

@pytest.mark.parametrize("enonce, propositions, index_correct", [
    ("Quel est le résultat de 1/2 + 1/3 ?", ["1/5", "2/3", "5/6", "1/6"], 2),
    ("Calcule 7 × 8.", ["54", "56", "64"], 1),
    ("Que vaut 2,5 + 0,25 ?", ["2,75", "2,30", "27,5"], 0),
    ("Combien font 12 ÷ 4 ?", ["3", "4", "8"], 0),
    ("Calcule (2 + 3) × 4.", ["14", "20", "24"], 1),
    ("Quel est le résultat de 1/2 + 1/4 ?", ["3/4", "2/6", "1/8"], 0),
    ("Quel est le résultat de 1/2 + 1/4 ?", ["0,75", "2/6", "1/8"], 0),  # bonne réponse écrite en décimal
    ("Calcule 3 - 5.", ["-2", "2", "8"], 0),
    ("Quel est le résultat de 1/2 + 1/3 ?", ["5/6", "2/5", "1/6"], 0),  # espaces fines insécables
    ("Combien font 3 x 4 ?", ["7", "12", "34"], 1),                              # « x » pour multiplier
    ("Complète : 3 + 4 = ?", ["7", "12", "34"], 0),
    ("Calcule l'opération suivante : 25 - 7.", ["18", "22", "32"], 0),
    ("Quel est le résultat du calcul suivant : 1 000 + 250 ?", ["1250", "1 250 000", "350"], 0),
])
def test_calcul_juste(enonce, propositions, index_correct):
    assert statut(enonce, propositions, index_correct) == VERIFIE


def test_calcul_faux():
    assert message("Quel est le résultat de 1/2 + 1/3 ?", ["2/5", "2/3", "5/6"], 1) == (
        "question 1 : 1/2 + 1/3 = 5/6, mais la réponse annoncée est « 2/3 » au lieu de « 5/6 »")


def test_aucune_proposition_juste():
    assert message("Que vaut 7 × 8 ?", ["54", "48", "64"], 0) == (
        "question 1 : 7 × 8 = 56, et aucune proposition ne correspond")


def test_plusieurs_propositions_justes():
    assert statut("Quel est le résultat de 2/3 - 1/6 ?", ["1/6", "1/2", "3/6"], 1) == FAUX


# --- comparaison, égalité, simplification --------------------------------------------------------

def test_comparaison_juste():
    assert statut("Quelle fraction est la plus petite entre 2/5 et 3/7 ?", ["2/5", "3/7", "1/2"], 0) == VERIFIE


def test_comparaison_a_un_seuil():
    assert statut("Quelle fraction est plus grande que 1/2 ?", ["1/3", "2/5", "3/4"], 2) == VERIFIE
    assert statut("Quelle fraction est plus grande que 1/2 ?", ["1/3", "2/5", "3/4"], 0) == FAUX


def test_comparaison_entre_un_intervalle_n_est_pas_tranchee():
    # « entre 3 et 7 » est peut-être un intervalle : la réponse 6 n'est pas une des valeurs citées
    assert statut("Quel est le plus grand nombre entier entre 3 et 7 ?", ["5", "6", "7"], 1) == A_RELIRE


def test_egalite():
    assert statut("Quelle fraction est égale à 3/4 ?", ["4/3", "6/8", "3/5"], 1) == VERIFIE
    assert statut("Quelle fraction est égale à 3/4 ?", ["4/3", "6/8", "3/5"], 0) == FAUX
    assert statut("Parmi ces fractions, laquelle est égale à 1/2 ?", ["2/4", "2/3", "3/4"], 0) == VERIFIE


def test_egalite_suivie_d_un_calcul_n_est_pas_une_egalite_simple():
    # « égale à 1/2 + 1/4 » : la cible est 3/4, pas 1/2
    assert statut("Quelle fraction est égale à 1/2 + 1/4 ?", ["1/2", "3/4", "2/6"], 0) != VERIFIE


def test_forme_irreductible():
    assert statut("Quelle est la forme irréductible de 4/8 ?", ["2/4", "1/2", "4/2"], 1) == VERIFIE
    assert statut("Quelle est la forme irréductible de 4/8 ?", ["2/4", "1/2", "4/2"], 0) == FAUX


def test_simplifier_n_exige_pas_la_forme_irreductible():
    # 2/4 est bien une simplification de 4/8 (on divise par 2) ; 3/6 n'en est pas une, bien qu'égale
    assert statut("Simplifie la fraction 4/8.", ["2/4", "1/3", "3/5"], 0) == VERIFIE
    assert statut("Simplifie la fraction 4/8.", ["3/6", "1/3", "3/5"], 0) == FAUX


# --- Pythagore ------------------------------------------------------------------------------------

def test_hypotenuse_fausse():
    q = ("Un triangle rectangle a pour côtés de l'angle droit 6 cm et 8 cm. "
         "Quelle est la longueur de l'hypoténuse ?")
    assert message(q, ["14 cm", "10 cm", "100 cm"], 0) == (
        "question 1 : l'hypoténuse mesure √(6² + 8²) = 10 cm, mais la réponse annoncée est « 14 cm » "
        "au lieu de « 10 cm »")


def test_hypotenuse_non_entiere_a_relire():
    q = ("Un triangle rectangle a pour côtés de l'angle droit 2 cm et 3 cm. "
         "Quelle est la longueur de l'hypoténuse ?")
    assert statut(q, ["5 cm", "3,6 cm", "13 cm"], 1) == A_RELIRE


def test_reciproque():
    q = "Un triangle a des côtés de 4 cm, 5 cm et 6 cm. Est-il rectangle ?"
    assert statut(q, ["Oui, car 6 est le plus grand côté", "Non, car 4² + 5² ≠ 6²"], 1) == VERIFIE
    assert message(q, ["Oui, car 6 est le plus grand côté", "Non, car 4² + 5² ≠ 6²"], 0) == (
        "question 1 : 4² + 5² = 41 ≠ 6² = 36, donc le triangle n'est pas rectangle, "
        "mais la réponse annoncée est « Oui, car 6 est le plus grand côté »")


# --- prudence : jamais « faux » sur une réponse juste ----------------------------------------------
# Un faux « faux » serait renvoyé au modèle par la reprise sur erreur, qui « corrigerait » une bonne
# réponse. Dans chacun de ces cas, la réponse annoncée est JUSTE et l'énoncé transforme les nombres.

@pytest.mark.parametrize("enonce, propositions, index_correct", [
    ("Calcule le double de 3 + 4.", ["7", "14", "10"], 1),
    ("Quel est le résultat de 3 + 4 si on le multiplie par 2 ?", ["7", "14", "9"], 1),
    ("Quelle fraction, multipliée par 2, est égale à 3/4 ?", ["3/4", "3/8", "6/4"], 1),
    ("Le double de quel nombre est plus grand que 10 ?", ["3", "4", "6"], 2),
    ("Quelle fraction est plus grande que 1/2 une fois son inverse calculé ?", ["3/4", "1/3", "2/3"], 1),
    ("Laquelle est la plus grande entre 2/5 et 3/7 si on ajoute 1 à chacune ?", ["7/5", "10/7", "2"], 1),
])
def test_un_enonce_qui_transforme_les_nombres_n_est_jamais_declare_faux(enonce, propositions, index_correct):
    assert statut(enonce, propositions, index_correct) != FAUX


@pytest.mark.parametrize("enonce, propositions", [
    ("Dans un triangle ABC rectangle en A, quelle égalité est vraie ?", ["BC² = AB² + AC²", "AB² = BC² + AC²"]),
    ("Léa a 3 billes et en gagne 2. Combien en a-t-elle ?", ["5", "6", "1"]),        # problème rédigé
    ("Calcule 1/2 + 1/3 puis 2 × 3.", ["5/6", "6", "11"]),                            # deux expressions
    ("Quelle fraction n'est pas égale à 1/2 ?", ["2/4", "3/6", "2/3"]),               # question négative
    ("Donne une valeur approchée de 10 ÷ 3.", ["3,3", "3,4", "3"]),                   # arrondi
    ("Que vaut 1/2 + 1/3 ?", ["cinq sixièmes", "2/5", "1/6"]),                        # réponse en lettres
    ("Quel est le résultat de 1/2 + 1/3 ? Donne la forme irréductible.", ["5/6", "2/5", "10/12"]),
])
def test_ce_qui_n_est_pas_reconnu_est_a_relire(enonce, propositions):
    assert statut(enonce, propositions, 0) == A_RELIRE


def test_hors_maths_tout_est_a_relire():
    # architecture §9.4 et plan.md 4.3 : « Hors maths : marquage à relire »
    q = question("En quelle année a eu lieu la prise de la Bastille ?", ["1789", "1792", "1815"], 0)
    assert valider(qcm(q, matiere="histoire-geo")) == {"n4": A_RELIRE, "n4_questions": [A_RELIRE]}


def test_bilan_de_l_exercice():
    juste = question("Calcule 7 × 8.", ["54", "56", "64"], 1)
    inconnue = question("Léa a 3 billes et en gagne 2. Combien en a-t-elle ?", ["5", "6", "1"], 0)
    assert valider(qcm(juste, juste)) == {"n4": VERIFIE, "n4_questions": [VERIFIE, VERIFIE]}
    assert valider(qcm(juste, inconnue)) == {"n4": A_RELIRE, "n4_questions": [VERIFIE, A_RELIRE]}


# --- calcul sûr -----------------------------------------------------------------------------------

@pytest.mark.parametrize("expression, attendu", [
    ("1/2 + 1/3", Fraction(5, 6)), ("3² + 4²", 25), ("0,1 + 0,2", Fraction(3, 10)), ("2^10", 1024),
    ("(2 + 3) × 4", 20), ("−3 + 5", 2), ("12 : 4", 3), ("2³", 8), ("2^-2", Fraction(1, 4)),
    ("1 000 + 250", 1250), ("1/2 + 1/3", Fraction(5, 6)),
])
def test_evaluer(expression, attendu):
    assert evaluer(expression) == attendu


@pytest.mark.parametrize("expression", [
    "__import__('os').system('ls')",   # rien n'est exécuté : caractères refusés
    "1/0", "2 ** 99999", "9^9^9", "(10**10)**10", "1234567890123 + 1", "2(3 + 4)", "", "1 +",
])
def test_evaluer_refuse(expression):
    with pytest.raises(Incalculable):
        evaluer(expression)


def test_evaluer_reste_rapide_sur_une_expression_piegee():
    debut = time.monotonic()
    with pytest.raises(Incalculable):
        evaluer("9**9**9**9")
    assert time.monotonic() - debut < 0.1


def test_une_tentative_d_execution_dans_l_enonce_ne_fait_rien():
    q = question("Calcule __import__('os').system('ls') + 1.", ["1", "2", "3"], 0)
    assert verifier_question(1, q).statut == A_RELIRE


@pytest.mark.parametrize("valeur, en_fraction, texte", [
    (Fraction(5, 6), True, "5/6"), (Fraction(56), True, "56"), (Fraction(3, 4), False, "0,75"),
    (Fraction(1, 3), False, "1/3"), (Fraction(-5, 2), False, "-2,5"),
])
def test_formater(valeur, en_fraction, texte):
    assert formater(valeur, en_fraction) == texte
