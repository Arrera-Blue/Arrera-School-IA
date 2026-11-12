"""Lot 1, étape 1.3 : le générateur de la phrase du CP au CE2 (generateur/procedural/francais/phrase.py ;
docs/Generateur-Procedural/lot-1-francais.md §5) — la table (le monde fermé, mot par mot), chaque genre juste par
construction, ce que chaque classe voit, l'aiguillage, un exercice de bout en bout."""

import random
import re
import shutil

import pytest

from generateur import procedural
from generateur.moteur import config, generation, registre
from generateur.moteur.validation.n2_schema import valider
from generateur.procedural import tables
from generateur.procedural.francais import phrase as ph

TIRAGES = 300
NATURES = {"determinant", "nom", "nom_propre", "adjectif", "verbe", "pronom", "adverbe", "preposition", "negation",
           "interrogatif", "exclamatif"}


def lignes():
    return tables.charger("francais", "phrases").lignes


def nombre_de_mots(texte: str) -> int:
    return len([t for t in texte.split() if re.search(r"\w", t)])


@pytest.fixture
def relues(tmp_path, monkeypatch):
    copie = tmp_path / "donnees"
    shutil.copytree(tables.DOSSIER, copie)
    monkeypatch.setattr(tables, "DOSSIER", copie)
    for matiere, nom in tables.lister():
        tables.relire(matiere, nom, "Essai")
    return copie


@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    return tmp_path


# --- la table ---------------------------------------------------------------------------------------

def test_la_table_des_phrases_est_coherente():
    assert len(lignes()) >= 60
    for p in lignes():
        jetons = p["mots"].split()
        assert jetons[-1] == p["phrase"][-1] and jetons[-1] in ".?!"            # le signe final
        mots = ph.mots(p)
        assert {n for _, n in mots} <= NATURES, p["phrase"]
        # la phrase s'écrit avec ses mots : rien d'oublié, rien en plus
        assert re.sub(r"[ .?!]", "", p["phrase"]) == "".join(m for m, _ in mots), p["phrase"]
        assert (p["type"] == "interrogative") == p["phrase"].endswith("?")
        assert (p["exclamative"] == "oui") == p["phrase"].endswith("!")
        assert (p["negative"] == "oui") == any(n == "negation" for _, n in mots)
        if p["type"] == "imperative":                                         # pas de sujet devant le verbe
            assert next(n for _, n in mots if n != "negation") == "verbe"
        if p["signe_impose"] == "oui":                                        # un mot impose le signe
            assert mots[0][1] in ("interrogatif", "exclamatif", "determinant") and p["phrase"][-1] in "?!"
        if any(n == "nom_propre" for _, n in mots):                           # pas avant le CE1
            assert p["depuis"] != "CP"
        if any(n == "adverbe" for _, n in mots):                              # l'adverbe : au CE2
            assert p["depuis"] == "CE2"
    # aucun prénom : seulement des villes et des fleuves
    assert {m for p in lignes() for m, n in ph.mots(p) if n == "nom_propre"} <= {"Paris", "Lyon", "Loire"}


# --- chaque genre, juste par construction -------------------------------------------------------------

@pytest.mark.parametrize("genre, niveau", [(g, n) for g in ph.GENRES for n in ph.CLASSES_DU_GENRE[g.__name__]],
                         ids=lambda x: getattr(x, "__name__", x))
def test_chaque_genre_est_juste_par_construction(genre, niveau):
    par_phrase = {p["phrase"]: p for p in lignes()}
    rng, vus = random.Random(2026), set()
    for _ in range(TIRAGES):
        s = procedural.tirer_une(genre, rng, set(), niveau)
        nom = s.cle[0]
        vus.add(s.cle)
        assert nombre_de_mots(s.enonce) <= 12, s.enonce
        assert len(set(s.distracteurs)) == len(s.distracteurs) >= 2 and s.reponse not in s.distracteurs
        if nom == "type_de_phrase":
            p = par_phrase[s.cle[1]]
            assert p["exclamative"] == "non" and s.reponse == ph.TYPES[p["type"]]
        elif nom == "forme":
            bonne, fausses = par_phrase[s.reponse], [par_phrase[d] for d in s.distracteurs]
            if "exclamati" in s.enonce or "émotion" in s.enonce:
                assert bonne["exclamative"] == "oui" and all(f["exclamative"] == "non" for f in fausses)
            elif "affirmative" in s.enonce or "n'est pas négative" in s.enonce:
                assert bonne["negative"] == "non" and all(f["negative"] == "oui" for f in fausses)
            else:
                assert bonne["negative"] == "oui" and all(f["negative"] == "non" for f in fausses)
        elif nom == "nature":
            p, mot = par_phrase[s.cle[1]], s.cle[2]
            natures = [n for m, n in ph.mots(p) if m == mot]
            assert len(natures) == 1 and natures[0] in ph.LIBELLES[niveau]   # au programme de la classe, une fois
            assert s.reponse == ph.LIBELLES[niveau][natures[0]]
            assert set(s.distracteurs) <= set(ph.LIBELLES[niveau].values())
            assert s.explication.endswith(f"c'est {s.reponse}.")
        elif nom == "ponctuation":
            p = par_phrase[s.cle[1]]
            assert p["signe_impose"] == "oui" and s.reponse == ph.SIGNES[p["phrase"][-1]]
        if niveau == "CP":
            assert not any(x in s.reponse for x in ("nom propre", "adverbe", "nom commun"))
    assert len(vus) >= 12


def test_les_classes_de_mots_suivent_le_programme():
    assert set(ph.LIBELLES["CP"]) == {"determinant", "nom", "adjectif", "verbe", "pronom"}
    assert set(ph.LIBELLES["CE1"]) == set(ph.LIBELLES["CP"]) | {"nom_propre"}
    assert set(ph.LIBELLES["CE2"]) == set(ph.LIBELLES["CE1"]) | {"adverbe"}


# --- l'aiguillage, et un exercice de bout en bout ------------------------------------------------------

@pytest.mark.parametrize("demande, generateur", [
    ({"notion": "les types de phrases", "matiere": "francais", "niveau": "CE1"}, "phrase"),
    ({"demande_enseignant": "la nature des mots pour des CP"}, "phrase"),
    ({"notion": "la ponctuation", "matiere": "francais", "niveau": "CE2"}, "phrase"),
    ({"notion": "la phrase à la forme négative", "matiere": "francais", "niveau": "CE1"}, "phrase"),
    ({"attendu": "francais.ce2.phrase-simple.05", "matiere": "francais", "niveau": "CE2"}, "phrase"),
    ({"attendu": "francais.cp.phrase-simple.05", "matiere": "francais", "niveau": "CP"}, "phrase"),
    ({"notion": "les accords", "matiere": "francais", "niveau": "CE1"}, "accords"),
    ({"notion": "la conjugaison", "matiere": "francais", "niveau": "CE1"}, "conjugaison"),
    ({"notion": "le discours rapporté", "matiere": "francais", "niveau": "CE2"}, None),
])
def test_l_aiguillage(relues, demande, generateur):
    assert procedural.aiguiller(demande) == generateur


def test_jamais_propose_tant_que_sa_table_n_est_pas_relue(relues):
    (relues / "relectures.yaml").write_text("{}\n", encoding="utf-8")
    assert procedural.aiguiller({"notion": "les types de phrases", "matiere": "francais", "niveau": "CE1"}) is None


@pytest.mark.parametrize("niveau", ["CP", "CE1", "CE2"])
def test_un_exercice_genere_de_bout_en_bout(relues, dossiers, niveau):
    demande = {"type": "qcm", "matiere": "francais", "niveau": niveau, "notion": "les types de phrases",
               "nb_questions": 12}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=3)
    valider(instance, registre.charger("qcm").schema, meta_autorise=True)
    meta = instance["meta"]
    assert (meta["origine"], meta["generateur"]) == ("procedural", "phrase") and meta["validation"]["n3"]
    assert meta["tables"] == {"francais/phrases": tables.charger("francais", "phrases").empreinte}
    assert len(instance["questions"]) == 12
    assert {q["genre"].split(".")[1] for q in meta["questions"]} <= {
        g for g, classes in ph.CLASSES_DU_GENRE.items() if niveau in classes}
