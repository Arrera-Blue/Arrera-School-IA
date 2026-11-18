"""Lot 2, étape 2.4 : le générateur de la géographie sans carte, du CP au CE2
(generateur/procedural/histoire_geo/geographie.py ; docs/Generateur-Procedural/lot-2-questionner-le-monde.md §5) — les
tables, chaque genre juste par construction (la réponse relue dans la table par un autre chemin ; chaque mauvaise
réponse fausse pour ce qui est demandé), aucun fait discuté, l'aiguillage (« histoire-géographie » nomme la matière,
« les fleuves français » sont de la géographie), un exercice de bout en bout."""

import random
import re
import shutil

import pytest

from generateur import procedural
from generateur.moteur import analyse, config, generation, registre
from generateur.moteur.validation.n2_schema import valider
from generateur.procedural import tables
from generateur.procedural.histoire_geo import geographie as g

TIRAGES = 300
M = "histoire-geo"


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
    monde = {l["nom"]: l for l in table("monde")}
    assert {n for n, l in monde.items() if l["sorte"] == "ocean"} == {"Atlantique", "Pacifique", "Indien"}  # programme
    assert not {"Antarctique", "Australie", "Arctique"} & set(monde)  # discutés (§3)
    assert {n for n, l in monde.items() if l["demande"] == "non"} == {"Amérique", "Océanie"}
    points = {l["nom"]: l for l in table("points_cardinaux") if l["sorte"] == "point"}
    assert {l["lettre"] for l in points.values()} == {"N", "E", "S", "O"}
    assert all(points[l["oppose"]]["oppose"] == n != l["oppose"] for n, l in points.items())
    lieux = {l["nom"]: l for l in table("lieux")}
    assert {n for n, l in lieux.items() if l["sorte"] == "chaine"} == {
        "les Andes", "les Alpes", "l'Atlas", "l'Himalaya", "les Rocheuses"}  # les cinq massifs du programme
    assert {n for n, l in lieux.items() if l["sorte"] == "fleuve"} == {"l'Amazone", "le Mississippi", "le Nil"}
    assert {n for n, l in lieux.items() if l["ou"] == "-"} == {"l'Antarctique"}
    assert all(l["ou"] in g.REGIONS for l in lieux.values() if l["ou"] != "-")
    mots = {l["mot"]: l for l in table("mots")}
    assert (mots["une plaine"]["jamais"], mots["un plateau"]["jamais"]) == ("un plateau", "une plaine")
    assert all(l["jamais"] in mots for l in mots.values() if l["jamais"] != "-")
    climats = table("climats")
    assert {l["zone"] for l in climats if l["sorte"] == "zone"} == {"tropicale", "tempérée", "froide"}
    assert {l["zone"] for l in climats if l["sorte"] == "territoire"} == {"tropicale", "tempérée", "froide"}
    france = {l["nom"]: l for l in table("france")}
    assert {n for n, l in france.items() if l["sorte"] == "massif"} == {
        "les Alpes", "le Jura", "le Massif central", "les Pyrénées", "les Vosges"}  # la Corse : écartée
    assert {n for n, l in france.items() if l["sorte"] == "fleuve"} == {
        "la Garonne", "la Loire", "le Maroni", "le Rhin", "le Rhône", "la Seine"}  # les six du programme
    assert all(france[l["se_jette"].removeprefix("dans ")]["sorte"] == "fleuve"
               for l in france.values() if l["sorte"] == "riviere")
    villes = table("villes")
    assert all(france[l["fleuve"]]["sorte"] == "fleuve" for l in villes)
    assert not any("Maroni" in l["ville"] for l in villes)  # son nom donnerait la réponse


# --- chaque genre, juste par construction -------------------------------------------------------------

SORTES = {"océan": "ocean", "continent": "continent", "pays": "pays"}


@pytest.mark.parametrize("genre, niveau", [(x, n) for x in g.GENRES for n in g.CLASSES_DU_GENRE[x.__name__]],
                         ids=lambda x: getattr(x, "__name__", x))
def test_chaque_genre_est_juste_par_construction(genre, niveau):
    monde = {l["nom"]: l for l in table("monde")}
    par_le = {l["le"]: l for l in table("monde")}
    points = {l["nom"]: l for l in table("points_cardinaux")}
    lieux = {l["nom"]: l for l in table("lieux")}
    mots = {l["mot"]: l for l in table("mots")}
    definitions = {l["definition"]: l for l in table("mots")}
    climats = {l["nom"]: l for l in table("climats")}
    zones = {l["zone"]: l for l in table("climats") if l["sorte"] == "zone"}
    france = {l["nom"]: l for l in table("france")}
    villes = {l["ville"]: l["fleuve"] for l in table("villes")}
    rng, vus = random.Random(2026), set()
    for _ in range(TIRAGES):
        s = procedural.tirer_une(genre, rng, set(), niveau)
        vus.add(s.cle)
        options = [s.reponse, *s.distracteurs]
        assert nombre_de_mots(s.enonce) <= 12, s.enonce
        assert len(set(options)) == len(options) >= 3, s
        nom = genre.__name__
        if nom == "continents":
            if q := re.fullmatch(r"Lequel est le nom d'un (\w+) \?", s.enonce):
                sorte = SORTES[q[1]]
                assert monde[s.reponse]["sorte"] == sorte and monde[s.reponse]["demande"] == "oui"
                assert all(monde[d]["sorte"] != sorte for d in s.distracteurs)
                if sorte != "ocean":  # l'Amérique, l'Océanie : jamais proposées pour « continent »
                    assert all(monde[d]["demande"] == "oui" for d in s.distracteurs)
            elif q := re.fullmatch(r"(.+) est…", s.enonce):
                l = next(x for le, x in par_le.items() if le.lower() == q[1].lower())
                assert s.reponse == g.SORTES_MONDE[l["sorte"]][0] and "océan" not in l["le"]
            else:
                assert s.enonce == "Sur quel continent se trouve la France hexagonale ?"
                assert s.reponse == monde["France"]["ou"] == "en Europe"
        elif nom == "points_cardinaux":
            if q := re.fullmatch(r"Quel point cardinal est à l'opposé (?:du |de )(.+) \?", s.enonce):
                point = q[1] if q[1].startswith("l'") else f"le {q[1]}"
                assert s.reponse == points[point]["oppose"] and s.reponse != point
            elif q := re.search(r"la lettre (\w) \?", s.enonce):
                assert points[s.reponse]["lettre"] == q[1]
            else:
                assert points[s.reponse]["sorte"] == "point"
                assert all(points[d]["sorte"] == "position" for d in s.distracteurs)
        elif nom == "lieux":
            if q := re.fullmatch(r"Où (?:coule|se trouve(?:nt)?) (.+) \?", s.enonce):
                assert lieux[q[1]]["ou"] == s.reponse and s.reponse not in s.distracteurs
                assert all(d in g.REGIONS for d in s.distracteurs)
            elif q := re.fullmatch(r"Lequel est (.+) \?", s.enonce):
                sorte = next(k for k, v in g.SORTES_LIEUX.items() if v == q[1])
                assert lieux[s.reponse]["sorte"] == sorte and all(lieux[d]["sorte"] != sorte for d in s.distracteurs)
            else:
                region = re.fullmatch(r"Lequel de ces lieux se trouve (.+) \?", s.enonce)[1]
                assert lieux[s.reponse]["ou"] == region and all(lieux[d]["ou"] != region for d in s.distracteurs)
        elif nom in ("relief", "vegetation"):
            sujet = re.fullmatch(r"(.+), c'est…", s.enonce)[1]
            sujet = sujet[0].lower() + sujet[1:]
            if sujet in mots:
                l, pris = mots[sujet], [definitions[o] for o in s.distracteurs]
                assert s.reponse == l["definition"]
            else:
                l, pris = definitions[sujet], [mots[o] for o in s.distracteurs]
                assert s.reponse == l["mot"]
            assert all(x["sorte"] == nom for x in pris)
            # jamais la plaine avec le plateau : la définition de l'une pourrait aller à l'autre
            assert all(l["jamais"] != x["mot"] and x["jamais"] != l["mot"] for x in pris)
        elif nom == "cours_eau":
            assert s.distracteurs[-1] in (mots["une vallée"]["mot"], mots["une vallée"]["definition"])
            if q := re.fullmatch(r"(.+) se jette (dans .+?)(?:, (un fleuve|une rivière))? : c'est…", s.enonce):
                l = france[q[1][0].lower() + q[1][1:]]
                assert l["se_jette"] == q[2]
                if l["sorte"] == "fleuve":
                    assert s.reponse == "un fleuve" and re.search(r"mer|océan", l["se_jette"])  # pas la Seine (Manche)
                else:
                    assert s.reponse == "une rivière"
                    assert france[q[2].removeprefix("dans ")]["sorte"] == "fleuve" and q[3] == "un fleuve"
            else:
                sujet = re.fullmatch(r"(.+), c'est…", s.enonce)[1]
                sujet = sujet[0].lower() + sujet[1:]
                l = mots.get(sujet) or definitions[sujet]
                assert l["sorte"] == "cours_eau"
                assert s.reponse == (l["definition"] if sujet == l["mot"] else l["mot"])
        elif nom == "climat":
            if q := re.fullmatch(r"Dans (la zone \w+)…", s.enonce):
                assert s.reponse == climats[q[1]]["climat"]
            elif q := re.fullmatch(r"(.+) : dans quelle zone \?", s.enonce):
                z = next(x for x in zones.values() if x["climat"].lower() == q[1].lower())
                assert s.reponse == z["nom"]
            elif q := re.fullmatch(r"Dans quelle zone climatique se trouve (.+) \?", s.enonce):
                assert s.reponse == zones[climats[q[1]]["zone"]]["nom"]
            else:
                z = climats[re.fullmatch(r"Lequel de ces territoires est dans (la zone \w+) \?", s.enonce)[1]]["zone"]
                assert climats[s.reponse]["zone"] == z and all(climats[d]["zone"] != z for d in s.distracteurs)
                assert all(climats[o]["sorte"] == "territoire" for o in options)
        elif nom == "france":
            massifs = {n for n, l in france.items() if l["sorte"] == "massif"}
            fleuves = {n for n, l in france.items() if l["sorte"] == "fleuve"}
            if s.enonce == "Lequel de ces massifs est en France ?":
                assert s.reponse in massifs and all(lieux[d]["ou"] not in ("en Europe", "-") for d in s.distracteurs)
            elif s.enonce == "Lequel est un des grands fleuves français ?":
                assert s.reponse in fleuves and all(lieux[d]["sorte"] == "fleuve" for d in s.distracteurs)
            elif s.enonce == "Lequel est un massif de montagnes ?":
                assert s.reponse in massifs and set(s.distracteurs) <= fleuves
            elif s.enonce == "Lequel est un fleuve ?":
                assert s.reponse in fleuves and set(s.distracteurs) <= massifs
            elif q := re.fullmatch(r"Quel fleuve passe à (.+) \?", s.enonce):
                assert s.reponse == villes[q[1]] and set(s.distracteurs) <= fleuves
            else:
                fleuve = re.fullmatch(r"Par quelle ville passe (.+) \?", s.enonce)[1]
                assert villes[s.reponse] == fleuve and all(villes[d] != fleuve for d in s.distracteurs)
    assert len(vus) >= {"continents": 10, "points_cardinaux": 9, "lieux": 17, "relief": 8, "vegetation": 6,
                        "cours_eau": 12, "climat": 16, "france": 19}[genre.__name__]


def test_aucun_fait_discute():
    """Jamais combien de continents, ni le plus long fleuve ; l'Amérique et l'Océanie ne sont jamais une bonne
    réponse, ni proposées pour « continent » ; jamais « où se trouve l'Antarctique » ; jamais la Seine « dans la
    Manche » au CE1 (un élève ne sait pas que c'est une mer)."""
    rng = random.Random(7)
    for genre in g.GENRES:
        for niveau in g.CLASSES_DU_GENRE[genre.__name__]:
            for _ in range(TIRAGES):
                s = procedural.tirer_une(genre, rng, set(), niveau)
                assert not re.search(r"[Cc]ombien|plus long|plus grand", s.enonce), s.enonce
                assert s.reponse not in ("Amérique", "Océanie")
                if "continent" in s.enonce:
                    assert not {"Amérique", "Océanie"} & set(s.distracteurs)
                assert "Antarctique" not in s.enonce and "Manche" not in s.enonce


# --- l'aiguillage, et un exercice de bout en bout ------------------------------------------------------

@pytest.mark.parametrize("demande, generateur", [
    ({"notion": "les continents et les océans", "matiere": M, "niveau": "CP"}, "geographie"),
    ({"notion": "les points cardinaux", "matiere": M, "niveau": "CP"}, "geographie"),
    ({"notion": "les fleuves du monde", "matiere": M, "niveau": "CE1"}, "geographie"),
    ({"notion": "le relief", "matiere": M, "niveau": "CE1"}, "geographie"),
    ({"notion": "fleuve et rivière", "matiere": M, "niveau": "CE1"}, "geographie"),
    ({"notion": "les zones climatiques", "matiere": M, "niveau": "CE1"}, "geographie"),
    ({"notion": "les massifs et les fleuves de France", "matiere": M, "niveau": "CE2"}, "geographie"),
    ({"notion": "la géographie", "matiere": M, "niveau": "CP"}, "geographie"),
    ({"attendu": f"{M}.cp.representations-monde.01", "matiere": M, "niveau": "CP"}, "geographie"),
    ({"attendu": f"{M}.ce2.repartition-population.04", "matiere": M, "niveau": "CE2"}, "geographie"),
    # « histoire-géographie » nomme la matière : ni l'histoire ni la géographie
    ({"notion": "les continents", "demande_enseignant": "un QCM d'histoire-géographie sur les continents",
      "matiere": M, "niveau": "CP"}, "geographie"),
    ({"notion": "les saisons", "demande_enseignant": "histoire-géographie : les saisons", "matiere": M,
      "niveau": "CP"}, "histoire"),
    # ce que le générateur ne fait pas : au modèle
    ({"notion": "localiser les océans sur un planisphère", "matiere": M, "niveau": "CP"}, None),
    ({"notion": "les paysages de montagne", "matiere": M, "niveau": "CE2"}, None),
    ({"notion": "les grandes villes du monde", "matiere": M, "niveau": "CE1"}, None),
    ({"notion": "les foyers de peuplement", "matiere": M, "niveau": "CE1"}, None),
    ({"notion": "le relief", "matiere": M, "niveau": "CE2"}, None),  # le relief : au CE1 seulement
    ({"notion": "les fleuves et les saisons", "matiere": M, "niveau": "CP"}, None),  # deux générateurs
])
def test_l_aiguillage(relues, demande, generateur):
    assert procedural.aiguiller(demande) == generateur


def test_jamais_propose_tant_que_ses_tables_ne_sont_pas_relues(relues):
    (relues / "relectures.yaml").write_text("{}\n", encoding="utf-8")
    assert procedural.aiguiller({"notion": "les points cardinaux", "matiere": M, "niveau": "CP"}) is None


@pytest.mark.parametrize("notion, niveau, genres", [
    ("les points cardinaux", "CP", {"points_cardinaux"}), ("les continents", "CP", {"continents"}),
    ("les continents", "CE1", {"lieux"}), ("les fleuves", "CE1", {"cours_eau", "lieux"}),
    ("les fleuves", "CE2", {"france"}), ("les fleuves du monde", "CE1", {"lieux"}), ("le relief", "CE1", {"relief"}),
    ("les déserts", "CE1", {"vegetation", "lieux"}), ("les montagnes", "CE1", {"relief", "lieux"}),
    ("les zones climatiques", "CE1", {"climat"}), ("les massifs de France", "CE2", {"france"}),
    ("les Alpes", "CE2", {"france"}), ("la France", "CP", {"continents"})])
def test_les_notions_precises(relues, notion, niveau, genres):
    choix = procedural.selection(g, {"notion": notion}, niveau)
    assert {x.__name__ for x in choix.genres} == genres


@pytest.mark.parametrize("phrase, generateur", [
    ("les continents et les océans CP", "geographie"), ("les fleuves français CE2", "geographie"),
    ("les grands fleuves français pour des CE2", "geographie"), ("le Nil CE1", "geographie"),
    ("la différence entre fleuve et rivière CE1", "geographie"), ("les saisons CP", "histoire"),
    ("un QCM de français sur les verbes CE1", "conjugaison"), ("les animaux du désert CE1", "vivant")])
def test_une_vraie_phrase_va_au_bon_generateur(relues, phrase, generateur):
    """De la phrase de l'enseignant au générateur : « français » après « fleuves » n'est pas la matière."""
    assert procedural.aiguiller(analyse.analyser(phrase).requete) == generateur


@pytest.mark.parametrize("niveau", ["CP", "CE1", "CE2"])
def test_un_exercice_genere_de_bout_en_bout(relues, dossiers, niveau):
    demande = {"type": "qcm", "matiere": M, "niveau": niveau, "notion": "la géographie", "nb_questions": 8}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=11)
    valider(instance, registre.charger("qcm").schema, meta_autorise=True)
    meta = instance["meta"]
    assert (meta["origine"], meta["generateur"]) == ("procedural", "geographie") and meta["validation"]["n3"]
    assert set(meta["tables"]) == {f"{M}/{n}" for n in g.TABLES}
    assert instance["matiere"] == M and len(instance["questions"]) == 8
    assert {q["genre"].split(".")[1] for q in meta["questions"]} <= {
        x for x, classes in g.CLASSES_DU_GENRE.items() if niveau in classes}


@pytest.mark.parametrize("attendu, niveau", [(f"{M}.cp.representations-monde.01", "CP"),
                                             (f"{M}.ce1.lieux-de-vie.01", "CE1"), (f"{M}.ce1.lieux-de-vie.04", "CE1"),
                                             (f"{M}.ce1.lieux-de-vie.06", "CE1"),
                                             (f"{M}.ce2.repartition-population.04", "CE2")])
def test_un_objectif_seul_donne_assez_de_questions_differentes(relues, dossiers, attendu, niveau):
    demande = {"type": "qcm", "matiere": M, "niveau": niveau, "notion": "la géographie", "nb_questions": 10,
               "attendu": attendu}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=4)
    assert len({q["enonce"] for q in instance["questions"]}) == 10


def test_le_relief_seul_part_au_modele_pour_dix_questions(relues, dossiers):
    """Le relief : 8 questions. Pour 10, le générateur le dit ; en mode automatique, le modèle écrit l'exercice."""
    demande = {"type": "qcm", "matiere": M, "niveau": "CE1", "notion": "le relief", "nb_questions": 10,
               "attendu": f"{M}.ce1.lieux-de-vie.03"}
    with pytest.raises(procedural.PasAssezDeQuestions):
        generation.generer(demande, "qcm", "maquette", mode="procedural", graine=1)
