"""Découverte des types d'exercice par listage de generateur/types/.

Aucun type n'est codé en dur : ajouter un type, c'est ajouter un dossier contenant
schema.json, prompt.txt, exemple.json et au moins un gabarit*.html.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from generateur.moteur import config

FICHIERS_REQUIS = ("schema.json", "prompt.txt", "exemple.json")


class TypeInconnu(Exception):
    pass


@dataclass(frozen=True)
class TypeExercice:
    nom: str
    dossier: Path
    schema: dict
    prompt: str
    exemple: dict
    gabarits: tuple[str, ...]


def lister() -> list[str]:
    return sorted(d.name for d in config.chemin("types").iterdir() if d.is_dir() and not d.name.startswith((".", "_")))


def charger(nom: str) -> TypeExercice:
    dossier = config.chemin("types") / nom
    if not dossier.is_dir():
        raise TypeInconnu(f"type « {nom} » inconnu ; types disponibles : {', '.join(lister())}")
    manquants = [f for f in FICHIERS_REQUIS if not (dossier / f).is_file()]
    gabarits = tuple(sorted(p.stem for p in dossier.glob("gabarit*.html")))
    if not gabarits:
        manquants.append("gabarit.html")
    if manquants:
        raise TypeInconnu(f"type « {nom} » incomplet, fichiers manquants : {', '.join(manquants)}")

    return TypeExercice(
        nom=nom,
        dossier=dossier,
        schema=json.loads((dossier / "schema.json").read_text(encoding="utf-8")),
        prompt=(dossier / "prompt.txt").read_text(encoding="utf-8"),
        exemple=json.loads((dossier / "exemple.json").read_text(encoding="utf-8")),
        gabarits=gabarits,
    )
