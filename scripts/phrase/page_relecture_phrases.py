"""La page de relecture de la table des phrases (lot 1, étape 1.3) : chaque phrase, son type, ses formes, et la
nature de chacun de ses mots, pour que l'enseignant la relise avant de la valider.

Usage : python -I page_relecture_phrases.py <generateur/procedural/donnees> <page.md>"""
import sys
from pathlib import Path

import yaml

donnees, page = Path(sys.argv[1]), Path(sys.argv[2])
phrases = yaml.safe_load((donnees / "francais" / "phrases.yaml").read_text(encoding="utf-8"))["lignes"]
NATURES = {"determinant": "dét.", "nom": "nom", "nom_propre": "nom propre", "adjectif": "adj.", "verbe": "verbe",
           "pronom": "pronom", "adverbe": "adverbe", "preposition": "(prép.)", "negation": "(négation)",
           "interrogatif": "(interrogatif)", "exclamatif": "(exclamatif)"}
TYPES = {"declarative": "déclarative", "interrogative": "interrogative", "imperative": "impérative"}
t = ["# Relecture : la table des phrases (`francais/phrases`)", "",
     f"> Page générée depuis la table ({len(phrases)} phrases). **À relire, puis à valider** (depuis `Arrera-School-IA`) :",
     "> `.venv/bin/python -m generateur.procedural.tables relire francais/phrases --par \"…\"`.",
     "> Chaque nature a déjà été comparée aux catégories que Lexique 3.83 donne au mot (255 mots, 0 écart) ; mais",
     "> **la nature dans la phrase** (« court » : verbe ou adjectif ?), c'est votre relecture qui la garantit.",
     "> Les natures entre parenthèses ne sont jamais demandées aux élèves. « Signe imposé » : un mot impose le point",
     "> final (« Où … ? », « Quel … ! ») ; seules ces phrases servent à la question « quel signe termine la phrase ».",
     "> Au CP, on demande : déterminant, nom, adjectif, verbe, pronom ; au CE1, aussi le nom propre ; au CE2, l'adverbe.",
     "", "| Phrase | Type | Formes | Signe imposé | Classe | Nature des mots |", "|---|---|---|---|---|---|"]
for p in phrases:
    formes = ", ".join(f for f, oui in (("négative", p["negative"]), ("exclamative", p["exclamative"])) if oui == "oui")
    natures = " · ".join(f"{m} *{NATURES[n]}*" for m, n in (j.split("/") for j in p["mots"].split() if "/" in j))
    t.append(f"| {p['phrase']} | {TYPES[p['type']]} | {formes or 'affirmative'} | {p['signe_impose']} | "
             f"dès le {p['depuis']} | {natures} |")
page.parent.mkdir(parents=True, exist_ok=True)
page.write_text("\n".join(t) + "\n", encoding="utf-8")
print(f"{page} : {len(phrases)} phrases")
