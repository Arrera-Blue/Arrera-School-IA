"""La voix des exercices (generateur/moteur/lecture.py) : Piper sur le PC enseignant, MP3 rangés dans la page (E5).
Une fausse voix sert aux tests ; un dernier test essaie la vraie, si elle est installée (modeles/piper/)."""

import base64
import json
import re

import pytest

from generateur.moteur import config, lecture, registre, rendu

VRAIE_VOIX = lecture.voix  # conftest.py la remplace par « aucune voix » pour tous les autres tests
SIWIS = config.RACINE / "modeles/piper/fr_FR-siwis-medium.onnx"


@pytest.fixture
def fausse_voix(tmp_path, monkeypatch):
    """Une voix qui « prononce » le texte en le recopiant, et compte ses appels ; le cache dans tmp_path."""
    appels = []

    def synthetiser(texte):
        appels.append(texte)
        return f"MP3:{texte}".encode()

    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: tmp_path / "lecture" if nom == "lecture" else vrai_chemin(nom))
    monkeypatch.setattr(lecture, "voix", lambda: lecture.Voix("essai", synthetiser))
    return appels


def exercice(**champs) -> dict:
    instance = json.loads(json.dumps(registre.charger("qcm").exemple))
    instance.update(champs)
    return instance


def lu(audio: dict, cle: str) -> str:
    return base64.b64decode(audio["clips"][cle]).decode().removeprefix("MP3:")


@pytest.mark.parametrize("ecrit, dit", [
    ("Quelle fraction est égale à 3/4 ?", "Quelle fraction est égale à 3 sur 4 ?"),
    ("3 / 4 de 120", "3 sur 4 de 120"),
    ("5² = 25", "5 au carré = 25"),
    ("2³", "2 au cube"),
    ("6 × 7", "6 fois 7"),
    ("18 ÷ 2 = 9", "18 divisé par 2 = 9"),
    ("le 14/07, et/ou", "le 14 sur 07, et/ou"),  # une date est lue comme une fraction : limite connue
])
def test_les_maths_sont_dites_en_mots(ecrit, dit):
    assert lecture.prononcable(ecrit) == dit


def test_un_morceau_par_texte_dans_l_ordre_d_origine(fausse_voix):
    instance = exercice()
    audio = lecture.pour_la_page(instance)
    n = len(instance["questions"])
    assert len(audio["questions"]) == n
    for i, (q, voix) in enumerate(zip(instance["questions"], audio["questions"]), start=1):
        assert lu(audio, voix["titre"]) == f"Question {i} sur {n}."
        assert lu(audio, voix["enonce"]) == lecture.prononcable(q["enonce"])
        # dans l'ordre du JSON : la page les remet dans l'ordre affiché (mélangé)
        assert [lu(audio, c) for c in voix["propositions"]] == [lecture.prononcable(p) for p in q["propositions"]]
        assert lu(audio, voix["explication"]) == lecture.prononcable(q["explication"])
    assert lu(audio, audio["fixes"]["choisie_B"]) == "Ta réponse : B."
    assert lu(audio, audio["fixes"]["bonne_D"]) == "La bonne réponse est D."
    assert lu(audio, audio["fixes"]["lettre_A"]) == "A :"


def test_un_texte_repete_n_est_range_qu_une_fois(fausse_voix):
    instance = exercice()
    for q in instance["questions"]:
        q["propositions"][0] = "Aucune de ces réponses"
    audio = lecture.pour_la_page(instance)
    cles = {voix["propositions"][0] for voix in audio["questions"]}
    assert len(cles) == 1 and fausse_voix.count("Aucune de ces réponses") == 1
    assert len(audio["clips"]) == len(set(fausse_voix))


def test_seules_les_lettres_utiles(fausse_voix):
    instance = exercice()
    for q in instance["questions"]:
        q["propositions"] = q["propositions"][:3]
        q["index_correct"] = min(q["index_correct"], 2)
    fixes = lecture.pour_la_page(instance)["fixes"]
    assert "lettre_C" in fixes and "lettre_D" not in fixes and "bonne_D" not in fixes


def test_une_voix_deja_faite_n_est_pas_refaite(fausse_voix, tmp_path):
    premiere = lecture.pour_la_page(exercice())
    appels = len(fausse_voix)
    assert len(list((tmp_path / "lecture").glob("*.mp3"))) == appels
    assert not list((tmp_path / "lecture").glob(".*.tmp"))  # écriture atomique
    seconde = lecture.pour_la_page(exercice())
    assert len(fausse_voix) == appels and seconde == premiere


def test_une_voix_en_panne_ne_fait_pas_echouer_le_rendu(monkeypatch, tmp_path, capsys):
    def en_panne(texte):
        raise RuntimeError("onnxruntime")

    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: tmp_path / nom if nom == "lecture" else vrai_chemin(nom))
    monkeypatch.setattr(lecture, "voix", lambda: lecture.Voix("panne", en_panne))
    assert lecture.pour_la_page(exercice()) is None
    assert "synthèse impossible (RuntimeError : onnxruntime) ; la page utilisera la voix du navigateur" in capsys.readouterr().err
    html = rendu.rendre(exercice(), "qcm")
    assert 'id="voix-rangee"' not in html and "Le théorème de Pythagore" in html


def test_la_page_range_la_voix_sans_qu_un_texte_puisse_en_sortir(fausse_voix):
    piege = "</script><script>alert(1)</script>"
    instance = exercice()
    instance["questions"][0]["enonce"] = f"Qui a écrit {piege} ?"
    html = rendu.rendre(instance, "qcm")
    bloc = re.search(r'<script type="application/json" id="voix-rangee">(.*?)</script>', html, re.S).group(1)
    audio = json.loads(bloc)
    assert lu(audio, audio["questions"][0]["enonce"]) == f"Qui a écrit {piege} ?"
    assert "<script>alert(1)" not in html


def test_sans_voix_demandee_rien_n_est_range(fausse_voix):
    assert 'id="voix-rangee"' not in rendu.rendre(exercice(), "qcm", voix=False) and not fausse_voix


@pytest.mark.parametrize("reglage, message", [
    ({}, None),
    ({"voix": ""}, None),
    ({"voix": "modeles/piper/absente.onnx"}, "voix introuvable (modeles/piper/absente.onnx)"),
])
def test_sans_voix_utilisable_la_page_garde_la_voix_du_navigateur(monkeypatch, capsys, reglage, message):
    monkeypatch.setattr(config, "charger", lambda: {"lecture": reglage})
    VRAIE_VOIX.cache_clear()
    try:
        assert VRAIE_VOIX() is None
    finally:
        VRAIE_VOIX.cache_clear()
    erreur = capsys.readouterr().err
    assert (message in erreur) if message else not erreur


@pytest.mark.skipif(not SIWIS.exists(), reason="voix siwis absente de modeles/piper/")
def test_la_vraie_voix(monkeypatch, tmp_path, capsys):
    pytest.importorskip("piper")
    for reglage, attendu in (({"voix": str(SIWIS.relative_to(config.RACINE)), "lenteur": 1.1}, True),
                             ({"voix": str(SIWIS.relative_to(config.RACINE)), "locuteur": "pierre"}, False)):
        monkeypatch.setattr(config, "charger", lambda: {"lecture": reglage})
        VRAIE_VOIX.cache_clear()
        try:
            voix = VRAIE_VOIX()
        finally:
            VRAIE_VOIX.cache_clear()
        if not attendu:  # siwis n'a qu'un locuteur
            assert voix is None and "locuteur « pierre » absent de la voix" in capsys.readouterr().err
            continue
        son = voix.synthetiser("Bonjour.")
        assert son[:3] == b"ID3" or son[0] == 0xFF  # un fichier MP3
        assert 2_000 < len(son) < 20_000
