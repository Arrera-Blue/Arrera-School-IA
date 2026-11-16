"""Chaque libellé du brouillon (ou du référentiel) est-il dans le texte officiel, mot pour mot ? La mise en page est
mise à part : sauts de ligne et de page, espaces, mot coupé après un trait d'union en fin de ligne, puce de la police
Symbol (un caractère privé, U+E000 à U+F8FF), exposant séparé de son nombre (« I er » → « Ier »).

Les programmes de 2026 (lot 2) : les titres des thèmes sont vérifiés aussi ; une introduction reprise devant chacune
de ses puces (« Connaitre et comprendre : Les grandes étapes… ») est vérifiée en deux morceaux, l'introduction puis
la puce, et signalée.

Usage : python -I verifier_mot_pour_mot_c2.py <texte officiel.txt> <brouillon.json | francais-cp.yaml …>
(le texte officiel : celui de pypdf, page par page, séparé par des lignes « ===== page N » ou « === page N === »)."""
import json
import re
import sys

EXPOSANT = re.compile(r"\b([IVX]+) (er|e)\b")

lignes = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if not re.match(r"^=+ page \d+", l)]
texte = ""
for ligne in lignes:
    if not ligne:
        continue
    texte += ligne if re.search(r"\w-$", texte) else " " + ligne
texte = EXPOSANT.sub(r"\1\2", re.sub(r"\s+", " ", re.sub(r"[-]", " ", texte)))

libelles, themes = [], []
for chemin in sys.argv[2:]:
    if chemin.endswith(".json"):
        for bloc in json.load(open(chemin, encoding="utf-8")):
            if "objectifs" in bloc:  # le français du cycle 2 (étape 0.4)
                libelles += [o["libelle"] for o in bloc["objectifs"]]
            else:                    # les programmes de 2026 (lot 2)
                libelles += [p for puces in bloc["colonnes"].values() for p in puces]
                themes.append(bloc["theme"])
    else:
        import yaml
        doc = yaml.safe_load(open(chemin, encoding="utf-8"))
        libelles += [a["libelle"] for t in doc["themes"] for a in t["attendus"]]
        if doc["matiere"] != "francais":
            themes += [t["theme"] for t in doc["themes"]]


def present(libelle: str) -> bool:
    libelle = re.sub(r"\s+", " ", libelle)
    if libelle in texte:
        return True
    intro, _, puce = libelle.partition(" : ")
    if puce and f"{intro} :" in texte and f"- {puce}" in texte:
        print(f"  ~ introduction et puce retrouvées séparément : {libelle[:80]}")
        return True
    return False


absents = [l for l in libelles + themes if not present(l)]
print(f"{len(libelles) - len([a for a in absents if a in libelles])} libellés sur {len(libelles)} retrouvés tels quels"
      + (f" ; {len(themes) - len([a for a in absents if a in themes])} titres de thèmes sur {len(themes)}" if themes else ""))
for l in absents:
    print("  ✗", l)
sys.exit(1 if absents else 0)
