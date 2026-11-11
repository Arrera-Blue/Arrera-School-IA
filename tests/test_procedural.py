"""Générateur procédural (étape 1.7) : tirages justes, habillage contrôlé, aiguillage, chaîne complète."""

import json
import random
import re

import pytest

from generateur import procedural
from generateur.moteur import config, generation, registre
from generateur.moteur.fournisseurs import ErreurFournisseur
from generateur.moteur.fournisseurs.base import Fournisseur
from generateur.moteur.validation import ErreurValidation, n3_pedagogie
from generateur.moteur.validation.n2_schema import valider
from generateur.moteur.validation.n3_pedagogie import cle_de_comparaison
from generateur.moteur.validation.n4_calcul import VERIFIE, verifier_question
from generateur.outils.bilan_n4 import mesurer
from generateur.procedural import habillage
from generateur.procedural.maths import pourcentages, pythagore
from generateur.procedural.habillage import controler

# les genres des maths (le français, à tables : tests/test_conjugaison.py…)
GENRES = [g for module in procedural.matieres()["maths"].generateurs() for g in module.GENRES]
# N3 demande au moins deux questions pour certaines règles : une seconde, neutre
AUTRE = {"enonce": "Quelle est la capitale de la France ?", "propositions": ["Paris", "Lyon", "Marseille"],
         "index_correct": 0, "explication": "Paris est la capitale de la France."}
TIRAGES = 1000


# --- tirages en masse : justes par construction, et confirmés par N4 ------------------------------

@pytest.mark.parametrize("genre", GENRES, ids=lambda g: g.__name__)
def test_tirages_en_masse(genre):
    rng = random.Random(f"tests-{genre.__name__}")
    tires = 0
    for _ in range(TIRAGES):
        try:
            s = genre(rng)
        except procedural.Retirer:
            continue
        tires += 1
        q = procedural.question(s, s.enonce, rng)
        # N4 recalcule l'énoncé-gabarit de son côté : un contrôle indépendant du calcul du générateur
        verdict = verifier_question(1, q)
        assert verdict.statut == VERIFIE, (s.enonce, s.reponse, s.distracteurs, verdict)
        # propositions distinctes en valeur (sauf la forme irréductible, où une simplification partielle, de même
        # valeur, est un piège voulu), et aucune règle bloquante de N3
        if s.genre != "fractions.irreductible":
            assert len({cle_de_comparaison(p) for p in q["propositions"]}) == len(q["propositions"])
        assert len(set(q["propositions"])) == len(q["propositions"])
        instance = {"type": "qcm", "titre": "Test", "matiere": "maths", "niveau": "5e", "notion": "test",
                    "questions": [q, AUTRE]}
        assert [c.message for c in n3_pedagogie.verifier(instance) if c.bloquant] == []
    assert tires > TIRAGES * 0.8  # les tirages refusés (Retirer) restent rares


def test_fractions_sans_distracteur_entier():
    """Recette 1.6 : « 9/1 » et « 4/4 », des entiers écrits en fractions, s'écartaient trop facilement."""
    from generateur.procedural.maths import fractions
    for genre in (g for g in fractions.GENRES if g is not fractions.comparaison):  # là : les fractions de l'énoncé
        rng = random.Random(f"entier-{genre.__name__}")
        for _ in range(TIRAGES):
            try:
                s = genre(rng)
            except procedural.Retirer:
                continue
            for proposition in s.distracteurs:
                if "/" in proposition:
                    n, d = proposition.split("/")
                    assert d != "1" and n != d, (s.enonce, proposition)


def test_reproductible_avec_la_meme_graine():
    for notion in procedural.notions():
        assert procedural.tirer(notion, 8, random.Random(42)) == procedural.tirer(notion, 8, random.Random(42))


def test_genres_varies_et_questions_distinctes():
    squelettes = procedural.tirer("pourcentages", 10, random.Random(1))
    genres = [s.genre for s in squelettes]
    assert set(genres[:5]) == {f"pourcentages.{g.__name__}" for g in pourcentages.GENRES}  # chacun une fois d'abord
    assert len({s.cle for s in squelettes}) == 10


def test_exercice_assemble_conforme_au_schema():
    rng = random.Random(3)
    squelettes = procedural.tirer("pythagore", 6, rng)
    instance = procedural.assembler("pythagore", "4e", squelettes, [s.enonce for s in squelettes], rng)
    valider(instance, registre.charger("qcm").schema)
    assert instance["titre"] == "Le théorème de Pythagore" and instance["matiere"] == "maths"
    for s, q in zip(squelettes, instance["questions"]):
        assert q["propositions"][q["index_correct"]] == s.reponse


# --- aiguillage ----------------------------------------------------------------------------------

@pytest.mark.parametrize("demande, notion", [
    ({"demande_enseignant": "un QCM de 5 questions sur le calcul mental pour des 6e"}, "calcul_mental"),
    ({"demande_enseignant": "un QCM de 5 questions sur les pourcentages pour des 5e"}, "pourcentages"),
    ({"demande_enseignant": "un QCM de 5 questions sur le théorème de Pythagore pour des 4e"}, "pythagore"),
    ({"notion": "Théorème de Pythagore", "matiere": "maths"}, "pythagore"),
    ({"demande_enseignant": "les soldes et les remises, pour des 5e"}, "pourcentages"),
    ({"demande_enseignant": "un QCM sur le triangle rectangle"}, "pythagore"),         # « angle » n'exclut rien
    ({"demande_enseignant": "un QCM de 5 questions sur les fractions pour des 6e"}, "fractions"),
    ({"demande_enseignant": "l'addition de fractions"}, "fractions"),               # pas le calcul mental
    ({"demande_enseignant": "l'addition et la soustraction"}, "calcul_mental"),
    ({"demande_enseignant": "fractions et pourcentages"}, None),                       # deux générateurs
    ({"demande_enseignant": "les fractions et les nombres décimaux"}, None),          # une notion non couverte
    ({"demande_enseignant": "pourcentages et Pythagore"}, None),                       # deux générateurs
    ({"demande_enseignant": "la multiplication des nombres décimaux"}, None),
    ({"demande_enseignant": "les équations"}, None),
    ({"demande_enseignant": "les aires et le théorème de Pythagore"}, None),
    ({"demande_enseignant": "la Révolution française", "matiere": "histoire-geo"}, None),
    ({"notion": "pourcentages", "matiere": "svt"}, None),
])
def test_aiguillage(demande, notion):
    assert procedural.aiguiller(demande) == notion


# --- contrôle de l'habillage ---------------------------------------------------------------------

REMISE = pourcentages.remise(random.Random(0))  # tirage fixe : on lit ses nombres plutôt que de les supposer


def test_remise_tiree():
    assert REMISE.enonce.startswith("Un article coûte") and REMISE.habillable


def _remise(texte: str) -> str:
    """Un énoncé réécrit avec les nombres du tirage REMISE : « {x} » et « {p} »."""
    x, p = (m for m in re.findall(r"\d+", REMISE.enonce))
    return texte.format(x=x, p=p)


@pytest.mark.parametrize("texte, refus", [
    ("Au marché, Léa repère un vélo à {x} €. Le jour des soldes, son prix baisse de {p} %. Combien va-t-elle "
     "le payer ?", None),
    ("Un jeu vidéo coûte {x} €. Pendant les soldes, il bénéficie d'une remise de {p} %. Quel est son prix après "
     "la remise ?", None),
    ("Léa achète 2 vélos à {x} € soldés à {p} %. Quel est le prix à payer ?", "nombres modifiés"),
    ("Léa achète deux vélos à {x} € soldés à {p} %. Quel est le prix à payer ?", "nombre écrit en lettres"),
    ("Un vélo coûte {x} €. Son prix augmente de {p} %. Quel est son nouveau prix ?", "sens modifié"),
    ("Un vélo coûte {x} €. Il est soldé à {p} %. Quel est le montant de la remise ?", "question modifiée"),
    ("Un vélo coûte {x} €. Il est soldé à {p} %. Observe la figure ci-dessous. Quel est son prix ?",
     "renvoi à une figure"),
    ("Un vélo coûte {x} €. Il est soldé à {p} %.", "point d'interrogation"),
    ("Un vélo coûte {x} € ? Il est soldé à {p} %. Quel est son prix ?", "point d'interrogation"),
    ("Un vélo coûte {x} €, soldé à {p} %. Écris à prof@exemple.fr : quel est son prix ?", "donnée personnelle"),
])
def test_controle_de_l_habillage_remise(texte, refus):
    resultat = controler(REMISE, _remise(texte))
    assert resultat is None if refus is None else refus in resultat


def test_controle_de_l_habillage_pythagore():
    hyp = pythagore.hypotenuse(random.Random(5))
    a, b = (int(x) for x in re.findall(r"(\d+) c?m\b", hyp.enonce))
    u = "cm" if " cm" in hyp.enonce else "m"
    ok = (f"Un jardin a la forme d'un triangle rectangle dont les côtés de l'angle droit mesurent {a} {u} et "
          f"{b} {u}. Quelle est la longueur de l'hypoténuse ?")
    assert controler(hyp, ok) is None
    # même nombres, mais l'hypoténuse devient une donnée : le sens a changé
    piege = (f"Dans un triangle rectangle, l'hypoténuse mesure {b} {u} et un côté {a} {u}. "
             "Quelle est la longueur de l'hypoténuse ?")
    assert "sens modifié" in controler(hyp, piege)
    echelle = f"Une échelle de {b} {u} est posée à {a} {u} d'un mur, à angle droit. À quelle hauteur arrive-t-elle ?"
    assert "question modifiée" in controler(hyp, echelle)
    # « les deux côtés de l'angle droit » ne change aucun calcul (recette 1.6) ; « deux » ailleurs, si
    deux_cotes = (f"Une voile a la forme d'un triangle rectangle ; les deux côtés de l'angle droit mesurent {a} {u} et "
                  f"{b} {u}. Quelle est la longueur de l'hypoténuse ?")
    assert controler(hyp, deux_cotes) is None
    deux_voiles = (f"Deux voiles ont la forme d'un triangle rectangle dont les côtés de l'angle droit mesurent {a} {u} "
                   f"et {b} {u}. Quelle est la longueur de l'hypoténuse ?")
    assert "nombre écrit en lettres" in controler(hyp, deux_voiles)


# --- habillage par un modèle (faux fournisseur) --------------------------------------------------

class Habilleur(Fournisseur):
    nom, modele = "habilleur", "réponses enregistrées"

    def __init__(self, reponse):
        self.reponse, self.recu = reponse, None

    def generer(self, messages: list[dict], schema: dict) -> str:
        self.recu = (messages, schema)
        if isinstance(self.reponse, Exception):
            raise self.reponse
        self.compteurs = {"tokens_lus": 900, "tokens_ecrits": 120}
        return self.reponse if isinstance(self.reponse, str) else json.dumps(self.reponse, ensure_ascii=False)


def test_habiller_accepte_et_refuse_question_par_question():
    squelettes = [REMISE, REMISE]
    bon = _remise("Au marché, Léa repère un vélo à {x} €. Le jour des soldes, son prix baisse de {p} %. "
                  "Combien va-t-elle le payer ?")
    fournisseur = Habilleur({"questions": [{"enonce": bon}, {"enonce": _remise("Un vélo à {x} € augmente de {p} %. "
                                                                              "Quel est son prix ?")}]})
    h = habillage.habiller(squelettes, "5e", fournisseur)
    assert h.enonces == [bon, REMISE.enonce]
    assert h.par_question[0] == {"habillage": "modele"} and h.par_question[1]["habillage"] == "gabarit"
    assert "sens modifié" in h.par_question[1]["refus"] and "augmente" in h.par_question[1]["texte_refuse"]
    assert h.appel["tokens_ecrits"] == 120
    messages, schema = fournisseur.recu
    assert json.loads(messages[1]["content"]) == {"niveau": "5e", "enonces": [REMISE.enonce, REMISE.enonce]}
    assert schema["properties"]["questions"]["minItems"] == 2


@pytest.mark.parametrize("reponse", [ErreurFournisseur("modèle injoignable"), "pas du JSON", {"questions": []}])
def test_habillage_impossible_garde_les_gabarits(reponse, capsys):
    h = habillage.habiller([REMISE], "5e", Habilleur(reponse))
    assert h.enonces == [REMISE.enonce] and h.par_question[0]["habillage"] == "gabarit" and h.appel is None
    assert "habillage impossible" in capsys.readouterr().out


def test_sans_genre_habillable_le_modele_n_est_pas_appele():
    calcul = procedural.tirer("calcul_mental", 3, random.Random(0))
    fournisseur = Habilleur(AssertionError("le modèle ne doit pas être appelé"))
    assert habillage.habiller(calcul, "6e", fournisseur).appel is None


# --- chaîne complète -----------------------------------------------------------------------------

@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    return tmp_path


def test_generer_sans_modele(dossiers):
    instance = generation.generer({"type": "qcm", "notion": "pourcentages", "nb_questions": 6}, "qcm", "maquette",
                                  graine=42)
    meta = instance["meta"]
    assert meta["origine"] == "procedural" and meta["generateur"] == "pourcentages" and meta["graine"] == 42
    assert meta["fournisseur"] == "procedural" and meta["appels"] == []
    assert len(instance["questions"]) == 6 and all(q["habillage"] == "gabarit" for q in meta["questions"])
    assert meta["validation"]["n4_questions"] == [VERIFIE] * 6
    again = generation.generer({"type": "qcm", "notion": "pourcentages", "nb_questions": 6}, "qcm", "maquette",
                               graine=42)
    assert again["questions"] == instance["questions"]                           # reproductible


def test_generer_avec_habillage(dossiers, monkeypatch):
    def habilleur(nom, reglages):
        # réécrit chaque énoncé habillable en ajoutant une phrase de contexte, sans toucher aux nombres
        class Contexte(Habilleur):
            def generer(self, messages, schema):
                enonces = json.loads(messages[1]["content"])["enonces"]
                self.reponse = {"questions": [{"enonce": f"Au collège, on se pose une question. {e}"} for e in enonces]}
                return super().generer(messages, schema)
        return Contexte(None)
    monkeypatch.setattr(generation, "creer", habilleur)

    instance = generation.generer({"type": "qcm", "notion": "pourcentages"}, "qcm", "habilleur", graine=7)

    meta = instance["meta"]
    assert meta["fournisseur"] == "habilleur" and len(meta["appels"]) == 1
    habilles = [q for q, m in zip(instance["questions"], meta["questions"]) if m["habillage"] == "modele"]
    assert habilles and all(q["enonce"].startswith("Au collège") for q in habilles)
    # en_pourcentage n'est pas habillable : son énoncé reste le gabarit
    assert all(m["habillage"] == "gabarit" for m in meta["questions"] if m["genre"].endswith("en_pourcentage"))


def test_refus_apres_habillage_puis_nouveau_tirage(dossiers, monkeypatch, capsys):
    vrai = generation.valider_le_fond
    refus = iter([ErreurValidation("N4", ["question 2 : un défaut"], (2,)),
                  ErreurValidation("N3", ["question 2 : encore un défaut"], (2,))])

    def valider_le_fond(instance):
        erreur = next(refus, None)
        if erreur:
            raise erreur
        return vrai(instance)
    monkeypatch.setattr(generation, "valider_le_fond", valider_le_fond)
    monkeypatch.setattr(generation, "creer", lambda nom, reglages: Habilleur(None))
    monkeypatch.setattr(habillage, "habiller", lambda squelettes, niveau, f, minimum=1: habillage.Habillage(
        [s.enonce for s in squelettes], [{"habillage": "modele"} for _ in squelettes]))

    instance = generation.generer({"type": "qcm", "notion": "pythagore"}, "qcm", "habilleur", graine=3)

    q2 = instance["meta"]["questions"][1]
    assert q2["habillage"] == "gabarit" and q2["retiree"] == "question 2 : encore un défaut"
    sortie = capsys.readouterr().out
    assert "question 2 : refusée après habillage (N4) → énoncé-gabarit" in sortie
    assert "question 2 : refusée (N3) → tirée à nouveau" in sortie


def test_modes(dossiers):
    ia = generation.generer({"type": "qcm", "notion": "pourcentages"}, "qcm", "maquette", mode="ia")
    assert "origine" not in ia["meta"]                                            # l'exemple de la maquette
    with pytest.raises(generation.AucunGenerateur):
        generation.generer({"type": "qcm", "notion": "les équations"}, "qcm", "maquette", mode="procedural")


def test_bilan_n4_ecarte_le_procedural(dossiers):
    instance = generation.generer({"type": "qcm", "notion": "calcul mental"}, "qcm", "maquette", graine=1)
    dossier = dossiers / "banque" / "instances"
    dossier.mkdir(parents=True)
    (dossier / "proc.json").write_text(json.dumps(instance, ensure_ascii=False), encoding="utf-8")
    bilan = mesurer(dossier, dossiers / "rejets")
    assert (bilan.procedurales, bilan.acceptees, bilan.questions) == (1, 0, 0)


def test_pas_de_distracteur_absurde_pour_pythagore():
    # cas réel du 07/10 : « 1 cm » proposé pour l'autre côté d'un triangle d'hypoténuse 25 cm et de côté 24 cm
    rng = random.Random(0)
    for _ in range(TIRAGES):
        for s in (pythagore.cote(rng), pythagore.hypotenuse(rng)):
            # 2 cm reste plausible pour un côté de 3 cm (triangle 3-4-5) ; 1 cm face à 24 et 25 cm ne l'est pas
            assert all(int(d.split()[0]) >= 2 for d in s.distracteurs), s


def test_controle_de_l_habillage_partie_d_un_tout():
    from generateur.procedural.maths import fractions
    s = fractions.partie(random.Random(2))
    n, k = re.findall(r"\d+", s.enonce)
    ok = f"Une pizza est coupée en {n} parts égales. Léa en mange {k}. Quelle fraction de la pizza a-t-elle mangée ?"
    assert controler(s, ok) is None
    assert controler(s, ok.replace("parts égales", "parts identiques")) is None
    # cas réel du 07/10 : « égales » disparaît ; et la question sur ce qui reste
    assert "il manque" in controler(s, ok.replace(" égales", ""))
    assert controler(s, ok.replace("a-t-elle mangée", "reste-t-il")) is not None


def test_pas_d_appel_au_modele_sous_le_seuil(capsys):
    # décision du 07/10 : un seul énoncé à réécrire ne vaut pas un appel au modèle (≈ 60 s)
    fournisseur = Habilleur(AssertionError("le modèle ne doit pas être appelé"))
    h = habillage.habiller([REMISE] + procedural.tirer("calcul_mental", 2, random.Random(0)), "5e", fournisseur,
                           minimum=2)
    assert h.appel is None and all(q["habillage"] == "gabarit" for q in h.par_question)
    assert "moins que le seuil (2)" in capsys.readouterr().out
    # à partir du seuil, le modèle est appelé
    deux = Habilleur({"questions": [{"enonce": REMISE.enonce}, {"enonce": REMISE.enonce}]})
    assert habillage.habiller([REMISE, REMISE], "5e", deux, minimum=2).appel is not None


def test_seuil_lu_dans_la_configuration():
    assert config.charger()["generation"]["habillage_min"] == 2


def test_toujours_refuse_une_erreur_claire(dossiers, monkeypatch):
    """Trois refus de suite (un bug du générateur) : ErreurValidation, avec son message ; pas une UnboundLocalError
    (« e » n'existe plus après le bloc except : vu au lot 1 du cycle 2, le 11/11)."""
    def refuser(instance):
        raise ErreurValidation("N3", ["question 1 : même énoncé que la question 2"], (1,))
    monkeypatch.setattr(generation, "valider_le_fond", refuser)
    with pytest.raises(ErreurValidation, match="même énoncé"):
        generation.generer({"type": "qcm", "notion": "les pourcentages", "niveau": "5e"}, "qcm", "maquette",
                           mode="procedural", graine=1)
