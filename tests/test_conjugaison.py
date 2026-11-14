"""Lot 1, étape 1.1 : le générateur de conjugaison du CP au CE2 (generateur/procedural/francais/conjugaison.py ;
docs/Generateur-Procedural/lot-1-francais.md §3) — la table, chaque genre juste par construction sur des centaines
de tirages, ce que chaque classe a le droit de voir, l'aiguillage (seulement si les tables sont relues), un exercice
généré de bout en bout."""

import random
import shutil
from collections import Counter

import pytest

from generateur import procedural
from generateur.moteur import config, generation, registre
from generateur.moteur.validation.n2_schema import valider
from generateur.procedural import tables
from generateur.procedural.francais import conjugaison as c

TIRAGES = 300
IRREGULIERS_CE2 = {"faire", "aller", "dire", "venir", "pouvoir", "voir", "vouloir", "prendre"}


@pytest.fixture
def relues(tmp_path, monkeypatch):
    """Les tables du dépôt, copiées et relues : le générateur peut être proposé."""
    copie = tmp_path / "donnees"
    shutil.copytree(tables.DOSSIER, copie)
    monkeypatch.setattr(tables, "DOSSIER", copie)
    for matiere, nom in tables.lister():  # toutes : l'aiguillage ne dépend pas de l'état des relectures du dépôt
        tables.relire(matiere, nom, "Essai")
    return copie


@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    return tmp_path


# --- la table ---------------------------------------------------------------------------------------

def test_la_table_suit_le_programme():
    t = tables.charger("francais", "conjugaisons")
    assert len(t.lignes) == 516 and tables.charger("francais", "terminaisons").cle == ("temps", "personne")
    cp = c.lignes("CP")
    assert {(l["infinitif"], l["temps"]) for l in cp} == {("être", "present"), ("avoir", "present")} and len(cp) == 12
    assert {l["infinitif"] for l in c.lignes("CE1")}.isdisjoint(IRREGULIERS_CE2)
    assert IRREGULIERS_CE2 <= {l["infinitif"] for l in c.lignes("CE2")}
    assert {l["temps"] for l in c.lignes("CE1")} == {"present", "imparfait", "futur", "passe_compose"}
    # au passé composé avec être, seulement il et ils (« je suis allé » / « allée » : deux réponses justes)
    avec_etre = [l for l in t.lignes if l["temps"] == "passe_compose" and l["forme"].split()[0] in ("est", "sont")]
    assert {l["infinitif"] for l in avec_etre} == {"aller", "venir", "arriver"}
    assert {l["personne"] for l in avec_etre} == {"il", "ils"}
    assert {(l["infinitif"], l["forme"]) for l in t.filtrer(personne="nous", temps="present")} >= {
        ("manger", "mangeons"), ("commencer", "commençons"), ("faire", "faisons"), ("être", "sommes")}


def test_le_pronom_et_l_elision():
    assert c.avec_le_pronom("je", "aime") == "j'aime" and c.avec_le_pronom("je", "ai chanté") == "j'ai chanté"
    assert c.avec_le_pronom("je", "suis") == "je suis" and c.avec_le_pronom("nous", "avons") == "nous avons"
    assert c.pronom_du_trou("je", "écoute") == "j'…" and c.pronom_du_trou("tu", "es") == "tu …"


# --- chaque genre, juste par construction -------------------------------------------------------------

def _ligne(infinitif: str, temps: str, pronom: str) -> dict:
    personne = {"elle": "il", "elles": "ils"}.get(pronom, pronom)
    lignes = tables.charger("francais", "conjugaisons").filtrer(infinitif=infinitif, temps=temps, personne=personne)
    assert len(lignes) == 1
    return lignes[0]


@pytest.mark.parametrize("genre, niveau", [(g, n) for g in c.GENRES for n in c.CLASSES_DU_GENRE[g.__name__]],
                         ids=lambda x: getattr(x, "__name__", x))
def test_chaque_genre_est_juste_par_construction(genre, niveau):
    table = tables.charger("francais", "conjugaisons")
    toutes_les_formes = {l["forme"] for l in table.lignes} | {l["infinitif"] for l in table.lignes}
    rng, vus = random.Random(2026), Counter()
    for _ in range(TIRAGES):
        try:
            s = genre(rng, niveau=niveau)
        except procedural.Retirer:
            continue
        nom, infinitif, temps, qui = s.cle
        vus[infinitif] += 1
        assert len(s.enonce.split()) <= 12, s.enonce                         # lisible au cycle 2
        assert len(set(s.distracteurs)) == 3 and s.reponse not in s.distracteurs
        if niveau == "CP":
            assert infinitif in ("être", "avoir") and temps == "present"
        if niveau == "CE1":
            assert infinitif not in IRREGULIERS_CE2
        if nom == "forme":                                                   # relue dans la table, par un autre chemin
            assert s.reponse == _ligne(infinitif, temps, qui)["forme"]
            assert set(s.distracteurs) <= toutes_les_formes                  # jamais une forme inventée
            assert all(d != s.reponse for d in s.distracteurs)
        elif nom == "temps":
            assert s.reponse == c.TEMPS[temps][1] and set(s.distracteurs) == {v[1] for v in c.TEMPS.values()} - {s.reponse}
            # la forme montrée n'est celle d'aucun autre temps, pour cette personne
            forme = _ligne(infinitif, temps, qui)["forme"]
            assert [l["temps"] for l in table.filtrer(infinitif=infinitif, personne=qui) if l["forme"] == forme] == [temps]
        elif nom == "infinitif":
            assert s.reponse == infinitif and set(s.distracteurs) <= toutes_les_formes
            assert infinitif not in s.distracteurs
        elif nom == "terminaison":
            fin = tables.charger("francais", "terminaisons").filtrer(temps=temps, personne=qui)[0]["terminaison"]
            assert s.reponse == fin and _ligne(infinitif, temps, qui)["forme"].endswith(fin[1:])
            assert set(s.distracteurs) <= {t["terminaison"] for t in tables.charger("francais", "terminaisons").lignes}
    assert len(vus) >= (2 if niveau == "CP" else 8)  # des verbes variés


def test_au_cp_seulement_conjuguer_etre_et_avoir():
    rng = random.Random(1)
    squelettes = procedural.tirer("conjugaison", 15, rng, niveau="CP")
    assert {s.genre for s in squelettes} == {"conjugaison.forme"}
    assert {s.cle[1] for s in squelettes} <= {"être", "avoir"} and len({s.cle for s in squelettes}) == 15


# --- l'aiguillage, et un exercice de bout en bout ------------------------------------------------------

@pytest.mark.parametrize("demande, generateur", [
    ({"notion": "la conjugaison au présent", "matiere": "francais", "niveau": "CE1"}, "conjugaison"),
    ({"demande_enseignant": "conjuguer être et avoir au présent pour des CP"}, "conjugaison"),
    ({"attendu": "francais.cp.orthographe-grammaticale.06", "matiere": "francais", "niveau": "CP"}, "conjugaison"),
    ({"attendu": "francais.ce2.orthographe-grammaticale.04", "matiere": "francais", "niveau": "CE2"}, "conjugaison"),
    ({"notion": "la conjugaison et les homophones", "matiere": "francais", "niveau": "CE2"}, None),  # autre notion
    ({"notion": "le passé simple", "matiere": "francais", "niveau": "CE2"}, None),
    ({"notion": "la conjugaison", "matiere": "francais", "niveau": "6e"}, None),                    # pas sa classe
    ({"attendu": "francais.cp.relations-mots.03", "matiere": "francais", "niveau": "CP"}, "vocabulaire"),  # pas le sien
])
def test_l_aiguillage(relues, demande, generateur):
    assert procedural.aiguiller(demande) == generateur


def test_jamais_propose_tant_que_les_tables_ne_sont_pas_relues(relues):
    demande = {"notion": "la conjugaison", "matiere": "francais", "niveau": "CE1"}
    assert procedural.aiguiller(demande) == "conjugaison"
    (relues / "relectures.yaml").write_text("{}\n", encoding="utf-8")  # aucune relecture
    assert procedural.aiguiller(demande) is None


@pytest.mark.parametrize("niveau, attendu", [("CP", None), ("CE1", "francais.ce1.orthographe-grammaticale.04"),
                                             ("CE2", None)])
def test_un_exercice_genere_de_bout_en_bout(relues, dossiers, niveau, attendu):
    demande = {"type": "qcm", "matiere": "francais", "niveau": niveau, "notion": "la conjugaison", "nb_questions": 10,
               **({"attendu": attendu} if attendu else {})}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=7)
    valider(instance, registre.charger("qcm").schema, meta_autorise=True)  # N2
    meta = instance["meta"]
    assert meta["origine"] == "procedural" and meta["generateur"] == "conjugaison" and meta["fournisseur"] == "procedural"
    assert meta["validation"]["n3"] and not meta.get("appels")              # N3 passé ; aucun appel au modèle
    assert meta["tables"] == {f"francais/{n}": tables.charger("francais", n).empreinte for n in c.TABLES}
    assert (instance["matiere"], instance["niveau"], len(instance["questions"])) == ("francais", niveau, 10)
    assert instance["meta"]["id"].startswith(f"qcm-conjugaison-{niveau.lower()}-")
    if attendu:  # seulement les genres qui le travaillent : conjuguer
        assert {q["genre"] for q in meta["questions"]} <= {"conjugaison.forme", "conjugaison.temps"}
    for q in instance["questions"]:
        assert len(q["propositions"]) == 4 and q["propositions"][q["index_correct"]]
