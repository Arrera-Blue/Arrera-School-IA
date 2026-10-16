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
    instance = exercice(avertissements=["question 2 : deux mauvaises réponses de même valeur",
                                        "le titre reprend la notion"],
                        regenerations=[{"question": 3, "ancienne": {}}])
    relecture = banque.relecture(instance)
    assert [q["n4"] for q in relecture["questions"]] == ["a_relire", "verifie", "verifie"]
    assert relecture["questions"][1]["avertissements"] == ["question 2 : deux mauvaises réponses de même valeur"]
    assert relecture["avertissements"] == ["le titre reprend la notion"]
    assert [q["regeneree"] for q in relecture["questions"]] == [False, False, True]
    assert relecture["a_relire"] == 1 and relecture["procedural"] is False


def test_un_calcul_du_programme_n_est_jamais_a_relire(dossiers, monkeypatch):
    # essai du 16/10 : 3 questions de pourcentages annoncées « à relire », alors que le programme a fait le calcul
    instance = generation.generer({"type": "qcm", "notion": "pourcentages", "niveau": "5e"}, "qcm", "maquette",
                                  graine=1)
    instance["meta"]["validation"]["n4_questions"] = ["a_relire"] * len(instance["questions"])
    relecture = banque.relecture(instance)
    assert relecture["procedural"] and relecture["a_relire"] == 0
    assert all(q["calcul"] == "programme" for q in relecture["questions"])
    assert banque.resume(instance)["a_relire"] == 0
