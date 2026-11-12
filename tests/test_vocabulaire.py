"""Lot 1, étape 1.4 : le générateur du vocabulaire du CP au CE2 (generateur/procedural/francais/vocabulaire.py ;
docs/Generateur-Procedural/lot-1-francais.md §6) — les tables, chaque genre juste par construction, l'aiguillage, un
exercice de bout en bout."""

import random
import re
import shutil
from collections import Counter

import pytest

from generateur import procedural
from generateur.moteur import config, generation, registre
from generateur.moteur.validation.n2_schema import valider
from generateur.procedural import tables
from generateur.procedural.francais import vocabulaire as v

TIRAGES = 300


def table(nom):
    return tables.charger("francais", nom).lignes


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


# --- les tables -------------------------------------------------------------------------------------

def test_les_tables_sont_coherentes():
    contraires = table("contraires")
    assert all(n == 1 for n in Counter(m for l in contraires for m in (l["mot"], l["contraire"])).values())
    for l in table("prefixes"):
        assert l["prefixe"][:-1] + l["mot"] == l["contraire"] and len(l["pieges"].split()) == 3
        assert l["prefixe"] not in l["pieges"].split()
    for l in table("familles"):
        assert len(set(l["pieges"].split()) | {l["mot"], l["parent"]}) == 5
    for l in table("lettres_muettes"):
        assert l["mot"].endswith(l["lettre"]) and l["famille"].startswith(l["mot"])
        assert l["lettre"] not in l["pieges"].split() and len(l["pieges"].split()) == 3
    assert all(n == 1 for n in Counter(l["mot"] for l in table("categories")).values())
    for t in table("niveaux_de_langue"):
        assert len({t["familier"], t["courant"], t["soutenu"]}) == 3


def test_la_cle_alphabetique():
    assert v.cle_alphabetique("École") == "ecole" and v.cle_alphabetique("sœur") == "soeur"
    assert sorted(["gâteau", "garçon", "gomme"], key=v.cle_alphabetique) == ["garçon", "gâteau", "gomme"]


# --- chaque genre, juste par construction -------------------------------------------------------------

@pytest.mark.parametrize("genre, niveau", [(g, n) for g in v.GENRES for n in v.CLASSES_DU_GENRE[g.__name__]],
                         ids=lambda x: getattr(x, "__name__", x))
def test_chaque_genre_est_juste_par_construction(genre, niveau):
    contraires = {m: (l, autre) for l in table("contraires")
                  for m, autre in ((l["mot"], l["contraire"]), (l["contraire"], l["mot"]))}
    categorie_de = {l["mot"]: l for l in table("categories")}
    registre_de = {t[r]: r for t in table("niveaux_de_langue") for r in v.REGISTRES}
    rng, vus = random.Random(2026), set()
    for _ in range(TIRAGES):
        s = procedural.tirer_une(genre, rng, set(), niveau)
        nom = s.cle[0]
        vus.add(s.cle)
        assert nombre_de_mots(s.enonce) <= 12, s.enonce
        assert len(set(s.distracteurs)) == len(s.distracteurs) >= 2 and s.reponse not in s.distracteurs
        options = [s.reponse, *s.distracteurs]
        if nom == "ordre_alphabetique":
            assert all(o in s.enonce for o in options)  # les mots dans l'énoncé : jamais deux fois le même
            ranges = sorted(options, key=v.cle_alphabetique)
            assert s.reponse == (ranges[0] if "premier" in s.enonce else ranges[-1])
            initiales = {v.cle_alphabetique(o)[0] for o in options}
            assert len(initiales) == (4 if niveau == "CP" else 1)
        elif nom == "contraire":
            mot = re.search(r"« (.+) »", s.enonce)[1]
            ligne, bon = contraires[mot]
            assert s.reponse == bon
            for d in s.distracteurs:  # même classe, autre champ de sens : jamais un autre contraire possible
                assert contraires[d][0]["classe"] == ligne["classe"] and contraires[d][0]["sens"] != ligne["sens"]
        elif nom == "contraire_prefixe":
            l = next(x for x in table("prefixes") if x["mot"] == s.cle[1])
            assert s.reponse == l["prefixe"] and set(s.distracteurs) == set(l["pieges"].split())
        elif nom == "famille":
            l = next(x for x in table("familles") if x["mot"] == s.cle[1])
            assert s.reponse == l["parent"] and set(s.distracteurs) == set(l["pieges"].split())
        elif nom == "generique":
            if s.enonce.startswith("Lequel"):
                categorie = re.search(r"est un (.+) \?", s.enonce)[1]
                assert categorie_de[s.reponse]["categorie"] == categorie
                assert all(categorie_de[d]["categorie"] != categorie for d in s.distracteurs)
            else:
                exemples = [m.strip().lower() for m in s.enonce.split(":")[0].split(",")]
                assert {categorie_de[e]["pluriel"] for e in exemples} == {s.reponse}
        elif nom == "niveau_de_langue":
            trios = table("niveaux_de_langue")
            demande = "courant" if s.enonce.startswith("En classe") else next(r for r in v.REGISTRES if r in s.enonce)
            reference = re.search(r"« (.+?) »", s.enonce)[1]
            trio = next(t for t in trios if reference in (t["familier"], t["courant"]))
            assert s.reponse == trio[demande] and registre_de[s.reponse] == demande
            for d in s.distracteurs:  # jamais le bon sens et le bon niveau à la fois
                assert not (d in trio.values() and registre_de[d] == demande)
                assert d != reference
            if niveau == "CP":
                assert demande in ("familier", "courant") and "soutenu" not in {registre_de[o] for o in options}
        elif nom == "lettre_muette":
            l = next(x for x in table("lettres_muettes") if x["mot"] == s.cle[1])
            assert s.reponse == l["lettre"] and set(s.distracteurs) == set(l["pieges"].split())
    assert len(vus) >= 8


# --- l'aiguillage, et un exercice de bout en bout ------------------------------------------------------

@pytest.mark.parametrize("demande, generateur", [
    ({"notion": "l'ordre alphabétique", "matiere": "francais", "niveau": "CP"}, "vocabulaire"),
    ({"demande_enseignant": "les contraires pour des CP"}, "vocabulaire"),
    ({"notion": "les familles de mots", "matiere": "francais", "niveau": "CE1"}, "vocabulaire"),
    ({"notion": "les niveaux de langue", "matiere": "francais", "niveau": "CE2"}, "vocabulaire"),
    ({"attendu": "francais.cp.orthographe-lexicale.04", "matiere": "francais", "niveau": "CP"}, "vocabulaire"),
    ({"attendu": "francais.ce1.relations-mots.04", "matiere": "francais", "niveau": "CE1"}, "vocabulaire"),
    ({"notion": "les synonymes", "matiere": "francais", "niveau": "CE1"}, None),        # décision 6
    ({"notion": "le sens propre et le sens figuré", "matiere": "francais", "niveau": "CE2"}, None),
    ({"notion": "les types de phrases", "matiere": "francais", "niveau": "CE1"}, "phrase"),
    ({"notion": "les accords", "matiere": "francais", "niveau": "CE1"}, "accords"),
    ({"notion": "la conjugaison", "matiere": "francais", "niveau": "CE1"}, "conjugaison"),
])
def test_l_aiguillage(relues, demande, generateur):
    assert procedural.aiguiller(demande) == generateur


def test_jamais_propose_tant_que_ses_tables_ne_sont_pas_relues(relues):
    (relues / "relectures.yaml").write_text("{}\n", encoding="utf-8")
    assert procedural.aiguiller({"notion": "les contraires", "matiere": "francais", "niveau": "CP"}) is None


@pytest.mark.parametrize("niveau", ["CP", "CE1", "CE2"])
def test_un_exercice_genere_de_bout_en_bout(relues, dossiers, niveau):
    demande = {"type": "qcm", "matiere": "francais", "niveau": niveau, "notion": "le vocabulaire", "nb_questions": 12}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=9)
    valider(instance, registre.charger("qcm").schema, meta_autorise=True)
    meta = instance["meta"]
    assert (meta["origine"], meta["generateur"]) == ("procedural", "vocabulaire") and meta["validation"]["n3"]
    assert set(meta["tables"]) == {f"francais/{n}" for n in v.TABLES}
    assert len(instance["questions"]) == 12
    assert {q["genre"].split(".")[1] for q in meta["questions"]} <= {
        g for g, classes in v.CLASSES_DU_GENRE.items() if niveau in classes}


@pytest.mark.parametrize("attendu, niveau", [("francais.cp.reemployer.03", "CP"), ("francais.cp.vocabulaire.03", "CP"),
                                             ("francais.ce2.relations-mots.03", "CE2")])
def test_un_objectif_seul_donne_assez_de_questions_differentes(relues, dossiers, attendu, niveau):
    """Un enseignant qui vise un seul objectif (« les niveaux de langue », CP) : 10 questions, toutes différentes
    (avec 3 formulations seulement, le tirage s'arrêtait à la 4e)."""
    demande = {"type": "qcm", "matiere": "francais", "niveau": niveau, "notion": "le vocabulaire", "nb_questions": 10,
               "attendu": attendu}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=4)
    assert len({q["enonce"] for q in instance["questions"]}) == 10

