"""Calcul mental (6e) : les quatre opérations sur des entiers.

Pas d'habillage par le modèle : une histoire (« Léa a 27 billes, elle en perd 15 ») pourrait changer
l'opération sans changer les nombres. Les énoncés varient par des formulations fixes, toutes lues par N4.
"""

import random

from generateur.procedural import Squelette, Retirer, distracteurs

NOM, TITRE, NOTION, NIVEAU = "calcul_mental", "Calcul mental", "calcul mental", "6e"
MOTS_CLES = ("calcul mental", "table de multiplication", "tables de multiplication", "addition", "soustraction",
             "multiplication", "quatre operations")
EXCLUS = ("fraction",)  # « l'addition de fractions » relève du générateur des fractions


def _enonce(rng: random.Random, calcul: str, en_lettres: str | None = None) -> str:
    formes = [f"Calcule mentalement : {calcul}.", f"Calcule {calcul}.", f"Combien font {calcul} ?"]
    if en_lettres:
        formes.append(f"Combien font {en_lettres} ?")
    return rng.choice(formes)


def addition(rng: random.Random) -> Squelette:
    a, b = rng.randint(11, 69), rng.randint(11, 69)
    if a % 10 == 0 or b % 10 == 0:
        raise Retirer("trop facile")
    s = a + b
    retenue = a % 10 + b % 10 >= 10
    return Squelette(
        genre=f"{NOM}.addition",
        enonce=_enonce(rng, f"{a} + {b}"),
        reponse=str(s),
        # la retenue oubliée (− 10) ou ajoutée à tort (+ 10), puis une erreur d'une unité
        distracteurs=distracteurs(str(s), [str(s - 10 if retenue else s + 10), str(s + 1), str(s - 1),
                                           str(s + 10), str(s - 10)]),
        explication=(f"On ajoute les dizaines ({a - a % 10} + {b - b % 10} = {a - a % 10 + b - b % 10}), puis les "
                     f"unités ({a % 10} + {b % 10} = {a % 10 + b % 10}) : {a} + {b} = {s}."),
        cle=("addition", min(a, b), max(a, b)),
    )


def soustraction(rng: random.Random) -> Squelette:
    a = rng.randint(31, 99)
    b = rng.randint(11, a - 6)
    d = a - b
    # l'erreur classique : soustraire chiffre à chiffre le plus petit du plus grand (40 − 13 → 33)
    chiffre_a_chiffre = abs(a // 10 - b // 10) * 10 + abs(a % 10 - b % 10)
    return Squelette(
        genre=f"{NOM}.soustraction",
        enonce=_enonce(rng, f"{a} − {b}"),
        reponse=str(d),
        distracteurs=distracteurs(str(d), [str(chiffre_a_chiffre), str(a + b), str(d + 10), str(d - 10),
                                           str(d + 1), str(d - 1)]),
        explication=f"{a} − {b} = {d}. Pour vérifier : {d} + {b} = {a}.",
        cle=("soustraction", a, b),
    )


def multiplication(rng: random.Random) -> Squelette:
    a, b = rng.randint(3, 9), rng.randint(3, 9)
    p = a * b
    return Squelette(
        genre=f"{NOM}.multiplication",
        enonce=_enonce(rng, f"{a} × {b}", f"{a} fois {b}"),
        reponse=str(p),
        # une table voisine, ou l'addition à la place de la multiplication
        distracteurs=distracteurs(str(p), [str(a * (b + 1)), str(a * (b - 1)), str(a + b), str((a + 1) * b),
                                           str((a - 1) * b)]),
        explication=f"C'est la table de {a} : {a} × {b} = {p}.",
        cle=("multiplication", min(a, b), max(a, b)),
    )


def division(rng: random.Random) -> Squelette:
    d, q = rng.randint(2, 9), rng.randint(2, 12)
    n = q * d
    return Squelette(
        genre=f"{NOM}.division",
        enonce=_enonce(rng, f"{n} ÷ {d}", f"{n} divisé par {d}"),
        reponse=str(q),
        # un quotient voisin, ou une soustraction à la place de la division
        distracteurs=distracteurs(str(q), [str(q + 1), str(q - 1), str(n - d), str(q + 2)]),
        explication=f"{n} ÷ {d} = {q}, car {d} × {q} = {n}.",
        cle=("division", n, d),
    )


GENRES = (addition, soustraction, multiplication, division)
