"""Brouillon du référentiel : les « Objectifs d'apprentissage » d'un niveau, mot pour mot, avec leur domaine et leur
thème. Usage : extraire_objectifs.py <texte> <niveau> <entetes-json> -> JSON sur la sortie standard.
entetes-json : {"domaines": [...], "themes": [...], "theme_precedent": bool}
  theme_precedent : le thème est la ligne juste avant « Objectifs d'apprentissage » (français)."""
import json
import re
import sys

texte, niveau, entetes = sys.argv[1], sys.argv[2], json.loads(open(sys.argv[3], encoding="utf-8").read())
NIVEAUX = {"Cours moyen première année", "Cours moyen deuxième année", "Sixième", "Cinquième", "Quatrième", "Troisième"}
ARRETS = ("Prolongements possibles", "Automatismes", "Connaissances et capacités attendues", "Repères",
          "Points de vigilance", "Point de vigilance", "Conditions favorables", "Principes", "−", "- ", "• ")
SUITE = (",", " de", " des", " du", " à", " et", " la", " le", " les", " en", " d’", " l’", " un", " une", " au", " aux",
         " par", " pour", " sur", " dans", " avec", " ou", " sa", " son", " ses", " leur", " leurs", " que", " qui")

lignes = []
for brute in open(texte, encoding="utf-8"):
    ligne = re.sub(r"\s+", " ", brute.strip())
    if not ligne or ligne.startswith("=== page") or re.match(r"^education\.gouv\.fr BO n°", ligne):
        continue
    lignes.append(ligne)

domaines, themes = set(entetes["domaines"]), set(entetes["themes"])
domaine = theme = niv = precedent = None
blocs, courant, dans = [], None, False
for ligne in lignes:
    if ligne in NIVEAUX:
        niv, dans = ligne, False
    elif ligne in domaines:
        domaine, theme, dans = ligne, None, False
    elif ligne in themes:
        theme, dans = ligne, False
    elif ligne == "Objectifs d’apprentissage":
        if entetes.get("theme_precedent") and precedent and not precedent.startswith(ARRETS) \
                and precedent not in NIVEAUX and precedent not in domaines:
            theme = precedent
        dans = True
        # une sous-rubrique (« Comparer des fractions ») : la ligne précédente a l'allure d'un titre
        sous = precedent if (not entetes.get("theme_precedent") and precedent and len(precedent) < 90
                             and not precedent.endswith((".", ":", ";")) and precedent[0].isupper()
                             and not precedent.startswith(ARRETS) and precedent not in themes
                             and precedent not in NIVEAUX and precedent not in domaines) else None
        courant = {"domaine": domaine, "theme": theme or domaine, "sous_theme": sous, "niveau": niv, "objectifs": []}
        blocs.append(courant)
    elif dans:
        if ligne.startswith(ARRETS):
            dans = False
        else:
            obj = courant["objectifs"]
            # la suite de l'objectif précédent : une minuscule en tête, ou une ligne précédente inachevée
            if obj and (ligne[0].islower() or ligne[0] in "(«" or obj[-1].endswith(SUITE)):
                obj[-1] += " " + ligne
            else:
                obj.append(ligne)
    precedent = ligne

json.dump([b for b in blocs if b["niveau"] == niveau and b["objectifs"]], sys.stdout, ensure_ascii=False, indent=1)
