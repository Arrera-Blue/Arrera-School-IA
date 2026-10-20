"""Le journal des accès (évolution E1, SEC-10) : qui a fait quoi, quand.

Jamais de mot de passe, de jeton ni de code. Un identifiant saisi qui ne correspond à aucun compte est noté
« (inconnu) » : c'est souvent un mot de passe tapé dans le mauvais champ. Gardé 6 mois (⚖6), comme le prévoit
le registre (docs/rgpd/registre.md §8).
"""

import sqlite3
from datetime import datetime, timedelta

from generateur.donnees.base import Base, maintenant_iso

CONSERVATION_JOURS = 183  # 6 mois


def noter(conn: sqlite3.Connection, action: str, auteur: dict | None = None, *, identifiant: str | None = None,
          cible: str | None = None, detail: str | None = None) -> None:
    """À appeler dans la transaction de l'action notée : l'action et sa trace sont enregistrées ensemble.
    `auteur` : le compte connecté (None : la ligne de commande, ou une connexion pas encore ouverte)."""
    if auteur is not None:
        identifiant = auteur["identifiant"]
    conn.execute("INSERT INTO journal (date, enseignant_id, identifiant, action, cible, detail) "
                 "VALUES (?, ?, ?, ?, ?, ?)",
                 (maintenant_iso(), auteur["id"] if auteur else None, identifiant, action, cible, detail))


def lire(base: Base, limite: int = 100) -> list[dict]:
    """Les entrées les plus récentes d'abord."""
    with base.lire() as conn:
        lignes = conn.execute("SELECT date, identifiant, action, cible, detail FROM journal ORDER BY id DESC LIMIT ?",
                              (limite,)).fetchall()
    return [dict(ligne) for ligne in lignes]


def purger(conn: sqlite3.Connection, maintenant: datetime | None = None, jours: int = CONSERVATION_JOURS) -> int:
    limite = ((maintenant or datetime.now()) - timedelta(days=jours)).isoformat(timespec="seconds")
    return conn.execute("DELETE FROM journal WHERE date < ?", (limite,)).rowcount
