"""Les données d'entraînement du modèle (plan IA, IA3) : à part de la vraie banque, jamais publiées, jamais versionnées.

    donnees/entrainement/          (config.yaml : chemins.entrainement ; hors git, comme tout donnees/)
        banque/instances/          les exercices du lot, rangés comme la banque : un JSON par exercice
        banque/rejets/             les générations refusées par N1 → N4
        banque/supprimes/
        sortie/                    leurs pages HTML
        avancement.jsonl           une ligne par demande de la génération de nuit (nuit.py) : de quoi reprendre

Le lot se range comme la banque (`utiliser` redirige ses dossiers pour tout le processus) : la génération, la relecture,
les corrections à la main s'y font avec le code habituel, sans jamais toucher aux exercices de l'enseignant.

    python -m generateur.entrainement nuit --jusqua 07:30
    python -m generateur.entrainement bilan
"""

from pathlib import Path

from generateur.moteur import config


def dossier() -> Path:
    return config.chemin("entrainement")


def chemins() -> dict[str, Path]:
    """Les dossiers du lot, sous les noms de ceux de la banque (config.yaml, `chemins`)."""
    d = dossier()
    return {"banque": d / "banque" / "instances", "rejets": d / "banque" / "rejets",
            "supprimes": d / "banque" / "supprimes", "sortie": d / "sortie"}


def utiliser() -> dict[str, Path]:
    """Toute la suite du processus range ses exercices dans le lot, plus dans la vraie banque."""
    lot = chemins()
    config.rediriger(lot)
    return lot
