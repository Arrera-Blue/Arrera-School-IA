"""Générateur procédural du cycle 2, lot 0, étape 0.1 : le CP, le CE1 et le CE2 dans toute l'application, et les
matières du cycle 2 (docs/Generateur-Procedural/cycle-2-cp-ce1-ce2.md) : la migration 006 (la table des classes
reconstruite sans rien perdre), les listes de classes et de matières d'accord partout, le référentiel, la phrase de
l'enseignant."""

import json
import re
import shutil
import sqlite3
import typing
from pathlib import Path

import pytest

from generateur import programmes
from generateur.donnees import base as module_base
from generateur.donnees import classes
from generateur.interface import api
from generateur.moteur import analyse, banque, config, generation, registre, rendu

RACINE = Path(__file__).resolve().parent.parent
MIGRATIONS = Path(module_base.__file__).parent / "migrations"


# --- la migration 006 ------------------------------------------------------------------------------

def base_avant_006(dossier: Path) -> sqlite3.Connection:
    """Une base arrêtée à la migration 005, avec une classe de 6e, deux élèves, un groupe et une publication."""
    anciennes = dossier / "migrations"
    anciennes.mkdir()
    for fichier in sorted(MIGRATIONS.glob("00[1-5]_*.sql")):
        shutil.copy(fichier, anciennes / fichier.name)
    conn = sqlite3.connect(dossier / "arrera.sqlite3", isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    module_base.migrer(conn, anciennes)
    conn.execute("INSERT INTO enseignant (id, identifiant, nom, role, empreinte, cree) "
                 "VALUES (1, 'prof', 'Prof', 'admin', 'x', '2026-11-10')")
    conn.execute("INSERT INTO classe (id, enseignant_id, nom, niveau, annee, creee, connexion, dernier_numero) "
                 "VALUES (7, 1, '6e B', '6e', '2026-2027', '2026-11-10', 'images', 2)")
    for numero, prenom in ((1, "Léa"), (2, "Hugo")):
        conn.execute("INSERT INTO eleve (classe_id, numero, nom, prenom, code, cree) VALUES (7, ?, 'ARNAUD', ?, 'e', "
                     "'2026-11-10')", (numero, prenom))
    conn.execute("INSERT INTO groupe (id, classe_id, nom, nature, cree) VALUES (3, 7, 'G', 'consolider', '2026-11-10')")
    conn.execute("INSERT INTO publication (classe_id, exercice, creee) VALUES (7, 'qcm-x', '2026-11-10')")
    with pytest.raises(sqlite3.IntegrityError):  # avant 006 : pas de classe de CP
        conn.execute("INSERT INTO classe (enseignant_id, nom, niveau, annee, creee) VALUES (1, 'CP A', 'CP', '2026-2027', "
                     "'2026-11-10')")
    return conn


def test_la_migration_006_garde_tout_et_ouvre_le_cycle_2(tmp_path):
    conn = base_avant_006(tmp_path)
    assert module_base.migrer(conn, MIGRATIONS) == ["006_classes_cycle2"]
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1  # remises comme avant
    assert conn.execute("SELECT id, nom, niveau, connexion, dernier_numero FROM classe").fetchall() == \
        [(7, "6e B", "6e", "images", 2)]
    assert conn.execute("SELECT COUNT(*) FROM eleve WHERE classe_id = 7").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM groupe WHERE classe_id = 7").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM publication WHERE classe_id = 7").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'classe' "
                        "AND name = 'classe_enseignant'").fetchone()
    # le CP, le CE1 et le CE2 entrent ; une classe inconnue, non
    for niveau in ("CP", "CE1", "CE2"):
        conn.execute("INSERT INTO classe (enseignant_id, nom, niveau, annee, creee) VALUES (1, ?, ?, '2026-2027', "
                     "'2026-11-10')", (f"{niveau} A", niveau))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO classe (enseignant_id, nom, niveau, annee, creee) VALUES (1, 'CM1 A', 'CM1', "
                     "'2026-2027', '2026-11-10')")
    # les clés étrangères tiennent toujours : supprimer la classe emporte ses élèves, ses groupes, ses publications
    conn.execute("DELETE FROM classe WHERE id = 7")
    assert [conn.execute(f"SELECT COUNT(*) FROM {t} WHERE classe_id = 7").fetchone()[0]
            for t in ("eleve", "groupe", "publication")] == [0, 0, 0]


def test_une_migration_qui_casse_une_cle_etrangere_est_annulee(tmp_path):
    dossier = tmp_path / "m"
    dossier.mkdir()
    (dossier / "001_a.sql").write_text("CREATE TABLE a (id INTEGER PRIMARY KEY);\nINSERT INTO a VALUES (1);",
                                       encoding="utf-8")
    (dossier / "002_b.sql").write_text("CREATE TABLE b (a_id INTEGER REFERENCES a (id));\nINSERT INTO b VALUES (1);",
                                       encoding="utf-8")
    (dossier / "003_casse.sql").write_text("DELETE FROM a;", encoding="utf-8")
    conn = sqlite3.connect(tmp_path / "b.sqlite3", isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(module_base.CleEtrangereCassee, match="003_casse"):
        module_base.migrer(conn, dossier)
    assert conn.execute("SELECT COUNT(*) FROM a").fetchone()[0] == 1  # 003 annulée en entier
    assert [r[0] for r in conn.execute("SELECT numero FROM migration")] == [1, 2]
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


# --- les classes et les matières, d'accord partout ------------------------------------------------

def test_les_classes_sont_les_memes_partout():
    schema = registre.charger("qcm").schema["properties"]
    attendues = ["CP", "CE1", "CE2", "6e", "5e", "4e", "3e"]
    assert list(programmes.NIVEAUX) == list(classes.NIVEAUX) == schema["niveau"]["enum"] == attendues
    assert list(typing.get_args(api.NouvelleClasse.model_fields["niveau"].annotation)) == attendues
    page = (RACINE / "generateur/interface/statique/index.html").read_text(encoding="utf-8")
    assert all(f'<option value="{n}"' in page for n in attendues)
    assert classes.CLASSES_AUX_IMAGES == ("CP", "CE1", "CE2", "6e")
    eleve = (RACINE / "generateur/classe/statique/eleve.js").read_text(encoding="utf-8")
    assert 'const ENFANT = ["CP", "CE1", "CE2", "6e"]' in eleve


def test_chaque_matiere_a_son_nom_partout():
    matieres = registre.charger("qcm").schema["properties"]["matiere"]["enum"]
    assert {"questionner-le-monde", "emc", "arts-plastiques", "education-musicale"} <= set(matieres)
    for chemin in ("generateur/interface/statique/app.js", "generateur/classe/statique/eleve.js",
                   "generateur/types/qcm/gabarit.html"):
        texte = (RACINE / chemin).read_text(encoding="utf-8")
        manquantes = [m for m in matieres if f'"{m}":' not in texte and f"{m}:" not in texte]
        assert manquantes == [], f"{chemin} : pas de nom pour {manquantes}"
    assert set(analyse.MOTS_DES_MATIERES) == set(analyse.NOMS_DES_MATIERES) == set(matieres)


def test_un_exercice_de_cp_se_rend_en_style_enfant_avec_le_nom_de_sa_matiere():
    instance = json.loads(json.dumps(registre.charger("qcm").exemple))
    instance.update(matiere="questionner-le-monde", niveau="CP")
    html = rendu.rendre(instance, "qcm")
    assert '<body data-style="enfant">' in html and "Questionner le monde" in html


@pytest.mark.parametrize("niveau", ["CP", "CE1", "CE2"])
def test_un_exercice_du_cycle_2_entre_dans_la_banque(tmp_path, monkeypatch, niveau):
    """Essai du 10/11 : « identifiant d'exercice invalide : 'qcm-les-saisons-CP-…' » après la génération ; un
    identifiant n'a que des minuscules."""
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    instance = json.loads(json.dumps(registre.charger("qcm").exemple))
    instance.update(matiere="questionner-le-monde", niveau=niveau, notion="Les saisons")
    ident = generation.identifiant("qcm", instance)
    assert re.fullmatch(rf"qcm-les-saisons-{niveau.lower()}-\d{{8}}-\d{{6}}", ident)
    instance["meta"] = {"id": ident, "statut": banque.GENERE}
    banque.ecrire(instance)
    assert banque.charger(ident)["niveau"] == niveau


# --- le référentiel ---------------------------------------------------------------------------------

def test_cycle_segment_et_ordre_des_classes():
    assert [programmes.cycle(n) for n in ("CP", "CE1", "CE2", "6e", "5e", "3e", "CM1", None)] == \
        [2, 2, 2, 3, 4, 4, None, None]
    assert [programmes.segment(n) for n in ("CP", "CE1", "6e")] == ["cp", "ce1", "6e"]
    assert programmes.rang("CP") < programmes.rang("CE2") < programmes.rang("6e") < programmes.rang("3e")
    assert programmes.ID_ATTENDU.match("francais.ce1.conjugaison.03")
    assert programmes.ID_THEME.match("francais.cp.lecture")
    assert not programmes.ID_ATTENDU.match("francais.CE1.conjugaison.03")  # en minuscules dans un identifiant
    assert not programmes.ID_ATTENDU.match("francais.cm1.conjugaison.03")
    assert programmes.verifier() == []


# --- la phrase de l'enseignant ------------------------------------------------------------------------

@pytest.mark.parametrize("phrase, matiere, niveau", [
    ("un QCM de conjugaison au présent pour des CE1", "francais", "CE1"),
    ("les saisons au CP", "questionner-le-monde", "CP"),
    # au cycle 2, les sciences, l'histoire et la géographie sont « questionner le monde »
    ("les états de l'eau pour des CE2", "questionner-le-monde", "CE2"),
    ("QCM sur les animaux en CP", "questionner-le-monde", "CP"),
    ("un quiz sur Louis XIV en cours élémentaire 2e année", "questionner-le-monde", "CE2"),
    # … mais pas au collège
    ("les états de l'eau en 5e", "physique-chimie", "5e"),
    ("les couleurs primaires en arts plastiques, CE1", "arts-plastiques", "CE1"),
    ("les instruments de musique pour des CP", "education-musicale", "CP"),
    ("la laïcité en 4e", "emc", "4e"),
    ("les symboles de la République en EMC pour des CE2", "emc", "CE2"),
])
def test_la_classe_et_la_matiere_du_cycle_2(phrase, matiere, niveau):
    requete = analyse.analyser(phrase).requete
    assert (requete["matiere"], requete["niveau"]) == (matiere, niveau)


def test_la_matiere_de_la_classe():
    permises = registre.charger("qcm").schema["properties"]["matiere"]["enum"]
    assert analyse.matiere_de_la_classe("svt", "CE1", permises) == "questionner-le-monde"
    assert analyse.matiere_de_la_classe("svt", "6e", permises) == "svt"
    assert analyse.matiere_de_la_classe("francais", "CP", permises) == "francais"
    assert analyse.matiere_de_la_classe("svt", None, permises) == "svt"
    assert analyse.matiere_de_la_classe("svt", "CE1", ["svt"]) == "svt"  # matière absente du type : rien ne change


# --- étape 0.2 : le générateur procédural rangé par matière -------------------------------------------

def test_les_generateurs_ranges_par_matiere():
    from generateur import procedural
    paquets = procedural.matieres()
    assert list(paquets) == ["maths"]
    noms = [m.NOM for p in paquets.values() for m in p.generateurs()]
    assert len(noms) == len(set(noms)) == len(procedural.notions())  # un nom n'est jamais pris deux fois
    for matiere, paquet in paquets.items():
        for module in paquet.generateurs():
            assert module.__name__ == f"generateur.procedural.{matiere}.{module.NOM}"
            assert module.MATIERE == matiere and module.NIVEAU in module.NIVEAUX
            assert set(module.NIVEAUX) <= set(programmes.NIVEAUX)
    # les maths du collège seulement (celles du cycle 2 ne sont pas couvertes)
    assert {n for m in paquets["maths"].generateurs() for n in m.NIVEAUX} == {"6e", "5e", "4e", "3e"}


@pytest.mark.parametrize("demande, generateur", [
    ({"notion": "le calcul mental", "niveau": "6e"}, "calcul_mental"),
    ({"notion": "le calcul mental", "niveau": "CP"}, None),        # pas le calcul mental de 6e pour des CP
    ({"notion": "le calcul mental", "matiere": "maths", "niveau": "CE2"}, None),
    ({"notion": "le théorème de Pythagore", "matiere": "maths", "niveau": "3e"}, "pythagore"),
    ({"notion": "les fractions", "matiere": "francais"}, None),    # aucun générateur de français, pour l'instant
    ({"attendu": "maths.6e.fractions", "matiere": "maths", "niveau": "CP"}, None),
])
def test_l_aiguillage_suit_la_matiere_et_la_classe(demande, generateur):
    from generateur import procedural
    assert procedural.aiguiller(demande) == generateur


def test_un_generateur_d_une_autre_matiere_est_aiguille_et_assemble(monkeypatch):
    """Ce que l'étape 0.2 prépare : un générateur de français (ici, un faux) trouvé par l'aiguillage et assemblé avec
    sa matière, sans rien changer aux maths."""
    import random
    from types import SimpleNamespace

    from generateur import procedural

    def accord(rng):
        return procedural.Squelette(genre="conjugaison_essai.accord", enonce="Ils (chanter) au présent : ils …",
                                    reponse="chantent", distracteurs=("chante", "chantes", "chantons"),
                                    explication="Avec « ils », la terminaison est -ent.", cle=("accord",))
    faux = SimpleNamespace(NOM="conjugaison_essai", TITRE="Conjugaison", NOTION="conjugaison", MATIERE="francais",
                           NIVEAU="CE1", NIVEAUX=("CE1", "CE2"), MOTS_CLES=("conjugaison",), GENRES=(accord,),
                           ATTENDUS={})
    francais = SimpleNamespace(MATIERE="francais", AUTRES_NOTIONS=re.compile(r"\bhomophone"),
                               generateurs=lambda: (faux,))
    vraies = procedural.matieres()
    monkeypatch.setattr(procedural, "matieres", lambda: {**vraies, "francais": francais})

    assert procedural.aiguiller({"notion": "la conjugaison", "matiere": "francais", "niveau": "CE1"}) == "conjugaison_essai"
    assert procedural.aiguiller({"notion": "la conjugaison", "niveau": "CE2"}) == "conjugaison_essai"
    assert procedural.aiguiller({"notion": "la conjugaison", "niveau": "CP"}) is None            # pas sa classe
    assert procedural.aiguiller({"notion": "la conjugaison et les homophones", "niveau": "CE1"}) is None  # autre notion
    assert procedural.aiguiller({"notion": "les fractions", "niveau": "6e"}) == "fractions"      # les maths, intactes
    rng = random.Random(1)
    squelettes = procedural.tirer("conjugaison_essai", 1, rng)
    exercice = procedural.assembler("conjugaison_essai", "CE1", squelettes, [s.enonce for s in squelettes], rng)
    assert (exercice["matiere"], exercice["niveau"], exercice["titre"]) == ("francais", "CE1", "Conjugaison")
    question = exercice["questions"][0]
    assert question["propositions"][question["index_correct"]] == "chantent"


# --- étape 0.4 : le programme de français du cycle 2 ------------------------------------------------

@pytest.mark.parametrize("phrase, attendu", [
    ("un QCM de conjugaison au présent pour des CE1", "francais.ce1.orthographe-grammaticale.04"),
    ("les synonymes et les antonymes au CP", "francais.cp.relations-mots.03"),
    ("un QCM sur le masculin et le féminin pour des CP", "francais.cp.orthographe-grammaticale.01"),
    ("l'ordre alphabétique au CP", "francais.cp.vocabulaire.03"),
])
def test_l_attendu_du_cycle_2_est_propose(phrase, attendu):
    """La phrase de l'enseignant → l'objectif officiel du CP au CE2, proposé à vérifier (comme en E2)."""
    analyse_ = analyse.analyser(phrase)
    assert analyse_.requete["attendu"] == attendu and analyse_.sources["attendu"] == "devine"
    assert programmes.attendu(attendu).qcm
