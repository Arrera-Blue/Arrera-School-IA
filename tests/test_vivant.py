"""Lot 2, étape 2.2 : le générateur du vivant, du CP au CE2 (generateur/procedural/sciences_et_technologie/ ;
docs/Generateur-Procedural/lot-2-questionner-le-monde.md §6) — les tables, chaque genre juste par construction (la
réponse relue dans la table par un autre chemin, chaque mauvaise réponse fausse pour la propriété demandée), aucun fait
discuté, l'aiguillage, un exercice de bout en bout."""

import random
import re
import shutil

import pytest

from generateur import procedural
from generateur.moteur import config, generation, registre
from generateur.moteur.validation.n2_schema import valider
from generateur.procedural import tables
from generateur.procedural.sciences_et_technologie import vivant as v

TIRAGES = 300
M = "sciences-et-technologie"


def table(nom):
    return tables.charger(M, nom).lignes


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
    elements = {l["element"]: l["categorie"] for l in table("etres_vivants")}
    assert "oeuf" not in elements and "œuf" not in elements  # un œuf fécondé contient un être vivant : écarté
    assert {"nid", "lait", "laine", "soie"} <= {e for e, c in elements.items() if c == "elabore"}  # le programme
    animaux = table("animaux")
    assert all(a["confusion"] != a["groupe"] for a in animaux)
    groupe = {a["nom"]: a["groupe"] for a in animaux}
    assert (groupe["le dauphin"], groupe["la chauve-souris"], groupe["l'araignée"]) == ("mammifère", "mammifère",
                                                                                        "arachnide")
    regime = {a["nom"]: a["regime"] for a in animaux}
    assert regime["l'araignée"] == regime["l'escargot"] == "-"  # discutés : jamais demandés
    assert {r["regime"] for r in table("regimes")} == {a["regime"] for a in animaux} - {"-"}
    assert [s["permet"] for s in table("sens") if s["sens"] == "le toucher"] == ["-"]
    assert [l["etape"] for l in sorted(table("cycle_plante"), key=lambda l: l["rang"])][0] == "la germination de la graine"
    petits = {p["jeune"]: p for p in table("petits")}
    assert {j for j, p in petits.items() if p["mues"] == "oui"} == {"la chenille", "l'asticot"}
    assert all(p["forme"] == "larve" for j, p in petits.items() if p["mues"] == "oui")
    # chaque chaîne : son milieu est un animal de la table, jamais carnivore ; son haut n'est pas un herbivore
    for c in table("chaines"):
        assert regime.get(c["milieu"], "-") != "carnivore" and regime.get(c["haut"], "-") != "herbivore"


# --- chaque genre, juste par construction -------------------------------------------------------------

@pytest.mark.parametrize("genre, niveau", [(g, n) for g in v.GENRES for n in v.CLASSES_DU_GENRE[g.__name__]],
                         ids=lambda x: getattr(x, "__name__", x))
def test_chaque_genre_est_juste_par_construction(genre, niveau):
    categorie = {l["element"]: l["categorie"] for l in table("etres_vivants")}
    animaux = {a["nom"]: a for a in table("animaux")}
    mange = {r["regime"]: r["mange"] for r in table("regimes")}
    sens = table("sens")
    parties = {l["element"]: l for l in table("plante")}
    etapes = [l["etape"] for l in sorted(table("cycle_plante"), key=lambda l: l["rang"])]
    petits = {p["jeune"]: p for p in table("petits")}
    loco = {l["animal"]: l for l in table("locomotion")}
    chaines = table("chaines")
    rng, vus = random.Random(2026), set()
    for _ in range(TIRAGES):
        s = procedural.tirer_une(genre, rng, set(), niveau)
        vus.add(s.cle)
        options = [s.reponse, *s.distracteurs]
        assert nombre_de_mots(s.enonce) <= 12, s.enonce
        assert len(set(options)) == len(options) >= 3, s
        nom = s.cle[0]
        if nom == "etre_vivant":
            assert sorted(re.search(r": (.+) \?", s.enonce)[1].split(", ")) == sorted(options)  # tous dans l'énoncé
            if s.enonce.startswith("Lequel est vivant"):
                assert categorie[s.reponse] == "vivant" and all(categorie[d] != "vivant" for d in s.distracteurs)
            elif "fabriqué" in s.enonce:
                assert categorie[s.reponse] == "elabore" and all(categorie[d] != "elabore" for d in s.distracteurs)
            else:  # « n'est pas vivant » : un élaboré n'est pas vivant non plus ; les mauvaises réponses sont vivantes
                assert categorie[s.reponse] != "vivant" and all(categorie[d] == "vivant" for d in s.distracteurs)
        elif nom == "regime":
            if s.enonce.startswith("Un animal qui mange"):
                assert mange[s.reponse] == re.search(r"mange (.+) est…", s.enonce)[1]
            elif m := re.fullmatch(r"(.+) est…", s.enonce):
                assert s.reponse == animaux[m[1][0].lower() + m[1][1:]]["regime"] != "-"
            elif m := re.fullmatch(r"Lequel de ces animaux est (\w+) \?", s.enonce):
                assert animaux[s.reponse]["regime"] == m[1]
                assert all(animaux[d]["regime"] not in (m[1], "-") for d in s.distracteurs)
            else:
                assert s.reponse == mange[re.search(r"Un animal (\w+) mange…", s.enonce)[1]]
        elif nom == "sens":
            l = next(x for x in sens if x["organe"] == s.reponse)
            assert l["sens"].split()[-1].removeprefix("l'") in s.enonce or (l["permet"] != "-" and l["permet"] in s.enonce)
            assert "toucher" not in s.enonce or "organe du toucher" in s.enonce
            assert not re.search(r"à quoi sert|équilibre", s.enonce)
        elif nom == "plante":
            if "besoin" in s.enonce:
                assert parties[s.reponse]["sorte"] == "besoin" and all(parties[d]["sorte"] == "piege" for d in s.distracteurs)
            else:
                role = re.search(r"(?:de la plante|qu'est-ce qui) (.+) \?", s.enonce)[1]
                assert parties[s.reponse]["role"] == role
                assert all(parties[d]["sorte"] == "partie" and parties[d]["role"] != role for d in s.distracteurs)
                if s.reponse in ("le fruit", "la graine"):
                    assert "la fleur" not in s.distracteurs
        elif nom == "classification":
            if m := re.search(r"range-t-on (.+) \?", s.enonce):
                a = animaux[m[1]]
                assert s.reponse == f"un {a['groupe']}"
                if a["confusion"] != "-":  # la confusion des élèves, toujours proposée
                    assert f"un {a['confusion']}" in s.distracteurs
            else:
                g = re.search(r"est un (\w+) \?", s.enonce)[1]
                assert animaux[s.reponse]["groupe"] == g and all(animaux[d]["groupe"] != g for d in s.distracteurs)
        elif nom == "cycle_plante":
            if m := re.search(r"juste (après|avant) (.+) \?", s.enonce):
                assert s.reponse == etapes[etapes.index(m[2]) + (1 if m[1] == "après" else -1)]
            else:
                rangs = sorted(etapes.index(o) for o in options)
                assert s.reponse == etapes[rangs[0] if "premier" in s.enonce else rangs[-1]]
        elif nom == "petits":
            if m := re.fullmatch(r"(.+) devient…", s.enonce):
                p = petits[m[1][0].lower() + m[1][1:]]
                assert s.reponse == v.un(p["adulte"]) and s.reponse not in s.distracteurs
            elif m := re.fullmatch(r"(.+) est…", s.enonce):
                p = petits[m[1][0].lower() + m[1][1:]]
                assert s.reponse == (v.LARVE if p["forme"] == "larve" else v.JEUNE)
            elif "sans" in s.enonce:
                assert petits[s.reponse]["mues"] == "non" and all(petits[d]["mues"] == "oui" for d in s.distracteurs)
            else:
                assert petits[s.reponse]["mues"] == "oui" and all(petits[d]["mues"] == "non" for d in s.distracteurs)
        elif nom == "locomotion":
            l = loco[s.cle[2]]
            assert s.reponse in (f"à {l['mode']}", f"les {l['organe']}")
        elif nom == "chaine":
            c = next(x for x in chaines if x["milieu"] == s.cle[2])
            if s.cle[1] == "haut":
                assert s.reponse == c["haut"]
                assert all(animaux[d]["regime"] == "herbivore" for d in s.distracteurs)  # ne mangent pas d'animaux
            else:
                assert s.reponse == c["bas"] and set(s.distracteurs) <= {x["haut"] for x in chaines}
    assert len(vus) >= (6 if genre is v.chaine else 10)  # 3 chaînes, 2 questions chacune


# --- l'aiguillage, et un exercice de bout en bout ------------------------------------------------------

@pytest.mark.parametrize("demande, generateur", [
    ({"notion": "le vivant et le non-vivant", "matiere": M, "niveau": "CP"}, "vivant"),
    ({"notion": "le régime alimentaire", "matiere": M, "niveau": "CE1"}, "vivant"),
    ({"notion": "les cinq sens", "matiere": M, "niveau": "CE1"}, "vivant"),
    ({"notion": "la chaîne alimentaire", "matiere": M, "niveau": "CE2"}, "vivant"),
    ({"notion": "les larves et la métamorphose", "matiere": M, "niveau": "CE2"}, "vivant"),
    ({"attendu": f"{M}.ce1.nutrition", "matiere": M, "niveau": "CE1"}, "vivant"),
    ({"attendu": f"{M}.ce2.locomotion.01", "matiere": M, "niveau": "CE2"}, "vivant"),
    ({"attendu": f"{M}.cp.diversite-vivant.01", "matiere": M, "niveau": "CP"}, "vivant"),
    # le corps, la matière et les objets ont leurs générateurs (étape 2.3) : jamais le vivant
    ({"notion": "les états de l'eau", "matiere": M, "niveau": "CE1"}, "matiere"),
    ({"notion": "le squelette et les articulations", "matiere": M, "niveau": "CP"}, "corps"),
    ({"notion": "l'origine animale ou végétale des aliments", "matiere": M, "niveau": "CP"}, "corps"),
    ({"attendu": f"{M}.cp.alimentation.01", "matiere": M, "niveau": "CP"}, "corps"),
    # ce que le générateur ne fait pas : au modèle
    ({"notion": "les animaux et l'environnement", "matiere": M, "niveau": "CE2"}, None),
    # une notion précise absente de la classe : au modèle (la chaîne alimentaire n'est pas au CP)
    ({"notion": "la chaîne alimentaire", "matiere": M, "niveau": "CP"}, None),
])
def test_l_aiguillage(relues, demande, generateur):
    assert procedural.aiguiller(demande) == generateur


def test_jamais_propose_tant_que_ses_tables_ne_sont_pas_relues(relues):
    (relues / "relectures.yaml").write_text("{}\n", encoding="utf-8")
    assert procedural.aiguiller({"notion": "le régime alimentaire", "matiere": M, "niveau": "CE1"}) is None


@pytest.mark.parametrize("notion, niveau, genres", [("le régime alimentaire", "CE1", {"regime"}),
                                                    ("la vie d'une plante", "CE2", {"cycle_plante"}),
                                                    ("les plantes", "CE1", {"plante"}),
                                                    ("les plantes", "CE2", {"cycle_plante"})])
def test_les_notions_precises(relues, notion, niveau, genres):
    choix = procedural.selection(v, {"notion": notion}, niveau)
    assert {g.__name__ for g in choix.genres} == genres


@pytest.mark.parametrize("niveau", ["CP", "CE1", "CE2"])
def test_un_exercice_genere_de_bout_en_bout(relues, dossiers, niveau):
    demande = {"type": "qcm", "matiere": M, "niveau": niveau, "notion": "le vivant", "nb_questions": 12}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=11)
    valider(instance, registre.charger("qcm").schema, meta_autorise=True)
    meta = instance["meta"]
    assert (meta["origine"], meta["generateur"]) == ("procedural", "vivant") and meta["validation"]["n3"]
    assert set(meta["tables"]) == {f"{M}/{n}" for n in v.TABLES}
    assert instance["matiere"] == M and len(instance["questions"]) == 12
    assert {q["genre"].split(".")[1] for q in meta["questions"]} <= {
        g for g, classes in v.CLASSES_DU_GENRE.items() if niveau in classes}


@pytest.mark.parametrize("attendu, niveau", [(f"{M}.cp.diversite-vivant.01", "CP"), (f"{M}.ce1.sens-perception.01", "CE1"),
                                             (f"{M}.ce1.nutrition.02", "CE1"), (f"{M}.ce2.environnement-proche.02", "CE2"),
                                             (f"{M}.ce2.reproduction-croissance.03", "CE2")])
def test_un_objectif_seul_donne_assez_de_questions_differentes(relues, dossiers, attendu, niveau):
    """10 questions, toutes différentes, pour un seul objectif (la chaîne alimentaire : avec le régime alimentaire)."""
    demande = {"type": "qcm", "matiere": M, "niveau": niveau, "notion": "le vivant", "nb_questions": 10,
               "attendu": attendu}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=4)
    assert len({q["enonce"] for q in instance["questions"]}) == 10
