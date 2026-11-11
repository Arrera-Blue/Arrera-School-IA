"""Chaque libellé du brouillon (ou du référentiel) est-il dans le texte officiel, mot pour mot ? La mise en page est
mise à part : sauts de ligne et de page, espaces, mot coupé après un trait d'union en fin de ligne, puce « \\uf0b7 ».

Usage : python -I verifier_mot_pour_mot_c2.py <annexe3.txt> <brouillon.json | francais-cp.yaml …>"""
import json
import re
import sys

lignes = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if not l.startswith("===== page")]
texte = ""
for ligne in lignes:
    if not ligne:
        continue
    texte += ligne if re.search(r"\w-$", texte) else " " + ligne
texte = re.sub(r"\s+", " ", texte.replace("", " "))

libelles = []
for chemin in sys.argv[2:]:
    if chemin.endswith(".json"):
        libelles += [o["libelle"] for b in json.load(open(chemin, encoding="utf-8")) for o in b["objectifs"]]
    else:
        import yaml
        doc = yaml.safe_load(open(chemin, encoding="utf-8"))
        libelles += [a["libelle"] for t in doc["themes"] for a in t["attendus"]]

absents = [l for l in libelles if re.sub(r"\s+", " ", l) not in texte]
print(f"{len(libelles) - len(absents)} libellés sur {len(libelles)} retrouvés tels quels")
for l in absents:
    print("  ✗", l)
sys.exit(1 if absents else 0)
