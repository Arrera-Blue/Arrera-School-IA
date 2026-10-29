"""La banque d'exercices (generateur/moteur/banque.py) : identifiants sûrs, statuts, décisions, relecture."""

import json

import pytest

from generateur.moteur import banque, config, generation, registre


@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    return tmp_path


def exercice(ident="qcm-pythagore-4e-20261013-100000", date="2026-10-13T10:00:00", **meta) -> dict:
    instance = json.loads(json.dumps(registre.charger("qcm").exemple))
    instance["meta"] = {"id": ident, "date": date, "statut": "genere",
                        "validation": {"n1": True, "n2": True, "n3": True, "n4": "a_relire",
                                       "n4_questions": ["a_relire", "verifie", "verifie"]}, **meta}
    return instance


@pytest.mark.parametrize("ident", ["../config", "..", "a/b", "A-MAJUSCULE", "", "x" * 200, "qcm-ok.json"])
def test_un_identifiant_ne_sort_jamais_de_la_banque(dossiers, ident):
    with pytest.raises(banque.ExerciceInconnu):
        banque.chemin(ident)


def test_ecrire_puis_relire(dossiers):
    json_chemin, html_chemin = banque.ecrire(exercice())
    assert json_chemin == dossiers / "banque" / "qcm-pythagore-4e-20261013-100000.json"
    assert banque.charger("qcm-pythagore-4e-20261013-100000")["titre"] == "Le théorème de Pythagore"
    assert "<html" in html_chemin.read_text(encoding="utf-8")
    assert not list((dossiers / "banque").glob(".*.tmp"))  # écriture atomique : aucun reste
    with pytest.raises(banque.ExerciceInconnu, match="introuvable"):
        banque.charger("qcm-absent-4e-20261013-100000")


def test_deux_exercices_dans_la_meme_seconde_ne_s_ecrasent_pas(dossiers):
    premier, second = exercice(), exercice()
    banque.enregistrer(premier)
    chemin_second, _ = banque.enregistrer(second)
    assert second["meta"]["id"] == "qcm-pythagore-4e-20261013-100000-2" and chemin_second.stem == second["meta"]["id"]
    assert len(banque.lister()) == 2
    banque.ecrire(premier)  # une modification, elle, remplace bien l'exercice
    assert len(banque.lister()) == 2


def test_decisions_gardees_dans_l_historique(dossiers):
    banque.ecrire(exercice())
    banque.decider("qcm-pythagore-4e-20261013-100000", "rejeter", "  trop facile  ")
    instance = banque.decider("qcm-pythagore-4e-20261013-100000", "accepter")
    assert instance["meta"]["statut"] == "accepte"
    assert [(d["statut"], d["motif"]) for d in instance["meta"]["decisions"]] == [("rejete", "trop facile"),
                                                                                   ("accepte", None)]
    with pytest.raises(ValueError):
        banque.decider("qcm-pythagore-4e-20261013-100000", "publier")


def test_rejeter_en_cochant_pourquoi(dossiers):
    """Plan IA, IA3 : les motifs cochés au rejet (ce que le modèle doit éviter), rangés dans l'ordre de la liste."""
    banque.ecrire(exercice())
    instance = banque.decider("qcm-pythagore-4e-20261013-100000", "rejeter", "« 7 cm » ne trompe personne",
                              ["distracteurs_faciles", "explication_fausse"])
    assert instance["meta"]["decisions"][-1]["motifs"] == ["explication_fausse", "distracteurs_faciles"]
    with pytest.raises(ValueError, match="motif de rejet inconnu"):
        banque.decider("qcm-pythagore-4e-20261013-100000", "rejeter", motifs=["trop_long"])
    with pytest.raises(ValueError, match="accompagne un rejet"):
        banque.decider("qcm-pythagore-4e-20261013-100000", "accepter", motifs=["reponse_fausse"])
    assert "motifs" not in banque.decider("qcm-pythagore-4e-20261013-100000", "rejeter")["meta"]["decisions"][-1]


def test_les_signalements_dans_la_liste(dossiers):
    banque.ecrire(exercice())
    faux = exercice("qcm-pythagore-4e-20261013-100001")
    faux["questions"][1]["index_correct"] = 0  # 3² + 4² = 25 : « 7 cm » est faux
    banque.ecrire(faux)
    assert {l["id"]: l["signalements"] for l in banque.lister()} == {"qcm-pythagore-4e-20261013-100000": 1,
                                                                     "qcm-pythagore-4e-20261013-100001": 2}


def test_lister_filtrer_et_trier(dossiers):
    banque.ecrire(exercice("qcm-ancien-4e-20261001-100000", "2026-10-01T10:00:00"))
    banque.ecrire(exercice("qcm-recent-4e-20261013-100000", "2026-10-13T10:00:00", statut="accepte"))
    (dossiers / "banque" / "illisible.json").write_text("{", encoding="utf-8")  # ignoré, sans erreur
    assert [x["id"] for x in banque.lister()] == ["qcm-recent-4e-20261013-100000", "qcm-ancien-4e-20261001-100000"]
    assert [x["id"] for x in banque.lister(statut_voulu="accepte")] == ["qcm-recent-4e-20261013-100000"]
    assert banque.lister(matiere="francais") == [] and len(banque.lister(niveau="4e")) == 2
    ligne = banque.lister()[1]
    assert (ligne["questions"], ligne["a_relire"], ligne["origine"], ligne["statut"]) == (3, 1, "modele", "genere")


def test_un_exercice_sans_statut_est_a_relire(dossiers):
    instance = exercice()
    del instance["meta"]["statut"]
    assert banque.statut(instance) == "genere"


def test_relecture_question_par_question():
    instance = exercice(regenerations=[{"question": 3, "ancienne": {}}])
    fond = {"erreurs": ["question 3 : 7 + 8 = 15, mais la réponse annoncée est « 16 »"], "questions": [3],
            "niveau": "N4", "avertissements": ["question 2 : deux mauvaises réponses de même valeur",
                                                "le titre reprend la notion"],
            "n4_questions": ["a_relire", "verifie", "faux"]}
    relecture = banque.relecture(instance, fond)
    assert [q["n4"] for q in relecture["questions"]] == ["a_relire", "verifie", "faux"]
    assert relecture["questions"][1]["avertissements"] == ["question 2 : deux mauvaises réponses de même valeur"]
    assert relecture["questions"][2]["erreurs"] == ["question 3 : 7 + 8 = 15, mais la réponse annoncée est « 16 »"]
    assert relecture["avertissements"] == ["le titre reprend la notion"]
    assert [q["regeneree"] for q in relecture["questions"]] == [False, False, True]
    assert (relecture["valide"], relecture["a_corriger"], relecture["a_relire"]) == (False, [3], 1)


def faux_pythagore() -> dict:
    """Une réponse fausse que le meta ne signale pas : le cas des 5 exercices acceptés avant le 07/10."""
    instance = exercice()
    instance["questions"][1]["index_correct"] = 0  # « 7 cm » pour l'hypoténuse d'un triangle 3-4
    return instance


def test_la_relecture_controle_avec_les_regles_du_jour(dossiers):
    relecture = banque.relecture(faux_pythagore())
    assert not relecture["valide"] and relecture["a_corriger"] == [2]
    assert relecture["questions"][1]["n4"] == "faux" and "5" in relecture["questions"][1]["erreurs"][0]
    assert banque.resume(faux_pythagore())["a_corriger"] == 1


def test_un_exercice_faux_ne_peut_pas_etre_accepte(dossiers):
    banque.ecrire(faux_pythagore())
    with pytest.raises(banque.ExerciceFaux, match="à corriger"):
        banque.decider("qcm-pythagore-4e-20261013-100000", "accepter")
    assert banque.decider("qcm-pythagore-4e-20261013-100000", "rejeter")["meta"]["statut"] == "rejete"


def test_un_calcul_du_programme_n_est_jamais_a_relire(dossiers, monkeypatch):
    # essai du 16/10 : 3 questions de pourcentages annoncées « à relire », alors que le programme a fait le calcul
    instance = generation.generer({"type": "qcm", "notion": "pourcentages", "niveau": "5e"}, "qcm", "maquette",
                                  graine=1)
    instance["meta"]["validation"]["n4_questions"] = ["a_relire"] * len(instance["questions"])
    relecture = banque.relecture(instance)
    assert relecture["procedural"] and relecture["a_relire"] == 0
    assert all(q["calcul"] == "programme" for q in relecture["questions"])
    assert banque.resume(instance)["a_relire"] == 0


# --- modifier une question à la main, rechercher, supprimer (architecture §11, B1, B3, B4) ---------------

IDENT = "qcm-pythagore-4e-20261013-100000"
HYPOTENUSE_6_8 = {"enonce": "Un triangle rectangle a pour côtés de l'angle droit 6 cm et 8 cm. Quelle est la longueur "
                            "de l'hypoténuse ?",
                  "propositions": ["14 cm", "10 cm", "48 cm"], "index_correct": 1,
                  "explication": "6² + 8² = 36 + 64 = 100, et 100 = 10², donc l'hypoténuse mesure 10 cm."}


def test_modifier_une_question(dossiers):
    banque.ecrire(exercice(statut="accepte"))
    instance = banque.modifier_question(IDENT, 2, dict(HYPOTENUSE_6_8))
    assert instance["questions"][1] == {**HYPOTENUSE_6_8, "difficulte": "facile"}  # la difficulté est gardée
    meta = instance["meta"]
    assert meta["statut"] == "genere"  # l'exercice a changé : à accepter de nouveau
    assert meta["modifications"][0]["question"] == 2 and meta["modifications"][0]["ancienne"]["propositions"][2] == "5 cm"
    assert meta["validation"]["n4_questions"][1] == "verifie"
    assert banque.charger(IDENT) == instance  # enregistrée
    relue = banque.relecture(instance)["questions"][1]
    assert relue["modifiee"] and not relue["regeneree"] and relue["calcul"] == "enseignant"


@pytest.mark.parametrize("changement, message", [
    ({"propositions": ["14 cm", "10 cm"]}, "il en faut au moins 3"),  # N2
    ({"index_correct": 0}, "10"),  # N4 : 14 cm annoncé, c'est 10 cm
    ({"propositions": ["10 cm", "10 cm", "48 cm"]}, "question 2"),  # N3 : deux propositions identiques
])
def test_une_modification_fausse_est_refusee(dossiers, changement, message):
    banque.ecrire(exercice())
    with pytest.raises(banque.ErreurValidation, match=message):
        banque.modifier_question(IDENT, 2, {**HYPOTENUSE_6_8, **changement})
    assert banque.charger(IDENT)["questions"][1]["propositions"] == ["7 cm", "12 cm", "5 cm", "25 cm"]  # inchangée


def test_une_modification_tolere_les_defauts_d_autres_questions(dossiers):
    banque.ecrire(faux_pythagore())  # question 2 fausse
    instance = banque.modifier_question(IDENT, 1, {**exercice()["questions"][0], "enonce": "Dans un triangle ABC "
                                                   "rectangle en A, laquelle de ces égalités est vraie ?"})
    assert instance["questions"][0]["enonce"].endswith("laquelle de ces égalités est vraie ?")
    with pytest.raises(ValueError, match="pas changé"):
        banque.modifier_question(IDENT, 1, instance["questions"][0])
    with pytest.raises(ValueError, match="inexistante"):
        banque.modifier_question(IDENT, 4, HYPOTENUSE_6_8)


def test_la_plus_recente_des_regeneration_et_modification_l_emporte():
    instance = exercice(regenerations=[{"question": 2, "date": "2026-10-17T10:00:00", "ancienne": {"enonce": "A"}}],
                        modifications=[{"question": 2, "date": "2026-10-17T11:00:00", "ancienne": {"enonce": "B"}},
                                       {"question": 3, "date": "2026-10-17T09:00:00", "ancienne": {"enonce": "C"}}])
    assert [(e["question"], e["nature"]) for e in banque.historique(instance)] == \
        [(3, "modification"), (2, "regeneration"), (2, "modification")]
    questions = banque.relecture(instance)["questions"]
    assert questions[1]["modifiee"] and not questions[1]["regeneree"]
    from generateur.outils.bilan_n4 import avant_regenerations
    origine = avant_regenerations(instance)["questions"]
    assert [origine[1]["enonce"], origine[2]["enonce"]] == ["A", "C"]  # défait à l'envers : la version de la chaîne


def test_une_question_du_programme_modifiee_n_est_plus_un_calcul_du_programme(dossiers):
    instance = generation.generer({"type": "qcm", "notion": "pourcentages", "niveau": "5e"}, "qcm", "maquette",
                                  graine=1)
    instance["meta"]["modifications"] = [{"question": 1, "date": "2026-10-17T10:00:00", "ancienne": {}}]
    questions = banque.relecture(instance)["questions"]
    assert questions[0]["calcul"] == "enseignant" and questions[1]["calcul"] == "programme"


def test_rechercher(dossiers):
    banque.ecrire(exercice())
    autre = exercice("qcm-revolution-4e-20261013-110000", "2026-10-13T11:00:00")
    autre.update(titre="La Révolution française", matiere="histoire-geo", notion="1789",
                 questions=[{"enonce": "En quelle année a lieu la prise de la Bastille ?", "propositions": ["1789", "1792",
                             "1815"], "index_correct": 0, "explication": "Le 14 juillet 1789."}] * 3)
    banque.ecrire(autre)
    assert [x["id"] for x in banque.lister(recherche="revolution")] == ["qcm-revolution-4e-20261013-110000"]
    assert [x["id"] for x in banque.lister(recherche="HYPOTÉNUSE 5 cm")] == [IDENT]  # énoncés, propositions
    assert banque.lister(recherche="hypoténuse révolution") == []  # chaque mot doit y être
    assert len(banque.lister(recherche="  ")) == 2


def test_supprimer(dossiers):
    _, page = banque.ecrire(exercice())
    destination = banque.supprimer(IDENT)
    assert destination == dossiers / "supprimes" / f"{IDENT}.json" and destination.exists()
    assert not page.exists() and banque.lister() == []
    with pytest.raises(banque.ExerciceInconnu):
        banque.supprimer(IDENT)


def test_un_exercice_accepte_ne_peut_pas_etre_supprime(dossiers):
    banque.ecrire(exercice(statut="accepte"))
    with pytest.raises(banque.SuppressionRefusee, match="rejeter"):
        banque.supprimer(IDENT)
    banque.decider(IDENT, "rejeter")
    assert banque.supprimer(IDENT).exists()
