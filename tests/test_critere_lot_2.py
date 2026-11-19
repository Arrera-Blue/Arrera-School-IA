"""Le critère de fin du lot 2 (docs/Generateur-Procedural/lot-2-questionner-le-monde.md §11.6) : les 20 demandes
réelles vont au bon générateur ; ce que le premier passage a trouvé ne revient pas. Pour tous les générateurs du
cycle 2 (lots 1 et 2) : chaque question tirée passe les règles de N3 (avant, N3 en refusait certaines, tirées à
nouveau sans bruit : « 2 000 grammes » lu « 2 », une explication qui recopiait l'énoncé), et un énoncé n'a qu'une clé
(deux « Lequel de ces repères est le plus ancien ? » dans un même exercice)."""

import random
import shutil
from collections import defaultdict

import pytest

from generateur import procedural
from generateur.moteur import analyse, config, generation
from generateur.moteur.validation import n3_pedagogie as n3
from generateur.procedural import Retirer, classes_du_genre, tables

CYCLE_2 = ("vivant", "corps", "matiere", "histoire", "geographie", "conjugaison", "accords", "phrase", "vocabulaire")
GENRES = [(nom, g, niveau) for nom in CYCLE_2 for g in procedural.notions()[nom].GENRES
          for niveau in classes_du_genre(procedural.notions()[nom], g)]
TIRAGES = 300

# les 20 demandes (scripts/essais/criteres/lot-2-questionner-le-monde.json) : la phrase, ce que l'enseignant complète
# dans le formulaire (la phrase est trop longue pour deviner la notion ; « grammes » est des maths ou des sciences)
DEMANDES = [
    ("vivant ou non vivant pour des CP", {}, "vivant"),
    ("le régime alimentaire des animaux en CE1", {}, "vivant"),
    ("les chaînes alimentaires pour mes CE2", {}, "vivant"),
    ("les catégories d'aliments au CP", {}, "corps"),
    ("les dents CE1, 8 questions", {}, "corps"),
    ("le rôle des muscles pour des CE2", {}, "corps"),
    ("l'eau solide ou liquide dans la nature, CP", {"notion": "l'eau solide ou liquide"}, "matiere"),
    ("le circuit électrique en CE1", {}, "matiere"),
    ("conducteurs et isolants CE1", {}, "matiere"),
    ("les grammes et les kilogrammes pour des CE2, 10 questions", {"matiere": "sciences-et-technologie"}, "matiere"),
    ("les jours de la semaine et les mois pour des CP", {"notion": "les jours de la semaine et les mois"}, "histoire"),
    ("les grandes périodes de l'histoire CE1", {}, "histoire"),
    ("les repères datés de l'histoire, CE2", {}, "histoire"),
    ("la Préhistoire pour mes CE2, 8 questions", {}, "histoire"),
    ("les continents et les océans au CP", {}, "geographie"),
    ("les points cardinaux CP", {}, "geographie"),
    ("les zones climatiques et le relief, CE1", {}, "geographie"),
    ("fleuve ou rivière, CE1", {}, "geographie"),
    ("les montagnes, les fleuves et les déserts du monde pour des CE1",
     {"notion": "les montagnes, les fleuves et les déserts du monde"}, "geographie"),
    ("les fleuves et les massifs de France, CE2, 10 questions", {}, "geographie"),
]


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


def _requete(phrase: str, formulaire: dict) -> dict:
    requete = analyse.analyser(phrase).requete
    return {**requete, **{c: v for c, v in formulaire.items() if not requete.get(c)}}


@pytest.mark.parametrize("phrase, formulaire, generateur", DEMANDES, ids=[d[0] for d in DEMANDES])
def test_chaque_demande_va_au_bon_generateur(relues, phrase, formulaire, generateur):
    requete = _requete(phrase, formulaire)
    assert procedural.aiguiller(requete) == generateur
    choix = procedural.selection(procedural.notions()[generateur], requete, requete["niveau"])
    assert choix.genres


def test_l_eau_solide_ou_liquide_est_des_sciences():
    assert analyse.analyser("l'eau solide ou liquide dans la nature, CP").requete["matiere"] == "sciences-et-technologie"


def test_un_objectif_devine_n_ecarte_plus_une_notion_nommee(relues):
    """« les jours de la semaine et les mois » : l'objectif deviné ne parle que des mois ; son thème garde les jours.
    Un objectif qui ne garde qu'une partie d'une notion la restreint toujours (« le présent » sans la terminaison :
    tests/test_notions_precises.py)."""
    requete = _requete("les jours de la semaine et les mois pour des CP", {"notion": "les jours de la semaine et les mois"})
    assert requete["attendu"] == "histoire-geo.cp.representations-temps.04"
    choix = procedural.selection(procedural.notions()["histoire"], requete, "CP")
    assert {g.__name__ for g in choix.genres} == {"jour", "mois"}


def test_les_dents_ont_assez_de_questions_pour_huit(relues):
    requete = _requete("les dents CE1, 8 questions", {})
    squelettes = procedural.tirer("corps", 8, random.Random(3),
                                  procedural.selection(procedural.notions()["corps"], requete, "CE1").genres, "CE1")
    assert len({s.enonce for s in squelettes}) == 8


@pytest.mark.parametrize("nom, genre, niveau", GENRES, ids=[f"{n}.{g.__name__}-{c}" for n, g, c in GENRES])
def test_chaque_question_passe_n3_et_n_a_qu_une_cle_par_enonce(nom, genre, niveau):
    rng, cles = random.Random(5), defaultdict(set)
    for _ in range(TIRAGES):
        try:
            s = procedural._appeler(genre, rng, niveau)
        except Retirer:
            continue
        q = procedural.question(s, s.enonce, rng)
        bloquants = [c.message for regle in n3.REGLES_PAR_QUESTION for c in regle(1, q) if c.bloquant]
        assert not bloquants, (q, bloquants)
        cles[n3.normaliser(s.enonce)].add(s.cle)
    assert all(len(c) == 1 for c in cles.values()), {e: c for e, c in cles.items() if len(c) > 1}


def test_regenerer_une_question_d_une_petite_notion_reussit(relues, dossiers):
    """« la phrase négative pour des CE2 », 15 questions sur 18 possibles : la question régénérée n'est ni l'ancienne
    ni une autre de l'exercice (avant : 20 tirages au hasard, et environ 1 régénération sur 30 échouait)."""
    demande = {**analyse.analyser("la phrase négative pour des CE2").requete, "type": "qcm", "nb_questions": 15}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=3)
    for _ in range(30):
        nouvelle = generation.regenerer_question(instance, 1)
        assert nouvelle["questions"][0]["enonce"] not in {q["enonce"] for q in instance["questions"]}


def test_une_chaine_ne_propose_jamais_ses_propres_animaux():
    """« L'herbe est mangée par le lapin, qui est mangé par… » : jamais « le lapin » parmi les mauvaises réponses."""
    from generateur.procedural.sciences_et_technologie import vivant
    rng = random.Random(4)
    for _ in range(TIRAGES):
        s = vivant.chaine(rng, "CE2")
        if ", qui " in s.enonce:
            bas, milieu = s.enonce.split(" par ")[0], s.enonce.split(" par ")[1].split(", qui")[0]
            assert milieu not in s.distracteurs and bas.lower() not in s.distracteurs, s
