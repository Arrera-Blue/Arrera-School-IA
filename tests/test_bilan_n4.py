"""Outil du point de décision de N4 (docs/etapes/etape-1.3.md §8)."""

import json
from collections import Counter
from pathlib import Path

from generateur.moteur import registre
from generateur.moteur.validation.n4_calcul import A_RELIRE, FAUX, VERIFIE
from generateur.outils.bilan_n4 import Bilan, decision, mesurer, rapport

DONNEES = Path(__file__).parent / "donnees"


def ecrire(chemin: Path, contenu: dict) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")


def test_mesure_acceptes_et_rejetes(tmp_path):
    instances, rejets = tmp_path / "instances", tmp_path / "rejets"
    ecrire(instances / "pythagore.json", registre.charger("qcm").exemple)               # maths, accepté
    ecrire(instances / "histoire.json", {"matiere": "histoire-geo", "questions": []})   # ignoré
    fractions = json.loads((DONNEES / "qcm-fractions-6e-reel.json").read_text(encoding="utf-8"))
    ecrire(rejets / "fractions.json", {"niveau": "N3", "instance": fractions})           # maths, rejeté
    ecrire(rejets / "illisible.json", {"niveau": "N1", "instance": None, "demande": {"notion": "x"}})

    bilan = mesurer(instances, rejets)

    assert (bilan.acceptees, bilan.rejetees, bilan.rejets_non_mesurables) == (1, 1, 1)
    # exemple : à relire, vérifié, vérifié ; fractions : faux, vérifié, faux, faux, faux
    assert bilan.statuts == Counter({VERIFIE: 3, FAUX: 4, A_RELIRE: 1})
    assert "GÉNÉRATEUR PROCÉDURAL" in decision(bilan) and "indicatif" in decision(bilan)
    assert "Questions : 8" in rapport(bilan)


def test_nature_des_questions_fausses(tmp_path):
    # QCM du 25/09 : Q1, Q3, Q4 ont plusieurs bonnes réponses ; Q5 a une réponse annoncée fausse
    ecrire(tmp_path / "instances" / "f.json",
           json.loads((DONNEES / "qcm-fractions-6e-reel.json").read_text(encoding="utf-8")))
    bilan = mesurer(tmp_path / "instances", tmp_path / "rejets")
    assert bilan.faux_par_nature == Counter({"plusieurs bonnes réponses": 3, "réponse annoncée fausse": 1})
    assert "dont plusieurs bonnes réponses : 3" in rapport(bilan)
    assert "remesurer après la reprise" in decision(bilan)


def test_filtre_depuis_une_date(tmp_path):
    instances, rejets = tmp_path / "instances", tmp_path / "rejets"
    ancien = json.loads((DONNEES / "qcm-fractions-6e-reel.json").read_text(encoding="utf-8"))  # meta.date 25/09
    recent = json.loads((DONNEES / "qcm-fractions-6e-20261003-rejete-a-tort.json").read_text(encoding="utf-8"))
    ecrire(instances / "ancien.json", ancien)
    ecrire(rejets / "recent.json", {"date": "2026-10-03T14:09:14", "niveau": "N3", "instance": recent})

    tout = mesurer(instances, rejets)
    assert (tout.acceptees, tout.rejetees, tout.statuts[FAUX]) == (1, 1, 4)

    nouveau_prompt = mesurer(instances, rejets, depuis="2026-10-03")
    assert (nouveau_prompt.acceptees, nouveau_prompt.rejetees) == (0, 1)
    assert nouveau_prompt.statuts == Counter({VERIFIE: 5})


def test_dossiers_absents(tmp_path):
    bilan = mesurer(tmp_path / "rien", tmp_path / "rien non plus")
    assert bilan.questions == 0 and "aucune question" in decision(bilan)


def test_seuils_de_decision():
    def bilan(verifie: int, faux: int, a_relire: int) -> Bilan:
        return Bilan(acceptees=10, statuts=Counter({VERIFIE: verifie, FAUX: faux, A_RELIRE: a_relire}))

    assert decision(bilan(70, 5, 25)).startswith("garder la chaîne actuelle")
    assert "se trompe trop souvent" in decision(bilan(50, 25, 25))
    assert "ne vérifie pas assez" in decision(bilan(40, 15, 45))
    assert decision(bilan(55, 15, 30)).startswith("zone intermédiaire")
