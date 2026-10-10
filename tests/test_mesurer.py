"""Phase 2 : le tableau des mesures par modèle et par machine (generateur/outils/mesurer.py)."""

import json
from pathlib import Path

from generateur.moteur import machine
from generateur.outils.mesurer import MODELE, PROCEDURAL, mesurer, rapport

VPS = {"systeme": "Linux x86_64", "processeur": "Intel Core Processor (Haswell, no TSX)", "coeurs": 4, "ram_go": 7.6}
MAC = {"systeme": "Darwin arm64", "processeur": "Apple M4 Pro", "coeurs": 12, "ram_go": 24.0}


def ecrire(chemin: Path, contenu: dict) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")


def appel(lus=3318, lecture=7.4, ecrits=531, ecriture=22.8, chargement=1.6, gpu=None) -> dict:
    a = {"tentative": 1, "tokens_lus": lus, "lecture_s": lecture, "tokens_ecrits": ecrits, "ecriture_s": ecriture,
         "chargement_s": chargement}
    return a if gpu is None else a | {"gpu": gpu}


def exercice(meta: dict, matiere="francais", questions=5) -> dict:
    return {"matiere": matiere, "questions": [{}] * questions, "meta": meta}


def test_meme_modele_sur_deux_machines_deux_lignes(tmp_path):
    # cas réel du 10/10 : le même GGUF met 395 s sur le VPS et 32 s sur le Mac ; les mélanger n'aurait aucun sens
    instances = tmp_path / "instances"
    base = {"fournisseur": "llamacpp", "modele": "gemma-4-E4B_q4_0-it.gguf", "tentatives": 1}
    ecrire(instances / "vps.json", exercice(base | {"machine": VPS, "date": "2026-10-10T14:55:34", "duree_s": 395.2,
                                                     "appels": [appel(lecture=204.2, ecrits=555, ecriture=183.9)]}))
    ecrire(instances / "mac.json", exercice(base | {"machine": MAC, "date": "2026-10-10T17:22:17", "duree_s": 31.9,
                                                     "appels": [appel(gpu=True)]}))

    mac, vps = mesurer(instances, tmp_path / "rejets")

    assert (mac.machine, vps.machine) == ("Apple M4 Pro, 12 cœurs, 24 Go",
                                          "Intel Core Processor (Haswell, no TSX), 4 cœurs, 7.6 Go")
    assert mac.durees == [31.9] and mac.par_question == [31.9 / 5] and mac.gpu == {True}
    assert round(mac.lecture[0]) == 448 and round(vps.lecture[0]) == 16
    tableau = rapport([mac, vps])
    assert "| oui |" in tableau and "| ? |" in tableau  # GPU : noté sur le Mac, inconnu avant


def test_rejets_comptes_et_taux_de_reussite(tmp_path):
    instances, rejets = tmp_path / "instances", tmp_path / "rejets"
    meta = {"fournisseur": "ollama", "modele": "gemma4:e4b-it-qat", "machine": VPS, "date": "2026-10-07T13:20:37"}
    ecrire(instances / "du-premier-coup.json", exercice(meta | {"tentatives": 1, "duree_s": 340}, "maths"))
    ecrire(instances / "repris.json", exercice(meta | {"tentatives": 3, "duree_s": 554}, "maths"))
    # un rejet garde ses champs à la racine, sans « meta » ; l'instance donne la matière et le nombre de questions
    ecrire(rejets / "rejete.json", meta | {"tentatives": 3, "duree_s": 514.1, "niveau": "N3",
                                           "instance": {"matiere": "maths", "questions": [{}] * 5}})
    ecrire(rejets / "illisible.json", meta | {"duree_s": 300, "niveau": "N1", "instance": None,
                                              "demande": {"matiere": "maths", "nb_questions": 10}})

    [g] = mesurer(instances, rejets)

    assert (g.premier_essai, g.apres_reprise, g.rejetees, g.generations) == (1, 1, 2, 4)
    # fichiers lus par ordre alphabétique : du-premier-coup, repris, puis illisible, rejete
    assert g.tentatives == [1, 3, 1, 3] and g.matieres == {"maths": 4}
    assert g.par_question[2] == 30  # N1 : le nombre de questions vient de la demande
    assert "| 1 (25%) | 1 | 2 | 2.0 |" in rapport([g])


def test_procedural_maquette_et_filtres(tmp_path):
    instances = tmp_path / "instances"
    ecrire(instances / "maquette.json", exercice({"fournisseur": "maquette", "modele": "exemple.json",
                                                  "date": "2026-10-06T20:29:42", "duree_s": 0.0}))
    ecrire(instances / "programme.json", exercice({"fournisseur": "procedural", "modele": None, "origine": "procedural",
                                                   "date": "2026-10-07T14:17:37", "duree_s": 0.0}, "maths"))
    ecrire(instances / "habille.json", exercice({"fournisseur": "ollama", "modele": "gemma4:e4b-it-qat",
                                                 "origine": "procedural", "date": "2026-10-08T08:13:54",
                                                 "duree_s": 108.0, "appels": [appel(chargement=0.0)]}, "maths"))
    ecrire(instances / "ancien.json", exercice({"fournisseur": "ollama", "modele": "qwen3:4b",
                                                "date": "2026-09-25T16:12:56", "duree_s": 231.1}, "maths"))

    groupes = mesurer(instances, tmp_path / "rejets")
    assert [(g.chemin, g.modele) for g in groupes] == [
        (MODELE, "qwen3:4b"), (PROCEDURAL, "aucun (programme seul)"), (PROCEDURAL, "gemma4:e4b-it-qat")]
    assert all(g.machine == "machine non relevée" for g in groupes)  # meta d'avant le 10/10
    assert groupes[2].chargements == []  # modèle déjà chargé : pas un chargement à froid

    assert [g.modele for g in mesurer(instances, tmp_path / "rejets", depuis="2026-10-08")] == ["gemma4:e4b-it-qat"]
    assert [g.chemin for g in mesurer(instances, tmp_path / "rejets", modele="gemma4:e4b-it-qat")] == [PROCEDURAL]
    assert "Aucune génération" in rapport([])


def test_machine_decrite_sans_rien_d_identifiant():
    decrite = machine.decrire()
    assert set(decrite) == {"systeme", "processeur", "coeurs", "ram_go"}
    assert decrite["coeurs"] and decrite["ram_go"] and decrite["ram_go"] > 0
    assert machine.libelle(MAC) == "Apple M4 Pro, 12 cœurs, 24 Go"
    assert machine.libelle({"systeme": "Linux x86_64"}) == "Linux x86_64"
    assert machine.libelle(None) == "machine non relevée"
