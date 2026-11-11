"""Brouillons extraits des BO -> référentiel YAML (generateur/programmes/). Corrections à la main listées ici, une par
une, pour que le passage du texte officiel au référentiel reste vérifiable.
Usage : construire_referentiel.py <dossier-brouillons> <dossier-sortie>"""
import json
import sys
import unicodedata
from pathlib import Path

import yaml

brouillons, sortie = Path(sys.argv[1]), Path(sys.argv[2])

C3 = {"cycle": 3, "texte": "Programmes d’enseignement de français et de mathématiques du cycle de consolidation (cycle 3)",
      "arrete": "Arrêté du 10 avril 2025 (JO du 16 avril 2025)", "nor": "MENE2504620A",
      "bo": "BO n° 16 du 17 avril 2025", "url": "https://www.education.gouv.fr/bo/2025/Hebdo16/MENE2504620A",
      "en_vigueur": "en 6e depuis la rentrée 2025-2026 (article 3 de l’arrêté)"}
C4 = {"cycle": 4, "texte": "Programmes d’enseignement de français et de mathématiques du cycle des approfondissements (cycle 4)",
      "arrete": "Arrêté du 18 février 2026 (JO du 4 mars 2026)", "nor": "MENE2602912A",
      "bo": "BO n° 10 du 5 mars 2026", "url": "https://www.education.gouv.fr/bo/2026/Hebdo10/MENE2602912A",
      "en_vigueur": "en 5e à la rentrée 2026-2027 (article 3 de l’arrêté)"}
PROGRAMMES = {
    "maths-6e": ("maths", "6e", C3, "Programme de mathématiques pour le cycle 3 (annexe), « Sixième »"),
    "maths-5e": ("maths", "5e", C4, "Annexe 2 – Programme de mathématiques pour le cycle 4, « Cinquième »"),
    "francais-6e": ("francais", "6e", C3, "Programme de français pour le cycle 3 (annexe), « Sixième »"),
    "francais-5e": ("francais", "5e", C4, "Annexe 1 – Programme de français pour le cycle 4, « Cinquième »"),
}

# --- corrections à la main ------------------------------------------------------------------------
# titres de rubriques et paragraphes que l'extraction a pris pour des objectifs
PAS_DES_OBJECTIFS = {
    "maths-6e": {"La fraction comme opérateur multiplicatif", "Comparer des fractions", "Pourcentages",
                 "Effectuer des opérations sur les fractions", "Mises en perspective historiques et culturelles",
                 "Cercles et disques", "Médiatrice d’un segment", "Angles", "Bissectrice d’un angle saillant",
                 "Triangles", "Symétrie axiale"},
    "francais-6e": {"Se repérer dans la phrase complexe", "Acquérir l’orthographe grammaticale"},
    "francais-5e": {"Approfondir sa maitrise des formes conjuguées du verbe et leur emploi",
                    "Observer, distinguer et employer à bon escient grammaire de l’écrit et grammaire de l’oral"},
}
PARAGRAPHES = ("En 6e, l’objectif est de faire opérer", "L’élève découvre l’histoire", "Selon ses intérêts et ses besoins",
               "Le triangle se prête", "Le travail de construction réalisé")
# maths 6e : sous-rubriques que l'extraction n'a pas pu lire (un paragraphe s'intercalait)
SOUS_THEMES = {
    "Utiliser une multiplication pour appliquer une fraction à un nombre entier": "La fraction comme opérateur multiplicatif",
    "Construire des triangles": "Triangles",
    "Connaître et utiliser les propriétés angulaires des triangles particuliers : triangle rectangle, triangle isocèle, triangle équilatéral": "Triangles",
    "Connaître la valeur de la somme des mesures des angles d’un triangle": "Triangles",
    "L’utiliser pour calculer des angles, effectuer des constructions et résoudre des problèmes": "Triangles",
    "Savoir que les médiatrices d’un triangle sont concourantes": "Triangles",
    "Connaître et construire le cercle circonscrit à un triangle": "Triangles",
    "Connaître la définition du symétrique d’un point par rapport à une droite": "Symétrie axiale",
    "Connaître et utiliser les propriétés de la symétrie axiale pour effectuer des constructions": "Symétrie axiale",
}
# texte réécrit : fraction empilée dans le PDF, ou deux objectifs sur une même ligne
REECRITS = {
    "Savoir que la fraction a b peut représenter un nombre entier, un nombre décimal non entier ou un nombre non décimal":
        ["Savoir que la fraction a/b peut représenter un nombre entier, un nombre décimal non entier ou un nombre non décimal"],
    "Justifier à l'oral ou à l'écrit l'accord du participe passé employé avec l'auxiliaire être et avec l'auxiliaire avoir "
    "(COD antéposé dont pronom personnel COD, à distinguer du COI). Identifier les verbes attributifs en repérant l’emploi "
    "occasionnellement attributif de certains verbes.": [
        "Justifier à l'oral ou à l'écrit l'accord du participe passé employé avec l'auxiliaire être et avec l'auxiliaire avoir "
        "(COD antéposé dont pronom personnel COD, à distinguer du COI).",
        "Identifier les verbes attributifs en repérant l’emploi occasionnellement attributif de certains verbes."],
    # maths 5e : objectifs écrits en liste à puces dans le BO
    "Sur une droite graduée :": [
        "Sur une droite graduée : lire l’abscisse d’un point donné ; placer un point d’abscisse donnée.",
        "Dans le plan muni d’un repère orthogonal : lire les coordonnées d’un point donné ; placer un point de coordonnées données."],
}

# identifiant court de chaque thème (le reste de l'identifiant est le rang de l'attendu dans le thème)
SLUGS = {
    "Les nombres entiers et décimaux": "nombres-decimaux", "Les fractions": "fractions", "Algèbre": "algebre",
    "Les longueurs": "longueurs", "Les aires": "aires", "Les volumes": "volumes",
    "Le repérage dans le temps et les durées": "durees", "Étude de configurations planes": "geometrie-plane",
    "La vision dans l’espace": "vision-espace", "Organisation et gestion de données": "donnees",
    "Les probabilités": "probabilites", "La proportionnalité": "proportionnalite",
    "Initiation à la pensée informatique": "pensee-informatique",
    "Opérations": "operations", "Nombres relatifs": "nombres-relatifs", "Nombres rationnels": "nombres-rationnels",
    "Puissances": "puissances", "Calcul littéral et algébrique": "calcul-litteral",
    "Repérage sur une droite et dans le plan": "reperage", "Représentation de l’espace": "espace",
    "Transformations": "transformations", "Angles": "angles", "Triangles": "triangles",
    "Parallélogrammes": "parallelogrammes", "Statistiques": "statistiques", "Probabilités": "probabilites",
    "Proportionnalité": "proportionnalite", "Fonctions": "fonctions", "La pensée informatique": "pensee-informatique",
    # français 6e
    "Lire avec fluidité": "lire-fluidite", "Lire à voix haute avec expressivité": "lire-voix-haute",
    "Lire et comprendre seul des textes, des documents et des images": "comprendre-textes",
    "Lire et comprendre des textes, des documents et des images pour apprendre dans toutes les disciplines": "comprendre-documents",
    "Lire une œuvre et se l’approprier": "lire-oeuvre", "Écrire à la main de manière fluide et efficace": "ecrire-main",
    "Écrire pour réfléchir, apprendre et mémoriser": "ecrire-reflechir", "Produire des écrits variés": "ecrits-varies",
    "Écouter pour comprendre": "ecouter", "Dire pour être compris dans toutes les disciplines": "dire",
    "Participer à des échanges verbaux": "echanges", "Enrichir son vocabulaire dans toutes les disciplines": "vocabulaire",
    "Établir des relations entre les mots": "relations-mots", "Réemployer le vocabulaire étudié": "reemployer",
    "Mémoriser l’orthographe des mots": "orthographe-lexicale", "Analyser une phrase simple": "phrase-simple",
    "Identifier les mots, un groupe de mots selon leur nature": "nature-mots",
    "Analyser le groupe nominal": "groupe-nominal",
    "Différencier phrase simple et phrase complexe à partir de la notion de proposition": "phrase-complexe",
    "Repérer les différents modes d’articulation des propositions au sein de la phrase complexe": "propositions",
    "Identifier les classes de mots subissant des variations": "classes-variables",
    "Réaliser la chaîne d’accords au sein du groupe nominal": "accords-gn", "Accorder le sujet et le verbe": "accord-sujet-verbe",
    "Approfondir sa maîtrise de la conjugaison": "conjugaison",
    # français 5e
    "Comprendre, interpréter, apprécier": "comprendre-interpreter", "Lire à voix haute, seul ou à plusieurs": "lire-voix-haute",
    "Appréhender une œuvre dans des contextes artistiques variés": "oeuvre-contextes",
    "Acquérir, structurer et mobiliser des connaissances littéraires et culturelles": "connaissances-litteraires",
    "Écrire des textes d’invention et de réflexion pour soi et pour autrui": "ecrire-invention",
    "Évaluer son écrit et savoir le faire évoluer": "evaluer-ecrit", "Prendre la parole, communiquer et interagir": "prendre-parole",
    "Écouter, comprendre et interpréter": "ecouter", "Dire, lire, jouer un texte": "dire-jouer",
    "Enrichir son vocabulaire": "vocabulaire", "Identifier les types de relations entre les mots": "relations-mots",
    "Réemployer son lexique et jouer avec les mots": "reemployer", "Comprendre la formation des mots": "formation-mots",
    "Écrire avec justesse (orthographe)": "orthographe-lexicale",
    "Comprendre ce qu’est une phrase pour mieux lire et mieux écrire": "phrase",
    "Connaitre les différents constituants d’une phrase": "constituants",
    "Observer et distinguer les registres de langue et ajuster ses choix au contexte": "registres",
    "Analyser et employer des paroles rapportées": "paroles-rapportees",
    "Maitriser la composition des formes verbales pour identifier un temps et le conjuguer": "formes-verbales",
    "Maitriser l’emploi des temps et des modes": "temps-modes",
    "Savoir accorder les mots dans la phrase et expliquer ses choix": "accords",
}

# --- « se prête à un QCM » : un classement du projet, pas du programme ---------------------------
# français : seuls le vocabulaire et la grammaire se travaillent par QCM ; lecture, écriture, oral : non
DOMAINES_QCM_FRANCAIS = {"Vocabulaire", "Vocabulaire et orthographe lexicale", "Grammaire et orthographe grammaticale"}
# un geste, une production ou une activité qu'un QCM ne peut pas évaluer
DEBUTS_SANS_QCM = ("Construire", "Tracer", "Mesurer un angle", "Graduer", "Planifier", "Réaliser des mesures", "Programmer",
                   "Produire et exécuter", "Répéter", "Inventer", "Recueillir", "Formuler des conjectures", "Manipuler",
                   "Effectuer une boucle", "Représenter, sur papier", "Mobiliser un algorithme", "Choisir une représentation",
                   "Introduire l’expression", "Produire un tableau", "Placer dans un repère", "Démontrer",
                   # français : écrire, produire, chercher dans un dictionnaire… pas reconnaître une forme parmi d'autres
                   "Améliorer son orthographe", "Mobiliser le vocabulaire", "Organiser", "Maitriser l’usage du dictionnaire",
                   "Jouer avec les mots", "Insérer des paroles", "Consolider les compétences", "Utiliser les manipulations syntaxiques",
                   "Choisir, de manière autonome", "À l’oral et à l’écrit, utiliser à bon escient le vocabulaire spécifique",
                   "Construire des réflexes")


def se_prete_au_qcm(matiere: str, domaine: str, libelle: str) -> bool:
    if matiere == "francais" and domaine not in DOMAINES_QCM_FRANCAIS:
        return False
    return not libelle.startswith(DEBUTS_SANS_QCM)


def propre(texte: str) -> str:
    texte = unicodedata.normalize("NFC", texte).replace("𝑥", "x")  # x mathématique italique du PDF → x
    texte = " ".join(texte.split())
    return texte[:-2] + "." if texte.endswith(" .") else texte


for nom, (matiere, niveau, source, extrait) in PROGRAMMES.items():
    blocs = json.loads((brouillons / f"{nom}.json").read_text(encoding="utf-8"))
    titres = {b["theme"] for b in blocs} | {b.get("sous_theme") for b in blocs if b.get("sous_theme")}
    themes: dict[str, dict] = {}
    for bloc in blocs:
        theme = themes.setdefault(bloc["theme"], {"domaine": bloc["domaine"], "theme": bloc["theme"], "attendus": []})
        for brut in bloc["objectifs"]:
            brut = propre(brut)
            if brut in PAS_DES_OBJECTIFS.get(nom, set()) or brut in titres or brut.startswith(PARAGRAPHES):
                continue
            for libelle in REECRITS.get(brut, [brut]):
                sous = SOUS_THEMES.get(libelle) or bloc.get("sous_theme")
                theme["attendus"].append({"libelle": libelle, "sous_theme": sous})
    sortie_themes = []
    for theme in themes.values():
        slug = SLUGS[theme["theme"]]
        attendus = []
        for rang, a in enumerate(theme["attendus"], 1):
            entree = {"id": f"{matiere}.{niveau}.{slug}.{rang:02d}", "libelle": a["libelle"]}
            if a["sous_theme"]:
                entree["sous_theme"] = a["sous_theme"]
            entree["qcm"] = se_prete_au_qcm(matiere, theme["domaine"], a["libelle"])
            attendus.append(entree)
        sortie_themes.append({"id": f"{matiere}.{niveau}.{slug}", "domaine": theme["domaine"], "theme": theme["theme"],
                              "attendus": attendus})
    document = {"matiere": matiere, "niveau": niveau, "cycle": source["cycle"],
                "source": {k: v for k, v in source.items() if k != "cycle"} | {"extrait": extrait, "releve": "2026-10-21"},
                "themes": sortie_themes}
    entete = (f"# Référentiel des attendus — {matiere}, {niveau} (évolution E2). Libellés recopiés MOT POUR MOT des\n"
              f"# « Objectifs d’apprentissage » du programme officiel (source ci-dessous) ; seuls les identifiants, les\n"
              f"# sous-thèmes de maths 6e et le champ « qcm » (se prête ou non à un QCM : classement du projet, pas du\n"
              f"# programme) sont ajoutés. Méthode et corrections : docs/etapes/etape-E2-programmes.md.\n")
    texte = yaml.safe_dump(document, allow_unicode=True, sort_keys=False, width=120)
    (sortie / f"{nom}.yaml").write_text(entete + texte, encoding="utf-8")
    total = sum(len(t["attendus"]) for t in sortie_themes)
    qcm = sum(a["qcm"] for t in sortie_themes for a in t["attendus"])
    print(f"{nom}: {len(sortie_themes)} thèmes, {total} attendus, dont {qcm} pour un QCM")
