"""Chaque libellé du brouillon (ou du référentiel) est-il dans le texte officiel, mot pour mot ? La mise en page est
mise à part : sauts de ligne et de page, espaces, mot coupé après un trait d'union en fin de ligne, puce de la police
Symbol (un caractère privé, U+E000 à U+F8FF), exposant séparé de son nombre (« I er » → « Ier »).

Les programmes de 2026 (lot 2) : les titres des thèmes sont vérifiés aussi ; une introduction reprise devant chacune
de ses puces (« Connaitre et comprendre : Les grandes étapes… ») est vérifiée en deux morceaux, l'introduction puis
la puce, et signalée.

Le programme de langues vivantes (lot 3) : la puce « • » d'une sous-liste est mise à part, comme celle de la police
Symbol ; une case du tableau coupée par un changement de page, dont pypdf colle la fin à la 2e colonne de la page
suivante (« mémorisées. I’m/I am 6. »), est vérifiée en deux morceaux : le début dans le texte, la fin au début d'une
ligne de la page suivante ; et signalée.

Usage : python -I verifier_mot_pour_mot_c2.py <texte officiel.txt> <brouillon.json | francais-cp.yaml …>
(le texte officiel : celui de pypdf, page par page, séparé par des lignes « ===== page N » ou « === page N === »)."""
import json
import re
import sys

EXPOSANT = re.compile(r"\b([IVX]+) (er|e)\b")

brutes = [l.strip() for l in open(sys.argv[1], encoding="utf-8")]
lignes = [l for l in brutes if not re.match(r"^=+ page \d+", l)]
texte = ""
for ligne in lignes:
    if not ligne:
        continue
    texte += ligne if re.search(r"\w-$", texte) else " " + ligne
texte = EXPOSANT.sub(r"\1\2", re.sub(r"\s+", " ", re.sub(r"[-•]", " ", texte)))
# le début de chaque page : ses premières lignes non vides (une case coupée par un changement de page)
debuts_de_page = [l for i, l in enumerate(brutes) if l and any(re.match(r"^=+ page \d+", b) for b in brutes[max(0, i - 3):i])]

libelles, themes = [], []
for chemin in sys.argv[2:]:
    if chemin.endswith(".json"):
        for bloc in json.load(open(chemin, encoding="utf-8")):
            if "code" in bloc:       # les langues vivantes (lot 3)
                libelles += [p["libelle"] for cle in ("attendus", "objectifs") for p in bloc[cle]]
                themes.append(bloc["competence"])
            elif "objectifs" in bloc:  # le français du cycle 2 (étape 0.4)
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
    mots = libelle.split(" ")
    for coupure in range(len(mots) - 1, 0, -1):  # la fin la plus courte d'abord
        debut, fin = " ".join(mots[:coupure]), " ".join(mots[coupure:])
        if debut in texte and any(d.startswith(fin) for d in debuts_de_page):
            print(f"  ~ en deux morceaux, de part et d'autre d'un changement de page : « …{debut[-40:]} » | « {fin} »")
            return True
    return False


absents = [l for l in libelles + themes if not present(l)]
print(f"{len(libelles) - len([a for a in absents if a in libelles])} libellés sur {len(libelles)} retrouvés tels quels"
      + (f" ; {len(themes) - len([a for a in absents if a in themes])} titres de thèmes sur {len(themes)}" if themes else ""))
for l in absents:
    print("  ✗", l)
sys.exit(1 if absents else 0)
