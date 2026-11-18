"""Lot 2, étape 2.3 : le générateur du corps humain, du CP au CE2 (generateur/procedural/sciences_et_technologie/corps.py ;
docs/Generateur-Procedural/lot-2-questionner-le-monde.md §7) — les tables, chaque genre juste par construction (la
réponse relue dans la table par un autre chemin, chaque mauvaise réponse fausse pour la propriété demandée), aucun fait
discuté, l'aiguillage, un exercice de bout en bout, et le modèle quand les questions manquent."""

import random
import re
import shutil

import pytest

from generateur import procedural
from generateur.moteur import analyse, config, generation, registre
from generateur.moteur.validation.n2_schema import valider
from generateur.procedural import tables
from generateur.procedural.sciences_et_technologie import corps as c

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
    aliments = {l["aliment"]: l for l in table("aliments")}
    # un aliment à deux catégories n'est jamais dans la table (§3) ; le lait, seulement par son origine
    assert not {"la pomme de terre", "la banane", "le beurre", "les petits pois", "le maïs"} & set(aliments)
    assert aliments["le lait"]["categorie"] == "-" and aliments["le lait"]["origine"] == "animale"
    assert {l["categorie"] for l in aliments.values()} - {"-"} == {  # les 6 catégories du programme
        "les fruits et légumes", "les viandes, poissons et œufs", "les produits laitiers", "les féculents et céréales",
        "les matières grasses", "les boissons"}
    assert all(l["origine"] == "-" for l in aliments.values() if l["transforme"] == "oui")  # le pain : plusieurs produits
    articulations = {l["articulation"]: l for l in table("articulations")}
    assert set(articulations) == {"le coude", "le poignet", "l'épaule", "le genou", "la cheville", "la hanche", "le cou"}
    assert {a: l["geste"] for a, l in articulations.items() if l["geste"] != "-"} == {
        "le coude": "plier le bras", "le genou": "plier la jambe", "le cou": "tourner la tête"}
    dents = {l["element"]: l for l in table("dents")}
    assert {e for e, l in dents.items() if l["sorte"] == "partie"} == {"la couronne", "la racine", "la pulpe", "l'émail"}
    assert all(l["jamais"] in dents or l["jamais"] == "-" for l in dents.values())
    muscles = {l["muscle"]: l for l in table("muscles")}
    assert (muscles["le biceps"]["infinitif"], muscles["le triceps"]["infinitif"]) == ("plier le bras", "tendre le bras")
    for l in table("effort"):  # jamais la respiration ni la transpiration (aucune source ne dit le sens)
        assert l["reponse"] not in l["faux"] and len(l["faux"].split(";")) >= 2
        assert not re.search(r"respir|transpir", l["question"] + l["reponse"])


# --- chaque genre, juste par construction -------------------------------------------------------------

@pytest.mark.parametrize("genre, niveau", [(g, n) for g in c.GENRES for n in c.CLASSES_DU_GENRE[g.__name__]],
                         ids=lambda x: getattr(x, "__name__", x))
def test_chaque_genre_est_juste_par_construction(genre, niveau):
    aliments = {l["aliment"]: l for l in table("aliments")}
    arts = {l["articulation"]: l for l in table("articulations")}
    os_ = {l["os"]: l for l in table("os")}
    dents = {l["element"]: l for l in table("dents")}
    muscles = {l["muscle"]: l for l in table("muscles")}
    effort = {l["question"]: l for l in table("effort")}
    rng, vus = random.Random(2026), set()
    for _ in range(TIRAGES):
        s = procedural.tirer_une(genre, rng, set(), niveau)
        vus.add(s.cle)
        options = [s.reponse, *s.distracteurs]
        assert nombre_de_mots(s.enonce) <= 12, s.enonce
        assert len(set(options)) == len(options) >= 3, s
        nom = s.cle[0]
        if nom == "aliments":
            if m := re.search(r"range-t-on (.+) \?", s.enonce):
                assert s.reponse == aliments[m[1]]["categorie"] != "-"
            else:
                categorie = re.search(r"fait partie (?:des|de la|du) (.+) \?", s.enonce)[1]
                assert aliments[s.reponse]["categorie"].endswith(categorie)
                assert all(aliments[d]["categorie"] not in (aliments[s.reponse]["categorie"], "-") for d in s.distracteurs)
        elif nom == "origine":
            if m := re.fullmatch(r"(.+) est un aliment d'origine…", s.enonce):
                assert s.reponse == aliments[m[1][0].lower() + m[1][1:]]["origine"] != "-"
            elif m := re.search(r"d'origine (\w+) \?", s.enonce):
                assert aliments[s.reponse]["origine"] == m[1]
                assert all(aliments[d]["origine"] not in (m[1], "-") for d in s.distracteurs)
            else:
                assert aliments[s.reponse]["transforme"] == "oui"
                assert all(aliments[d]["transforme"] == "non" for d in s.distracteurs)
        elif nom == "squelette":
            if m := re.search(r"se trouve entre (.+) \?", s.enonce):
                assert arts[s.reponse]["entre"] == m[1]
            elif m := re.search(r"permet de (.+) \?", s.enonce):
                assert arts[s.reponse]["geste"] == m[1]
                # jamais une articulation de la même partie du corps (l'épaule bouge aussi le bras)
                assert all(arts[d]["partie"] != arts[s.reponse]["partie"] for d in s.distracteurs)
            elif m := re.search(r"l'os (?:de la|du|de l') ?(.+) \?", s.enonce):
                assert os_[s.reponse]["lieu"].endswith(m[1])
            else:
                assert os_[s.reponse]["role"] == re.search(r"qu'est-ce qui (.+) \?", s.enonce)[1]
        elif nom == "dents":
            if m := re.search(r"Quelle partie de la dent (.+) \?", s.enonce):
                assert dents[s.reponse]["description"] == m[1]
                assert dents[s.reponse]["jamais"] not in s.distracteurs
                assert all(dents[d]["sorte"] == "partie" for d in s.distracteurs)
            elif "Combien" in s.enonce:
                assert dents[s.reponse]["sorte"] == "nombre_de_lait"
            else:
                assert dents[s.reponse]["sorte"] == "definitives"
                assert all(dents[d]["sorte"] == "piege" for d in s.distracteurs)
        elif nom == "muscles":
            if m := re.search(r"Quel muscle permet de (.+) \?", s.enonce):
                assert muscles[s.reponse]["infinitif"] == m[1] and muscles[s.reponse]["demande"] == "oui"
            elif m := re.search(r"Que fait (.+) quand", s.enonce):
                assert s.reponse == f"il {muscles[m[1]]['present']}" and muscles[m[1]]["demande"] == "oui"
            else:
                verbe, reste = re.search(r"Quand on (\w+) (.+), quelle", s.enonce).groups()
                assert arts[s.reponse]["geste"] == f"{verbe}r {reste}"
                assert all(arts[d]["partie"] != arts[s.reponse]["partie"] for d in s.distracteurs)
        elif nom == "effort":
            assert s.reponse == effort[s.enonce]["reponse"]
    assert len(vus) >= {"dents": 6, "muscles": 7, "effort": 3}.get(genre.__name__, 12)


# --- l'aiguillage, et un exercice de bout en bout ------------------------------------------------------

@pytest.mark.parametrize("demande, generateur", [
    ({"notion": "les catégories d'aliments", "matiere": M, "niveau": "CP"}, "corps"),
    ({"notion": "l'origine animale ou végétale des aliments", "matiere": M, "niveau": "CP"}, "corps"),
    ({"notion": "le squelette et les articulations", "matiere": M, "niveau": "CP"}, "corps"),
    ({"notion": "les dents", "matiere": M, "niveau": "CE1"}, "corps"),
    ({"notion": "les muscles", "matiere": M, "niveau": "CE2"}, "corps"),
    ({"notion": "le corps humain", "matiere": M, "niveau": "CE2"}, "corps"),
    ({"attendu": f"{M}.cp.alimentation.01", "matiere": M, "niveau": "CP"}, "corps"),
    ({"attendu": f"{M}.ce1.croissance-mouvement", "matiere": M, "niveau": "CE1"}, "corps"),
    # ce que le générateur ne fait pas : au modèle
    ({"notion": "l'hygiène et la santé", "matiere": M, "niveau": "CP"}, None),
    ({"notion": "l'équilibre alimentaire", "matiere": M, "niveau": "CE1"}, None),
    ({"notion": "la respiration pendant l'effort", "matiere": M, "niveau": "CE2"}, None),
    ({"notion": "les dents", "matiere": M, "niveau": "CP"}, None),  # pas au programme du CP
    ({"notion": "les aliments", "matiere": M, "niveau": "CE1"}, None),  # au CE1 : leurs apports, pas couverts
])
def test_l_aiguillage(relues, demande, generateur):
    assert procedural.aiguiller(demande) == generateur


def test_jamais_propose_tant_que_ses_tables_ne_sont_pas_relues(relues):
    (relues / "relectures.yaml").write_text("{}\n", encoding="utf-8")
    assert procedural.aiguiller({"notion": "les dents", "matiere": M, "niveau": "CE1"}) is None


@pytest.mark.parametrize("notion, niveau, genres", [("l'origine des aliments", "CP", {"origine"}),
                                                    ("les aliments", "CP", {"aliments", "origine"}),
                                                    ("le squelette", "CP", {"squelette"}),
                                                    ("les muscles et les articulations", "CE2", {"muscles"}),
                                                    ("le pouls pendant l'effort", "CE2", {"effort"}),
                                                    ("le cœur pendant l'effort", "CE2", {"effort"})])
def test_les_notions_precises(relues, notion, niveau, genres):
    choix = procedural.selection(c, {"notion": notion}, niveau)
    assert {g.__name__ for g in choix.genres} == genres


@pytest.mark.parametrize("niveau, nombre", [("CP", 12), ("CE1", 5), ("CE2", 6)])  # tour à tour : 3 de chaque au CE2
def test_un_exercice_genere_de_bout_en_bout(relues, dossiers, niveau, nombre):
    demande = {"type": "qcm", "matiere": M, "niveau": niveau, "notion": "le corps humain", "nb_questions": nombre}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=11)
    valider(instance, registre.charger("qcm").schema, meta_autorise=True)
    meta = instance["meta"]
    assert (meta["origine"], meta["generateur"]) == ("procedural", "corps") and meta["validation"]["n3"]
    assert set(meta["tables"]) == {f"{M}/{n}" for n in c.TABLES}
    assert instance["matiere"] == M and len(instance["questions"]) == nombre
    assert {q["genre"].split(".")[1] for q in meta["questions"]} <= {
        g for g, classes in c.CLASSES_DU_GENRE.items() if niveau in classes}


@pytest.mark.parametrize("attendu, niveau", [(f"{M}.cp.alimentation.01", "CP"), (f"{M}.cp.croissance-mouvement.01", "CP")])
def test_un_objectif_seul_donne_assez_de_questions_differentes(relues, dossiers, attendu, niveau):
    demande = {"type": "qcm", "matiere": M, "niveau": niveau, "notion": "le corps humain", "nb_questions": 10,
               "attendu": attendu}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=4)
    assert len({q["enonce"] for q in instance["questions"]}) == 10


def test_trop_peu_de_questions_l_exercice_part_au_modele(relues, dossiers, monkeypatch):
    """Le cœur pendant l'effort : trois questions. Pour cinq, le générateur le dit ; en mode automatique, le modèle
    écrit l'exercice (contrôlé comme d'habitude), au lieu d'un échec."""
    demande = {"type": "qcm", "matiere": M, "niveau": "CE2", "notion": "l'effort", "nb_questions": 5,
               "attendu": f"{M}.ce2.croissance-mouvement.03"}
    with pytest.raises(procedural.PasAssezDeQuestions):
        generation.generer(demande, "qcm", "maquette", mode="procedural", graine=1)

    class AuModele(Exception):
        pass

    def au_modele(*args, **kwargs):
        raise AuModele

    monkeypatch.setattr(generation, "construire_messages", au_modele)
    with pytest.raises(AuModele):
        generation.generer(demande, "qcm", "maquette", graine=1)


@pytest.mark.parametrize("phrase, generateur", [("les catégories d'aliments pour des CP", "corps"),
                                                ("les articulations et les os CP", "corps"), ("les dents CE1", "corps"),
                                                ("le cœur pendant l'effort CE2", "corps"),
                                                ("le régime alimentaire des animaux CE1", "vivant"),
                                                ("l'hygiène CE1", None)])
def test_une_vraie_phrase_va_au_bon_generateur(relues, phrase, generateur):
    """De la phrase de l'enseignant au générateur : la matière trouvée (« cœur » se lit « coeur », pas « cur »)."""
    requete = analyse.analyser(phrase).requete
    assert requete["matiere"] == (M if generateur else None) or generateur is None
    assert procedural.aiguiller(requete) == generateur
