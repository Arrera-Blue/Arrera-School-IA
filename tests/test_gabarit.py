"""Le gabarit du QCM (generateur/types/qcm/gabarit.html) : page autonome, hors ligne, faisable au clavier (E5).
Le parcours au clavier et la lecture à voix haute sont essayés dans Chrome : tests/navigateur/exercice.mjs."""

import json
import re

from generateur.moteur import registre, rendu


def page(**champs) -> str:
    instance = json.loads(json.dumps(registre.charger("qcm").exemple))
    instance.update(champs)
    return rendu.rendre(instance, "qcm")


def test_la_page_reste_hors_ligne():
    html = page()
    assert ('content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; img-src data:; '
            'media-src data:"' in html)
    # aucune adresse externe : ni script, ni feuille de style, ni image, ni lien
    assert not re.search(r"(src|href)\s*=\s*[\"']?(https?:)?//", html)


def test_la_carte_de_touches_est_affichable():
    html = page()
    assert 'id="btn-touches" aria-expanded="false" aria-controls="touches"' in html
    assert '<section id="touches" hidden' in html
    for touche in ("<kbd>A</kbd>", "<kbd>1</kbd>", "<kbd>→</kbd>", "<kbd>Entrée</kbd>", "<kbd>L</kbd>",
                   "<kbd>R</kbd>", "<kbd>?</kbd>"):
        assert touche in html


def test_un_bouton_ecouter_par_question_et_une_seule_question_en_cours():
    html = page()
    n = len(registre.charger("qcm").exemple["questions"])
    assert html.count('class="discret ecouter" hidden') == n  # affiché par le script, si le navigateur sait lire
    assert html.count('class="question courante"') == 1
    assert html.count('tabindex="-1" data-correct=') == n


def test_le_texte_du_modele_reste_du_texte():
    html = page(titre="<script>alert(1)</script>")
    assert "<script>alert(1)" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
