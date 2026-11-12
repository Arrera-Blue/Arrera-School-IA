"""Le second contrôle de la table des phrases (lot 1, étape 1.3) : la nature déclarée de chaque mot doit être l'une
des catégories que Lexique 3.83 donne à ce mot (http://www.lexique.org, CC BY-SA 4.0 : téléchargé à part).

Ce contrôle ne prouve pas la nature dans la phrase (« court » est un verbe ou un adjectif) : il attrape une nature
impossible (« chat/verbe »). La nature dans la phrase, c'est la relecture de l'enseignant qui la garantit. Les noms
propres ne sont pas dans Lexique : vérifiés seulement par leur majuscule.

Usage : python -I verifier_phrases.py <Lexique383.tsv> <generateur/procedural/donnees>"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

import yaml

lexique, donnees = Path(sys.argv[1]), Path(sys.argv[2])
categories = defaultdict(set)
with open(lexique, encoding="utf-8") as f:
    for ligne in csv.DictReader(f, delimiter="\t"):
        categories[ligne["ortho"]].add(ligne["cgram"])

# la nature du projet → les catégories de Lexique qui la permettent
PERMISES = {
    "determinant": {"ART:def", "ART:ind", "ADJ:pos", "ADJ:dem", "ADJ:int", "ADJ:num", "ADJ:ind"},
    "nom": {"NOM"}, "adjectif": {"ADJ"}, "verbe": {"VER", "AUX"}, "pronom": {"PRO:per"},
    "adverbe": {"ADV"}, "preposition": {"PRE"}, "negation": {"ADV"},
    "interrogatif": {"ADV", "ADV:int", "PRO:int", "CON"}, "exclamatif": {"ADV", "CON", "PRO:rel", "ADV:int"},
}
ELISIONS = {"l'": ("le", "la"), "n'": ("ne",)}

phrases = yaml.safe_load((donnees / "francais" / "phrases.yaml").read_text(encoding="utf-8"))["lignes"]
ecarts, n = [], 0
for p in phrases:
    for jeton in p["mots"].split():
        if "/" not in jeton:
            continue  # le signe final
        mot, nature = jeton.split("/")
        n += 1
        if nature == "nom_propre":
            if not mot[0].isupper():
                ecarts.append(f"« {p['phrase']} » : {mot} (nom propre) sans majuscule")
            continue
        formes = ELISIONS.get(mot.lower(), (mot.lower(), mot.replace("œ", "oe").lower()))
        trouvees = set().union(*(categories.get(f, set()) for f in formes))
        if not trouvees:
            ecarts.append(f"« {p['phrase']} » : « {mot} » absent de Lexique")
        elif not trouvees & PERMISES[nature]:
            ecarts.append(f"« {p['phrase']} » : « {mot} » déclaré {nature}, Lexique : {', '.join(sorted(trouvees))}")
print(f"{n} mots vérifiés dans {len(phrases)} phrases ; {len(ecarts)} écart(s)")
for e in ecarts:
    print("  ✗", e)
sys.exit(1 if ecarts else 0)
