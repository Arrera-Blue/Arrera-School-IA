"""Fractions (6e) : forme irréductible, fraction égale, comparaison, partie d'un tout, addition.

Deuxième lot du générateur procédural, décidé le 07/10 : sur les fractions, Gemma prenait 9 minutes pour 5
questions, se trompait en calcul (3/4 ÷ 2/4 = 1/2) et proposait sans cesse une fraction et sa forme simplifiée
comme deux réponses. Les distracteurs reprennent les erreurs classiques : additionner numérateurs et
dénominateurs, ne simplifier qu'un des deux termes, comparer les seuls numérateurs.
"""

import math
import random
from fractions import Fraction

from generateur.procedural import Retirer, Squelette, distracteurs

NOM, TITRE, NOTION, NIVEAU = "fractions", "Les fractions", "fractions", "6e"
MOTS_CLES = ("fraction",)

# la partie et le tout : « dont 3 sont coloriées », « Léa en mange 3 »… pas « ce qui reste »
COMPLEMENT = r"\breste|\brestant|\bnon\b|\bautres?\b|\bsauf\b|\bne\b|\bn'"


def ecrire(f: Fraction | tuple[int, int]) -> str:
    """(6, 8) → « 6/8 », sans simplifier ; Fraction(3, 4) → « 3/4 »."""
    n, d = (f.numerator, f.denominator) if isinstance(f, Fraction) else f
    return f"{n}/{d}"


def plausibles(*couples: tuple[int, int]) -> list[str]:
    """Les candidats écrits en fractions, sans « 9/1 » ni « 4/4 » : un entier écrit en fraction se repère et s'écarte
    trop facilement (recette 1.6, 08/10)."""
    return [ecrire((n, d)) for n, d in couples if d != 1 and n != d]


def _premier_avec(rng: random.Random, d: int, maxi: int | None = None) -> int:
    """Un numérateur qui rend la fraction irréductible : 3 pour 8, jamais 4 ni 8."""
    return rng.choice([x for x in range(1, (maxi or 2 * d - 1) + 1) if math.gcd(x, d) == 1 and x != d])


def irreductible(rng: random.Random) -> Squelette:
    q = rng.randint(2, 10)
    p = _premier_avec(rng, q)
    k = rng.choice([2, 3, 4, 5, 6])
    n, d = p * k, q * k
    if d > 60:
        raise Retirer("nombres trop grands pour la 6e")
    reponse = ecrire((p, q))
    # une simplification partielle (même valeur, mais pas irréductible : N3 l'admet ici), l'inverse,
    # un seul terme simplifié
    g = next((g for g in (2, 3) if k % g == 0 and g < k), None)
    partielle = [ecrire((n // g, d // g))] if g else []
    return Squelette(
        genre=f"{NOM}.irreductible",
        enonce=rng.choice([f"Quelle est la forme irréductible de {n}/{d} ?",
                           f"Écris la fraction {n}/{d} sous forme irréductible."]),
        reponse=reponse,
        distracteurs=distracteurs(reponse, [*partielle, *plausibles((q, p), (p, d), (n, q), (p + 1, q), (p, q + 1))],
                                  egales_permises=True),
        explication=f"On divise le numérateur et le dénominateur par leur plus grand diviseur commun, {k} : "
                    f"{n} ÷ {k} = {p} et {d} ÷ {k} = {q}. La forme irréductible de {n}/{d} est {p}/{q}.",
        cle=("irreductible", n, d),
    )


def egale(rng: random.Random) -> Squelette:
    b = rng.randint(2, 9)
    a = _premier_avec(rng, b)
    k = rng.randint(2, 6)
    reponse = ecrire((a * k, b * k))
    return Squelette(
        genre=f"{NOM}.egale",
        enonce=f"Quelle fraction est égale à {a}/{b} ?",
        reponse=reponse,
        # ajouter le même nombre en haut et en bas, ne multiplier qu'un seul terme
        distracteurs=distracteurs(reponse, plausibles((a + k, b + k), (a * k, b), (a, b * k), (a * k, b * k + 1),
                                                      (a * k + 1, b * k))),
        explication=f"On multiplie le numérateur et le dénominateur de {a}/{b} par le même nombre, {k} : "
                    f"{a} × {k} = {a * k} et {b} × {k} = {b * k}, donc {a}/{b} = {a * k}/{b * k}.",
        cle=("egale", a, b, k),
    )


def comparaison(rng: random.Random) -> Squelette:
    d = rng.randint(3, 10)
    m = rng.choice([1, 2, 3])  # même dénominateur, ou l'un multiple de l'autre
    x = Fraction(_premier_avec(rng, d), d)
    n2 = rng.randint(1, 2 * d * m - 1)
    y = Fraction(n2, d * m)
    if x == y:
        raise Retirer("fractions égales")
    plus_grande = rng.random() < 0.5
    gagnante = max(x, y) if plus_grande else min(x, y)
    fx, fy = ecrire(x), ecrire((n2, d * m))
    reponse = fx if gagnante == x else fy
    sens = "grande" if plus_grande else "petite"
    if m == 1:
        explication = (f"Les deux fractions ont le même dénominateur, {d} : on compare les numérateurs. La plus "
                       f"{sens} est {reponse}.")
    else:
        explication = (f"On écrit {fx} avec le dénominateur {d * m} : {fx} = {x.numerator * m}/{d * m}. On compare "
                       f"alors {x.numerator * m}/{d * m} et {fy} : la plus {sens} est {reponse}.")
    return Squelette(
        genre=f"{NOM}.comparaison",
        enonce=f"Quelle est la plus {sens} des fractions {fx} et {fy} ?",
        reponse=reponse,
        distracteurs=distracteurs(reponse, [fy if reponse == fx else fx, "Elles sont égales"], nombre=2),
        explication=explication,
        cle=("comparaison", fx, fy, sens),
    )


def partie(rng: random.Random) -> Squelette:
    n = rng.randint(3, 12)
    k = rng.randint(1, n - 1)
    reponse = ecrire((k, n))
    return Squelette(
        genre=f"{NOM}.partie",
        enonce=f"Une figure est divisée en {n} parties égales, dont {k} sont coloriées. Quelle fraction de la "
               "figure est coloriée ?",
        reponse=reponse,
        # l'inverse, la partie rapportée au reste, le reste
        distracteurs=distracteurs(reponse, plausibles((n, k), (k, n - k), (n - k, n), (k, n + k))),
        explication=f"La figure est partagée en {n} parties égales ; {k} sont coloriées : la partie coloriée "
                    f"représente {k}/{n} de la figure.",
        cle=("partie", k, n),
        habillable=True,
        # des parts égales, et la question porte sur ces parts, pas sur ce qui reste
        obligatoires=(r"égal|identiques|même taille|mêmes tailles", r"parts?\b|parties|morceaux|tranches|cases|carreaux"),
        interdits=(COMPLEMENT,),
        demande=(r"fraction",),
        demande_interdits=(COMPLEMENT,),
    )


def addition(rng: random.Random) -> Squelette:
    d = rng.randint(3, 10)
    m = rng.choice([1, 1, 2, 3])  # même dénominateur le plus souvent, sinon l'un multiple de l'autre
    a, b = _premier_avec(rng, d, d - 1), rng.randint(1, d * m - 1)
    num, den = a * m + b, d * m
    reponse = ecrire((num, den))
    return Squelette(
        genre=f"{NOM}.addition",
        enonce=f"Calcule {a}/{d} + {b}/{d * m}.",
        reponse=reponse,
        # additionner numérateurs et dénominateurs, ou garder les numérateurs sans les convertir
        distracteurs=distracteurs(reponse, plausibles((a + b, d + d * m), (a + b, d * m), (a * b, den),
                                                      (num + 1, den), (num - 1, den))),
        explication=(f"Les fractions ont le même dénominateur : on additionne les numérateurs. "
                     f"{a}/{d} + {b}/{d} = {a + b}/{d}." if m == 1 else
                     f"On écrit {a}/{d} avec le dénominateur {d * m} : {a}/{d} = {a * m}/{d * m}. Puis on additionne "
                     f"les numérateurs : {a * m}/{d * m} + {b}/{d * m} = {num}/{den}."),
        cle=("addition", a, d, b, d * m),
    )


GENRES = (irreductible, egale, comparaison, partie, addition)
# les attendus du programme que chaque genre travaille (E2.5) ; « partie d'un tout » : sens vu au cours moyen
ATTENDUS = {
    "irreductible": {"6e": ("maths.6e.fractions.08",)},             # Établir des égalités de fractions
    "egale": {"6e": ("maths.6e.fractions.08",)},
    "comparaison": {"6e": ("maths.6e.fractions.09",),               # Comparer et encadrer des fractions
                    "5e": ("maths.5e.nombres-rationnels.01",)},     # Comparer des fractions.
    "addition": {"6e": ("maths.6e.fractions.11",),                  # Additionner et soustraire des fractions
                 "5e": ("maths.5e.nombres-rationnels.02",)},        # … de dénominateurs quelconques.
}
