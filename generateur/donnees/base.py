"""La base SQLite du PC enseignant (évolution E1). Sécurité : docs/etapes/etape-E1-securite.md.

- SEC-1 : `sqlite3` de la bibliothèque standard ; fichier lisible par le seul compte qui fait tourner le
  serveur (droits 600, dossier 700), mode WAL, clés étrangères actives, migrations numérotées
  (`migrations/001_nom.sql`), appliquées une fois, dans l'ordre, chacune dans une transaction ;
- SEC-2 : requêtes paramétrées uniquement : une valeur n'est jamais collée dans le texte d'une requête
  (vérifié par tests/test_donnees.py, qui lit ce dossier) ;
- SEC-13 : une sauvegarde par jour (`.backup` de SQLite), gardée 7 jours, avec les mêmes droits.

Une connexion par opération (`lire`, `ecrire`) : SQLite l'ouvre en une fraction de milliseconde, et le
serveur web traite les requêtes dans plusieurs fils, qui ne doivent pas partager une connexion.
"""

import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

MIGRATIONS = Path(__file__).with_name("migrations")
NOM_MIGRATION = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
NOM_SAUVEGARDE = re.compile(r"^base-(\d{8}-\d{6})\.sqlite3$")
FORMAT_SAUVEGARDE = "%Y%m%d-%H%M%S"
GARDER_SAUVEGARDES_JOURS = 7


def maintenant_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _dossier_prive(dossier: Path) -> None:
    """Un dossier créé ici n'est ouvert qu'à son propriétaire (700) ; un dossier existant n'est pas touché."""
    if not dossier.exists():
        dossier.mkdir(parents=True, mode=0o700)
        os.chmod(dossier, 0o700)  # mkdir applique le masque du processus (umask)


def _fichier_prive(fichier: Path) -> None:
    """Crée le fichier vide en 600 avant que SQLite ne l'ouvre : jamais un instant lisible par les autres
    comptes du PC ; un fichier existant est remis en 600."""
    _dossier_prive(fichier.parent)
    if not fichier.exists():
        os.close(os.open(fichier, os.O_WRONLY | os.O_CREAT, 0o600))
    os.chmod(fichier, 0o600)


def instructions(script: str):
    """Découpe un script SQL en instructions complètes, pour les exécuter une à une dans UNE transaction :
    `executescript()` validerait la transaction en cours avant de commencer."""
    tampon = ""
    for ligne in script.splitlines(keepends=True):
        tampon += ligne
        if sqlite3.complete_statement(tampon):
            yield tampon
            tampon = ""
    if any(ligne.strip() and not ligne.strip().startswith("--") for ligne in tampon.splitlines()):
        raise ValueError(f"instruction SQL incomplète (point-virgule manquant ?) : {tampon.strip()[:80]}")


def migrations_disponibles(dossier: Path = MIGRATIONS) -> list[tuple[int, str, Path]]:
    """(numéro, nom, fichier), dans l'ordre ; les numéros vont de 1 à n, sans trou ni doublon."""
    trouvees = []
    for fichier in sorted(Path(dossier).glob("*.sql")):
        m = NOM_MIGRATION.match(fichier.name)
        if not m:
            raise ValueError(f"migration mal nommée : {fichier.name} (attendu : 001_nom.sql)")
        trouvees.append((int(m.group(1)), fichier.stem, fichier))
    numeros = [numero for numero, _, _ in trouvees]
    if numeros != list(range(1, len(numeros) + 1)):
        raise ValueError(f"migrations : numéros manquants ou en double ({numeros})")
    return trouvees


class CleEtrangereCassee(RuntimeError):
    """Une migration laisserait une ligne qui renvoie à une ligne absente : elle est annulée."""


def migrer(conn: sqlite3.Connection, dossier: Path = MIGRATIONS) -> list[str]:
    """Applique les migrations qui manquent ; renvoie leurs noms. Chacune entière, ou pas du tout.

    Les clés étrangères sont coupées le temps des migrations (hors transaction : SQLite l'exige), pour qu'une
    migration puisse reconstruire une table (006 : changer une contrainte CHECK) sans que la suppression de l'ancienne
    efface en cascade les lignes qui s'y rattachent ; avant de valider chaque migration, `foreign_key_check` vérifie
    qu'aucune clé n'est cassée (si la connexion les appliquait). Elles sont remises comme avant à la fin."""
    conn.execute("CREATE TABLE IF NOT EXISTS migration (numero INTEGER PRIMARY KEY, nom TEXT NOT NULL, "
                 "date TEXT NOT NULL)")
    cles_etrangeres = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    appliquees = []
    try:
        for numero, nom, fichier in migrations_disponibles(dossier):
            conn.execute("BEGIN IMMEDIATE")  # verrou d'écriture : deux processus ne migrent pas en même temps
            try:
                if conn.execute("SELECT 1 FROM migration WHERE numero = ?", (numero,)).fetchone():
                    conn.execute("ROLLBACK")
                    continue
                for instruction in instructions(fichier.read_text(encoding="utf-8")):
                    conn.execute(instruction)
                if cles_etrangeres and (cassees := conn.execute("PRAGMA foreign_key_check").fetchall()):
                    raise CleEtrangereCassee(f"migration {nom} annulée : {len(cassees)} clé(s) étrangère(s) cassée(s) "
                                             f"(table {cassees[0][0]})")
                conn.execute("INSERT INTO migration (numero, nom, date) VALUES (?, ?, ?)",
                             (numero, nom, maintenant_iso()))
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
            appliquees.append(nom)
    finally:
        conn.execute("PRAGMA foreign_keys = ON" if cles_etrangeres else "PRAGMA foreign_keys = OFF")
    return appliquees


def sauvegardes(dossier: Path) -> list[tuple[datetime, Path]]:
    """Les sauvegardes présentes, de la plus ancienne à la plus récente."""
    trouvees = []
    for fichier in Path(dossier).glob("base-*.sqlite3") if Path(dossier).is_dir() else []:
        m = NOM_SAUVEGARDE.match(fichier.name)
        if m:
            trouvees.append((datetime.strptime(m.group(1), FORMAT_SAUVEGARDE), fichier))
    return sorted(trouvees)


class Base:
    def __init__(self, chemin: Path | str, migrations: Path = MIGRATIONS):
        self.chemin = Path(chemin)
        self.migrations = Path(migrations)
        self._prete = False
        self._verrou = threading.Lock()

    def preparer(self) -> None:
        """Crée la base si besoin et applique les migrations manquantes ; une fois par processus."""
        with self._verrou:
            if self._prete:
                return
            _fichier_prive(self.chemin)
            conn = self._ouvrir()
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                migrer(conn, self.migrations)
            finally:
                conn.close()
            self._prete = True

    def _ouvrir(self) -> sqlite3.Connection:
        # isolation_level=None : aucune transaction implicite ; `ecrire` les ouvre et les ferme lui-même
        conn = sqlite3.connect(self.chemin, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def lire(self):
        self.preparer()
        conn = self._ouvrir()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def ecrire(self):
        """Une transaction : tout est enregistré à la sortie du bloc, ou rien si une exception en sort."""
        self.preparer()
        conn = self._ouvrir()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()

    def sauvegarder(self, dossier: Path, maintenant: datetime | None = None) -> Path:
        """Copie cohérente de la base (`.backup`, même pendant des écritures), en 600."""
        cible = Path(dossier) / f"base-{(maintenant or datetime.now()).strftime(FORMAT_SAUVEGARDE)}.sqlite3"
        _fichier_prive(cible)
        with self.lire() as source:
            destination = sqlite3.connect(cible)
            try:
                source.backup(destination)
            finally:
                destination.close()
        return cible

    def sauvegarder_si_besoin(self, dossier: Path, maintenant: datetime | None = None,
                              garder_jours: int = GARDER_SAUVEGARDES_JOURS) -> Path | None:
        """Une sauvegarde par jour au plus ; efface celles de plus de `garder_jours` jours. Renvoie la nouvelle
        sauvegarde, ou None si la dernière a moins d'un jour."""
        maintenant = maintenant or datetime.now()
        existantes = sauvegardes(dossier)
        nouvelle = None
        if not existantes or maintenant - existantes[-1][0] >= timedelta(days=1):
            nouvelle = self.sauvegarder(dossier, maintenant)
        for date, fichier in sauvegardes(dossier):
            if maintenant - date > timedelta(days=garder_jours):
                fichier.unlink()
        return nouvelle
