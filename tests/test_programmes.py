"""E2 : se baser sur les programmes officiels — référentiel, proposition d'un attendu, contrôle du niveau,
rattachement des exercices (generateur/programmes/, validation/programme.py, procédural, génération)."""

import json
import random

import pytest

from generateur import procedural, programmes
from generateur.moteur import config, generation
from generateur.moteur.fournisseurs.base import Fournisseur
from generateur.moteur.validation import fond
from generateur.moteur.validation import programme as controle_niveau


# --- le référentiel ---------------------------------------------------------------------------------

def test_le_referentiel_est_sain():
    assert programmes.verifier() == []


def test_sept_programmes_sources_citees():
    documents = {(d["matiere"], d["niveau"]): d for d in programmes.documents()}
    assert set(documents) == {("maths", "6e"), ("maths", "5e"), ("francais", "6e"), ("francais", "5e"),
                              ("francais", "CP"), ("francais", "CE1"), ("francais", "CE2")}
    for (matiere, niveau), doc in documents.items():
        source = doc["source"]
        if niveau == "6e":
            assert doc["cycle"] == 3 and source["nor"] == "MENE2504620A" and source["bo"] == "BO n° 16 du 17 avril 2025"
        elif niveau in ("CP", "CE1", "CE2"):  # le cycle 2 : générateur procédural du cycle 2, étape 0.4 (10/11)
            assert doc["cycle"] == 2 and source["nor"] == "MENE2415135A" and source["bo"] == "BO n° 41 du 31 octobre 2024"
        else:
            assert doc["cycle"] == 4 and source["nor"] == "MENE2602912A" and source["bo"] == "BO n° 10 du 5 mars 2026"
    # 368 libellés relevés le 21/10/2026, 182 le 10/11/2026 : tout ajout ou retrait doit être voulu (et la doc mise
    # à jour)
    assert len(programmes.lister()) == 550
    assert {(m, n): len(programmes.lister(m, n)) for m, n in documents} == {
        ("maths", "6e"): 95, ("maths", "5e"): 104, ("francais", "6e"): 85, ("francais", "5e"): 84,
        ("francais", "CP"): 70, ("francais", "CE1"): 60, ("francais", "CE2"): 52}


def test_le_francais_du_cycle_2():
    """Relevé mot pour mot dans l'annexe 3 du BO n° 41 du 31 octobre 2024 (docs/Generateur-Procedural/ §11.4)."""
    a = programmes.attendu("francais.ce2.orthographe-grammaticale.03")
    assert a.libelle == ("Apprendre à conjuguer au présent, à l’imparfait, au futur et au passé composé de l’indicatif être "
                         "et avoir, les verbes du premier groupe et les verbes irréguliers du 3e groupe (faire, aller, dire, "
                         "venir, pouvoir, voir, vouloir, prendre).")
    assert a.qcm and a.niveau == "CE2" and a.cycle == 2 and a.domaine == "Grammaire et orthographe"
    assert a.theme == "Découvrir, comprendre et mettre en œuvre l’orthographe grammaticale"
    # un mot coupé en fin de ligne, recollé : « grapho-phonémiques » ; la lecture n'est pas un QCM
    a = programmes.attendu("francais.cp.identifier-mots.01")
    assert "correspondances grapho-phonémiques (CGP)" in a.libelle and not a.qcm
    assert programmes.attendu("francais.cp.relations-mots.03").libelle == "Savoir trouver des synonymes et des antonymes."
    # consulter un dictionnaire, la fluence verbale : pas des QCM
    assert not programmes.attendu("francais.ce2.vocabulaire.05").qcm and not programmes.attendu("francais.ce2.reemployer.04").qcm
    assert programmes.couvert("francais", "CP") and not programmes.couvert("maths", "CP")
    assert {t["id"].split(".")[2] for t in programmes.arbre("francais", "CE1", qcm=None)["themes"]} >= {
        "vocabulaire", "relations-mots", "phrase-simple", "orthographe-grammaticale"}


def test_libelles_officiels():
    a = programmes.attendu("maths.6e.fractions.09")
    assert a.libelle == "Comparer et encadrer des fractions" and a.theme == "Les fractions"
    assert a.sous_theme == "Comparer des fractions" and a.qcm and a.niveau == "6e" and a.cycle == 3
    assert programmes.attendu("maths.5e.calcul-litteral.06").libelle == \
        "Réduire une expression littérale de la forme ax + b, où a et b sont des nombres décimaux."
    # lire à voix haute ne se travaille pas par un QCM
    assert not programmes.attendu("francais.6e.lire-voix-haute.01").qcm
    assert programmes.attendu("inconnu") is None and programmes.attendu(None) is None


def test_themes_et_couverture():
    t = programmes.theme("maths.5e.nombres-relatifs")
    assert t["theme"] == "Nombres relatifs" and len(t["attendus"]) == 13 and t["source"] == "BO n° 10 du 5 mars 2026"
    assert programmes.libelle("maths.5e.nombres-relatifs") == "Tout le thème : Nombres relatifs"
    assert programmes.couvre("maths.5e.nombres-relatifs", "maths.5e.nombres-relatifs.07")
    assert programmes.couvre("maths.5e.nombres-relatifs.07", "maths.5e.nombres-relatifs")
    assert not programmes.couvre("maths.5e.nombres-relatifs", "maths.5e.nombres-rationnels.01")
    assert programmes.couvert("maths", "6e") and not programmes.couvert("maths", "4e")
    assert not programmes.couvert("svt", "6e")


def test_arbre_pour_le_formulaire():
    arbre = programmes.arbre("francais", "6e")
    assert arbre["source"]["bo"] == "BO n° 16 du 17 avril 2025"
    libelles = [a["libelle"] for t in arbre["themes"] for a in t["attendus"]]
    assert len(libelles) == len(programmes.lister("francais", "6e", qcm=True))
    assert all(t["attendus"] for t in arbre["themes"])  # aucun thème vide (lecture, oral : hors QCM)
    assert len([a for t in programmes.arbre("francais", "6e", None)["themes"] for a in t["attendus"]]) == 85
    assert programmes.arbre("maths", "3e") is None


@pytest.mark.parametrize("texte, matiere, niveau, attendu", [
    ("les fractions", "maths", "6e", "maths.6e.fractions"),                    # le thème
    ("comparer des fractions", "maths", "6e", "maths.6e.fractions.09"),        # un attendu se détache
    ("les nombres relatifs", "maths", "5e", "maths.5e.nombres-relatifs"),
    ("calculer une moyenne", "maths", "5e", "maths.5e.statistiques.06"),
    ("les synonymes", "francais", "6e", "francais.6e.relations-mots.03"),
    ("l’accord sujet-verbe", "francais", "6e", "francais.6e.accord-sujet-verbe"),  # l'apostrophe sépare les mots
    ("calcul mental", "maths", "6e", None),                                    # rien d'assez proche
    ("Pythagore", "maths", "4e", None),                                        # 4e : pas au référentiel
])
def test_proposer(texte, matiere, niveau, attendu):
    assert programmes.proposer(texte, matiere, niveau)[0] == attendu


def test_proposer_ne_tranche_pas_entre_ex_aequo():
    attendu, egaux = programmes.proposer("les pourcentages", "maths", "6e")
    assert attendu is None and len(egaux) == 5


# --- le contrôle du niveau (E2.6) --------------------------------------------------------------------

def qcm(niveau: str, *enonces: str, matiere: str = "maths") -> dict:
    return {"type": "qcm", "titre": "Essai", "matiere": matiere, "niveau": niveau, "notion": "essai",
            "questions": [{"enonce": e, "propositions": ["1", "2", "3"], "index_correct": 0,
                           "explication": "Explication suffisante."} for e in enonces]}


def test_une_notion_de_4e_dans_un_exercice_de_6e():
    exercice = qcm("6e", "Quelle est l'aire d'un carré de côté 3 cm ?", "Quelle est la racine carrée de 49 ?",
                   "Un pavé a une hauteur de 4 cm : quel est son volume ?")
    messages = controle_niveau.avertissements(exercice)
    assert len(messages) == 1 and messages[0].startswith("question 2 : « racine carrée » est au programme de 4e, pas de 6e")
    assert controle_niveau.avertissements({**exercice, "niveau": "4e"}) == []  # au niveau : rien
    assert controle_niveau.avertissements({**exercice, "niveau": None}) == []


def test_reperes_de_5e_cites_par_leur_attendu():
    messages = controle_niveau.avertissements(qcm("6e", "Range ces nombres relatifs : −3 ; 2 ; −1.",
                                                  "Trace la hauteur issue de A dans le triangle ABC."))
    assert [m[:12] for m in messages] == ["question 1 :", "question 2 :"]
    assert "« Définir les nombres relatifs. »" not in messages[0] and "Définir les nombres relatifs." in messages[0]


def test_francais_et_titre():
    exercice = qcm("5e", "Conjugue « venir » au présent.", matiere="francais")
    exercice["titre"] = "Le subjonctif présent"
    assert controle_niveau.avertissements(exercice)[0].startswith("l'exercice : « subjonctif » est au programme de 4e")


def test_un_avertissement_jamais_un_rejet():
    exercice = qcm("6e", "Quelle est la racine carrée de 16 ?", "Comment s'appelle un triangle à trois côtés égaux ?",
                   "Comment s'appelle un polygone à quatre côtés ?")
    avertissements, _ = fond.valider_le_fond(exercice)  # ne lève pas
    assert any("racine carrée" in a for a in avertissements)
    assert any("racine carrée" in a for a in fond.controler(exercice)["avertissements"])


# --- le générateur procédural déclare ses attendus (E2.5) --------------------------------------------

@pytest.mark.parametrize("attendu, niveau, notion", [
    ("maths.6e.fractions", "6e", "fractions"),           # thème : le générateur qui en couvre le plus d'attendus
    ("maths.6e.fractions.17", "6e", "pourcentages"),      # « Appliquer un pourcentage… »
    ("maths.5e.nombres-rationnels.01", "5e", "fractions"),
    ("maths.6e.nombres-decimaux.14", "6e", "calcul_mental"),
    ("maths.5e.nombres-relatifs", "5e", None),            # aucun générateur : le modèle
    ("maths.6e.fractions.13", "6e", None),
])
def test_aiguillage_par_attendu(attendu, niveau, notion):
    assert procedural.aiguiller({"matiere": "maths", "niveau": niveau, "attendu": attendu}) == notion


def test_les_attendus_declares_existent():
    for nom, module in procedural.notions().items():
        for genre, par_classe in getattr(module, "ATTENDUS", {}).items():
            assert genre in {g.__name__ for g in module.GENRES}, (nom, genre)
            for ids in par_classe.values():
                assert all(programmes.attendu(i) for i in ids), (nom, genre, ids)


def test_tirage_limite_aux_genres_de_l_attendu():
    module = procedural.notions()["fractions"]
    genres = procedural.genres_pour(module, "maths.6e.fractions.09", "6e")
    assert [g.__name__ for g in genres] == ["comparaison"]
    squelettes = procedural.tirer("fractions", 6, random.Random(1), genres)
    assert {s.genre for s in squelettes} == {"fractions.comparaison"}


@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    return tmp_path


def test_exercice_procedural_rattache(dossiers):
    vise = generation.generer({"type": "qcm", "matiere": "maths", "niveau": "6e", "notion": "fractions",
                               "attendu": "maths.6e.fractions.09"}, "qcm", "maquette", graine=3)
    assert vise["meta"]["programme"] == {"attendus": ["maths.6e.fractions.09"],
                                         "libelles": ["Comparer et encadrer des fractions"], "choisi": True,
                                         "source": "BO n° 16 du 17 avril 2025"}
    assert {q["genre"] for q in vise["meta"]["questions"]} == {"fractions.comparaison"}
    # sans attendu choisi : les attendus que les questions tirées travaillent
    libre = generation.generer({"type": "qcm", "notion": "pourcentages", "niveau": "6e", "nb_questions": 5},
                               "qcm", "maquette", graine=4)
    assert libre["meta"]["programme"]["choisi"] is False
    assert set(libre["meta"]["programme"]["attendus"]) <= {"maths.6e.fractions.16", "maths.6e.fractions.17",
                                                            "maths.6e.nombres-decimaux.06"}
    # Pythagore (4e) : au-delà du référentiel, rattaché à rien
    assert "programme" not in generation.generer({"type": "qcm", "notion": "Pythagore", "niveau": "4e"}, "qcm",
                                                 "maquette", graine=5)["meta"]


# --- la génération par le modèle (E2.4) ---------------------------------------------------------------

def test_le_modele_lit_le_texte_officiel():
    type_exo = generation.registre.charger("qcm")
    demande = {"type": "qcm", "matiere": "maths", "niveau": "5e", "notion": "nombres relatifs",
               "attendu": "maths.5e.nombres-relatifs.07", "demande_enseignant": "des additions simples"}
    utilisateur = generation.construire_messages(type_exo, demande)[1]["content"]
    lue = json.loads(utilisateur.split("Demande :\n")[1].split("\n\nPhrase de l'enseignant")[0])
    assert lue["attendu"] == {"libelle": "Additionner deux nombres décimaux relatifs.", "theme": "Nombres relatifs",
                              "classe": "5e", "programme": "programme officiel (BO n° 10 du 5 mars 2026)"}
    assert "attendu = « Additionner deux nombres décimaux relatifs. »" in utilisateur  # le rappel, en clair
    theme = generation.construire_messages(type_exo, {**demande, "attendu": "maths.5e.puissances"})[1]["content"]
    assert "Connaitre les carrés des entiers de 0 à 12." in theme
    assert "« attendu »" in type_exo.prompt


class Relatifs(Fournisseur):
    nom, modele = "faux", "faux-modele"

    def generer(self, messages, schema):
        questions = [{"enonce": e, "propositions": p, "index_correct": i, "explication": "On applique la règle des signes."}
                     for e, p, i in (("Quel est l'opposé de 7 ?", ["−7", "7", "0"], 0),
                                     ("Quel nombre est négatif ?", ["3", "−2", "5"], 1),
                                     ("Quelle est la distance à zéro de −4 ?", ["0", "−4", "4"], 2))]
        return json.dumps({"type": "qcm", "titre": "Les nombres relatifs", "matiere": "maths", "niveau": "5e",
                           "notion": "nombres relatifs", "questions": questions}, ensure_ascii=False)


def test_exercice_du_modele_rattache(dossiers, monkeypatch):
    monkeypatch.setattr(generation, "creer", lambda nom, reglages: Relatifs())
    instance = generation.generer({"type": "qcm", "matiere": "maths", "niveau": "5e", "notion": "nombres relatifs",
                                   "nb_questions": 3, "attendu": "maths.5e.nombres-relatifs"}, "qcm", mode="ia")
    assert instance["meta"]["programme"]["attendus"] == ["maths.5e.nombres-relatifs"]
    assert instance["meta"]["programme"]["libelles"] == ["Tout le thème : Nombres relatifs"]
    assert not any("au programme de" in a for a in instance["meta"]["avertissements"])  # en 5e : au niveau
