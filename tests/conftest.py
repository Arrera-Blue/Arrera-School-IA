"""Réglages communs aux tests."""

import pytest

from generateur.donnees import codes, comptes, sessions
from generateur.moteur import lecture


@pytest.fixture(autouse=True)
def connexion_rapide(monkeypatch):
    """scrypt allégé (n = 2¹⁰ au lieu de 2¹⁷ : 2 ms au lieu de 0,3 s) et aucune pause après un échec de
    connexion ; test_comptes.py vérifie à part les paramètres réels."""
    monkeypatch.setattr(comptes, "SCRYPT", {"n": 2 ** 10, "r": 8, "p": 1})
    monkeypatch.setattr(codes, "SCRYPT_CODE", {"n": 2 ** 10, "r": 8, "p": 1})
    monkeypatch.setattr(sessions, "PAUSE_S", 0)


@pytest.fixture(autouse=True)
def sans_voix(monkeypatch):
    """Les pages se rendent sans la voix de Piper (pas de modèle de voix à charger, rien d'écrit dans cache/) ;
    test_lecture.py essaie la voix à part."""
    monkeypatch.setattr(lecture, "voix", lambda: None)
