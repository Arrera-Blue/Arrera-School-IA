"""Lecture de config.yaml et résolution des chemins du projet."""

from functools import cache
from pathlib import Path

import yaml

# generateur/moteur/config.py → la racine du dépôt est deux niveaux au-dessus du paquet
RACINE = Path(__file__).resolve().parents[2]


@cache
def charger() -> dict:
    with open(RACINE / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def chemin(nom: str) -> Path:
    """Chemin absolu d'une entrée de la section `chemins` de config.yaml."""
    return RACINE / charger()["chemins"][nom]
