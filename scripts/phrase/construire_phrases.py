"""La table des phrases (lot 1, étape 1.3 : docs/Generateur-Procedural/lot-1-francais.md §5), écrite à la main par
Claude (décision 3 : environ 60 phrases) : `francais/phrases`.

Chaque phrase : son type (déclarative, interrogative, impérative), si elle est négative, si elle est exclamative (des
« formes » dans le programme du cycle 2), si son signe final est imposé par un mot (« Où … ? », « Quel … ! » : seules
celles-là servent à la question de ponctuation), et **la nature de chacun de ses mots** dans la phrase (le monde fermé,
mot par mot : « Le/determinant petit/adjectif chat/nom dort/verbe »). Aucun prénom (il pourrait être celui d'un
élève) : les noms propres sont des villes ou des fleuves.

Les natures : determinant, nom, nom_propre, adjectif, verbe, pronom (personnel), adverbe ; et, jamais interrogées,
preposition, negation (ne, n', pas, jamais), interrogatif (où, quand, qui), exclamatif (comme, que).

Usage : python -I construire_phrases.py <generateur/procedural/donnees>
Puis : verifier_phrases.py (la nature de chaque mot comparée aux catégories de Lexique 3)."""
import sys
from pathlib import Path

import yaml

# (mots annotés, type, négative, exclamative, signe imposé, depuis) ; la phrase s'écrit à partir des mots
PHRASES = [
    # déclaratives
    ("Le/determinant chat/nom dort/verbe .", "declarative", "non", "non", "non", "CP"),
    ("Le/determinant petit/adjectif chien/nom court/verbe .", "declarative", "non", "non", "non", "CP"),
    ("La/determinant maman/nom lit/verbe un/determinant livre/nom .", "declarative", "non", "non", "non", "CP"),
    ("Les/determinant enfants/nom jouent/verbe dans/preposition la/determinant cour/nom .", "declarative", "non", "non",
     "non", "CP"),
    ("Il/pronom mange/verbe une/determinant pomme/nom rouge/adjectif .", "declarative", "non", "non", "non", "CP"),
    ("Nous/pronom allons/verbe à/preposition l'/determinant école/nom .", "declarative", "non", "non", "non", "CP"),
    ("Elle/pronom chante/verbe une/determinant jolie/adjectif chanson/nom .", "declarative", "non", "non", "non", "CP"),
    ("Le/determinant soleil/nom brille/verbe .", "declarative", "non", "non", "non", "CP"),
    ("Mon/determinant frère/nom a/verbe un/determinant vélo/nom bleu/adjectif .", "declarative", "non", "non", "non",
     "CP"),
    ("La/determinant fleur/nom est/verbe belle/adjectif .", "declarative", "non", "non", "non", "CP"),
    ("Les/determinant oiseaux/nom chantent/verbe le/determinant matin/nom .", "declarative", "non", "non", "non", "CP"),
    ("Tu/pronom as/verbe un/determinant gros/adjectif chien/nom .", "declarative", "non", "non", "non", "CP"),
    ("Le/determinant train/nom arrive/verbe vite/adverbe .", "declarative", "non", "non", "non", "CE2"),
    ("Paris/nom_propre est/verbe une/determinant grande/adjectif ville/nom .", "declarative", "non", "non", "non", "CE1"),
    ("La/determinant Loire/nom_propre est/verbe un/determinant long/adjectif fleuve/nom .", "declarative", "non", "non",
     "non", "CE1"),
    ("Le/determinant bébé/nom pleure/verbe fort/adverbe .", "declarative", "non", "non", "non", "CE2"),
    ("Vous/pronom parlez/verbe bien/adverbe .", "declarative", "non", "non", "non", "CE2"),
    ("Lyon/nom_propre est/verbe une/determinant belle/adjectif ville/nom .", "declarative", "non", "non", "non", "CE1"),
    ("La/determinant neige/nom tombe/verbe doucement/adverbe .", "declarative", "non", "non", "non", "CE2"),
    ("Ils/pronom aiment/verbe les/determinant gâteaux/nom .", "declarative", "non", "non", "non", "CP"),
    ("Ma/determinant sœur/nom porte/verbe une/determinant robe/nom verte/adjectif .", "declarative", "non", "non", "non",
     "CP"),
    ("Le/determinant facteur/nom passe/verbe tôt/adverbe .", "declarative", "non", "non", "non", "CE2"),
    # négatives
    ("Le/determinant chat/nom ne/negation dort/verbe pas/negation .", "declarative", "oui", "non", "non", "CP"),
    ("Je/pronom ne/negation mange/verbe pas/negation .", "declarative", "oui", "non", "non", "CP"),
    ("Elle/pronom ne/negation chante/verbe pas/negation .", "declarative", "oui", "non", "non", "CP"),
    ("Nous/pronom ne/negation jouons/verbe pas/negation dehors/adverbe .", "declarative", "oui", "non", "non", "CE2"),
    ("Il/pronom n'/negation aime/verbe pas/negation la/determinant soupe/nom .", "declarative", "oui", "non", "non",
     "CP"),
    ("Les/determinant enfants/nom ne/negation crient/verbe pas/negation .", "declarative", "oui", "non", "non", "CP"),
    ("Tu/pronom ne/negation viens/verbe jamais/negation .", "declarative", "oui", "non", "non", "CP"),
    ("Le/determinant bus/nom n'/negation arrive/verbe pas/negation .", "declarative", "oui", "non", "non", "CP"),
    ("Mon/determinant ami/nom ne/negation lit/verbe pas/negation .", "declarative", "oui", "non", "non", "CP"),
    ("La/determinant porte/nom n'/negation est/verbe pas/negation ouverte/adjectif .", "declarative", "oui", "non",
     "non", "CP"),
    ("Vous/pronom ne/negation parlez/verbe pas/negation .", "declarative", "oui", "non", "non", "CP"),
    ("Le/determinant chien/nom n'/negation est/verbe pas/negation méchant/adjectif .", "declarative", "oui", "non",
     "non", "CP"),
    # interrogatives
    ("Où/interrogatif est/verbe le/determinant chat/nom ?", "interrogative", "non", "non", "oui", "CP"),
    ("Tu/pronom viens/verbe ?", "interrogative", "non", "non", "non", "CP"),
    ("Quand/interrogatif part/verbe le/determinant train/nom ?", "interrogative", "non", "non", "oui", "CP"),
    ("Où/interrogatif vont/verbe les/determinant enfants/nom ?", "interrogative", "non", "non", "oui", "CP"),
    ("Qui/interrogatif mange/verbe la/determinant pomme/nom ?", "interrogative", "non", "non", "oui", "CP"),
    ("Qui/interrogatif a/verbe un/determinant vélo/nom ?", "interrogative", "non", "non", "oui", "CP"),
    ("Tu/pronom aimes/verbe les/determinant bonbons/nom ?", "interrogative", "non", "non", "non", "CP"),
    ("Où/interrogatif est/verbe ma/determinant gomme/nom ?", "interrogative", "non", "non", "oui", "CP"),
    ("Qui/interrogatif chante/verbe ?", "interrogative", "non", "non", "oui", "CP"),
    ("Vous/pronom venez/verbe demain/adverbe ?", "interrogative", "non", "non", "non", "CE2"),
    # impératives
    ("Range/verbe ta/determinant chambre/nom .", "imperative", "non", "non", "non", "CP"),
    ("Ferme/verbe la/determinant porte/nom .", "imperative", "non", "non", "non", "CP"),
    ("Mange/verbe ta/determinant soupe/nom .", "imperative", "non", "non", "non", "CP"),
    ("Écoute/verbe la/determinant maîtresse/nom .", "imperative", "non", "non", "non", "CP"),
    ("Viens/verbe ici/adverbe .", "imperative", "non", "non", "non", "CE2"),
    ("Prends/verbe ton/determinant cartable/nom .", "imperative", "non", "non", "non", "CP"),
    ("Ne/negation cours/verbe pas/negation .", "imperative", "oui", "non", "non", "CP"),
    ("Lave/verbe tes/determinant mains/nom .", "imperative", "non", "non", "non", "CP"),
    ("Regarde/verbe le/determinant ciel/nom .", "imperative", "non", "non", "non", "CP"),
    ("Ne/negation touche/verbe pas/negation le/determinant feu/nom .", "imperative", "oui", "non", "non", "CP"),
    # exclamatives (des « formes » dans le programme : jamais pour la question de type)
    ("Quel/determinant beau/adjectif jardin/nom !", "declarative", "non", "oui", "oui", "CP"),
    ("Comme/exclamatif il/pronom fait/verbe chaud/adjectif !", "declarative", "non", "oui", "oui", "CP"),
    ("Quelle/determinant belle/adjectif robe/nom !", "declarative", "non", "oui", "oui", "CP"),
    ("Que/exclamatif tu/pronom es/verbe grand/adjectif !", "declarative", "non", "oui", "oui", "CP"),
    ("Le/determinant gâteau/nom est/verbe délicieux/adjectif !", "declarative", "non", "oui", "non", "CP"),
    ("Quel/determinant joli/adjectif chat/nom !", "declarative", "non", "oui", "oui", "CP"),
    ("Comme/exclamatif la/determinant mer/nom est/verbe belle/adjectif !", "declarative", "non", "oui", "oui", "CP"),
    ("Elle/pronom court/verbe vite/adverbe !", "declarative", "non", "oui", "non", "CE2"),
]
NATURES = ["determinant", "nom", "nom_propre", "adjectif", "verbe", "pronom", "adverbe", "preposition", "negation",
           "interrogatif", "exclamatif"]


def ecrite(mots: str) -> str:
    """« Il/pronom n'/negation aime/verbe pas/negation . » → « Il n'aime pas. »"""
    texte = ""
    for jeton in mots.split():
        mot = jeton.split("/")[0]
        if jeton in (".", "?", "!"):
            texte += ("." if jeton == "." else f" {jeton}")  # « ? » et « ! » après une espace (insécable à l'écrit)
        elif texte and not texte.endswith("'"):
            texte += " " + mot
        else:
            texte += mot
    return texte


def ecrire(dossier: Path) -> None:
    lignes = [{"phrase": ecrite(m), "mots": m, "type": t, "negative": neg, "exclamative": exc, "signe_impose": sig,
               "depuis": d, "source": "claude"} for m, t, neg, exc, sig, d in PHRASES]
    donnees = {
        "description": "Des phrases simples, courtes : leur type, si elles sont négatives ou exclamatives (des formes, "
                       "pour le programme du cycle 2), si leur signe final est imposé par un mot, et la nature de "
                       "chacun de leurs mots dans la phrase (« mots » : mot/nature, le signe final à part). Aucun "
                       "prénom : les noms propres sont des villes ou des fleuves.",
        "sources": {"claude": {"nom": "Phrases écrites par Claude ; la nature de chaque mot comparée aux catégories "
                                      "de Lexique 3.83", "url": "http://www.lexique.org", "consulte": "2026-11-12",
                               "licence": "CC BY-SA 4.0 (Lexique 3), pour la comparaison seulement"}},
        "proprietes": {"phrase": "texte", "mots": "texte", "type": ["declarative", "interrogative", "imperative"],
                       "negative": ["oui", "non"], "exclamative": ["oui", "non"], "signe_impose": ["oui", "non"],
                       "depuis": ["CP", "CE1", "CE2"]},
        "cle": ["phrase"],
        "lignes": lignes,
    }
    entete = ("# Table de référence (générateur procédural du français, lot 1, étape 1.3), écrite par Claude avec\n"
              "# scripts/phrase/construire_phrases.py, comparée à Lexique 3.83 (scripts/phrase/verifier_phrases.py).\n"
              "# À relire par l'utilisateur : python -m generateur.procedural.tables relire francais/phrases --par \"…\"\n")
    (dossier / "francais").mkdir(parents=True, exist_ok=True)
    (dossier / "francais" / "phrases.yaml").write_text(
        entete + yaml.safe_dump(donnees, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")
    print(f"francais/phrases.yaml : {len(lignes)} phrases")


if __name__ == "__main__":
    ecrire(Path(sys.argv[1]))
