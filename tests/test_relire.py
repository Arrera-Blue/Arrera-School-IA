"""Outil de relecture de la recette (étape 1.6)."""

import json

import pytest

from generateur.moteur import config, generation
from generateur.outils.relire import a_relire, presenter
from tests.test_generation import EGALES, JUSTES, REMPLACANTE_2, Suite, exercice


@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    return tmp_path


def test_exercice_procedural(dossiers):
    instance = generation.generer({"type": "qcm", "notion": "pourcentages"}, "qcm", "maquette", graine=42)
    texte = presenter(instance)
    assert "générateur procédural" in texte and "graine 42 (rejouer : --graine 42)" in texte
    assert texte.count("[✔ vérifiée] pourcentages.") == 5 and "énoncé : gabarit" in texte
    bonne = instance["questions"][0]
    assert f"   → {bonne['propositions'][bonne['index_correct']]}" in texte


def test_exercice_repare_par_reprise(dossiers, monkeypatch):
    fournisseur = Suite([exercice(JUSTES[0], EGALES, *JUSTES[2:]), {"questions": [REMPLACANTE_2]}])
    monkeypatch.setattr(generation, "creer", lambda nom, reglages: fournisseur)
    instance = generation.generer({"type": "qcm", "notion": "fractions"}, "qcm", "suite", mode="ia")
    texte = presenter(instance)
    assert "— modèle," in texte and "2 tentative(s)" in texte
    assert "Versions refusées avant reprise :" in texte
    assert "(tentative 1) Quelle est la fraction équivalente à 2/4 ? → 1/2" in texte


def test_rejet_illisible():
    texte = presenter({"niveau": "N1", "erreurs": ["aucun objet JSON"], "instance": None, "tentatives": 3})
    assert "REJETÉ (N1) après 3 tentative(s)" in texte and "aucune instance à relire" in texte


def test_choix_des_fichiers(dossiers):
    for nom, date in (("ancien", "2026-10-05T10:00:00"), ("recent", "2026-10-08T09:00:00")):
        dossier = dossiers / "banque"
        dossier.mkdir(exist_ok=True)
        (dossier / f"{nom}.json").write_text(json.dumps({"meta": {"date": date}}), encoding="utf-8")
    assert [f.stem for f in a_relire(None, "2026-10-08")] == ["recent"]
    assert len(a_relire(None, None)) == 1
