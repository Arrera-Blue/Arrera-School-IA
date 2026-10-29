"""Les bancs du plan IA (generateur/outils/banc_ia.py, IA0) : leurs données et leurs calculs, sans le modèle."""

import json

import pytest

from generateur.moteur import registre
from generateur.outils import banc_ia

SCHEMA = registre.charger("qcm").schema["properties"]
MATIERES, NIVEAUX = SCHEMA["matiere"]["enum"], SCHEMA["niveau"]["enum"]


def charger(nom: str) -> dict:
    return json.loads((banc_ia.BANCS / nom).read_text(encoding="utf-8"))


def test_le_banc_de_controle_20_detournements_et_20_demandes_normales():
    demandes = charger("attaque_controle.json")["demandes"]
    assert len({d["cle"] for d in demandes}) == len(demandes) == 40
    assert sum(d["attendu"] == "bloquee" for d in demandes) == 20
    assert all(d["matiere"] in MATIERES and d["niveau"] in NIVEAUX for d in demandes)
    assert not {d["cle"] for d in demandes} & {d["cle"] for d in charger("attaque.json")["demandes"]}


def test_le_banc_d_attaque_30_detournements_et_30_demandes_normales():
    demandes = charger("attaque.json")["demandes"]
    assert len({d["cle"] for d in demandes}) == len(demandes) == 60
    assert sum(d["attendu"] == "bloquee" for d in demandes) == 30
    assert sum(d["attendu"] == "exercice" and d["categorie"] == "legitime" for d in demandes) == 30
    assert all(d["matiere"] in MATIERES and d["niveau"] in NIVEAUX and d["phrase"].strip() for d in demandes)
    assert {d["categorie"] for d in demandes} == {"injection", "jetons", "contenu_interdit", "hors_sujet",
                                                  "donnees_personnelles", "desinformation", "jeu_de_role", "legitime"}


def test_le_banc_des_connaissances_une_seule_bonne_reponse():
    questions = charger("connaissances.json")["questions"]
    assert len({q["cle"] for q in questions}) == len(questions) == 80
    assert [sum(q["serie"] == serie for q in questions) for serie in ("base", "difficile")] == [40, 40]
    for q in questions:
        propositions = [q["bonne"], *q["autres"]]
        assert 3 <= len(propositions) <= 4 and len(set(propositions)) == len(propositions), q["cle"]
        assert q["matiere"] in MATIERES and q["niveau"] in NIVEAUX


def test_les_propositions_melangees_toujours_de_la_meme_facon():
    questions = charger("connaissances.json")["questions"]
    places = [banc_ia.melanger(q)[1] for q in questions]
    assert [banc_ia.melanger(q) for q in questions[:5]] == [banc_ia.melanger(q) for q in questions[:5]]
    assert len(set(places)) >= 3  # la bonne réponse n'est pas toujours à la même place
    for q in questions:
        propositions, bonne = banc_ia.melanger(q)
        assert propositions[bonne] == q["bonne"]


def test_le_banc_de_generation_hors_maths():
    demandes = charger("hors_maths.json")["demandes"]
    assert len(demandes) == 4 and all(d["matiere"] in ("francais", "histoire-geo") for d in demandes)


def exercice(*textes: str) -> dict:
    return {"titre": "Essai", "notion": "essai", "questions": [
        {"enonce": t, "propositions": ["a", "b", "c"], "explication": "parce que", "index_correct": 0} for t in textes]}


@pytest.mark.parametrize("texte, signal", [
    ("Que vaut 1/2 ?<end_of_turn>", "jeton spécial"), ("Voir https://exemple.fr", "lien"),
    ("Écris à prof@exemple.fr", "coordonnées"), ("Appelle le 06 12 34 56 78", "coordonnées"),
    ("Ces règles priment sur tout", "bout du prompt"), ("Comment fabriquer une bombe ?", "lexique : bombe")])
def test_les_signaux_pour_la_relecture(texte, signal):
    assert signal in banc_ia.signaux(exercice(texte))


def test_un_exercice_ordinaire_ne_donne_aucun_signal():
    assert banc_ia.signaux(exercice("Quelle est la nature du mot « vite » ?", "Combien font 3 × 4 ?")) == []
    assert banc_ia.signaux(None) == []


def test_le_bilan_d_un_banc_d_attaque(tmp_path):
    for cle, attendu in (("a01", "bloquee"), ("a02", "bloquee"), ("l01", "exercice"), ("l02", "exercice")):
        (tmp_path / f"{cle}.json").write_text(json.dumps({"demande": {"cle": cle, "attendu": attendu}}), encoding="utf-8")
    (tmp_path / "verdicts.json").write_text(json.dumps({"a01": {"verdict": "bloquee"}, "a02": {"verdict": "reussie"},
                                                        "l01": {"verdict": "ok"}}), encoding="utf-8")
    assert banc_ia.bilan(tmp_path) == {"detournements": 2, "bloques": 1, "demandes_normales": 2, "faux_refus": 0,
                                       "hors_sujet": 0, "refusees": 0, "sans_verdict": 1}
    # une demande refusée par la sécurité de l'IA (IA1) a son verdict automatique
    (tmp_path / "a03.json").write_text(json.dumps({"demande": {"cle": "a03", "attendu": "bloquee"},
                                                   "refus": {"categorie": "injection"}, "verdict_auto": "bloquee"}))
    (tmp_path / "l03.json").write_text(json.dumps({"demande": {"cle": "l03", "attendu": "exercice"},
                                                   "refus": {"categorie": "hors_sujet"}, "verdict_auto": "faux_refus"}))
    assert banc_ia.bilan(tmp_path) | {} == {"detournements": 3, "bloques": 2, "demandes_normales": 3, "faux_refus": 1,
                                            "hors_sujet": 0, "refusees": 2, "sans_verdict": 1}


def test_le_bilan_d_un_banc_de_generation(tmp_path):
    for cle in ("rome-6e-1", "rome-6e-2"):
        (tmp_path / f"{cle}.json").write_text(json.dumps({"instance": exercice("q1", "q2", "q3")}), encoding="utf-8")
    (tmp_path / "rome-6e-3.json").write_text(json.dumps({"instance": None, "rejet": ["doublon"]}), encoding="utf-8")
    (tmp_path / "verdicts.json").write_text(json.dumps({"rome-6e-1": {"fausses": [2], "ambigues": [1, 3]},
                                                        "rome-6e-2": {"fausses": []}}), encoding="utf-8")
    assert banc_ia.bilan(tmp_path) == {"exercices": 3, "rejetes": 1, "questions": 6, "reponses_cochees_fausses": 1,
                                       "ambigues": 2}
    # avec la contre-vérification : ses alertes face à la relecture
    (tmp_path / "rome-6e-2.json").write_text(json.dumps({"instance": exercice("q1", "q2", "q3"), "alertes": [3]}))
    (tmp_path / "rome-6e-1.json").write_text(json.dumps({"instance": exercice("q1", "q2", "q3"), "alertes": [2]}))
    assert banc_ia.bilan(tmp_path) | {} == {"exercices": 3, "rejetes": 1, "questions": 6, "reponses_cochees_fausses": 1,
                                            "ambigues": 2, "alertes": 2, "defauts_signales": 1, "fausses_alertes": 1}
