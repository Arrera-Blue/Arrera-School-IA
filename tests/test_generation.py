"""Génération de bout en bout, sans modèle : le meta d'un exercice accepté, et la conservation des rejets."""

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
        generation.generer({"type": "qcm", "demande_enseignant": "fractions 6e"}, "qcm", "rejoue")

    fichiers = list((dossiers / "rejets").glob("*.json"))
    assert len(fichiers) == 1 and e.value.rejet == fichiers[0]
    rejet = json.loads(fichiers[0].read_text(encoding="utf-8"))
    assert rejet["niveau"] == "N3" and rejet["questions"] == [1, 3, 4]
    assert rejet["instance"]["matiere"] == "maths"  # N4 pourra être recalculée dessus
    assert rejet["brut"] == brut and rejet["modele"] == "réponse enregistrée"
    assert (dossiers / "sortie" / "derniere_reponse_brute.txt").read_text(encoding="utf-8") == brut


def test_un_rejet_n1_est_conserve_sans_instance(dossiers, monkeypatch):
    rejouer(monkeypatch, "Voici votre exercice ! (mais pas de JSON)")
    with pytest.raises(ErreurValidation):
        generation.generer({"type": "qcm", "notion": "test"}, "qcm", "rejoue")
    rejet = json.loads(next((dossiers / "rejets").glob("*.json")).read_text(encoding="utf-8"))
    assert rejet["niveau"] == "N1" and rejet["instance"] is None


def test_deux_rejets_rapproches_ne_s_ecrasent_pas(dossiers, monkeypatch):
    rejouer(monkeypatch, "pas de JSON")
    for _ in range(2):
        with pytest.raises(ErreurValidation):
            generation.generer({"type": "qcm", "notion": "test"}, "qcm", "rejoue")
    assert len(list((dossiers / "rejets").glob("*.json"))) == 2


def test_resume_n4():
    instance = {"matiere": "maths", "meta": {"validation": {"n4_questions": [VERIFIE, A_RELIRE, VERIFIE]}}}
    assert generation.resume_n4(instance) == "N4 : 2 question(s) recalculée(s) et juste(s), 1 à relire (question 2)"
    instance["matiere"] = "histoire-geo"
    assert "hors maths" in generation.resume_n4(instance)
