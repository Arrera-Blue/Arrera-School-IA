"""Lot 1, critère de fin (13/11) : sur 20 demandes réelles, 13 exercices étaient à côté de la demande. Le bon
générateur était choisi, mais il tirait dans toutes ses questions au lieu de celles de la notion demandée (« les
contraires » : 2 questions sur 10 ; « l'imparfait » : 2 sur 5). Les notions précises (procedural.Precision), les
retouches de la relecture (les phrases du CP, les natures variées), la matière lue dans la phrase."""

import random
import re
import shutil
from collections import Counter

import pytest

from generateur import procedural
from generateur.moteur import analyse, config, generation, registre
from generateur.moteur.validation.n2_schema import valider
from generateur.procedural import tables
from generateur.procedural.francais import conjugaison as c
from generateur.procedural.francais import phrase as ph

FRANCAIS = procedural.matieres()["francais"].generateurs()


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


def requete(phrase: str) -> dict:
    """La demande telle que l'interface l'envoie : la phrase analysée par les règles (l'attendu proposé, gardé)."""
    return analyse.analyser(phrase).requete


# --- les notions précises ---------------------------------------------------------------------------

@pytest.mark.parametrize("module", FRANCAIS, ids=lambda m: m.NOM)
def test_chaque_notion_precise_se_reconnait_a_son_titre(module):
    noms = {g.__name__ for g in module.GENRES}
    for p in module.PRECISIONS:
        assert procedural.preciser(module, {"notion": p.titre})[0] is p, p.titre
        assert set(p.genres) <= noms, p.titre


# les limites connues, assumées (13/11) : un seul verbe à un seul temps au CP (8 pronoms) ; la ponctuation du CE2
# (11 phrases au signe imposé, comme pour son objectif) ; la phrase exclamative (9 formulations)
AU_PLUS = {("conjugaison", "le verbe être", "CP"): 8, ("conjugaison", "le verbe avoir", "CP"): 8,
           ("phrase", "la ponctuation", "CE2"): 10,
           **{("phrase", "la phrase exclamative", n): 9 for n in ("CP", "CE1", "CE2")}}


def test_chaque_notion_precise_donne_15_questions_differentes():
    """Une notion précise seule, dans chaque classe où le générateur la connaît : 15 questions (le maximum du QCM),
    toutes différentes, chacune de l'un de ses genres."""
    for module in FRANCAIS:
        for p in module.PRECISIONS:
            for niveau in module.NIVEAUX:
                choix = procedural.selection(module, {"notion": p.titre}, niveau)
                if not choix.genres:  # pas dans cette classe (l'imparfait au CP) : la demande part au modèle
                    continue
                nombre = AU_PLUS.get((module.NOM, p.titre, niveau), 15)
                squelettes = procedural.tirer(module.NOM, nombre, random.Random(1), choix.genres, niveau, choix.criteres)
                assert len({s.enonce for s in squelettes}) == nombre, (module.NOM, p.titre, niveau)
                if p.genres:
                    assert {s.genre.split(".")[1] for s in squelettes} <= set(p.genres), (module.NOM, p.titre)


@pytest.mark.parametrize("phrase, generateur, genres", [
    # les 20 demandes du critère de fin (« trouver le verbe dans la phrase » : aucun générateur ne pose cette question)
    ("la conjugaison au présent pour des CE1", "conjugaison", {"forme"}),  # l'attendu proposé : pas la terminaison
    ("les verbes être et avoir au présent, CP", "conjugaison", {"forme"}),
    ("le futur des verbes en -er pour mes CE2, 10 questions", "conjugaison", {"forme"}),
    ("l'imparfait en CE2", "conjugaison", {"forme"}),
    ("retrouver l'infinitif d'un verbe conjugué, CE1", "conjugaison", {"infinitif"}),
    ("le singulier et le pluriel des noms pour des CP", "accords", {"determinant", "singulier_pluriel"}),
    ("masculin et féminin en CE1", "accords", {"accord_gn"}),
    ("les accords dans le groupe nominal, CE2, 10 questions", "accords",
     {"determinant", "accord_gn", "pluriel_irregulier", "feminin_irregulier"}),
    ("l'accord du sujet et du verbe pour mes CE1", "accords", {"sujet_verbe"}),
    ("les pluriels en -aux et les féminins particuliers, CE2", "accords", {"pluriel_irregulier", "feminin_irregulier"}),
    ("les types de phrases en CE1", "phrase", {"type_de_phrase"}),
    ("la phrase négative pour des CE2", "phrase", {"forme"}),
    ("la ponctuation au CP", None, None),  # la ponctuation de fin de phrase : au CE2 seulement
    ("la nature des mots : nom, verbe, adjectif, CE2, 10 questions", "phrase", {"nature"}),
    ("la forme affirmative et la forme négative au CP", "phrase", {"forme"}),
    ("l'ordre alphabétique au CP", "vocabulaire", {"ordre_alphabetique"}),
    ("les contraires en CE1, 10 questions", "vocabulaire", {"contraire", "contraire_prefixe"}),
    ("les familles de mots CE2", "vocabulaire", {"famille"}),
    ("les lettres muettes pour des CP", "vocabulaire", {"lettre_muette"}),
    ("les niveaux de langue en CE2", "vocabulaire", {"niveau_de_langue"}),
    # sans notion précise : tout le générateur, comme avant
    ("un QCM de conjugaison pour des CE1", "conjugaison", {"forme", "temps", "infinitif", "terminaison"}),
    ("la ponctuation au CE2", "phrase", {"ponctuation"}),
    ("l'imparfait au CP", None, None),  # pas au programme du CP
])
def test_une_demande_reelle_ne_tire_que_sa_notion(relues, phrase, generateur, genres):
    demande = requete(phrase)
    assert demande["matiere"] == "francais"
    assert procedural.aiguiller(demande) == generateur
    if generateur:
        choix = procedural.selection(procedural.notions()[generateur], demande, demande["niveau"])
        assert {g.__name__ for g in choix.genres} == genres


def test_les_criteres_ne_valent_que_pour_les_genres_de_leur_notion():
    """« l'imparfait et l'infinitif » : la forme et la terminaison à l'imparfait ; l'infinitif de n'importe quelle
    forme. « le présent et le futur » : les deux temps."""
    choix = procedural.selection(c, {"notion": "l'imparfait et l'infinitif"}, "CE1")
    assert {g.__name__ for g in choix.genres} == {"forme", "terminaison", "infinitif"}
    assert choix.criteres == {"forme": {"temps": ("imparfait",)}, "terminaison": {"temps": ("imparfait",)}}
    choix = procedural.selection(c, {"notion": "le présent et le futur des verbes en -er"}, "CE2")
    assert choix.criteres["forme"] == {"temps": ("futur", "present"), "groupe": ("1",)}
    assert choix.criteres["terminaison"] == {"temps": ("present",), "groupe": ("1",)}
    assert procedural.titre(c, choix.titres) == "La conjugaison : le futur, le présent, les verbes en -er"


def _verbe(enonce: str) -> str:
    return re.search(r"\((.+)\)$", enonce)[1]


@pytest.mark.parametrize("phrase, nombre, titre, verifier", [
    ("l'imparfait en CE2", 15, "La conjugaison : l'imparfait",
     lambda q: q["enonce"].startswith("Complète à l'imparfait")),
    ("les verbes être et avoir au présent, CP", 8, "La conjugaison : le présent, être et avoir",
     lambda q: q["enonce"].startswith("Complète au présent") and _verbe(q["enonce"]) in ("être", "avoir")),
    ("le futur des verbes en -er pour mes CE2, 10 questions", 10, "La conjugaison : le futur, les verbes en -er",
     lambda q: q["enonce"].startswith("Complète au futur")
     and tables.charger("francais", "conjugaisons").filtrer(infinitif=_verbe(q["enonce"]))[0]["groupe"] == "1"),
    ("la phrase négative pour des CE2", 15, "La phrase : la forme négative",
     lambda q: q["enonce"] in ph.FORMULES_FORME["negative"] + ph.FORMULES_FORME["affirmative"]),
    ("les contraires en CE1, 10 questions", 10, "Le vocabulaire : les contraires",
     lambda q: "contraire" in q["enonce"]),
])
def test_l_exercice_respecte_la_notion_et_la_question_regeneree_aussi(relues, dossiers, phrase, nombre, titre,
                                                                         verifier):
    demande = {**requete(phrase), "type": "qcm", "nb_questions": nombre}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=3)
    valider(instance, registre.charger("qcm").schema, meta_autorise=True)
    assert instance["titre"] == titre and instance["meta"]["precision"]["titres"]
    assert len(instance["questions"]) == nombre and all(map(verifier, instance["questions"]))
    nouvelle = generation.regenerer_question(instance, 1)
    assert nouvelle["questions"][0] != instance["questions"][0] and verifier(nouvelle["questions"][0])


def test_une_notion_trop_courte_pour_le_nombre_demande_le_dit():
    with pytest.raises(RuntimeError, match="demander moins de questions"):
        choix = procedural.selection(c, {"notion": "le verbe être"}, "CP")
        procedural.tirer("conjugaison", 9, random.Random(1), choix.genres, "CP", choix.criteres)


# --- les retouches de la relecture ------------------------------------------------------------------------

def test_au_cp_la_negation_seule_distingue_les_phrases():
    """« Une seule phrase est affirmative : laquelle ? » → « Tu aimes les bonbons ? » : juste, mais un élève de CP
    confond affirmative et déclarative. Au CP, des phrases déclaratives, sans exclamation."""
    par_phrase = {p["phrase"]: p for p in tables.charger("francais", "phrases").lignes}
    rng, vues = random.Random(5), 0
    for _ in range(300):
        s = ph.forme(rng, "CP", {"forme": ("negative", "affirmative")})
        options = [par_phrase[o] for o in (s.reponse, *s.distracteurs)]
        assert all(o["type"] == "declarative" and o["exclamative"] == "non" for o in options), s.enonce
        vues += 1
    assert vues == 300
    # au CE1, toujours tous les types : la forme et le type sont deux choses
    types = {par_phrase[o]["type"] for _ in range(200)
             for s in [ph.forme(rng, "CE1", {"forme": ("negative", "affirmative")})] for o in (s.reponse, *s.distracteurs)}
    assert types == {"declarative", "interrogative", "imperative"}


@pytest.mark.parametrize("niveau", ["CP", "CE1", "CE2"])
def test_la_nature_des_mots_est_variee(niveau):
    """La relecture : « un verbe » était la réponse 7 fois sur 10 au CE2. Chaque classe de mots du programme revient à
    peu près autant que les autres."""
    rng = random.Random(8)
    reponses = Counter(ph.nature(rng, niveau).reponse for _ in range(1400))
    assert set(reponses) == set(ph.LIBELLES[niveau].values())
    assert max(reponses.values()) < 1.5 * 1400 / len(reponses)


@pytest.mark.parametrize("phrase", ["les types de phrases en CE1", "la phrase négative pour des CE2",
                                    "les contraires en CE1", "les familles de mots CE2", "les niveaux de langue en CE2"])
def test_la_matiere_est_lue_dans_la_phrase(phrase):
    """La matière n'était pas trouvée par les règles (le modèle la complétait, quand il était libre)."""
    assert requete(phrase)["matiere"] == "francais"


@pytest.mark.parametrize("niveau", ["CP", "CE1", "CE2"])
def test_les_types_de_phrases_sont_varies(niveau):
    """La relecture : « déclarative » était la réponse aux 5 questions de « les types de phrases » (CE1)."""
    rng = random.Random(4)
    reponses = Counter(ph.type_de_phrase(rng, niveau).reponse for _ in range(900))
    assert set(reponses) == set(ph.TYPES.values()) and max(reponses.values()) < 1.5 * 900 / 3


def test_un_mot_qui_a_aussi_ce_sens_n_est_jamais_un_piege():
    """La relecture : « Quel mot soutenu veut dire « travail » ? » proposait « ouvrage », juste aussi (« se mettre à
    l'ouvrage ») : la colonne « aussi » de la table l'écarte."""
    from generateur.procedural.francais import vocabulaire as v
    rng, vues = random.Random(2), 0
    for _ in range(3000):
        s = v.niveau_de_langue(rng, "CE2")
        if "« travail »" in s.enonce:
            vues += 1
            assert "ouvrage" not in s.distracteurs
    assert vues > 50


@pytest.mark.parametrize("notion, niveau, nombre", [("les contraires", "CE1", 10), ("les contraires", "CP", 10),
                                                    ("les niveaux de langue", "CE2", 8),
                                                    ("les niveaux de langue", "CP", 8), ("le vocabulaire", "CE1", 15)])
def test_deux_questions_d_un_meme_sujet_seulement_faute_d_autres(notion, niveau, nombre):
    """La relecture : « le contraire de éteindre » puis « le contraire de allumer », ou « travail » soutenu puis
    familier, dans un même exercice : l'une donne la réponse de l'autre. Tant qu'il reste d'autres sujets (8 sens dans
    la table des niveaux de langue), jamais deux fois le même ; au-delà, le tirage va quand même jusqu'au bout."""
    from generateur.procedural.francais import vocabulaire as v
    choix = procedural.selection(v, {"notion": notion}, niveau)
    for graine in range(60):
        squelettes = procedural.tirer("vocabulaire", nombre, random.Random(graine), choix.genres, niveau, choix.criteres)
        sujets = [s.sujet for s in squelettes if s.sujet]
        assert len(sujets) == len(set(sujets)), (graine, sujets)
    choix = procedural.selection(v, {"notion": "les niveaux de langue"}, "CE2")
    squelettes = procedural.tirer("vocabulaire", 15, random.Random(1), choix.genres, "CE2", choix.criteres)
    assert len({s.enonce for s in squelettes}) == 15 and len({s.sujet for s in squelettes}) == 8


def test_l_explication_du_mot_courant_ne_tourne_pas_en_rond():
    from generateur.procedural.francais import vocabulaire as v
    rng = random.Random(3)
    for _ in range(200):
        s = v.niveau_de_langue(rng, "CE1")
        if s.enonce.startswith("En classe"):
            assert f"« {s.reponse} » est le mot courant" not in s.explication
            assert s.explication.endswith(".") and f"on dit « {s.reponse} », le mot courant" in s.explication
