"""Génération de bout en bout, sans modèle : le meta d'un exercice accepté, et la conservation des rejets.

Ces tests portent sur la chaîne avec le modèle : `mode="ia"`, sinon « fractions » passerait par le générateur
procédural (étape 1.7)."""

import copy
import json
from pathlib import Path

import pytest

from generateur.moteur import config, generation
from generateur.moteur.fournisseurs.base import Fournisseur
from generateur.moteur.validation import ErreurValidation
from generateur.moteur.validation.n4_calcul import A_RELIRE, VERIFIE

DONNEES = Path(__file__).parent / "donnees"


class Rejoue(Fournisseur):
    """Fournisseur de test : renvoie une réponse fixée à l'avance."""
    nom = "rejoue"
    modele = "réponse enregistrée"

    def __init__(self, reponse: str):
        self.reponse = reponse

    def generer(self, messages: list[dict], schema: dict) -> str:
        return self.reponse


@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    """Sortie, banque et rejets dans un dossier temporaire ; les types restent ceux du dépôt."""
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    return tmp_path


def rejouer(monkeypatch, reponse: str) -> None:
    monkeypatch.setattr(generation, "creer", lambda nom, reglages: Rejoue(reponse))


def test_exercice_accepte_meta_complet(dossiers):
    instance = generation.generer({"type": "qcm", "notion": "test"}, "qcm", "maquette")
    validation = instance["meta"]["validation"]
    assert validation["n1"] and validation["n2"] and validation["n3"]
    assert validation["n4"] == A_RELIRE and validation["n4_questions"] == [A_RELIRE, VERIFIE, VERIFIE]
    assert instance["meta"]["avertissements"] == []
    assert not (dossiers / "rejets").exists()  # rien n'est rejeté


def test_un_rejet_est_conserve_avec_son_instance(dossiers, monkeypatch):
    fautif = json.loads((DONNEES / "qcm-fractions-6e-reel.json").read_text(encoding="utf-8"))
    del fautif["meta"]
    brut = json.dumps(fautif, ensure_ascii=False)
    rejouer(monkeypatch, brut)

    with pytest.raises(ErreurValidation) as e:
        generation.generer({"type": "qcm", "demande_enseignant": "fractions 6e"}, "qcm", "rejoue", mode="ia")

    fichiers = list((dossiers / "rejets").glob("*.json"))
    assert len(fichiers) == 1 and e.value.rejet == fichiers[0]
    rejet = json.loads(fichiers[0].read_text(encoding="utf-8"))
    # N3 : Q1, Q3, Q4 (deux bonnes réponses) ; N4 : Q5 (2/5 annoncé plus grand que 3/7)
    assert rejet["niveau"] == "N3, N4" and rejet["questions"] == [1, 3, 4, 5]
    assert rejet["instance"]["matiere"] == "maths"  # N4 pourra être recalculée dessus
    assert rejet["brut"] == brut and rejet["modele"] == "réponse enregistrée"
    assert (dossiers / "sortie" / "derniere_reponse_brute.txt").read_text(encoding="utf-8") == brut


def test_n3_et_n4_signalent_tous_les_defauts_d_un_coup(dossiers, monkeypatch):
    # second QCM du 03/10 : N3 rejetait Q1, Q2, Q4 et l'erreur de calcul de Q3 restait cachée
    fautif = json.loads((DONNEES / "qcm-fractions-6e-20261003-rejete-a-raison.json").read_text(encoding="utf-8"))
    rejouer(monkeypatch, json.dumps(fautif, ensure_ascii=False))

    with pytest.raises(ErreurValidation) as e:
        generation.generer({"type": "qcm", "notion": "fractions"}, "qcm", "rejoue", mode="ia")

    assert e.value.niveau == "N3, N4"
    assert e.value.questions == (1, 2, 3, 4, 5)
    numeros = [int(m.split(" ")[1]) for m in e.value.erreurs]
    assert numeros == [1, 2, 3, 4, 5]  # un message par question, dans l'ordre : pas de doublon N3/N4
    assert "la plus grande valeur est 3/7" in e.value.erreurs[2]
    rejet = json.loads(next((dossiers / "rejets").glob("*.json")).read_text(encoding="utf-8"))
    assert rejet["niveau"] == "N3, N4" and rejet["instance"] is not None


def test_un_rejet_n1_est_conserve_sans_instance(dossiers, monkeypatch):
    rejouer(monkeypatch, "Voici votre exercice ! (mais pas de JSON)")
    with pytest.raises(ErreurValidation):
        generation.generer({"type": "qcm", "notion": "test"}, "qcm", "rejoue", mode="ia")
    rejet = json.loads(next((dossiers / "rejets").glob("*.json")).read_text(encoding="utf-8"))
    assert rejet["niveau"] == "N1" and rejet["instance"] is None


def test_deux_rejets_rapproches_ne_s_ecrasent_pas(dossiers, monkeypatch):
    rejouer(monkeypatch, "pas de JSON")
    for _ in range(2):
        with pytest.raises(ErreurValidation):
            generation.generer({"type": "qcm", "notion": "test"}, "qcm", "rejoue", mode="ia")
    assert len(list((dossiers / "rejets").glob("*.json"))) == 2


def test_resume_n4():
    instance = {"matiere": "maths", "meta": {"validation": {"n4_questions": [VERIFIE, A_RELIRE, VERIFIE]}}}
    assert generation.resume_n4(instance) == "N4 : 2 question(s) recalculée(s) et juste(s), 1 à relire (question 2)"
    instance["matiere"] = "histoire-geo"
    assert "hors maths" in generation.resume_n4(instance)


# --- reprise sur erreur (étape 1.4) --------------------------------------------------------------

class Suite(Fournisseur):
    """Fournisseur de test : renvoie une réponse différente à chaque appel, et garde ce qu'on lui a envoyé."""
    nom = "suite"
    modele = "réponses enregistrées"

    def __init__(self, reponses: list):
        self.reponses = list(reponses)
        self.appels: list[tuple[list[dict], dict]] = []

    def generer(self, messages: list[dict], schema: dict) -> str:
        self.appels.append((messages, schema))
        reponse = self.reponses.pop(0)
        return reponse if isinstance(reponse, str) else json.dumps(reponse, ensure_ascii=False)


def q(enonce: str, propositions: list[str], index_correct: int = 0) -> dict:
    return {"enonce": enonce, "propositions": propositions, "index_correct": index_correct,
            "explication": f"Explication de la question « {enonce[:30]} », pour les tests."}


# premier QCM de Gemma du 05/10 : accepté, N4 vérifie les 5 questions
JUSTES = [
    q("Quelle fraction représente la partie coloriée d'une figure divisée en 8 parties égales, dont 3 sont "
      "coloriées ?", ["3/8", "8/3", "3/5", "5/8"]),
    q("Le nombre 0,5 peut s'écrire sous quelle forme de fraction irréductible ?", ["1/5", "5/10", "1/2", "2/1"], 2),
    q("Si tu as un gâteau coupé en 4 parts égales et que tu en manges 1, quelle fraction du gâteau as-tu "
      "mangée ?", ["1/4", "4/1", "3/4", "1/3"]),
    q("Pour additionner 1/3 et 1/6, quel est le dénominateur commun le plus petit ?", ["3", "6", "18", "2"], 1),
    q("Quelle fraction est équivalente à 2/3 ?", ["4/5", "6/9", "2/6", "3/6"], 1),
]
# défauts réels du 05/10 : plusieurs bonnes réponses (N3), figure absente (N3)
EGALES = q("Quelle est la fraction équivalente à 2/4 ?", ["1/2", "2/8", "4/8", "3/6"])
FIGURE = q("Quelle fraction représente la partie hachurée de la figure ci-jointe ?", ["1/3", "1/2", "2/3"], 1)
REMPLACANTE_2 = q("Quelle fraction est équivalente à 1/2 ?", ["2/5", "1/4", "3/6", "2/3"], 2)
REMPLACANTE_4 = q("Simplifie la fraction 6/9 en trouvant la fraction équivalente la plus simple.",
                  ["2/3", "3/6", "6/18", "1/9"])


def exercice(*questions: dict) -> dict:
    return {"type": "qcm", "titre": "Les fractions", "matiere": "maths", "niveau": "6e", "notion": "fractions",
            "questions": [copy.deepcopy(x) for x in questions]}


@pytest.fixture
def suite(dossiers, monkeypatch):
    """Installe un fournisseur Suite ; tentatives_max reste celui de config.yaml sauf réglage explicite."""
    def installer(reponses: list, tentatives_max: int = 3) -> Suite:
        fournisseur = Suite(reponses)
        monkeypatch.setattr(generation, "creer", lambda nom, reglages: fournisseur)
        cfg = copy.deepcopy(config.charger())
        cfg["generation"]["tentatives_max"] = tentatives_max
        monkeypatch.setattr(config, "charger", lambda: cfg)
        return fournisseur
    return installer


def test_reprise_des_seules_questions_refusees(suite, capsys):
    initial = exercice(JUSTES[0], EGALES, JUSTES[2], FIGURE, JUSTES[4])
    fournisseur = suite([initial, {"questions": [REMPLACANTE_2, REMPLACANTE_4]}])

    instance = generation.generer({"type": "qcm", "notion": "fractions"}, "qcm", "suite", mode="ia")

    # les questions 2 et 4 sont remplacées à leur place, les autres sont intactes
    assert instance["questions"] == [JUSTES[0], REMPLACANTE_2, JUSTES[2], REMPLACANTE_4, JUSTES[4]]
    meta = instance["meta"]
    assert meta["tentatives"] == 2 and meta["tentatives_par_question"] == [1, 2, 1, 2, 1]
    [reprise] = meta["reprises"]
    assert reprise["tentative"] == 2 and reprise["questions"] == [2, 4]
    assert reprise["resultat"] == "questions remplacées"
    assert reprise["questions_remplacees"] == [EGALES, FIGURE]  # les versions fautives, pour les mesures
    assert [int(m.split(" ")[1]) for m in reprise["erreurs"]] == [2, 4]
    assert meta["validation"]["n4_questions"] == [VERIFIE] * 5
    assert not (generation.config.chemin("rejets")).exists()

    # ce que le modèle a reçu à la reprise : la conversation prolongée, et un schéma de 2 questions
    messages, schema = fournisseur.appels[1]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[:2] == fournisseur.appels[0][0]                  # début identique : réutilisable par Ollama
    assert json.loads(messages[2]["content"]) == initial                 # sa réponse, telle qu'il l'a écrite
    correction = messages[3]["content"]
    assert "les questions 2 et 4, dans cet ordre" in correction and "exactement 2 questions" in correction
    assert "« 1/2 », « 4/8 » et « 3/6 » ont la même valeur" in correction
    assert "aucune image" in correction
    assert list(schema["properties"]) == ["questions"]
    assert schema["properties"]["questions"]["minItems"] == schema["properties"]["questions"]["maxItems"] == 2

    sortie = capsys.readouterr().out
    assert "✗ tentative 1 refusée (N3) : les questions 2 et 4" in sortie
    assert "→ reprise 1/2 : les questions 2 et 4…" in sortie


def test_abandon_apres_tentatives_max(suite):
    initial = exercice(JUSTES[0], EGALES, *JUSTES[2:])
    fournisseur = suite([initial, {"questions": [EGALES]}, {"questions": [EGALES]}])

    with pytest.raises(ErreurValidation) as e:
        generation.generer({"type": "qcm", "notion": "fractions"}, "qcm", "suite", mode="ia")

    assert len(fournisseur.appels) == 3 and e.value.questions == (2,)
    rejet = json.loads(e.value.rejet.read_text(encoding="utf-8"))
    assert rejet["tentatives"] == 3 and [r["tentative"] for r in rejet["reprises"]] == [2, 3]
    assert rejet["instance"]["questions"][1] == EGALES        # N4 pourra être recalculée sur la dernière version


def test_une_reprise_illisible_est_redemandee(suite):
    initial = exercice(JUSTES[0], EGALES, *JUSTES[2:])
    fournisseur = suite([initial, "désolé, je ne peux pas", {"questions": [REMPLACANTE_2]}])

    instance = generation.generer({"type": "qcm", "notion": "fractions"}, "qcm", "suite", mode="ia")

    assert instance["questions"][1] == REMPLACANTE_2
    assert instance["meta"]["tentatives"] == 3 and instance["meta"]["tentatives_par_question"] == [1, 2, 1, 1, 1]
    rate, reussie = instance["meta"]["reprises"]
    assert rate["resultat"] == "réponse inutilisable (N1)" and reussie["resultat"] == "questions remplacées"
    # la 3e tentative redemande la même question, en signalant l'échec de la 2e
    correction = fournisseur.appels[2][0][3]["content"]
    assert "remplacer la question 2." in correction and "n'était pas utilisable" in correction
    assert "aucun objet JSON" in correction


def test_un_json_initial_invalide_fait_reprendre_tout_l_exercice(suite):
    fournisseur = suite(["Voici votre exercice ! (mais pas de JSON)", exercice(*JUSTES)])

    instance = generation.generer({"type": "qcm", "notion": "fractions"}, "qcm", "suite", mode="ia")

    messages, schema = fournisseur.appels[1]
    assert "renvoie l'exercice complet" in messages[3]["content"] and "aucun objet JSON" in messages[3]["content"]
    assert messages[2]["content"] == "Voici votre exercice ! (mais pas de JSON)"
    assert "titre" in schema["properties"]                                     # schéma complet
    assert instance["meta"]["tentatives"] == 2 and instance["meta"]["tentatives_par_question"] == [1] * 5
    assert instance["meta"]["reprises"][0]["resultat"] == "exercice regénéré"


def test_un_defaut_hors_question_fait_reprendre_tout_l_exercice(suite):
    avec_courriel = exercice(*JUSTES)
    avec_courriel["consigne"] = "Envoie tes réponses à prof@exemple.fr"
    fournisseur = suite([avec_courriel, exercice(*JUSTES)])

    instance = generation.generer({"type": "qcm", "notion": "fractions"}, "qcm", "suite", mode="ia")

    assert "renvoie l'exercice complet" in fournisseur.appels[1][0][3]["content"]
    assert "consigne" not in instance and instance["meta"]["tentatives_par_question"] == [2] * 5


def test_tout_l_exercice_est_revalide_apres_une_reprise(suite):
    # la remplaçante de la question 2 recopie la question 1 : c'est elle qui est refusée à son tour
    initial = exercice(JUSTES[0], EGALES, *JUSTES[2:])
    fournisseur = suite([initial, {"questions": [JUSTES[0]]}, {"questions": [REMPLACANTE_2]}])

    instance = generation.generer({"type": "qcm", "notion": "fractions"}, "qcm", "suite", mode="ia")

    assert "même énoncé que la question 1" in fournisseur.appels[2][0][3]["content"]
    assert instance["questions"][1] == REMPLACANTE_2 and instance["meta"]["tentatives_par_question"][1] == 3


def test_sans_reprise_si_tentatives_max_vaut_1(suite):
    fournisseur = suite([exercice(JUSTES[0], EGALES, *JUSTES[2:])], tentatives_max=1)
    with pytest.raises(ErreurValidation):
        generation.generer({"type": "qcm", "notion": "fractions"}, "qcm", "suite", mode="ia")
    assert len(fournisseur.appels) == 1


def test_premier_essai_reussi_sans_reprise(suite):
    suite([exercice(*JUSTES)])
    instance = generation.generer({"type": "qcm", "notion": "fractions"}, "qcm", "suite", mode="ia")
    assert instance["meta"]["tentatives"] == 1 and instance["meta"]["reprises"] == []
    assert instance["meta"]["tentatives_par_question"] == [1] * 5


def test_message_de_reprise_au_singulier():
    texte = generation.message_de_reprise(["question 3 : un défaut"], [3], [])
    assert texte == ("Ta réponse a été refusée par la vérification automatique :\n"
                     "- question 3 : un défaut\n\n"
                     "Écris 1 nouvelle question pour remplacer la question 3. Même notion et même niveau ; ne "
                     "reprends aucune des autres questions de l'exercice ; respecte toutes les règles du message "
                     "système. Réponds uniquement par un objet JSON de la forme {\"questions\": [...]}, avec "
                     "exactement 1 question.")


# --- compteurs du modèle dans le meta (étape 1.5) ------------------------------------------------

class Compte(Suite):
    """Suite qui annonce aussi des compteurs, comme Ollama."""
    def generer(self, messages: list[dict], schema: dict) -> str:
        self.compteurs = {"tokens_lus": 1000 * (len(self.appels) + 1), "tokens_ecrits": 300, "chargement_s": 0.1}
        return super().generer(messages, schema)


def test_meta_garde_les_compteurs_de_chaque_appel(dossiers, monkeypatch, capsys):
    fournisseur = Compte([exercice(JUSTES[0], EGALES, *JUSTES[2:]), {"questions": [REMPLACANTE_2]}])
    monkeypatch.setattr(generation, "creer", lambda nom, reglages: fournisseur)

    instance = generation.generer({"type": "qcm", "notion": "fractions"}, "qcm", "compte", mode="ia")

    appels = instance["meta"]["appels"]
    assert [a["tentative"] for a in appels] == [1, 2]
    assert [a["tokens_lus"] for a in appels] == [1000, 2000] and all(a["tokens_ecrits"] == 300 for a in appels)
    assert "(1000 tokens lus, 300 écrits ; chargement 0.1 s)" in capsys.readouterr().out


def test_detail_appel_sans_compteurs():
    assert generation.detail_appel(None) == "" and generation.detail_appel({}) == ""
    assert generation.detail_appel({"tokens_ecrits": 12}) == " (12 écrits)"
    assert generation.detail_appel({"tokens_lus": 3318, "tokens_ecrits": 544, "chargement_s": 7.9, "lecture_s": 300.2,
                                    "ecriture_s": 122.5}) == (" (3318 tokens lus, 544 écrits ; chargement 7.9 s, "
                                                              "lecture 300.2 s, écriture 122.5 s)")


# --- la demande de l'enseignant : nombre de questions et classe (recette 1.6) --------------------

@pytest.mark.parametrize("phrase, nb_questions, niveau", [
    ("un QCM de 15 questions sur le calcul mental pour des 6e", 15, "6e"),   # cas réel du 08/10 : 5 produites
    ("un QCM de 3 questions sur le passé composé pour des 5e", 3, "5e"),
    ("10 questions de Pythagore en 4ème", 10, "4e"),
    ("les fractions, classe de sixième", None, "6e"),
    ("un QCM de 40 questions sur les fractions", None, None),                 # hors des bornes du schéma
    ("une question sur les fractions", None, None),
])
def test_completer_demande(phrase, nb_questions, niveau):
    demande = generation.completer_demande({"demande_enseignant": phrase})
    assert (demande.get("nb_questions"), demande.get("niveau")) == (nb_questions, niveau)


def test_completer_demande_respecte_les_options():
    demande = generation.completer_demande({"demande_enseignant": "15 questions pour des 6e", "nb_questions": 4,
                                            "niveau": "5e"})
    assert (demande["nb_questions"], demande["niveau"]) == (4, "5e")


def test_le_procedural_respecte_le_nombre_demande(dossiers):
    instance = generation.generer({"type": "qcm", "demande_enseignant": "un QCM de 15 questions sur le calcul "
                                   "mental pour des 6e"}, "qcm", "maquette", graine=1)
    assert len(instance["questions"]) == 15 and instance["niveau"] == "6e"


def test_debut_du_message_identique_pour_toutes_les_demandes():
    # le cache du modèle (Ollama, llama.cpp) réutilise le début commun : il doit aller jusqu'à la demande
    type_exo = generation.registre.charger("qcm")
    a = generation.construire_messages(type_exo, {"notion": "fractions", "nb_questions": 5, "niveau": "6e"})
    b = generation.construire_messages(type_exo, {"notion": "la Révolution", "nb_questions": 12, "niveau": "4e"})
    assert a[0] == b[0]
    commun = a[1]["content"].split("Demande :")[0]
    assert b[1]["content"].startswith(commun)
    assert "Exemple d'une sortie valide" in commun
