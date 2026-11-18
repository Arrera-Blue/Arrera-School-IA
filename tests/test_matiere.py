"""Lot 2, étape 2.3 : le générateur de la matière et des objets, du CP au CE2
(generateur/procedural/sciences_et_technologie/matiere.py ; docs/Generateur-Procedural/lot-2-questionner-le-monde.md
§8) — les tables, chaque genre juste par construction (la réponse relue dans la table, ou recalculée, par un autre
chemin ; chaque mauvaise réponse fausse pour la propriété demandée), aucun fait discuté, l'aiguillage, un exercice de
bout en bout."""

import random
import re
import shutil

import pytest

from generateur import procedural
from generateur.moteur import config, generation, registre
from generateur.moteur.validation.n2_schema import valider
from generateur.procedural import tables
from generateur.procedural.sciences_et_technologie import matiere as m

TIRAGES = 300
M = "sciences-et-technologie"


def table(nom):
    return tables.charger(M, nom).lignes


def nombre_de_mots(texte: str) -> int:
    return len([t for t in texte.split() if re.search(r"\w", t)])


def entier(texte: str) -> int:
    return int(re.sub(r"\D", "", texte))


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
    etats = {m.nu(l["nom"]): l["etat"] for l in table("etats_eau")}
    assert not {"nuage", "brouillard", "cascade"} & set(etats)  # discutés (§3)
    assert {e for e, x in etats.items() if x == "solide"} == {"grêle", "neige", "glace", "banquise", "glacier"}
    changements = {l["nom"]: l for l in table("changements")}
    assert (changements["la fonte"]["proche"], changements["la congélation"]["proche"]) == ("la fusion",
                                                                                            "la solidification")
    conservation = {(l["quand"], l["grandeur"]): l["valeur"] for l in table("conservation")}
    assert conservation == {("l'eau gèle", "masse"): "ne change pas", ("la glace fond", "masse"): "ne change pas",
                            ("l'eau gèle", "place"): "plus de place", ("la glace fond", "place"): "moins de place"}
    assert set(tables.charger(M, "conservation").proprietes["valeur"]) == {v for vs in m.VALEURS.values() for v in vs}
    materiaux = {m.nu(l["materiau"]): l["nature"] for l in table("materiaux")}
    assert not {"graphite", "mine de crayon", "eau", "bois", "bois humide"} & set(materiaux)  # le bois est dit « sec »
    assert {x for x, n in materiaux.items() if n == "conducteur"} == {"cuivre", "fer", "aluminium"}
    objets = {l["objet"]: l for l in table("objets")}
    assert all(l["technique"] == "oui" for l in objets.values() if l["electrique"] != "-")
    assert all(objets[l["jumeau"]]["electrique"] == "oui" for l in objets.values() if l["jumeau"] != "-")
    assert not any("vélo" in o for o in objets)  # « vélo » seul ne dit pas s'il a une assistance électrique
    exemples = {m.nu(l["element"]) for l in table("solides_liquides") if l["sorte"] == "exemple"}
    assert not {"sable", "sel", "sucre en poudre"} & exemples  # des solides qui s'écoulent
    assert {l["role"] for l in table("ordinateur")} == set(m.ROLES)
    for l in table("circuit"):
        assert l["reponse"] not in [f.strip() for f in l["faux"].split(";")]


# --- chaque genre, juste par construction -------------------------------------------------------------

@pytest.mark.parametrize("genre, niveau", [(g, n) for g in m.GENRES for n in m.CLASSES_DU_GENRE[g.__name__]],
                         ids=lambda x: getattr(x, "__name__", x))
def test_chaque_genre_est_juste_par_construction(genre, niveau):
    etats = {m.nu(l["nom"]): l["etat"] for l in table("etats_eau")}
    objets = {m.nu(l["objet"]): l for l in table("objets")}
    objets.update({l["objet"]: l for l in table("objets")})
    changements = {l["nom"]: l for l in table("changements")}
    conservation = {(l["quand"], l["grandeur"]): l["valeur"] for l in table("conservation")}
    materiaux = {m.nu(l["materiau"]): l["nature"] for l in table("materiaux")}
    circuit = {l["question"]: l for l in table("circuit")}
    solides = {m.nu(l["element"]): l for l in table("solides_liquides")}
    solides.update({l["element"]: l for l in table("solides_liquides")})
    roles = {m.nu(l["element"]): l["role"] for l in table("ordinateur")}
    roles.update({l["element"]: l["role"] for l in table("ordinateur")})
    rng, vus = random.Random(2026), set()
    for _ in range(TIRAGES):
        s = procedural.tirer_une(genre, rng, set(), niveau)
        vus.add(s.cle)
        options = [s.reponse, *s.distracteurs]
        assert nombre_de_mots(s.enonce) <= 12, s.enonce
        assert len(set(options)) == len(options) >= 3, s
        nom = s.cle[0]
        cites = re.search(r": ([^:]+) \?$", s.enonce)
        if nom in ("etat_eau", "objet_technique", "conducteur", "solide_liquide", "ordinateur", "objet_electrique") \
                and cites and s.cle[1] != "sert":
            assert sorted(cites[1].split(", ")) == sorted(options)  # toutes les propositions dans l'énoncé
        if nom == "etat_eau":
            etat = re.search(r"est-elle (\w+)", s.enonce)[1]
            assert etats[s.reponse] == etat and all(etats[d] != etat for d in s.distracteurs)
        elif nom == "objet_technique":
            oui = "oui" if "n'est pas" not in s.enonce else "non"
            assert objets[s.reponse]["technique"] == oui and all(objets[d]["technique"] != oui for d in s.distracteurs)
        elif nom == "changement_etat":
            l = changements[s.reponse]
            assert l["sorte"] == "changement"
            assert l["quand"] in s.enonce or f"l'état {l['de']} à l'état {l['vers']}" in s.enonce \
                or f"L'eau {l['de']} devient {l['vers']}" in s.enonce
            assert all(changements[d]["proche"] != s.reponse for d in s.distracteurs)  # jamais « la fonte » pour la fusion
        elif nom == "conservation":
            quand = "l'eau gèle" if "l'eau gèle" in s.enonce else "la glace fond"
            assert s.reponse == conservation[(quand, "masse" if "masse" in s.enonce else "place")]
        elif nom == "conducteur":
            nature = "conducteur" if "laisse passer" in s.enonce else "isolant"
            assert materiaux[s.reponse] == nature and all(materiaux[d] != nature for d in s.distracteurs)
        elif nom == "circuit":
            assert s.reponse == circuit[s.enonce]["reponse"]
        elif nom == "objet_electrique":
            if q := re.search(r"le même travail qu'(.+) \?", s.enonce):
                assert objets[q[1]]["jumeau"] == s.reponse
                assert all(objets[d]["electrique"] == "oui" for d in s.distracteurs)
            else:
                oui = "non" if "sans" in s.enonce else "oui"
                assert objets[s.reponse]["electrique"] == oui
                assert all(objets[d]["electrique"] not in (oui, "-") for d in s.distracteurs)
        elif nom == "solide_liquide":
            if q := re.search(r"Lequel est un (\w+)", s.enonce):
                assert solides[s.reponse]["etat"] == q[1] and all(solides[d]["etat"] != q[1] for d in s.distracteurs)
            elif q := re.fullmatch(r"Un (\w+) a…", s.enonce):
                assert solides[s.reponse]["sorte"] == "propriete" and solides[s.reponse]["etat"] == q[1]
            else:
                assert s.reponse == "horizontale"
        elif nom == "ordinateur":
            if q := re.search(r"À quoi (?:sert|servent) (.+) \?", s.enonce):
                assert s.reponse == m.ROLES[roles[q[1]]]
            else:
                role = next(k for k, v in m.ROLES.items() if v in s.enonce)
                assert roles[s.reponse] == role and all(roles[d] != role for d in s.distracteurs)
        elif nom == "masses":
            if q := re.fullmatch(r"Combien de grammes (?:fait|font) (.+) kilogrammes? et (.+) grammes? \?", s.enonce):
                attendu = entier(q[1]) * 1000 + entier(q[2])
            elif q := re.fullmatch(r"Combien de grammes (?:fait|font) (.+) kilogrammes? \?", s.enonce):
                attendu = entier(q[1]) * 1000
            else:
                attendu = entier(re.fullmatch(r"Combien de kilogrammes font (.+) grammes \?", s.enonce)[1]) // 1000
            assert entier(s.reponse) == attendu and all(entier(d) != attendu for d in s.distracteurs)
    assert len(vus) >= {"changement_etat": 6, "conservation": 4, "circuit": 6}.get(genre.__name__, 12)


# --- l'aiguillage, et un exercice de bout en bout ------------------------------------------------------

@pytest.mark.parametrize("demande, generateur", [
    ({"notion": "les états de l'eau", "matiere": M, "niveau": "CP"}, "matiere"),
    ({"notion": "les états de l'eau", "matiere": M, "niveau": "CE1"}, "matiere"),
    ({"notion": "la fusion et la solidification", "matiere": M, "niveau": "CE1"}, "matiere"),
    ({"notion": "conducteurs et isolants", "matiere": M, "niveau": "CE1"}, "matiere"),
    ({"notion": "le circuit électrique", "matiere": M, "niveau": "CE1"}, "matiere"),
    ({"notion": "les objets techniques", "matiere": M, "niveau": "CP"}, "matiere"),
    ({"notion": "solides et liquides", "matiere": M, "niveau": "CE2"}, "matiere"),
    ({"notion": "l'ordinateur", "matiere": M, "niveau": "CE2"}, "matiere"),
    ({"notion": "convertir des grammes en kilogrammes", "matiere": M, "niveau": "CE2"}, "matiere"),
    ({"attendu": f"{M}.ce1.electricite", "matiere": M, "niveau": "CE1"}, "matiere"),
    ({"attendu": f"{M}.cp.objets-techniques.01", "matiere": M, "niveau": "CP"}, "matiere"),
    # ce que le générateur ne fait pas : au modèle
    ({"notion": "la température et le thermomètre", "matiere": M, "niveau": "CP"}, None),
    ({"notion": "la matérialité de l'air", "matiere": M, "niveau": "CE1"}, None),
    ({"notion": "programmer un robot", "matiere": M, "niveau": "CE1"}, None),
    ({"notion": "les masses", "matiere": M, "niveau": "CP"}, None),  # le vocabulaire des masses : pas couvert
    ({"notion": "le circuit électrique", "matiere": M, "niveau": "CE2"}, None),  # pas au programme du CE2
])
def test_l_aiguillage(relues, demande, generateur):
    assert procedural.aiguiller(demande) == generateur


def test_jamais_propose_tant_que_ses_tables_ne_sont_pas_relues(relues):
    (relues / "relectures.yaml").write_text("{}\n", encoding="utf-8")
    assert procedural.aiguiller({"notion": "conducteurs et isolants", "matiere": M, "niveau": "CE1"}) is None


@pytest.mark.parametrize("notion, niveau, genres", [
    ("les états de l'eau", "CP", {"etat_eau"}), ("les états de l'eau", "CE1", {"changement_etat", "conservation"}),
    ("les états de la matière", "CE2", {"solide_liquide"}), ("la masse de l'eau qui gèle", "CE1", {"conservation"}),
    ("les objets électriques", "CE1", {"objet_electrique"}), ("le circuit électrique", "CE1", {"circuit"}),
    ("l'électricité", "CE1", {"conducteur", "circuit"}), ("les objets techniques", "CE1", {"objet_electrique"}),
    ("les objets techniques", "CE2", {"ordinateur"}), ("les masses", "CE2", {"masses"})])
def test_les_notions_precises(relues, notion, niveau, genres):
    choix = procedural.selection(m, {"notion": notion}, niveau)
    assert {g.__name__ for g in choix.genres} == genres


@pytest.mark.parametrize("niveau", ["CP", "CE1", "CE2"])
def test_un_exercice_genere_de_bout_en_bout(relues, dossiers, niveau):
    demande = {"type": "qcm", "matiere": M, "niveau": niveau, "notion": "la matière et les objets", "nb_questions": 12}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=11)
    valider(instance, registre.charger("qcm").schema, meta_autorise=True)
    meta = instance["meta"]
    assert (meta["origine"], meta["generateur"]) == ("procedural", "matiere") and meta["validation"]["n3"]
    assert set(meta["tables"]) == {f"{M}/{n}" for n in m.TABLES}
    assert instance["matiere"] == M and len(instance["questions"]) == 12
    assert {q["genre"].split(".")[1] for q in meta["questions"]} <= {
        g for g, classes in m.CLASSES_DU_GENRE.items() if niveau in classes}


@pytest.mark.parametrize("attendu, niveau", [(f"{M}.cp.etats-matiere.01", "CP"), (f"{M}.cp.objets-techniques.01", "CP"),
                                             (f"{M}.ce1.electricite.02", "CE1"), (f"{M}.ce1.objets-techniques.02", "CE1"),
                                             (f"{M}.ce2.etats-matiere.01", "CE2"), (f"{M}.ce2.objets-techniques.01", "CE2"),
                                             (f"{M}.ce2.masse-volumes-temps.01", "CE2")])
def test_un_objectif_seul_donne_assez_de_questions_differentes(relues, dossiers, attendu, niveau):
    demande = {"type": "qcm", "matiere": M, "niveau": niveau, "notion": "la matière", "nb_questions": 10,
               "attendu": attendu}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=4)
    assert len({q["enonce"] for q in instance["questions"]}) == 10
