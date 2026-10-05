"""N3 — chaque règle est testée sur un cas fabriqué, et sur le vrai QCM des fractions du 25/09/2026."""

import copy
import json
from pathlib import Path

import pytest

from generateur.moteur import registre
from generateur.moteur.validation import ErreurValidation
from generateur.moteur.validation.n3_pedagogie import forme_irreductible, valeur, valider, verifier

DONNEES = Path(__file__).parent / "donnees"


def qcm(*questions: dict) -> dict:
    return {"type": "qcm", "titre": "Test", "matiere": "maths", "niveau": "6e", "notion": "test",
            "questions": list(questions)}


def question(propositions: list[str], index_correct: int = 0, enonce: str = "Combien font deux plus deux ?",
             explication: str = "On ajoute deux unités à deux unités, ce qui donne quatre.") -> dict:
    return {"enonce": enonce, "propositions": propositions, "index_correct": index_correct,
            "explication": explication}


def bloquants(instance: dict) -> list[str]:
    return [c.message for c in verifier(instance) if c.bloquant]


def avertissements(instance: dict) -> list[str]:
    return [c.message for c in verifier(instance) if not c.bloquant]


# --- le cas réel qui a motivé N3 ------------------------------------------------------------------

def test_le_qcm_des_fractions_est_rejete_sur_les_questions_fautives():
    instance = json.loads((DONNEES / "qcm-fractions-6e-reel.json").read_text(encoding="utf-8"))
    with pytest.raises(ErreurValidation) as e:
        valider(instance)
    assert e.value.niveau == "N3"
    # Q1 : 3/4 et 6/8 ; Q3 : quatre écritures de 1/2 ; Q4 : 1/2 et 3/6.
    # Q5 (2/5 annoncé plus grand que 3/7) est une erreur de calcul : elle relève de N4, pas de N3.
    assert e.value.questions == (1, 3, 4)
    assert any("« 3/4 » et « 6/8 »" in m for m in e.value.erreurs)
    assert any("« 2/4 », « 1/2 », « 3/6 » et « 5/10 »" in m for m in e.value.erreurs)


def test_l_exemple_de_reference_passe_sans_aucun_constat():
    assert verifier(registre.charger("qcm").exemple) == []


# --- valeurs numériques ---------------------------------------------------------------------------

@pytest.mark.parametrize("a, b", [
    ("3/4", "6/8"), ("3/4", "0,75"), ("0.75", "75 %"), ("1/2", "0,5"),
    ("1 m", "100 cm"), ("2,5 km", "2500 m"), ("1 kg", "1000 g"), ("1 L", "100 cL"),
    ("1 m²", "10000 cm²"), ("2 h", "120 min"), ("1 000", "1000"), ("−3", "-3"), ("90°", "90 °"),
])
def test_ecritures_equivalentes(a, b):
    assert valeur(a) is not None and valeur(a) == valeur(b)


@pytest.mark.parametrize("a, b", [
    ("3/4", "4/3"), ("1 m", "1 cm"), ("1 m", "1 m²"), ("1 m", "1 kg"), ("75 %", "75"), ("5 élèves", "5 pommes"),
])
def test_ecritures_differentes(a, b):
    assert valeur(a) != valeur(b)


@pytest.mark.parametrize("texte", ["Oui, car 6² + 8² = 10²", "BC² = AB² + AC²", "Paris", "3 × 4", "1/0"])
def test_ce_qui_n_est_pas_un_nombre_seul_n_est_pas_converti(texte):
    assert valeur(texte) is None


# --- règles bloquantes ----------------------------------------------------------------------------

def test_propositions_equivalentes():
    assert bloquants(qcm(question(["1 m", "10 cm", "100 cm"]))) == [
        "question 1 : les propositions « 1 m » et « 100 cm » ont la même valeur ; "
        "une seule proposition peut être juste, les autres doivent être fausses"]


def test_mauvaises_reponses_egales_entre_elles_avertissement_seulement():
    # 1/2 + 1/4 = 3/4 : « 2/4 » et « 1/2 » sont égales, mais ce sont deux MAUVAISES réponses
    q = question(["3/4", "2/4", "1/2"], index_correct=0, enonce="Quel est le résultat de 1/2 + 1/4 ?")
    assert bloquants(qcm(q)) == []
    assert any("mauvaises réponses « 2/4 » et « 1/2 »" in m for m in avertissements(qcm(q)))


def test_qcm_reel_du_3_octobre_n_est_plus_rejete():
    # généré avec le nouveau prompt : 5 questions justes, rejeté à tort par l'ancienne règle de N3
    instance = json.loads((DONNEES / "qcm-fractions-6e-20261003-rejete-a-tort.json").read_text(encoding="utf-8"))
    avertissements_n3 = valider(instance)
    assert [m.split(" :")[0] for m in avertissements_n3 if "mauvaises réponses" in m] == ["question 3", "question 4"]


@pytest.mark.parametrize("propositions, index_correct", [
    (["La partie coloriée", "3 parts sur 4 parts", "4 parts sur 3 parts", "3 parts sur 4 parts coloriées"], 1),
    (["1/3", "2/5", "1/3 est plus grande", "2/5 est plus grande"], 1),
])
def test_bonne_reponse_contenue_dans_une_autre_proposition(propositions, index_correct):
    # cas réels du 03/10 : les deux formulations sont justes
    q = question(propositions, index_correct=index_correct, enonce="Quelle est la bonne réponse ?")
    assert bloquants(qcm(q)) == []
    assert any("se recoupent" in m for m in avertissements(qcm(q)))


def test_nombres_qui_se_ressemblent_ne_se_recoupent_pas():
    # « 8 » n'est pas contenu dans « 18 », ni « 1/2 » dans « 11/2 »
    assert not any("se recoupent" in m for m in avertissements(qcm(question(["8", "18", "28"]))))
    assert not any("se recoupent" in m for m in avertissements(qcm(question(["1/2", "11/2", "3/2"]))))


def test_forme_irreductible_demandee_les_fractions_egales_sont_les_distracteurs():
    # seule 1/2 est irréductible : 2/4 a la même valeur mais c'est une mauvaise réponse, pas une ambiguïté
    q = question(["2/4", "1/2", "4/2"], index_correct=1, enonce="Quelle est la forme irréductible de 4/8 ?",
                 explication="On divise 4 et 8 par leur plus grand diviseur commun, 4 : on obtient 1/2.")
    assert bloquants(qcm(q)) == []


def test_simplifiee_sans_irreductible_reste_ambigu():
    # « simplifiée » : 2/4 et 1/2 sont toutes deux des simplifications de 4/8 (question 3 du 25/09)
    q = question(["2/4", "1/2", "3/5"], index_correct=1, enonce="Quelle fraction est simplifiée dans l'écriture 4/8 ?")
    assert any("même valeur" in m for m in bloquants(qcm(q)))


def test_simplifier_la_fraction_de_depart_recopiee_est_un_distracteur():
    # cas réel du 05/10 (gemma4) : « 6/12 » recopie la fraction de départ, ce n'est pas une simplification
    q = question(["2/6", "3/4", "1/2", "6/12"], index_correct=2, enonce="Simplifier la fraction 6/12 donne :",
                 explication="On divise 6 et 12 par 6 : on obtient 1/2.")
    assert bloquants(qcm(q)) == []


def test_simplifier_une_autre_simplification_reste_une_seconde_bonne_reponse():
    # 2/4 est 6/12 divisé par 3 : c'est aussi une simplification juste
    q = question(["2/4", "3/4", "1/2", "6/12"], index_correct=2, enonce="Simplifier la fraction 6/12 donne :",
                 explication="On divise 6 et 12 par 6 : on obtient 1/2.")
    assert bloquants(qcm(q)) == ["question 1 : les propositions « 2/4 » et « 1/2 » ont la même valeur ; une seule "
                                 "proposition peut être juste, les autres doivent être fausses"]


def test_simplifier_la_fraction_de_depart_en_double_reste_un_doublon():
    q = question(["6/12", "3/4", "1/2", "6 / 12"], index_correct=2, enonce="Simplifie 6/12.",
                 explication="On divise 6 et 12 par 6 : on obtient 1/2.")
    assert bloquants(qcm(q)) == ["question 1 : la proposition « 6/12 » apparaît 2 fois"]


def test_sans_simplifier_la_fraction_de_depart_reste_une_bonne_reponse():
    # « équivalente à 6/12 » : 6/12 est bel et bien égale à elle-même
    q = question(["6/12", "3/4", "1/2"], index_correct=2, enonce="Quelle fraction est équivalente à 6/12 ?",
                 explication="On divise 6 et 12 par 6 : on obtient 1/2.")
    assert any("même valeur" in m for m in bloquants(qcm(q)))


@pytest.mark.parametrize("enonce", [
    "Quelle fraction représente la partie hachurée de la figure ci-jointe ?",   # cas réel du 05/10 (gemma4)
    "Quelle fraction est représentée sur le schéma suivant ?",
    "Observe la figure : quelle fraction est coloriée ?",
    "Quel nombre est placé sur la droite graduée ci-dessous ?",
    "Regardez le dessin ci-contre. Quelle part a été mangée ?",
])
def test_figure_absente(enonce):
    q = question(["1/3", "1/2", "2/3"], index_correct=1, enonce=enonce,
                 explication="Deux parts sur quatre sont coloriées, soit la moitié.")
    messages = bloquants(qcm(q))
    assert len(messages) == 1 and "aucune image" in messages[0]


@pytest.mark.parametrize("enonce", [
    # la figure est décrite en mots (cas réel du 05/10, accepté)
    "Quelle fraction représente la partie coloriée d'une figure divisée en 8 parties égales, dont 3 sont coloriées ?",
    "Laquelle des fractions ci-dessous est égale à 1/2 ?",                       # renvoie aux propositions
    "Parmi les nombres suivants, lequel est le plus grand ?",
    "Un carré est partagé en 4 parts égales et 1 part est coloriée. Quelle fraction de la figure est coloriée ?",
])
def test_figure_decrite_ou_renvoi_aux_propositions(enonce):
    q = question(["1/3", "1/2", "3/8"], index_correct=1, enonce=enonce,
                 explication="On compte les parts coloriées et le nombre total de parts.")
    assert not any("aucune image" in m for m in bloquants(qcm(q)))


@pytest.mark.parametrize("texte, attendu", [
    ("1/2", True), ("3", True), ("5 / 7", True), ("2/4", False), ("0,5", False), ("6/3", False), ("4/1", False),
])
def test_forme_irreductible(texte, attendu):
    assert forme_irreductible(texte) is attendu


def test_doublon_textuel_insensible_a_la_casse_et_a_la_ponctuation():
    assert bloquants(qcm(question(["Paris", "Lyon", "paris."]))) == [
        "question 1 : la proposition « Paris » apparaît 2 fois"]


def test_proposition_vide():
    assert "question 1 : proposition(s) 3 vide(s)" in bloquants(qcm(question(["4", "5", "  "])))


@pytest.mark.parametrize("formule", ["Toutes les réponses ci-dessus", "Aucune de ces réponses"])
def test_formules_qui_renvoient_aux_autres_propositions(formule):
    assert any("renvoie aux autres propositions" in m for m in bloquants(qcm(question(["4", "5", formule]))))


def test_explication_qui_recopie_l_enonce():
    q = question(["4", "5", "6"], explication="Combien font deux plus deux ?")
    assert any("recopie l'énoncé" in m for m in bloquants(qcm(q)))


def test_explication_qui_repete_la_reponse():
    q = question(["Le Nil est le plus long", "L'Amazone", "Le Rhin"],
                 enonce="Quel fleuve est le plus long d'Afrique ?", explication="Le Nil est le plus long.")
    assert any("répéter la bonne réponse" in m for m in bloquants(qcm(q)))


def test_enonces_dupliques():
    q = question(["4", "5", "6"])
    assert bloquants(qcm(q, copy.deepcopy(q))) == ["question 2 : même énoncé que la question 1"]


@pytest.mark.parametrize("texte, nature", [
    ("Écris à lea.martin@exemple.fr", "une adresse électronique"),
    ("Appelle le 06 12 34 56 78", "un numéro de téléphone"),
    ("Voir https://exemple.fr", "un lien web"),
])
def test_donnees_personnelles_et_liens(texte, nature):
    q = question(["4", "5", "6"], enonce=f"{texte}. Combien font deux plus deux ?")
    assert f"question 1 : contient {nature}, interdit dans un exercice" in bloquants(qcm(q))


def test_un_nombre_decimal_n_est_pas_pris_pour_un_telephone():
    assert bloquants(qcm(question(["0,12", "0,5", "0,75"]))) == []


# --- avertissements -------------------------------------------------------------------------------

def test_bonne_reponse_toujours_a_la_meme_position():
    instance = qcm(*(question(["4", "5", "6"], enonce=f"Question numéro {i} ?") for i in range(3)))
    assert bloquants(instance) == []
    assert any("toujours en position 1" in m for m in avertissements(instance))


def test_bonne_reponse_toujours_la_plus_longue():
    instance = qcm(*(question(["une réponse plutôt longue", "courte", "brève"], enonce=f"Question {i} ?",
                              index_correct=0) for i in range(3)))
    assert any("toujours la proposition la plus longue" in m for m in avertissements(instance))


def test_bonne_reponse_nettement_plus_longue():
    q = question(["Parce que la Terre tourne autour du Soleil en un an environ", "La Lune", "Mars"])
    assert any("nettement plus longue" in m for m in avertissements(qcm(q)))


def test_enonce_flou():
    q = question(["4", "5", "6"], enonce="Combien font généralement deux plus deux ?")
    assert any("« généralement »" in m for m in avertissements(qcm(q)))


def test_les_avertissements_ne_bloquent_pas():
    q = question(["4", "5", "6"], enonce="Combien font généralement deux plus deux ?")
    assert valider(qcm(q)) == avertissements(qcm(q))
