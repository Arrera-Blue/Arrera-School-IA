"""N4 du français (16/11/2026 ; docs/Generateur-Procedural/controle-du-modele.md) : les formes verbales inventées par le
modèle (« je parleons »), refusées ; l'ordre alphabétique, recalculé ; jamais une fausse alerte sur le générateur."""

import random

import pytest

from generateur import procedural
from generateur.moteur.validation import ErreurValidation, fond, n4_calcul, n4_francais
from generateur.procedural import tables

FRANCAIS = procedural.matieres()["francais"].generateurs()


def question(enonce, propositions, correct=0, explication="Une explication."):
    return {"enonce": enonce, "propositions": propositions, "index_correct": correct, "explication": explication}


def exercice(*questions, titre="Un exercice", matiere="francais"):
    return {"type": "qcm", "titre": titre, "matiere": matiere, "niveau": "CE1", "notion": "une notion",
            "questions": list(questions)}


def statuts(x):
    return [v.statut for v in n4_calcul.verifier(x)]


# --- la liste de Lexique ------------------------------------------------------------------------------------

def test_la_liste_de_lexique_et_sa_licence():
    lisezmoi = (n4_francais.LEXIQUE.parent / "LISEZMOI.md").read_text(encoding="utf-8")
    assert "Lexique 3.83" in lisezmoi and "CC BY-SA 4.0" in lisezmoi and "même licence" in lisezmoi
    assert len(n4_francais.mots()) > 100_000
    for mot in ("aurais", "arriva", "prendrions", "étaient", "généralement", "tutoiement", "chevaux"):
        assert n4_francais.connu(mot), mot
    for mot in ("parleons", "sommesons", "ontent", "regardaisais"):
        assert not n4_francais.connu(mot), mot


# --- les formes verbales inventées -------------------------------------------------------------------------

@pytest.mark.parametrize("texte, inventee", [
    # des exercices réels du modèle (comparaison du 15/11, banque, lot d'entraînement)
    ("je parleons", "parleons"), ("nous sommesons", "sommesons"), ("ils ontent", "ontent"), ("Tu aimaisais", "aimaisais"),
    ("elle prenaitais", "prenaitais"), ("Vous parleznt", "parleznt"), ("tu finiss", "finiss"), ("Tu grandiss", "grandiss"),
    ("Nous finissonsons", "finissonsons"), ("Tu ferasais", "ferasais"), ("j'aimerezons", "aimerezons"),
    ("J’regardaisais", "regardaisais"),
])
def test_une_forme_inventee_est_trouvee(texte, inventee):
    assert n4_francais.formes_inventees(texte) == [inventee]


@pytest.mark.parametrize("texte", [
    # de vraies formes, de tous les temps (nos tables n'en ont que 4 : « j'aurais » y manque)
    "j'aurais", "il arriva", "nous prendrions", "qu'ils viennent", "vous fîtes", "elles rougissaient",
    "ils étayent",          # absent de Lexique, mais d'« étayer » : une forme régulière
    "vous vous lavez", "il généralement", "le tutoiement", "elle a été", "on mange",
    "nous finiss-ions", "nous chant + ons",  # une coupe voulue, dans une explication
    "il Paris", "elle COD",                  # une majuscule : un nom propre, un sigle
    "il chant",             # un vrai mot employé comme une forme : la limite connue (pas vu)
    "",
])
def test_une_vraie_forme_ou_un_autre_mot_n_est_jamais_signale(texte):
    assert n4_francais.formes_inventees(texte) == []


def test_une_forme_inventee_est_refusee_et_revient_au_modele():
    x = exercice(question("Complète au présent : nous … (chanter)", ["chantons", "nous chantes", "nous chantez"]),
                 question("Comment conjugue-t-on parler au présent avec « je » ?", ["je parle", "je parleons", "je parlez"]))
    assert statuts(x) == ["a_relire", "faux"]
    with pytest.raises(ErreurValidation) as e:
        fond.valider_le_fond(x)
    assert e.value.niveau == "N4" and e.value.questions == (2,)
    assert "« parleons », dans la proposition « je parleons », n'est pas une forme française" in e.value.erreurs[0]
    # à la relecture aussi : un exercice déjà enregistré est montré faux (il ne peut pas être accepté)
    assert fond.controler(x)["erreurs"] and fond.controler(x)["questions"] == [2]


def test_les_autres_matieres_ne_changent_pas():
    q = question("je parleons ?", ["a", "b", "c"])
    assert statuts(exercice(q, matiere="histoire-geo")) == ["a_relire"]
    assert statuts(exercice(question("Calcule 2 + 3.", ["5", "6", "7"]), matiere="maths")) == ["verifie"]


# --- l'ordre alphabétique -----------------------------------------------------------------------------------

def test_le_premier_et_le_dernier_mot():
    q = question("Dans l'ordre alphabétique, quel mot vient en premier : roi, nuage, maison, escargot ?",
                 ["roi", "nuage", "maison", "escargot"], correct=3)
    assert statuts(exercice(q)) == ["verifie"]
    assert statuts(exercice(dict(q, index_correct=2))) == ["faux"]
    dernier = question("Dans l'ordre alphabétique, quel mot vient en dernier : âne, sac, bonbon, poire ?",
                       ["âne", "sac", "bonbon", "poire"], correct=1)
    assert statuts(exercice(dernier)) == ["verifie"]
    # les mots de l'énoncé : le bon n'est pas parmi les propositions
    absent = question("Dans l'ordre alphabétique, quel mot vient en premier : roi, nuage, abeille ?",
                      ["roi", "nuage", "maison"], correct=1)
    v = n4_francais.verifier(exercice(absent))[0]
    assert v.statut == "faux" and "« abeille »" in v.message and "aucune proposition" in v.message


def test_les_deux_erreurs_du_modele_au_cp():
    """La comparaison du 15/11 (aveugle-21) : « chanson » coché juste après « chat » ; « lampe, livre, lion »."""
    x = exercice(
        question("Quel mot vient juste après 'chat' dans l'ordre alphabétique ?",
                 ["chien", "chapeau", "chanson", "château"], correct=2),
        question("Parmi ces mots, lequel est le premier ?", ["soleil", "sapin", "souris", "serpent"], correct=1),
        question("Range ces mots dans l'ordre : livre, lampe, lion.",
                 ["livre, lampe, lion", "lampe, livre, lion", "lion, lampe, livre"], correct=1),
        question("Quel mot est le dernier dans cette liste ?", ["pomme", "poire", "pêche", "poule"], correct=3),
        question("Quel mot commence par la lettre 'm' ?", ["soleil", "maison", "arbre", "bateau"], correct=1),
        titre="Ordre alphabétique")
    verdicts = n4_francais.verifier(x)
    assert [v.statut for v in verdicts] == ["faux", "verifie", "faux", "verifie", "a_relire"]
    assert "« château »" in verdicts[0].message and "« lampe, lion, livre »" in verdicts[2].message
    # sans « alphabétique » ni dans l'énoncé, ni dans le titre : rien n'est recalculé
    assert statuts(dict(x, titre="Des mots", notion="les mots")) == ["faux", "a_relire", "a_relire", "a_relire",
                                                                      "a_relire"]


@pytest.mark.parametrize("enonce, propositions", [
    ("Dans l'ordre alphabétique inverse, quel mot vient en premier ?", ["roi", "nuage", "maison"]),
    ("Dans l'ordre alphabétique, quelle lettre vient en premier ?", ["b", "a", "c"]),
    ("Dans l'ordre alphabétique, quel mot vient en deuxième : roi, nuage, maison ?", ["roi", "nuage", "maison"]),
    ("Dans l'ordre alphabétique, quel mot vient en premier ?", ["élève", "eleve", "maison"]),   # se rangent pareil
    ("Dans l'ordre alphabétique, quel mot vient en premier ?", ["la pomme", "le roi", "un sac"]),  # des groupes
])
def test_au_moindre_doute_l_ordre_alphabetique_reste_a_relire(enonce, propositions):
    assert statuts(exercice(question(enonce, propositions))) == ["a_relire"]


# --- jamais une fausse alerte sur le générateur -------------------------------------------------------------

@pytest.fixture
def relues(tmp_path, monkeypatch):
    import shutil
    copie = tmp_path / "donnees"
    shutil.copytree(tables.DOSSIER, copie)
    monkeypatch.setattr(tables, "DOSSIER", copie)
    for matiere, nom in tables.lister():
        tables.relire(matiere, nom, "Essai")


@pytest.mark.parametrize("module", FRANCAIS, ids=lambda m: m.NOM)
def test_le_generateur_n_est_jamais_refuse(relues, module):
    """Ses questions sont justes par construction : N4 du français ne doit jamais les refuser ; il vérifie celles de
    l'ordre alphabétique."""
    rng = random.Random(16)
    for niveau in module.NIVEAUX:
        for genre in module.GENRES:
            if niveau not in procedural.classes_du_genre(module, genre):
                continue
            for _ in range(150):
                s = procedural.tirer_une(genre, rng, set(), niveau)
                v = n4_francais.verifier_question(1, question(s.enonce, [s.reponse, *s.distracteurs], 0, s.explication),
                                                  module.TITRE)
                assert v.statut != "faux", (genre.__name__, niveau, s.enonce, v.message)
                if genre.__name__ == "ordre_alphabetique":
                    assert v.statut == "verifie", s.enonce
