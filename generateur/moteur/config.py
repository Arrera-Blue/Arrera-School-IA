"""Lecture de config.yaml et résolution des chemins du projet."""

from functools import cache
from pathlib import Path

import yaml

# generateur/moteur/config.py → la racine du dépôt est deux niveaux au-dessus du paquet
RACINE = Path(__file__).resolve().parents[2]
# des entrées de `chemins` rangées ailleurs pour tout le processus (plan IA, IA3 : le lot d'entraînement)
_REDIRIGES: dict[str, Path] = {}


@cache
def charger() -> dict:
    with open(RACINE / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def chemin(nom: str) -> Path:
    """Chemin absolu d'une entrée de la section `chemins` de config.yaml."""
    if nom in _REDIRIGES:
        return _REDIRIGES[nom]
    return RACINE / charger()["chemins"][nom]


def rediriger(chemins: dict[str, Path]) -> None:
    """Range ces entrées de `chemins` ailleurs, pour tout le processus. La génération de nuit et la relecture du lot
    d'entraînement (plan IA, IA3) se servent ainsi de la banque telle quelle, sans jamais toucher à la vraie."""
    _REDIRIGES.update(chemins)
