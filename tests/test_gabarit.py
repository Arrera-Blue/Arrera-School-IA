"""Le gabarit du QCM (generateur/types/qcm/gabarit.html) : page autonome, hors ligne, faisable au clavier (E5), en jeu
(E7 : une question à la fois ; style « enfant » du CP à la 6e, « collège » de la 5e à la 3e).
Le parcours au clavier, les animations et la lecture à voix haute sont essayés dans Chrome : tests/navigateur/exercice.mjs."""

import json
import re

import pytest

from generateur.moteur import registre, rendu


def page(**champs) -> str:
    instance = json.loads(json.dumps(registre.charger("qcm").exemple))
    instance.update(champs)
    return rendu.rendre(instance, "qcm")


def test_la_page_reste_hors_ligne():
    html = page()
    assert ('content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; img-src data:; '
            'media-src data:; font-src data:"' in html)
    # aucune adresse externe : ni script, ni feuille de style, ni image, ni police, ni lien
    assert not re.search(r"(src|href)\s*=\s*[\"']?(https?:)?//", html)
    assert not re.search(r"url\(\s*[\"']?(https?:)?//", html)


def test_la_carte_de_touches_est_affichable():
    html = page()
    assert 'id="btn-touches" aria-expanded="false" aria-controls="touches"' in html
    assert '<section class="carte aide" id="touches" hidden' in html
    for touche in ("<kbd>A</kbd>", "<kbd>1</kbd>", "<kbd>→</kbd>", "<kbd>Entrée</kbd>", "<kbd>L</kbd>",
                   "<kbd>R</kbd>", "<kbd>?</kbd>"):
        assert touche in html


def test_une_question_a_la_fois_et_un_bouton_ecouter_par_question():
    html = page()
    n = len(registre.charger("qcm").exemple["questions"])
    assert html.count('class="bouton-rond ecouter" hidden') == n  # affiché par le script, si le navigateur sait lire
    # toutes cachées au départ : le script montre la première, puis une à la fois
    assert len(re.findall(r'<section class="question" id="question-\d+" data-correct="\d" [^>]*hidden>', html)) == n


@pytest.mark.parametrize("niveau, style", [("CP", "enfant"), ("CE1", "enfant"), ("CE2", "enfant"), ("6e", "enfant"),
                                           ("5e", "college"), ("4e", "college"), ("3e", "college")])
def test_le_style_suit_le_niveau(niveau, style):
    html = page(niveau=niveau)
    assert f'<body data-style="{style}">' in html
    if style == "enfant":
        assert 'font-family: "Andika"' in html and 'id="compagnon"' in html and 'class="rideau vague"' in html
        assert 'id="points"' not in html and 'font-family: "Atkinson Hyperlegible"' not in html
    else:
        assert 'font-family: "Atkinson Hyperlegible"' in html and 'class="rideau balayage"' in html and 'id="points"' in html
        assert 'id="compagnon"' not in html and 'font-family: "Andika"' not in html


@pytest.mark.parametrize("niveau, d_office", [("CP", True), ("CE1", True), ("CE2", False), ("6e", False), ("5e", False)])
def test_au_cp_et_au_ce1_un_ecran_commencer_puis_la_lecture_d_office(niveau, d_office):
    """Cycle 2, décision 9 (étape 1.5 du lot 1) : au CP et au CE1, l'écran « Commencer » d'abord (le clic autorise le
    son), la case « Lire les questions à voix haute » cochée d'office ; la question cachée derrière. Ailleurs, rien ne
    change : l'exercice commence dès l'ouverture."""
    html = page(niveau=niveau)
    assert ('id="ecran-depart"' in html) is d_office
    assert ('<section class="carte" id="ecran-question" hidden>' in html) is d_office
    assert ('<section class="carte" id="ecran-question">' in html) is not d_office
    if d_office:
        assert '<input type="checkbox" id="lire-auto" checked>' in html and 'id="btn-commencer"' in html


def test_les_polices_sont_rangees_dans_la_page():
    polices = rendu.polices(registre.charger("qcm").dossier)
    assert set(polices) == {"andika-400", "andika-700", "atkinson-400", "atkinson-700"}
    html = page(niveau="6e")
    assert html.count("url(data:font/woff2;base64,") == 2  # seulement la police du style de la page
    assert polices["andika-400"][:40] in html and polices["atkinson-400"][:40] not in html


def test_le_texte_du_modele_reste_du_texte():
    html = page(titre="<script>alert(1)</script>")
    assert "<script>alert(1)" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
