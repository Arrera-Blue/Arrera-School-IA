"""Réglages communs aux tests."""

from pathlib import Path

import pytest

from generateur.donnees import codes, comptes, sessions
from generateur.moteur import config, generation, lecture


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


@pytest.fixture(autouse=True)
def sans_contre_verification(monkeypatch):
    """La contre-vérification (plan IA, IA1.4) reposerait chaque question au faux modèle des tests ;
    test_securite.py l'essaie à part (generation.CONTRE_VERIFIER)."""
    monkeypatch.setattr(generation, "contre_verifier", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def sans_redirection(monkeypatch):
    """Les dossiers redirigés vers le lot d'entraînement (plan IA, IA3 : `config.rediriger`) le sont pour tout le
    processus : chaque test repart sans redirection, et n'en laisse aucune au suivant."""
    monkeypatch.setattr(config, "_REDIRIGES", {})


# --- la vraie banque n'est jamais touchée par les tests ---------------------------------------------------
# Incident du 29/10 : un test lançait une régénération sans attendre sa fin ; la tâche, finie après le test (la
# banque temporaire déjà rendue), écrivait dans la vraie banque. La suite échoue désormais si la banque a changé,
# ou le lot d'entraînement (plan IA, IA3).

RACINE = Path(__file__).resolve().parents[1]
VRAIE_BANQUE = [RACINE / "banque" / dossier for dossier in ("instances", "rejets")]
VRAI_LOT = RACINE / "donnees" / "entrainement"


def _contenu() -> list[str]:
    return sorted([str(p) for d in VRAIE_BANQUE if d.is_dir() for p in d.iterdir()]
                  + [f"{p}:{p.stat().st_size}" for p in VRAI_LOT.rglob("*") if p.is_file()])


def pytest_sessionstart(session):
    session.config.stash_banque = _contenu()


def pytest_sessionfinish(session, exitstatus):
    avant, apres = set(session.config.stash_banque), set(_contenu())
    if avant != apres:
        print(f"\n✘ LA VRAIE BANQUE OU LE LOT D'ENTRAÎNEMENT A CHANGÉ PENDANT LES TESTS : ajoutés {sorted(apres - avant)}, "
              f"retirés {sorted(avant - apres)}")
        session.exitstatus = 1

