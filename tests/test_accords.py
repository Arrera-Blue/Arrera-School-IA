"""Lot 1, étape 1.2 : le générateur des accords du CP au CE2 (generateur/procedural/francais/accords.py ;
docs/Generateur-Procedural/lot-1-francais.md §4) — les tables, chaque genre juste par construction sur des centaines
de tirages, ce que chaque classe voit, l'aiguillage (seulement si les tables sont relues), un exercice de bout en
bout."""

import random
import shutil
import unicodedata

import pytest

from generateur import procedural
from generateur.moteur import config, generation, registre
from generateur.moteur.validation.n2_schema import valider
from generateur.procedural import tables
from generateur.procedural.francais import accords as a
from generateur.procedural.francais import conjugaison

TIRAGES = 300
H_ASPIRE = {"hibou"}  # « le hibou » : pas d'élision


def table(nom):
    return tables.charger("francais", nom)


@pytest.fixture
def relues(tmp_path, monkeypatch):
    copie = tmp_path / "donnees"
    shutil.copytree(tables.DOSSIER, copie)
    monkeypatch.setattr(tables, "DOSSIER", copie)
    for nom in a.TABLES:
        tables.relire("francais", nom, "Essai")
    return copie


@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    return tmp_path


# --- les tables -------------------------------------------------------------------------------------

def test_les_tables_sont_coherentes():
    noms = {n["nom"]: n for n in table("noms").lignes}
    assert len(noms) >= 100
    for n in noms.values():  # l'article défini : l' devant une voyelle ou un h muet, jamais devant un h aspiré
        initiale = unicodedata.normalize("NFD", n["nom"][0])[0]  # « â » → « a »
        voyelle = initiale in "aeiouyh" and n["nom"] not in H_ASPIRE
        assert (n["article"] == "l'") == voyelle, n["nom"]
        assert n["article"] in ("le", "l'") if n["genre"] == "m" else n["article"] in ("la", "l'")
    for adj in table("adjectifs").lignes:  # quatre formes toutes différentes : une seule bonne réponse
        assert len({adj["ms"], adj["fs"], adj["mp"], adj["fp"]}) == 4
        assert adj["pour"] == "tout" or set(adj["pour"].split()) <= {"personne", "animal", "objet", "lieu", "aliment",
                                                                     "nature"}
    irreguliers = {l["singulier"]: l for l in table("pluriels_irreguliers").lignes}
    for s, l in irreguliers.items():
        assert len({l["singulier"], l["pluriel"], l["erreur"]}) == 3
        if s in noms:  # les deux tables d'accord, et le pluriel irrégulier au CE2
            assert noms[s]["pluriel"] == l["pluriel"] and noms[s]["depuis"] == "CE2"
    for n in noms.values():
        if n["pluriel"] not in (n["nom"] + "s", n["nom"]):
            assert n["nom"] in irreguliers, n["nom"]
    for l in table("feminins").lignes:
        assert len({l["masculin"], l["feminin"], l["erreur"]}) == 3


# --- chaque genre, juste par construction -------------------------------------------------------------

@pytest.mark.parametrize("genre, niveau", [(g, n) for g in a.GENRES for n in a.CLASSES_DU_GENRE[g.__name__]],
                         ids=lambda x: getattr(x, "__name__", x))
def test_chaque_genre_est_juste_par_construction(genre, niveau):
    noms = {n["nom"]: n for n in table("noms").lignes}
    par_pluriel = {n["pluriel"]: n for n in noms.values()}
    rng, deja, vus = random.Random(2026), set(), set()
    for _ in range(TIRAGES):
        s = procedural.tirer_une(genre, rng, set(), niveau)
        nom = s.cle[0]
        vus.add(s.cle)
        assert len(s.enonce.split()) <= 12, s.enonce
        assert len(set(s.distracteurs)) == len(s.distracteurs) >= 2 and s.reponse not in s.distracteurs
        if nom == "determinant":
            forme = s.cle[1]
            if forme in noms:
                assert s.reponse == noms[forme]["article"] and noms[forme]["pluriel"] != forme
            else:
                assert s.reponse == "les" and forme in par_pluriel
            assert set(s.distracteurs) == {"le", "la", "l'", "les"} - {s.reponse}
        elif nom == "masculin_feminin":
            cherche = "f" if "féminin" in s.enonce else "m"
            assert noms[s.reponse]["genre"] == cherche
            assert all(noms[d]["genre"] != cherche for d in s.distracteurs)
        elif nom == "singulier_pluriel":
            au_pluriel = s.cle[1]
            assert s.reponse.split()[0] in (("les", "des") if au_pluriel else ("le", "la", "un", "une")) \
                or (not au_pluriel and s.reponse.startswith("l'"))
            for d in s.distracteurs:
                assert (d.split()[0] in ("les", "des")) != au_pluriel
        elif nom == "accord_gn":
            ms, n, nombre = s.cle[1:]
            adj = next(x for x in table("adjectifs").lignes if x["ms"] == ms)
            assert s.reponse == adj[a.FORME[(noms[n]["genre"], nombre)]]
            assert set(s.distracteurs) == {adj[f] for f in ("ms", "fs", "mp", "fp")} - {s.reponse}
            assert adj["pour"] == "tout" or noms[n]["sorte"] in adj["pour"].split()
            if niveau == "CP":
                assert a._regulier(adj)
        elif nom == "pluriel_irregulier":
            l = next(x for x in table("pluriels_irreguliers").lignes if x["singulier"] == s.cle[1])
            assert s.reponse == l["pluriel"] and set(s.distracteurs) == {l["erreur"], l["singulier"]}
        elif nom == "feminin_irregulier":
            l = next(x for x in table("feminins").lignes if x["masculin"] == s.cle[1])
            assert s.reponse == l["feminin"] and set(s.distracteurs) == {l["erreur"], l["masculin"]}
        elif nom == "sujet_verbe":
            n, pluriel, infinitif, temps = s.cle[1:]
            personne = "ils" if pluriel else "il"
            conj = table("conjugaisons")
            assert s.reponse == conj.filtrer(infinitif=infinitif, temps=temps, personne=personne)[0]["forme"]
            assert set(s.distracteurs) <= {l["forme"] for l in conj.filtrer(infinitif=infinitif, temps=temps)}
            assert noms[n]["sorte"] in a.VERBES and infinitif in a.VERBES[noms[n]["sorte"]]
            assert not (temps == "passe_compose" and infinitif == "arriver")
            if niveau == "CP":
                assert temps == "present"
            assert f"« {a.PRONOM[(noms[n]['genre'], pluriel)]} »" in s.explication  # elles, pour les poules
        if niveau == "CP" and nom not in ("pluriel_irregulier", "feminin_irregulier"):  # pas de pluriel irrégulier
            assert not any(m in s.enonce + s.reponse for m in ("chevaux", "oiseaux", "bateaux", "animaux"))
    assert len(vus) >= (8 if nom in ("masculin_feminin", "singulier_pluriel") else 15)  # des questions variées


def test_les_noms_suivent_la_classe():
    assert all(n["depuis"] == "CP" for n in a.noms("CP"))
    assert {"cheval", "oiseau", "bijou"} <= {n["nom"] for n in a.noms("CE2")}
    assert not {"cheval", "oiseau", "bijou"} & {n["nom"] for n in a.noms("CE1")}


# --- l'aiguillage, et un exercice de bout en bout ------------------------------------------------------

@pytest.mark.parametrize("demande, generateur", [
    ({"notion": "les accords dans le groupe nominal", "matiere": "francais", "niveau": "CE1"}, "accords"),
    ({"demande_enseignant": "le masculin et le féminin pour des CP"}, "accords"),
    ({"notion": "accorder le verbe avec le sujet", "matiere": "francais", "niveau": "CE2"}, "accords"),
    ({"attendu": "francais.cp.orthographe-grammaticale.04", "matiere": "francais", "niveau": "CP"}, "accords"),
    ({"attendu": "francais.ce2.orthographe-grammaticale.01", "matiere": "francais", "niveau": "CE2"}, "accords"),
    ({"attendu": "francais.ce1.orthographe-grammaticale.04", "matiere": "francais", "niveau": "CE1"}, "conjugaison"),
    ({"notion": "la conjugaison au futur", "matiere": "francais", "niveau": "CE1"}, "conjugaison"),
    ({"notion": "l'accord du participe passé", "matiere": "francais", "niveau": "CE2"}, None),
    ({"notion": "la conjugaison et les accords", "matiere": "francais", "niveau": "CE1"}, None),  # deux générateurs
])
def test_l_aiguillage(relues, demande, generateur):
    assert procedural.aiguiller(demande) == generateur


def test_jamais_propose_tant_que_ses_tables_ne_sont_pas_relues(tmp_path, monkeypatch):
    copie = tmp_path / "donnees"
    shutil.copytree(tables.DOSSIER, copie)
    monkeypatch.setattr(tables, "DOSSIER", copie)
    (copie / "relectures.yaml").write_text("{}\n", encoding="utf-8")
    for nom in conjugaison.TABLES:  # la conjugaison relue, les accords non
        tables.relire("francais", nom, "Essai")
    assert procedural.aiguiller({"notion": "les accords", "matiere": "francais", "niveau": "CE1"}) is None
    assert procedural.aiguiller({"notion": "la conjugaison", "matiere": "francais", "niveau": "CE1"}) == "conjugaison"


@pytest.mark.parametrize("niveau", ["CP", "CE1", "CE2"])
def test_un_exercice_genere_de_bout_en_bout(relues, dossiers, niveau):
    demande = {"type": "qcm", "matiere": "francais", "niveau": niveau, "notion": "les accords", "nb_questions": 12}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=5)
    valider(instance, registre.charger("qcm").schema, meta_autorise=True)  # N2
    meta = instance["meta"]
    assert (meta["origine"], meta["generateur"], meta["fournisseur"]) == ("procedural", "accords", "procedural")
    assert meta["validation"]["n3"] and not meta.get("appels")
    assert set(meta["tables"]) == {f"francais/{n}" for n in a.TABLES}
    assert len(instance["questions"]) == 12
    genres = {q["genre"].split(".")[1] for q in meta["questions"]}
    assert genres <= {g for g, classes in a.CLASSES_DU_GENRE.items() if niveau in classes}
    for q in instance["questions"]:
        assert 3 <= len(q["propositions"]) <= 4
