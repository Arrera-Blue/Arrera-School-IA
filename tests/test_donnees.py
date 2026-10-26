"""E1 : le socle SQLite (generateur/donnees/base.py) — droits, migrations, sauvegardes, requêtes paramétrées."""

import ast
import os
import sqlite3
import stat
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from generateur.donnees import base as module_base
from generateur.donnees.base import Base, instructions, migrations_disponibles, sauvegardes

DONNEES = Path(module_base.__file__).parent


def droits(chemin: Path) -> int:
    return stat.S_IMODE(os.stat(chemin).st_mode)


def test_la_base_est_privee_en_wal_avec_les_cles_etrangeres(tmp_path):
    base = Base(tmp_path / "donnees" / "arrera.sqlite3")
    with base.ecrire() as conn:
        conn.execute("INSERT INTO journal (date, action) VALUES (?, ?)", ("2026-10-20T10:00:00", "essai"))
    assert droits(base.chemin) == 0o600 and droits(base.chemin.parent) == 0o700
    for annexe in base.chemin.parent.glob("arrera.sqlite3-*"):  # -wal, -shm : mêmes droits que la base
        assert droits(annexe) == 0o600, annexe.name
    with base.lire() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert [tuple(r) for r in conn.execute("SELECT numero, nom FROM migration")] == [(1, "001_comptes"),
                                                                                         (2, "002_classes"), (3, "003_suivi")]


def test_une_base_existante_est_remise_en_600(tmp_path):
    chemin = tmp_path / "arrera.sqlite3"
    chemin.touch(mode=0o644)
    os.chmod(chemin, 0o644)
    Base(chemin).preparer()
    assert droits(chemin) == 0o600


def test_un_echec_annule_toute_la_transaction(tmp_path):
    base = Base(tmp_path / "b.sqlite3")
    with pytest.raises(RuntimeError), base.ecrire() as conn:
        conn.execute("INSERT INTO journal (date, action) VALUES (?, ?)", ("2026-10-20T10:00:00", "essai"))
        raise RuntimeError("panne au milieu")
    with base.lire() as conn:
        assert conn.execute("SELECT COUNT(*) FROM journal").fetchone()[0] == 0


def ecrire_migrations(dossier: Path, **scripts: str) -> Path:
    dossier.mkdir(exist_ok=True)
    for nom, script in scripts.items():
        (dossier / f"{nom}.sql").write_text(script, encoding="utf-8")
    return dossier


def test_migrations_appliquees_une_fois_dans_l_ordre(tmp_path):
    dossier = ecrire_migrations(tmp_path / "m", **{
        "001_a": "-- un commentaire ; avec un point-virgule\nCREATE TABLE a (x INTEGER);\nINSERT INTO a VALUES (1);",
        "002_b": "CREATE TABLE b (y INTEGER REFERENCES a (x));"})
    chemin = tmp_path / "b.sqlite3"
    conn = sqlite3.connect(chemin, isolation_level=None)
    assert module_base.migrer(conn, dossier) == ["001_a", "002_b"]
    assert module_base.migrer(conn, dossier) == []  # rien à refaire
    ecrire_migrations(dossier, **{"003_c": "ALTER TABLE b ADD COLUMN z TEXT;"})
    assert module_base.migrer(conn, dossier) == ["003_c"]
    assert [r[0] for r in conn.execute("SELECT numero FROM migration ORDER BY numero")] == [1, 2, 3]


def test_une_migration_ratee_ne_laisse_rien(tmp_path):
    dossier = ecrire_migrations(tmp_path / "m", **{
        "001_a": "CREATE TABLE a (x INTEGER);",
        "002_b": "CREATE TABLE b (y INTEGER);\nINSERT INTO table_absente VALUES (1);"})
    conn = sqlite3.connect(tmp_path / "b.sqlite3", isolation_level=None)
    with pytest.raises(sqlite3.OperationalError):
        module_base.migrer(conn, dossier)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "a" in tables and "b" not in tables  # 001 faite ; 002 annulée en entier
    assert [r[0] for r in conn.execute("SELECT numero FROM migration")] == [1]


@pytest.mark.parametrize("noms, message", [(["001_a", "003_c"], "manquants"), (["01_a"], "mal nommée"),
                                           (["001_A"], "mal nommée")])
def test_migrations_mal_numerotees(tmp_path, noms, message):
    dossier = ecrire_migrations(tmp_path / "m", **{nom: "SELECT 1;" for nom in noms})
    with pytest.raises(ValueError, match=message):
        migrations_disponibles(dossier)


def test_decoupage_des_instructions():
    assert len(list(instructions("CREATE TABLE a (x TEXT DEFAULT ';');\n-- fin ; vraiment\n"))) == 1
    with pytest.raises(ValueError, match="incomplète"):
        list(instructions("CREATE TABLE a (x INTEGER)"))


def test_les_migrations_du_projet_sont_bien_numerotees():
    assert [nom for _, nom, _ in migrations_disponibles()][0] == "001_comptes"


# --- sauvegardes (SEC-13) -------------------------------------------------------------------------

def test_sauvegarde_privee_et_restaurable(tmp_path):
    base = Base(tmp_path / "arrera.sqlite3")
    with base.ecrire() as conn:
        conn.execute("INSERT INTO journal (date, action) VALUES (?, ?)", ("2026-10-20T10:00:00", "avant"))
    copie = base.sauvegarder(tmp_path / "sauvegardes", datetime(2026, 10, 20, 12, 0, 0))
    assert copie.name == "base-20261020-120000.sqlite3" and droits(copie) == 0o600
    assert droits(copie.parent) == 0o700
    restauree = sqlite3.connect(copie)
    assert restauree.execute("SELECT action FROM journal").fetchall() == [("avant",)]


def test_une_sauvegarde_par_jour_gardee_7_jours(tmp_path):
    base = Base(tmp_path / "arrera.sqlite3")
    dossier = tmp_path / "sauvegardes"
    debut = datetime(2026, 10, 1, 8, 0, 0)
    assert base.sauvegarder_si_besoin(dossier, debut) is not None
    assert base.sauvegarder_si_besoin(dossier, debut + timedelta(hours=5)) is None  # déjà une aujourd'hui
    for jour in range(1, 12):
        base.sauvegarder_si_besoin(dossier, debut + timedelta(days=jour))
    dates = [date for date, _ in sauvegardes(dossier)]
    fin = debut + timedelta(days=11)
    assert dates[-1] == fin and all(fin - d <= timedelta(days=7) for d in dates) and len(dates) == 8


# --- requêtes paramétrées uniquement (SEC-2) ------------------------------------------------------

SQL = ("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "PRAGMA", "WHERE", "VALUES")


def _contient_sql(texte: str) -> bool:
    return any(mot in texte.split() or f"{mot} " in texte for mot in SQL)


def assemblages_sql(source: str) -> list[int]:
    """Les lignes où un texte de requête est assemblé : f-string, « % », « + » ou .format()."""
    lignes = []
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, ast.JoinedStr):
            texte = "".join(v.value for v in noeud.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
            if _contient_sql(texte):
                lignes.append(noeud.lineno)
        elif isinstance(noeud, ast.BinOp) and isinstance(noeud.op, (ast.Mod, ast.Add)):
            for cote in (noeud.left, noeud.right):
                if isinstance(cote, ast.Constant) and isinstance(cote.value, str) and _contient_sql(cote.value):
                    lignes.append(noeud.lineno)
        elif (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute) and noeud.func.attr == "format"
              and isinstance(noeud.func.value, ast.Constant) and _contient_sql(str(noeud.func.value.value))):
            lignes.append(noeud.lineno)
    return lignes


def test_le_controle_reconnait_une_requete_assemblee():
    assert assemblages_sql('conn.execute(f"SELECT * FROM t WHERE nom = \'{nom}\'")') == [1]
    assert assemblages_sql('conn.execute("DELETE FROM t WHERE id = %s" % ident)') == [1]
    assert assemblages_sql('conn.execute("SELECT * FROM t WHERE id = " + ident)') == [1]
    assert assemblages_sql('conn.execute("SELECT * FROM t WHERE id = ?", (ident,))') == []


@pytest.mark.parametrize("fichier", sorted(DONNEES.glob("*.py")), ids=lambda f: f.name)
def test_aucune_requete_assemblee_dans_generateur_donnees(fichier):
    assert assemblages_sql(fichier.read_text(encoding="utf-8")) == [], f"{fichier.name} : requête assemblée"
