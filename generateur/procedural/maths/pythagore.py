"""Théorème de Pythagore (4e) : l'hypoténuse, le côté manquant, la réciproque.

Les longueurs viennent de triplets pythagoriciens entiers (3-4-5, 5-12-13…) : les résultats sont entiers, sans
arrondi. Le piège de l'habillage : avec les mêmes nombres, faire d'un côté de l'angle droit l'hypoténuse
(« une échelle de 12 m posée à 5 m du mur »). D'où l'exigence du mot « hypoténuse » là où il le faut.
"""

import random

from generateur.procedural import Squelette, distracteurs
from generateur.procedural.maths import COLLEGE

NOM, TITRE, NOTION, NIVEAU = "pythagore", "Le théorème de Pythagore", "théorème de Pythagore", "4e"
MATIERE, NIVEAUX = "maths", COLLEGE  # NIVEAU : la classe par défaut ; NIVEAUX : celles où il s'applique
MOTS_CLES = ("pythagore", "hypotenuse", "triangle rectangle")

TRIPLETS = ((3, 4, 5), (5, 12, 13), (8, 15, 17), (7, 24, 25), (20, 21, 29))
COTE_MAX = 50
RECTANGLE = r"rectangle|angle droit|perpendiculaire|équerre"


def triplet(rng: random.Random) -> tuple[int, int, int]:
    a, b, c = rng.choice(TRIPLETS)
    k = rng.randint(1, COTE_MAX // c)
    return a * k, b * k, c * k


def _unite(rng: random.Random) -> str:
    return rng.choice(["cm", "m"])


def hypotenuse(rng: random.Random) -> Squelette:
    a, b, c = triplet(rng)
    u = _unite(rng)
    s = a * a + b * b
    reponse = f"{c} {u}"
    return Squelette(
        genre=f"{NOM}.hypotenuse",
        enonce=f"Un triangle est rectangle ; les côtés de l'angle droit mesurent {a} {u} et {b} {u}. "
               "Quelle est la longueur de l'hypoténuse ?",
        reponse=reponse,
        # la somme des côtés, le carré sans la racine, la différence (si elle n'est pas absurde)
        distracteurs=distracteurs(reponse, [f"{a + b} {u}", f"{s} {u}", *([f"{b - a} {u}"] if b - a >= 3 else []),
                                            f"{c + 1} {u}", f"{c - 1} {u}"]),
        explication=f"D'après le théorème de Pythagore, le carré de l'hypoténuse est la somme des carrés des côtés "
                    f"de l'angle droit : {a}² + {b}² = {a * a} + {b * b} = {s}. L'hypoténuse mesure donc "
                    f"√{s} = {c} {u}.",
        cle=("hypotenuse", a, b),
        habillable=True,
        obligatoires=(RECTANGLE, rf"\d ?{u}\b"),
        # l'hypoténuse est demandée, jamais donnée
        interdits=(r"hypoténuse (?:\S+ ){0,5}?(?:mesure|mesurant|vaut|fait|est de|de|=) ?\d",),
        demande=(r"hypoténuse",),
    )


def cote(rng: random.Random) -> Squelette:
    a, b, c = triplet(rng)
    connu, cherche = (a, b) if rng.random() < 0.5 else (b, a)
    u = _unite(rng)
    reponse = f"{cherche} {u}"
    return Squelette(
        genre=f"{NOM}.cote",
        enonce=f"L'hypoténuse d'un triangle rectangle mesure {c} {u} et un côté de l'angle droit mesure "
               f"{connu} {u}. Quelle est la longueur de l'autre côté de l'angle droit ?",
        reponse=reponse,
        # la différence (si elle n'est pas absurde : 25 − 24 = 1), la somme, le carré sans la racine
        distracteurs=distracteurs(reponse, [*([f"{c - connu} {u}"] if c - connu >= 3 else []), f"{c + connu} {u}",
                                            f"{c * c - connu * connu} {u}", f"{cherche + 1} {u}",
                                            f"{cherche - 1} {u}"]),
        explication=f"D'après le théorème de Pythagore, {c}² = {connu}² + ?², donc ?² = {c * c} − {connu * connu} "
                    f"= {cherche * cherche}, et ? = √{cherche * cherche} = {cherche}. L'autre côté mesure "
                    f"{cherche} {u}.",
        cle=("cote", c, connu),
        habillable=True,
        # l'hypoténuse donnée est bien celle du tirage
        obligatoires=(RECTANGLE, rf"hypoténuse (?:\S+ ){{0,6}}?{c} ?{u}\b"),
        demande_interdits=(r"hypoténuse",),
    )


def reciproque(rng: random.Random) -> Squelette:
    a, b, c = triplet(rng)
    rectangle = rng.random() < 0.5
    if not rectangle:  # un côté décalé de 1 : le triangle existe toujours, mais n'est plus rectangle
        c += 1
    u = _unite(rng)
    s, carre = a * a + b * b, c * c
    cotes = [a, b, c]
    rng.shuffle(cotes)
    x, y, z = cotes
    oui, non = f"Oui, car {a}² + {b}² = {c}²", f"Non, car {a}² + {b}² ≠ {c}²"
    if rectangle:
        reponse, candidats = oui, [non, f"Non, car {a} + {b} ≠ {c}"]
        conclusion = "L'égalité est vraie, donc, d'après la réciproque du théorème de Pythagore, le triangle est rectangle"
    else:
        reponse, candidats = non, [oui, f"Oui, car {c} est le plus grand côté"]
        conclusion = ("L'égalité est fausse, donc, d'après le théorème de Pythagore, le triangle n'est pas rectangle "
                      "(s'il l'était, l'égalité serait vraie)")
    return Squelette(
        genre=f"{NOM}.reciproque",
        enonce=f"Un triangle a pour côtés {x} {u}, {y} {u} et {z} {u}. Est-il rectangle ?",
        reponse=reponse,
        distracteurs=distracteurs(reponse, candidats, nombre=2),
        explication=f"Le plus grand côté mesure {c} {u}. {a}² + {b}² = {a * a} + {b * b} = {s} et {c}² = {carre}. "
                    f"{conclusion}.",
        cle=("reciproque", a, b, c),
        habillable=True,
        obligatoires=(rf"\d ?{u}\b",),
        demande=(RECTANGLE,),
    )


GENRES = (hypotenuse, cote, reciproque)
