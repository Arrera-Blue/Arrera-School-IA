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


def test_qcm_reel_du_3_octobre_rejete_a_raison():
    # second QCM du 03/10 : les 5 questions sont fausses ; Q2 (« somme de ») et Q5 (« différence entre »)
    # n'étaient pas reconnues avant l'ajout du reconnaisseur d'opérations nommées
    instance = json.loads((DONNEES / "qcm-fractions-6e-20261003-rejete-a-raison.json").read_text(encoding="utf-8"))
    verdicts = verifier(instance)
    assert [v.statut for v in verdicts] == [FAUX] * 5
    assert verdicts[4].message == ("question 5 : la différence de 5/6 et 1/3 vaut 1/2, "
                                   "mais la réponse annoncée est « 1/6 » au lieu de « 1/2 »")


def test_qcm_reel_du_3_octobre_troisieme_essai():
    # Q2 et Q5 : plusieurs fractions égales justes ; Q3 : « 2/5 » annoncée ET « 2/5 est plus grande »
    # proposée : deux formulations de la bonne réponse, donc jamais « vérifié »
    instance = json.loads((DONNEES / "qcm-fractions-6e-20261003-troisieme.json").read_text(encoding="utf-8"))
    assert [v.statut for v in verifier(instance)] == [A_RELIRE, FAUX, A_RELIRE, A_RELIRE, FAUX]


# Les 5 QCM de gemma4:e4b-it-qat du 05/10 (même demande : « un QCM de 5 questions sur les fractions pour
# des 6e »). Les 25 réponses annoncées sont justes ; les « faux » sont des questions à plusieurs bonnes
# réponses, que N3 rejetait déjà.
GEMMA_20261005 = [
    ("084508 accepté", [
        ("Quelle fraction représente la partie coloriée d'une figure divisée en 8 parties égales, dont 3 sont "
         "coloriées ?", ["3/8", "8/3", "3/5", "5/8"], 0, VERIFIE),
        ("Le nombre 0,5 peut s'écrire sous quelle forme de fraction irréductible ?",
         ["1/5", "5/10", "1/2", "2/1"], 2, VERIFIE),
        ("Si tu as un gâteau coupé en 4 parts égales et que tu en manges 1, quelle fraction du gâteau as-tu "
         "mangée ?", ["1/4", "4/1", "3/4", "1/3"], 0, VERIFIE),
        ("Pour additionner 1/3 et 1/6, quel est le dénominateur commun le plus petit ?",
         ["3", "6", "18", "2"], 1, VERIFIE),
        ("Quelle est la fraction équivalente à 2/5 si on multiplie le numérateur et le dénominateur par 3 ?",
         ["6/15", "2/8", "5/15", "6/8"], 0, VERIFIE),
    ]),
    ("091759 rejeté", [
        ("Quelle fraction représente la partie hachurée de la figure ci-jointe ?",          # figure absente : N3
         ["1/3", "1/2", "2/3", "3/4"], 1, A_RELIRE),
        ("Simplifier la fraction 6/12 donne :", ["2/6", "3/4", "1/2", "6/12"], 2, VERIFIE),
        ("Le nombre 3/5 est égal à quel nombre décimal ?", ["0,35", "0,53", "0,6", "3,5"], 2, A_RELIRE),
        ("Quelle est la fraction équivalente à 2/4 ?", ["1/2", "2/8", "4/8", "3/6"], 0, FAUX),
        ("Si tu as 10 parts et que tu en manges 3, quelle fraction as-tu mangée ?",
         ["3/10", "7/10", "10/3", "3/7"], 0, VERIFIE),
    ]),
    ("124620 rejeté", [
        ("Quelle fraction représente la partie coloriée d'une figure divisée en 4 parties égales, dont 1 est "
         "colorée ?", ["1/2", "1/3", "1/4", "4/1"], 2, VERIFIE),
        ("Dans la fraction 3/5, quel nombre est le dénominateur ?", ["3", "5", "8", "1"], 1, A_RELIRE),
        ("Quelle fraction est équivalente à 1/2 ?", ["2/5", "1/4", "3/6", "2/3"], 2, VERIFIE),
        ("Si tu as 12 bonbons et que tu en donnes 4, quelle fraction des bonbons as-tu donnés ?",
         ["4/12", "8/12", "1/3", "1/4"], 0, FAUX),
        ("Simplifie la fraction 6/9 en trouvant la fraction équivalente la plus simple.",
         ["2/3", "3/6", "6/18", "1/9"], 0, VERIFIE),
    ]),
    ("124848 rejeté", [
        ("Quelle fraction représente la partie coloriée d'une figure divisée en 4 parts égales, dont 1 est "
         "colorée ?", ["4/1", "1/4", "1/3", "3/4"], 1, VERIFIE),
        ("Pour simplifier la fraction 6/12, quel est le plus grand diviseur commun au numérateur et au "
         "dénominateur ?", ["2", "3", "6", "12"], 2, A_RELIRE),
        ("Comment écrire le nombre 0,5 sous forme de fraction irréductible ?",
         ["5/10", "1/2", "2/5", "5/5"], 1, VERIFIE),
        ("Quel est le résultat de l'addition de deux fractions : 1/4 + 1/4 ?",
         ["2/8", "2/4", "1/2", "2/16"], 1, FAUX),
        ("Si tu as une tarte entière et que tu en manges 2/3, quelle fraction de tarte te reste-t-il ?",
         ["1/3", "2/3", "3/2", "1/6"], 0, A_RELIRE),
    ]),
    ("125113 accepté", [
        ("Quelle fraction représente la partie coloriée d'un rectangle divisé en 8 parties, dont 3 sont "
         "coloriées ?", ["3/8", "8/3", "3+8", "1/8"], 0, VERIFIE),
        ("L'écriture décimale 0,5 correspond à quelle fraction simplifiée ?",
         ["1/5", "5/100", "1/2", "2/5"], 2, VERIFIE),
        ("Si tu as une tarte coupée en 10 parts égales et que tu en manges 4, quelle fraction as-tu mangée ?",
         ["4/10", "10/4", "4/6", "1/4"], 0, VERIFIE),
        ("Pour additionner 1/4 et 1/2, quel est le dénominateur commun le plus petit ?",
         ["2", "4", "8", "1/2"], 1, VERIFIE),
        ("Quelle fraction est équivalente à 2/3 ?", ["4/5", "6/9", "2/6", "3/6"], 1, VERIFIE),
    ]),
]


@pytest.mark.parametrize("nom, questions", GEMMA_20261005, ids=[nom for nom, _ in GEMMA_20261005])
def test_qcm_reels_du_5_octobre_gemma(nom, questions):
    instance = qcm(*(question(e, p, i) for e, p, i, _ in questions))
    assert [v.statut for v in verifier(instance)] == [attendu for *_, attendu in questions]


def test_bilan_des_5_qcm_gemma():
    # avant les extensions du 05/10 : 9 vérifiées, 0 fausse, 16 à relire
    statuts = [attendu for _, questions in GEMMA_20261005 for *_, attendu in questions]
    assert (statuts.count(VERIFIE), statuts.count(FAUX), statuts.count(A_RELIRE)) == (17, 3, 5)


def test_une_reformulation_de_la_bonne_reponse_empeche_le_verdict_verifie():
    enonce = "Quelle fraction est plus grande : 1/3 ou 2/5 ?"
    assert statut(enonce, ["1/3", "2/5", "1/3 est plus grande", "2/5 est plus grande"], 1) == A_RELIRE
    assert statut(enonce, ["1/3", "2/5", "1/3 est plus grande", "les deux sont égales"], 1) == VERIFIE
    assert statut(enonce, ["1/3", "2/5", "3/4"], 1) == VERIFIE


@pytest.mark.parametrize("enonce, propositions, index_correct, attendu", [
    ("Quelle est la somme de 1/3 et 1/6 ?", ["1/2", "2/9", "1/9"], 0, VERIFIE),
    ("Quelle est la somme de 1/3 et 1/6 ?", ["1/2", "2/9", "3/6"], 0, FAUX),        # deux bonnes réponses
    ("Quelle est la différence entre 5/6 et 1/3 ?", ["1/2", "1/6", "2/3"], 1, FAUX),
    ("Quelle est la différence entre 1/3 et 5/6 ?", ["1/2", "1/6", "2/3"], 0, A_RELIRE),  # ordre ambigu
    ("Calcule le produit de 3 et 4.", ["7", "12", "34"], 1, VERIFIE),
    ("Quel est le quotient de 12 par 4 ?", ["3", "8", "48"], 0, VERIFIE),
    ("Quel est le quotient de 12 par 0 ?", ["0", "12", "1"], 0, A_RELIRE),
    ("Quelle est la somme de 1/3 et 1/6 si on la double ?", ["1", "1/2", "2/9"], 0, A_RELIRE),
])
def test_operations_nommees(enonce, propositions, index_correct, attendu):
    assert statut(enonce, propositions, index_correct) == attendu


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


def test_forme_la_plus_simple_vaut_irreductible():
    # cas réel du 06/10 (gemma4) : 3/6 et 2/4 simplifient bien 6/12, mais pas « à sa forme la plus simple »
    enonce = "Simplifie la fraction 6/12 à sa forme la plus simple."
    assert statut(enonce, ["3/6", "1/2", "2/4", "6/12"], 1) == VERIFIE
    assert statut(enonce, ["3/6", "1/2", "2/4", "6/12"], 0) == FAUX
    assert statut("Écris 6/12 sous sa forme la plus simple.", ["3/6", "1/2", "2/4"], 1) == VERIFIE


@pytest.mark.parametrize("enonce, propositions, index_correct, attendu", [
    ("Le nombre 0,5 peut s'écrire sous quelle forme de fraction irréductible ?", ["5/10", "1/2", "1/5"], 1, VERIFIE),
    ("Le nombre 0,5 peut s'écrire sous quelle forme de fraction irréductible ?", ["5/10", "1/2", "1/5"], 0, FAUX),
    ("Écris 25 % sous forme de fraction irréductible.", ["25/100", "1/4", "1/25"], 1, VERIFIE),
    ("Écris 1,5 sous forme de fraction irréductible.", ["15/10", "3/2", "1/5"], 1, VERIFIE),
    ("Écris 0,5 sous forme de fraction irréductible.", ["5/10", "un demi", "1/5"], 1, A_RELIRE),  # en lettres
    ("Écris -0,5 sous forme de fraction irréductible.", ["-1/2", "1/2", "-5/10"], 0, A_RELIRE),   # négatif
    ("Écris 3 sous forme de fraction irréductible.", ["3", "3/1", "6/2"], 0, A_RELIRE),           # entier seul
    ("Simplifie 0,5.", ["1/2", "5/10", "0,05"], 0, A_RELIRE),                    # irréductible non demandée
    ("L'écriture décimale 0,5 correspond à quelle fraction simplifiée ?", ["5/10", "1/2", "1/5"], 1, VERIFIE),
    ("L'écriture décimale 0,5 correspond à quelle fraction simplifiée ?", ["5/10", "1/2", "1/5"], 0, FAUX),
])
def test_forme_irreductible_d_un_decimal(enonce, propositions, index_correct, attendu):
    assert statut(enonce, propositions, index_correct) == attendu


def test_forme_irreductible_d_un_decimal_message():
    assert message("Écris 0,75 sous forme de fraction irréductible.", ["75/100", "3/4", "7/5"], 0) == (
        "question 1 : la forme irréductible de 0,75 est 3/4, mais la réponse annoncée est « 75/100 » "
        "au lieu de « 3/4 »")


# --- parts d'un tout ------------------------------------------------------------------------------

@pytest.mark.parametrize("enonce, propositions, index_correct, attendu", [
    ("Une pizza est coupée en 8 parts. Tu en manges 3. Quelle fraction de la pizza as-tu mangée ?",
     ["3/8", "5/8", "8/3"], 0, VERIFIE),
    ("Une pizza est coupée en 8 parts. Tu en manges 3. Quelle fraction de la pizza as-tu mangée ?",
     ["3/8", "5/8", "8/3"], 1, FAUX),
    ("Une figure est partagée en 6 parties égales, dont 2 sont hachurées. Quelle fraction de la figure est "
     "hachurée ?", ["2/6", "4/6", "2/4"], 0, VERIFIE),
    ("Une figure est partagée en 6 parties égales, dont 2 sont hachurées. Quelle fraction de la figure est "
     "hachurée ?", ["2/6", "1/3", "2/4"], 0, FAUX),                                    # 2/6 et 1/3
])
def test_parts_d_un_tout(enonce, propositions, index_correct, attendu):
    assert statut(enonce, propositions, index_correct) == attendu


def test_parts_d_un_tout_message():
    assert message("Si tu as 10 parts et que tu en manges 3, quelle fraction as-tu mangée ?",
                   ["7/10", "3/10", "3/7"], 0) == (
        "question 1 : 3 parts sur 10 représentent 3/10, mais la réponse annoncée est « 7/10 » au lieu de « 3/10 »")


@pytest.mark.parametrize("enonce, propositions, index_correct", [
    # la partie restante ou non coloriée : la réponse est 5/8, pas 3/8
    ("Une pizza est coupée en 8 parts et tu en manges 3. Quelle fraction de la pizza reste-t-il ?",
     ["5/8", "3/8", "8/5"], 0),
    ("Une figure divisée en 8 parties égales, dont 3 sont coloriées. Quelle fraction n'est pas coloriée ?",
     ["5/8", "3/8", "8/5"], 0),
    ("Une figure divisée en 8 parties égales, dont 3 sont coloriées. Quelle fraction est non coloriée ?",
     ["5/8", "3/8", "8/5"], 0),
    ("Une figure divisée en 8 parties égales, dont 3 sont coloriées. Quelle fraction de la figure est blanche ?",
     ["5/8", "3/8", "8/5"], 0),
    # la question porte sur une autre action que celle qui désigne les parts
    ("Un gâteau est coupé en 8 parts, dont 3 sont mangées par Léo. Quelle fraction Léa a-t-elle prise ?",
     ["2/8", "3/8", "5/8"], 0),
    # deux groupes de parts : trois nombres cités
    ("Un gâteau est coupé en 8 parts. Tu en manges 3 et ton frère 2. Quelle fraction as-tu mangée ?",
     ["3/8", "5/8", "2/8"], 0),
    # la partie est elle-même une fraction
    ("Si tu as une tarte entière et que tu en manges 2/3, quelle fraction de tarte te reste-t-il ?",
     ["1/3", "2/3", "3/2"], 0),
    # le tout est transformé
    ("Un gâteau est coupé en 8 parts, puis chaque part est coupée en deux. Tu en manges 3. Quelle fraction "
     "as-tu mangée ?", ["3/16", "3/8", "6/16"], 0),
])
def test_parts_d_un_tout_prudence(enonce, propositions, index_correct):
    assert statut(enonce, propositions, index_correct) == A_RELIRE


def test_egalite_avec_la_fraction():
    assert statut("Quelle est la fraction équivalente à 2/3 ?", ["4/5", "6/9", "2/6"], 1) == VERIFIE
    assert statut("Quelle est une fraction égale à 3/4 ?", ["6/8", "3/8", "4/3"], 1) == FAUX


def test_resultat_de_l_addition_de_deux_fractions():
    assert statut("Quel est le résultat de l'addition de deux fractions : 1/4 + 1/2 ?",
                  ["3/4", "2/6", "1/8"], 0) == VERIFIE


# --- même opération sur les deux termes d'une fraction --------------------------------------------

@pytest.mark.parametrize("enonce, propositions, index_correct, attendu", [
    ("Quelle est la fraction équivalente à 2/5 si on multiplie le numérateur et le dénominateur par 3 ?",
     ["6/15", "2/8", "5/15", "6/8"], 0, VERIFIE),
    ("Quelle est la fraction équivalente à 2/5 si on multiplie le numérateur et le dénominateur par 3 ?",
     ["6/15", "2/8", "5/15", "6/8"], 3, FAUX),
    # 12/30 vaut aussi 2/5, mais ce n'est pas le résultat de la multiplication par 3
    ("Quelle est la fraction équivalente à 2/5 si on multiplie le numérateur et le dénominateur par 3 ?",
     ["12/30", "6/15", "5/15"], 1, VERIFIE),
    ("Quelle fraction obtiens-tu en multipliant ses deux termes par 4 ? La fraction de départ est 3/7.",
     ["12/28", "7/11", "12/7"], 0, VERIFIE),
    ("Quelle fraction obtient-on si l'on divise le numérateur et le dénominateur de 6/15 par 3 ?",
     ["2/5", "3/12", "2/15"], 0, VERIFIE),
    ("Simplifie 6/15 en divisant le numérateur et le dénominateur par 3.", ["2/5", "3/12", "2/15"], 0, VERIFIE),
    ("Simplifie 6/15 en divisant le numérateur et le dénominateur par 3.", ["2/5", "3/12", "2/15"], 2, FAUX),
])
def test_memes_termes(enonce, propositions, index_correct, attendu):
    assert statut(enonce, propositions, index_correct) == attendu


def test_memes_termes_message():
    assert message("Quelle est la fraction équivalente à 2/5 si on multiplie le numérateur et le dénominateur "
                   "par 3 ?", ["6/8", "6/15", "2/8"], 0) == (
        "question 1 : en multipliant les deux termes de 2/5 par 3, on obtient 6/15, mais la réponse annoncée "
        "est « 6/8 » au lieu de « 6/15 »")


@pytest.mark.parametrize("enonce, propositions, index_correct", [
    # la question porte sur un seul terme : la bonne réponse est un nombre, pas une fraction
    ("Si on multiplie le numérateur et le dénominateur de 2/5 par 3, quel numérateur obtient-on ?",
     ["6", "15", "5"], 0),
    # une seconde transformation après la première
    ("Quelle fraction obtient-on si on multiplie le numérateur et le dénominateur de 2/5 par 3, puis "
     "qu'on ajoute 1 ?", ["21/15", "6/15", "7/16"], 0),
    # 7 n'est pas divisible par 2
    ("Quelle fraction obtient-on si on divise le numérateur et le dénominateur de 7/10 par 2 ?",
     ["3,5/5", "7/5", "14/20"], 0),
    # oui / non : rien à comparer
    ("Si on multiplie le numérateur et le dénominateur de 2/5 par 3, la fraction change-t-elle de valeur ?",
     ["Non, elle reste égale", "Oui, elle triple"], 0),
])
def test_memes_termes_prudence(enonce, propositions, index_correct):
    assert statut(enonce, propositions, index_correct) == A_RELIRE


# --- plus petit dénominateur commun ---------------------------------------------------------------

@pytest.mark.parametrize("enonce, propositions, index_correct, attendu", [
    ("Pour additionner 1/3 et 1/6, quel est le dénominateur commun le plus petit ?", ["3", "6", "18", "2"], 1, VERIFIE),
    ("Pour additionner 1/3 et 1/6, quel est le dénominateur commun le plus petit ?", ["3", "6", "18", "2"], 2, FAUX),
    ("Quel est le plus petit dénominateur commun de 3/4 et 5/6 ?", ["24", "12", "10"], 1, VERIFIE),
    ("Pour comparer 1/2, 2/3 et 3/4, quel est le plus petit dénominateur commun ?", ["12", "24", "9"], 0, VERIFIE),
    ("Pour soustraire 1/4 de 5/6, quel est le plus petit dénominateur commun ?", ["24", "12", "10"], 0, FAUX),
])
def test_plus_petit_denominateur(enonce, propositions, index_correct, attendu):
    assert statut(enonce, propositions, index_correct) == attendu


def test_plus_petit_denominateur_message():
    assert message("Quel est le plus petit dénominateur commun de 3/4 et 5/6 ?", ["24", "12", "10"], 0) == (
        "question 1 : le plus petit dénominateur commun de 3/4 et 5/6 est 12, mais la réponse annoncée est "
        "« 24 » au lieu de « 12 »")


@pytest.mark.parametrize("enonce, propositions, index_correct", [
    # « un » dénominateur commun : 6, 12 et 18 conviennent tous
    ("Pour additionner 1/3 et 1/6, quel dénominateur commun peut-on utiliser ?", ["6", "12", "18"], 1),
    # 2/4 n'est pas irréductible : 4 ou 2 selon qu'on simplifie d'abord
    ("Quel est le plus petit dénominateur commun de 2/4 et 1/3 ?", ["12", "6", "7"], 0),
    # la réponse attendue est une fraction réécrite, pas le dénominateur
    ("Quel est le plus petit dénominateur commun de 1/3 et 1/6 ? Écris 1/3 avec ce dénominateur.",
     ["2/6", "1/6", "3/6"], 0),
    # le double de 1/3 n'est pas 1/3
    ("Pour additionner le double de 1/3 et 1/6, quel est le dénominateur commun le plus petit ?",
     ["6", "3", "18"], 0),
])
def test_plus_petit_denominateur_prudence(enonce, propositions, index_correct):
    assert statut(enonce, propositions, index_correct) == A_RELIRE


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


# --- cas réels du 07/10 (gemma4) : calcul mental, pourcentages, Pythagore ------------------------
# 15 questions de 3 exercices acceptés ; 4 réponses annoncées étaient fausses, toutes laissées « à relire » ce jour-là

REELS_0710 = [
    ("Calcule mentalement : 12 + 15.", ["25", "37", "18", "27"], 0, FAUX),                  # 27
    ("Quel est le résultat de 40 - 13 ?", ["27", "33", "53", "23"], 0, VERIFIE),
    ("Calcule mentalement : 7 x 6.", ["36", "42", "48", "13"], 1, VERIFIE),
    ("Combien font 100 divisé par 5 ?", ["20", "50", "10", "1000"], 0, VERIFIE),
    ("Calcule mentalement : 25 + 50.", ["65", "75", "125", "55"], 1, VERIFIE),
    ("Qu'est-ce que le pourcentage ?", ["Un nombre divisé par 100", "Un nombre exprimé en unités",
                                        "Une fraction simplifiée", "Une mesure de longueur"], 0, A_RELIRE),
    ("Quel est le pourcentage correspondant à la fraction 25/100 ?", ["25 %", "125 %", "0,25 %", "2,5 %"], 0, VERIFIE),
    ("Calcule 20 % de 150.", ["20", "30", "15", "25"], 1, VERIFIE),
    # 35 € : absente des propositions ; vue grâce à nouveau_prix (07/10, étape 1.7)
    ("Si un article coûte 50 € et qu'il est soldé à 30 %, quel est son nouveau prix ?",
     ["30 €", "15 €", "20 €", "40 €"], 2, FAUX),
    ("Un élève a obtenu 18 bonnes réponses sur 25. Quel est son pourcentage de réussite ?",
     ["72 %", "18 %", "75 %", "80 %"], 3, FAUX),                                              # 72 %
    ("Dans un triangle ABC rectangle en B, quels sont les côtés de l'angle droit ?",
     ["AB et BC", "AC et AB", "BC et AC"], 0, A_RELIRE),
    ("Un triangle rectangle possède des côtés de 5 cm et 12 cm. Quelle est la longueur de l'hypoténuse ?",
     ["13 cm", "17 cm", "17 cm²", "7 cm"], 0, VERIFIE),
    ("Un triangle a pour côtés 7 cm, 8 cm et 11 cm. Est-ce un triangle rectangle ?",
     ["Oui, car 7² + 8² = 11²", "Non, car 7² + 11² = 8²", "Non, car 8² + 11² = 7²"], 0, FAUX),  # 113 ≠ 121
    ("Si l'hypoténuse d'un triangle rectangle mesure 10 cm et un côté de l'angle droit mesure 6 cm, quelle est "
     "la longueur du deuxième côté ?", ["8 cm", "16 cm", "100 cm", "4 cm"], 0, VERIFIE),
    ("Un carré de côté 4 cm est divisé en deux par une diagonale. Quel est la longueur de cette diagonale ?",
     ["4 cm", "8 cm", "4√2 cm", "16 cm"], 2, A_RELIRE),                                       # racine non lue
]


@pytest.mark.parametrize("enonce, propositions, index_correct, attendu", REELS_0710)
def test_cas_reels_du_0710(enonce, propositions, index_correct, attendu):
    assert statut(enonce, propositions, index_correct) == attendu


def test_cas_reels_du_0710_messages():
    assert message(*REELS_0710[0][:3]) == "question 1 : 12 + 15 = 27, mais la réponse annoncée est « 25 » au lieu de « 27 »"
    assert message(*REELS_0710[9][:3]) == ("question 1 : 18 sur 25 représentent 72 %, mais la réponse annoncée est "
                                           "« 80 % » au lieu de « 72 % »")
    assert message(*REELS_0710[12][:3]) == ("question 1 : 7² + 8² = 113 ≠ 11² = 121, donc le triangle n'est pas "
                                            "rectangle, mais la réponse annoncée est « Oui, car 7² + 8² = 11² »")


@pytest.mark.parametrize("enonce, propositions, index_correct, attendu", [
    ("Calcule 20 % de 150 €.", ["30 €", "20 €", "15 €"], 0, VERIFIE),
    ("Calcule 20 % de 150 €.", ["20 €", "30 €", "15 €"], 0, FAUX),
    ("Quel est 10 % de 50 ?", ["5", "10", "0,5"], 0, VERIFIE),
    ("Calcule 20 % de 150.", ["30 %", "20", "15"], 0, A_RELIRE),             # « 30 % » : maladresse, pas un calcul
    ("Calcule 20 % de 150 puis ajoute 5.", ["35", "30"], 0, A_RELIRE),       # le calcul continue
])
def test_pourcentage_d_un_nombre(enonce, propositions, index_correct, attendu):
    assert statut(enonce, propositions, index_correct) == attendu


@pytest.mark.parametrize("enonce, propositions, index_correct, attendu", [
    ("Écris 3/4 en pourcentage.", ["75 %", "34 %", "0,75 %"], 0, VERIFIE),
    ("Écris 0,5 sous forme de pourcentage.", ["5 %", "50 %", "0,5 %"], 0, FAUX),
    ("Écris 3/4 en pourcentage.", ["0,75", "75 %", "34 %"], 0, A_RELIRE),   # 0,75 n'est pas écrit en pourcentage
    # la question inversée : le pourcentage d'erreurs, ou les mauvaises réponses comptées
    ("Un élève a obtenu 18 bonnes réponses sur 25. Quel est son pourcentage d'erreurs ?", ["28 %", "72 %"], 0, A_RELIRE),
    ("Un élève a 7 mauvaises réponses sur 25. Quel est son pourcentage de réussite ?", ["72 %", "28 %"], 0, A_RELIRE),
    ("Sur 25 questions, Léa en a réussi 18. Quel est son pourcentage de réussite ?", ["72 %", "80 %"], 0, A_RELIRE),
])
def test_ecriture_en_pourcentage(enonce, propositions, index_correct, attendu):
    assert statut(enonce, propositions, index_correct) == attendu


COTE = ("Dans un triangle rectangle, l'hypoténuse mesure 13 cm et un côté mesure 5 cm. "
        "Quelle est la longueur de l'autre côté ?")


@pytest.mark.parametrize("enonce, propositions, index_correct, attendu", [
    (COTE, ["12 cm", "8 cm", "18 cm"], 0, VERIFIE),
    (COTE, ["8 cm", "12 cm", "18 cm"], 0, FAUX),
    (COTE.replace("13", "10").replace("5 cm", "4 cm"), ["9,2 cm", "6 cm"], 0, A_RELIRE),  # √84 : arrondi
    # l'hypoténuse est donnée : la demander n'a pas de sens, N4 ne s'y risque pas
    ("Un triangle rectangle a une hypoténuse de 5 cm et un côté de 3 cm. Quelle est la mesure de l'hypoténuse ?",
     ["5 cm", "4 cm"], 0, A_RELIRE),
    ("Un triangle a pour côtés 6 cm, 8 cm et 10 cm. Est-ce un triangle rectangle ?",
     ["Non, car 6² + 8² ≠ 10²", "Oui, car 6² + 8² = 10²"], 0, FAUX),
])
def test_pythagore_cote_manquant_et_reciproque(enonce, propositions, index_correct, attendu):
    assert statut(enonce, propositions, index_correct) == attendu


@pytest.mark.parametrize("enonce, propositions, index_correct, attendu", [
    ("Combien font 7 fois 8 ?", ["54", "56", "15"], 0, FAUX),
    ("Combien font 3 plus 4 ?", ["7", "12"], 0, VERIFIE),
    ("Calcule de tête : 9 × 7.", ["63", "56"], 0, VERIFIE),
    ("Calcule le double de 3 plus 4.", ["14", "10"], 0, A_RELIRE),          # transformation : non lu
    ("Combien de fois 3 est-il contenu dans 12 ?", ["4", "3"], 0, A_RELIRE),
])
def test_operations_en_toutes_lettres(enonce, propositions, index_correct, attendu):
    assert statut(enonce, propositions, index_correct) == attendu


PRIX = "Un article coûte 50 €. Il est soldé à 30 %. Quel est son nouveau prix ?"


@pytest.mark.parametrize("enonce, propositions, index_correct, attendu", [
    (PRIX, ["35 €", "15 €", "20 €"], 0, VERIFIE),
    (PRIX, ["15 €", "35 €", "20 €"], 0, FAUX),                               # le montant de la remise
    ("Le prix d'un article de 180 € augmente de 25 %. Quel est son nouveau prix ?", ["45 €", "225 €", "205 €"], 1,
     VERIFIE),
    ("Le prix d'un article de 180 € augmente de 25 %. Quel est son nouveau prix ?", ["45 €", "225 €", "205 €"], 2,
     FAUX),
    # deux articles, ou deux remises successives : le calcul n'est plus celui qu'on lit
    ("Deux articles coûtent 50 €. Ils sont soldés à 30 %. Quel est leur nouveau prix ?", ["35 €", "15 €"], 0, A_RELIRE),
    ("Un article coûte 50 €. Il est soldé à 30 %, puis encore à 10 %. Quel est son nouveau prix ?", ["31,5 €", "35 €"],
     0, A_RELIRE),
    (PRIX, ["35 %", "15 €", "20 €"], 0, A_RELIRE),                           # « 35 % » : pas un prix
])
def test_nouveau_prix(enonce, propositions, index_correct, attendu):
    assert statut(enonce, propositions, index_correct) == attendu
