"""Brouillon du référentiel des programmes de 2026 du cycle 2 (lot 2, étape 2.0) : sciences et technologie (annexe 1
du BO n° 24 du 11 juin 2026), histoire-géographie (annexe 3 du BO n° 22 du 28 mai 2026). Les colonnes, mot pour mot,
avec leur domaine, leur classe et leur thème.

Le format : des tableaux à deux colonnes (sciences : « Objectifs d'apprentissage | Propositions de démarches et
d'activités ») ou à trois (histoire-géographie : « Objectifs d'apprentissage | Attendus (connaissances et
compétences) | Repères »), chaque case faite de puces « - ». Le texte brut de pypdf mêle les colonnes (parfois sur une
même ligne), et son mode « mise en page » rend des pages vides pour les sciences. Mais pypdf donne chaque morceau de
texte avec sa position, et la suite des morceaux redonne exactement son texte brut (vérifié ici, page par page) :
chaque morceau est donc rangé dans sa colonne **par sa position sur la page** (`COLONNES`), puis les lignes de chaque
colonne relues de haut en bas.

- un tableau commence à la ligne d'en-tête (« Objectifs d'apprentissage ») et finit à la première ligne écrite dans la
  marge de gauche (un titre, un paragraphe, « Mots-clés ») ; il peut passer d'une page à la suivante ;
- dans une colonne, une ligne qui commence par « - » ouvre une puce ; une ligne sans puce au début d'une colonne est
  une introduction, reprise devant chacune de ses puces (« Connaitre et comprendre : » au CE2) ;
- mise en page : un mot coupé en fin de ligne après un trait d'union est recollé sans espace (« chasseurs-cueilleurs ») ;
  un exposant séparé de son nombre par pypdf est recollé (« du I er siècle » → « du Ier siècle ») ;
  la puce de la police Symbol (un caractère privé, U+E000 à U+F8FF) d'une sous-liste est retirée ;
- les titres (domaines, classes, thèmes) sont ceux du sommaire, au début de chaque annexe ; en histoire-géographie,
  « Thème 1 : » et la durée en périodes de l'année (« (trois périodes) ») sont retirés du titre du thème, comme les
  repères de période du français (étape 0.4) ; aux objets techniques, sans thème, le thème est le domaine.

Usage : python -I extraire_objectifs_2026.py <sciences|histoire-geo> <annexe.pdf> <première page> <dernière page>
-> JSON sur la sortie standard ; sur la sortie d'erreur, chaque correction de mise en page."""
import json
import re
import sys

from pypdf import PdfReader

# les limites des colonnes, en points depuis le bord gauche : les puces sont à 39 et 300,5 en sciences (une virgule
# finit une ligne de la première colonne à 291,6 : « d’agir, ») ; à 39, 213 et 388 en histoire-géographie ; la marge
# des titres et des paragraphes est à 36
COLONNES = {"sciences": (299,), "histoire-geo": (205, 380)}
# les colonnes relevées : les objectifs ; en histoire-géographie, les attendus aussi (les repères servent de source aux
# tables du générateur, pas au référentiel)
GARDEES = {"sciences": (0,), "histoire-geo": (0, 1)}
NOMS_COLONNES = {"sciences": ("Objectifs d’apprentissage", "Propositions de démarches et d’activités"),
                 "histoire-geo": ("Objectifs d’apprentissage", "Attendus (connaissances et compétences)", "Repères")}
MARGE = 37.5
CLASSES = {"Cours préparatoire": "CP", "Cours élémentaire première année": "CE1",
           "Cours élémentaire deuxième année": "CE2"}
PRIVE = re.compile(r"[-]")
EXPOSANT = re.compile(r"\b([IVX]+) (er|e)\b")  # « I er siècle » : l'exposant, séparé par pypdf, recollé (« Ier »)
DUREE = re.compile(r"\s*\((?:une|deux|trois|quatre|cinq|une ou deux|trois ou quatre|première|deuxième|troisième|"
                   r"quatrième|cinquième|deuxième et troisième|quatrième et cinquième) périodes?\)\s*$")

genre, chemin, premiere, derniere = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
limites = COLONNES[genre]


def colonne(x: float) -> int:
    return sum(x >= limite for limite in limites)


# --- les lignes de chaque page : [(y, x du premier morceau, {colonne: texte}, texte de toute la ligne)] -----------
def lignes_de(page) -> list[tuple[float, float, dict[int, str], str]]:
    morceaux = []

    def visiteur(texte, cm, tm, police, taille):
        morceaux.append((texte, tm[4] * cm[0] + cm[4], tm[5] * cm[3] + cm[5]))

    brut = page.extract_text(visitor_text=visiteur)
    assert "".join(m[0] for m in morceaux) == brut, "les morceaux ne redonnent pas le texte de la page"
    lignes: list[dict] = []
    derniere, position = None, None  # la ligne du dernier morceau écrit, et sa colonne : les espaces seuls leur reviennent
    for texte, x, y in morceaux:
        texte = texte.replace("\n", " ")
        if not texte.strip():
            if derniere:
                derniere["colonnes"][position] += texte
                derniere["texte"] += texte
            continue
        if derniere and abs(y - derniere["y"]) <= 4:
            ligne = derniere  # un exposant (« Ier », « IIe ») reste sur sa ligne
        else:
            ligne = next((l for l in lignes if abs(y - l["y"]) <= 1), None)
            if ligne is None:
                ligne = {"y": y, "x": x, "colonnes": {}, "texte": ""}
                lignes.append(ligne)
        ligne["x"] = min(ligne["x"], x)
        c = colonne(x)
        ligne["colonnes"][c] = ligne["colonnes"].get(c, "") + texte
        ligne["texte"] += texte
        derniere, position = ligne, c
    propre = lambda t: re.sub(r"\s+", " ", t).strip()
    return [(l["y"], l["x"], {c: propre(t) for c, t in l["colonnes"].items()}, propre(l["texte"]))
            for l in sorted(lignes, key=lambda l: -l["y"])]


def recoller(texte: str) -> str:
    recolle = EXPOSANT.sub(r"\1\2", texte)
    if recolle != texte:
        print(f"~ exposant recollé : {texte[:70]}", file=sys.stderr)
    return recolle


lecteur = PdfReader(chemin)
lignes = []
for numero in range(premiere, derniere + 1):
    lignes += lignes_de(lecteur.pages[numero - 1])

# --- le sommaire : les titres, jusqu'à « Principes » (le second : le premier est dans le sommaire) ---------------
texte_ligne = [t for _, _, _, t in lignes]
fin_sommaire = [i for i, t in enumerate(texte_ligne) if t == "Principes"][1]
sommaire = texte_ligne[1:fin_sommaire]  # sans « Sommaire »
DOMAINES = {"sciences": ("La matière, les mesures, l’électricité", "Les êtres vivants dans leur environnement",
                         "Le corps humain et la santé", "Les objets techniques au cœur de la société"),
            "histoire-geo": ("Histoire", "Géographie")}[genre]
manquants = [d for d in DOMAINES if d not in sommaire]
assert not manquants, f"domaines absents du sommaire : {manquants}"

# --- les tableaux --------------------------------------------------------------------------------------------
tableaux, domaine, classe, theme, courant, titre = [], None, None, None, None, None
for y, x, cols, texte in lignes[fin_sommaire + 1:]:
    if courant is not None and x < MARGE:
        courant = None  # une ligne dans la marge : le tableau est fini
    if courant is None:
        if texte in DOMAINES:
            domaine, classe, theme = texte, None, None
        elif texte.split(" : ")[0] in CLASSES:
            classe, theme = CLASSES[texte.split(" : ")[0]], None
        elif genre == "sciences" and texte in sommaire:
            theme = texte
        elif genre == "histoire-geo" and texte.startswith("Thème "):
            titre = [texte]
            continue
        elif titre is not None and not texte.startswith(("Question", "Objectifs")) and not texte.startswith("Comment"):
            titre.append(texte)
            continue
        if titre is not None:
            theme = recoller(re.sub(r"\s+", " ", " ".join(titre)).split(" : ", 1)[1])
            theme, avant = DUREE.sub("", theme), theme
            if theme != avant:
                print(f"~ durée retirée du titre : {avant[len(theme):].strip()}", file=sys.stderr)
            titre = None
        if texte.startswith("Objectifs"):
            courant = {"domaine": domaine, "classe": classe, "theme": theme or domaine,
                       "colonnes": {c: [] for c in GARDEES[genre]}, "intro": {}, "entete": True}
            tableaux.append(courant)
        continue
    if courant["entete"]:  # la fin de l'en-tête, sur une deuxième ligne (« compétences) », « d’activités »)
        if all(t in ("compétences)", "d’activités", "Repères", "") for t in cols.values()):
            continue
        courant["entete"] = False
    for c, t in cols.items():
        if c not in GARDEES[genre]:
            continue
        t = recoller(PRIVE.sub(" ", t).strip())
        if t != cols[c]:
            print(f"~ puce Symbol retirée : {cols[c][:50]}", file=sys.stderr)
        puces = courant["colonnes"][c]
        if t.startswith("- ") or t == "-":
            puces.append(courant["intro"].get(c, "") + t[2:].strip())
        elif not puces:
            courant["intro"][c] = t + " "
            print(f"~ introduction reprise devant ses puces : « {t} »", file=sys.stderr)
        elif re.search(r"\w-$", puces[-1]):
            print(f"~ recollé : …{puces[-1][-20:]}|{t[:20]}…", file=sys.stderr)
            puces[-1] += t
        else:
            puces[-1] += " " + t

sortie = [{"domaine": t["domaine"], "classe": t["classe"], "theme": t["theme"],
           "colonnes": {NOMS_COLONNES[genre][c]: [re.sub(r"\s+", " ", p).strip() for p in puces]
                        for c, puces in t["colonnes"].items()}}
          for t in tableaux]
json.dump(sortie, sys.stdout, ensure_ascii=False, indent=1)
