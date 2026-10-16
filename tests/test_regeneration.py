"""Phase 3 : régénérer une question à la demande de l'enseignant, et suivre une génération en direct."""

import copy
import json

import pytest

from generateur.moteur import config, generation, registre
from generateur.moteur.fournisseurs.base import Fournisseur
from generateur.moteur.validation import ErreurValidation
from generateur.outils.bilan_n4 import avant_regenerations

NOUVELLE = {"enonce": "Dans un triangle rectangle, comment s'appelle le côté opposé à l'angle droit ?",
            "propositions": ["la médiane", "l'hypoténuse", "la hauteur"], "index_correct": 1,
            "explication": "Le côté opposé à l'angle droit est le plus long : c'est l'hypoténuse."}


class Modele(Fournisseur):
    """Écrit l'exercice d'exemple, puis les questions de remplacement qu'on lui a données ; diffuse sa réponse
    en petits morceaux, comme llama.cpp, pour le suivi en direct."""
    nom, modele = "faux", "faux-modele"

    def __init__(self, remplacements: list[dict] | None = None):
        self.remplacements = list(remplacements or [NOUVELLE])
        self.recus: list[list[dict]] = []

    def generer(self, messages, schema):
        self.recus.append(messages)
        if set(schema["properties"]) == {"questions"}:
            nombre = schema["properties"]["questions"]["minItems"]
            reponse = json.dumps({"questions": [self.remplacements.pop(0) for _ in range(nombre)]}, ensure_ascii=False)
        else:
            reponse = json.dumps(registre.charger("qcm").exemple, ensure_ascii=False)
        for i in range(0, len(reponse), 7):  # « "enonce" » coupé entre deux morceaux, parfois
            if self.au_fil:
                self.au_fil(reponse[i:i + 7])
        return reponse


@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    return tmp_path


@pytest.fixture
def modele(monkeypatch):
    faux = Modele()
    monkeypatch.setattr(generation, "creer", lambda nom, reglages: faux)
    return faux


DEMANDE = {"type": "qcm", "matiere": "maths", "niveau": "4e", "notion": "Pythagore",
           "demande_enseignant": "un QCM de 3 questions sur Pythagore pour des 4e"}


def test_la_generation_est_suivie_en_direct(dossiers, modele):
    evenements = []
    instance = generation.generer(DEMANDE, "qcm", mode="ia", suivi=evenements.append)
    etapes = [e["etape"] for e in evenements]
    assert etapes[0] == "modele" and etapes[-2:] == ["validation", "valide"]
    ecriture = [e for e in evenements if e["etape"] == "ecriture"]
    # la question en cours d'écriture, d'après les clés « enonce » de la réponse, même coupées en morceaux
    assert max(e["question"] for e in ecriture) == 3 and {e["sur"] for e in ecriture} == {3}
    assert "question 3 sur 3" in ecriture[-1]["message"]
    assert modele.au_fil is None  # rendu après l'appel
    assert instance["meta"]["demande"]["nb_questions"] == 3  # la demande complétée, pour une régénération


def test_regenerer_une_question_du_modele(dossiers, modele):
    instance = generation.generer(DEMANDE, "qcm", mode="ia")
    instance["meta"]["statut"] = "accepte"
    avant = copy.deepcopy(instance)

    nouvelle = generation.regenerer_question(instance, 2, motif="trop proche du cours")

    assert instance == avant  # l'original n'est pas modifié
    assert nouvelle["questions"][1] == NOUVELLE
    assert nouvelle["questions"][0] == avant["questions"][0] and nouvelle["questions"][2] == avant["questions"][2]
    meta = nouvelle["meta"]
    assert meta["statut"] == "genere"  # l'exercice a changé : à accepter de nouveau
    [trace] = meta["regenerations"]
    assert (trace["question"], trace["motif"], trace["origine"], trace["tentatives"]) == \
        (2, "trop proche du cours", "modele", 1)
    assert trace["ancienne"] == avant["questions"][1]
    assert meta["validation"]["n4_questions"][1] == "a_relire"
    assert meta["tentatives_par_question"] == avant["meta"]["tentatives_par_question"]  # mesures inchangées
    # la conversation est reprise : même demande, l'exercice actuel, puis la demande de l'enseignant
    message = modele.recus[-1][-1]["content"]
    assert message.startswith("L'enseignant a relu l'exercice et demande une autre question :")
    assert "question 2 : l'enseignant demande de la remplacer par une autre question (trop proche du cours)" in message
    assert "exactement 1 question" in message


def test_une_question_refusee_est_reprise_puis_l_exercice_reste_intact(dossiers, modele):
    instance = generation.generer(DEMANDE, "qcm", mode="ia")
    doublon = copy.deepcopy(instance["questions"][0])  # N3 refuse un énoncé déjà présent
    modele.remplacements = [doublon, doublon, doublon]
    with pytest.raises(ErreurValidation) as e:
        generation.regenerer_question(instance, 2)
    assert e.value.erreurs[0] == "la question 2 n'a pas pu être remplacée après 3 tentative(s)"
    assert not (dossiers / "rejets").exists()  # pas un rejet du modèle : l'exercice d'origine reste valable


def test_la_meme_question_recrite_est_refusee(dossiers, modele):
    instance = generation.generer(DEMANDE, "qcm", mode="ia")
    identique = copy.deepcopy(instance["questions"][1])
    modele.remplacements = [identique, NOUVELLE]
    nouvelle = generation.regenerer_question(instance, 2)
    assert nouvelle["questions"][1] == NOUVELLE and nouvelle["meta"]["regenerations"][0]["tentatives"] == 2
    assert "écris une question différente" in modele.recus[-1][-1]["content"]


def test_regenerer_une_question_procedurale(dossiers):
    instance = generation.generer({"type": "qcm", "notion": "fractions", "niveau": "6e"}, "qcm", "maquette", graine=3)
    nouvelle = generation.regenerer_question(instance, 4)
    assert nouvelle["questions"][3] != instance["questions"][3]
    assert [q for i, q in enumerate(nouvelle["questions"]) if i != 3] == \
        [q for i, q in enumerate(instance["questions"]) if i != 3]
    genre_avant = instance["meta"]["questions"][3]["genre"]
    assert nouvelle["meta"]["questions"][3] == {"genre": genre_avant, "habillage": "gabarit", "regeneree": True}
    assert nouvelle["meta"]["regenerations"][0]["origine"] == "procedural"
    assert nouvelle["meta"]["validation"]["n4_questions"][3] == "verifie"  # juste par construction, et vérifié


def test_numero_hors_de_l_exercice(dossiers, modele):
    instance = generation.generer(DEMANDE, "qcm", mode="ia")
    for numero in (0, 4):
        with pytest.raises(ValueError, match="inexistante"):
            generation.regenerer_question(instance, numero)


def test_une_ancienne_instance_sans_demande_enregistree(dossiers, modele):
    instance = generation.generer(DEMANDE, "qcm", mode="ia")
    del instance["meta"]["demande"]  # exercices d'avant le 13/10
    nouvelle = generation.regenerer_question(instance, 1)
    assert nouvelle["questions"][0] == NOUVELLE
    utilisateur = modele.recus[-1][1]["content"]
    assert '"nb_questions": 3' in utilisateur and "un QCM de 3 questions sur Pythagore" in utilisateur


def test_les_mesures_ignorent_les_choix_de_l_enseignant(dossiers, modele):
    instance = generation.generer(DEMANDE, "qcm", mode="ia")
    nouvelle = generation.regenerer_question(instance, 2)
    assert avant_regenerations(nouvelle)["questions"] == instance["questions"]
    assert avant_regenerations(instance) is instance
