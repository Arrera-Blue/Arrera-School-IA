"""Pourcentages (5e) : p % d'un nombre, remise, augmentation, écriture en pourcentage, taux de réussite.

Le piège de l'habillage, ici, c'est le sens : avec les mêmes nombres, « soldé à 30 % » peut devenir
« augmenté de 30 % », ou la question peut demander le montant de la remise au lieu du nouveau prix. D'où des
motifs obligatoires et interdits, sur tout l'énoncé et sur la question finale.
"""

import math
import random
from fractions import Fraction

from generateur.procedural import Retirer, Squelette, distracteurs, ecrire
from generateur.procedural.maths import COLLEGE

NOM, TITRE, NOTION, NIVEAU = "pourcentages", "Les pourcentages", "pourcentages", "5e"
MATIERE, NIVEAUX = "maths", COLLEGE  # NIVEAU : la classe par défaut ; NIVEAUX : celles où il s'applique
MOTS_CLES = ("pourcentage", "pour cent", "remise", "soldes", "reduction", "augmentation", "taux")

# une question inversée ou niée : « combien ne sont pas… », « ce qui reste »
NEGATION = r"\bne\b|\bn'|\bpas\b|\bnon\b|\breste|\bautres?\b|\bsauf\b"
BAISSE = r"sold|réduc|remise|rabais|baiss|promo|diminu"
HAUSSE = r"augment|hausse|plus cher|major"
PRIX = r"prix|pa[iy]e|coût|vaut|vend|tarif"
# une question sur la variation elle-même, pas sur le nouveau prix
MONTANT = r"montant|économi|de combien"


def euros(x: Fraction | int) -> str:
    return f"{ecrire(x)} €"


def montant(rng: random.Random, p: int, mini: int, maxi: int) -> int:
    """Un nombre rond (multiple de 10) entre mini et maxi, dont p % est entier : 25 % de 40, pas de 30."""
    pas = math.lcm(10, 100 // math.gcd(p, 100))
    if pas > maxi:
        raise Retirer("aucun montant possible")
    return rng.randrange(max(pas, mini - mini % pas), maxi + 1, pas)


def pourcentage_de(rng: random.Random) -> Squelette:
    p = rng.choice([5, 10, 20, 25, 30, 40, 50, 75])
    x = montant(rng, p, 20, 400)
    r = p * x // 100
    return Squelette(
        genre=f"{NOM}.pourcentage_de",
        enonce=f"Calcule {p} % de {x}.",
        reponse=str(r),
        # ce qui reste (x − r), l'oubli d'un zéro, le pourcentage lui-même
        distracteurs=distracteurs(str(r), [str(x - r), str(r * 10), str(p), str(r + 10), str(r * 2)]),
        explication=f"{p} % de {x}, c'est {x} × {p} ÷ 100 = {r}.",
        cle=("pourcentage_de", p, x),
        habillable=True,
        interdits=(NEGATION, BAISSE, HAUSSE),
    )


def remise(rng: random.Random) -> Squelette:
    p = rng.choice([10, 20, 25, 30, 40, 50])
    x = montant(rng, p, 20, 200)
    m = p * x // 100
    r = x - m
    return Squelette(
        genre=f"{NOM}.remise",
        enonce=f"Un article coûte {x} €. Il est soldé à {p} %. Quel est son nouveau prix ?",
        reponse=euros(r),
        # le montant de la remise, le prix moins le pourcentage, la remise ajoutée
        distracteurs=distracteurs(euros(r), [euros(m), euros(x - p), euros(x + m), euros(r + 5)]),
        explication=f"La remise est de {p} % de {x} €, soit {x} × {p} ÷ 100 = {m} €. Le nouveau prix est "
                    f"{x} − {m} = {r} €.",
        cle=("remise", p, x),
        habillable=True,
        obligatoires=(BAISSE,),
        interdits=(HAUSSE, NEGATION),
        # la question porte sur le prix à payer, pas sur le montant de la remise
        demande=(PRIX,),
        demande_interdits=(MONTANT, r"quelle (?:est|sera) la (?:remise|réduction|baisse)"),
    )


def augmentation(rng: random.Random) -> Squelette:
    p = rng.choice([5, 10, 20, 25, 50])
    x = montant(rng, p, 20, 200)
    m = p * x // 100
    r = x + m
    return Squelette(
        genre=f"{NOM}.augmentation",
        enonce=f"Le prix d'un article de {x} € augmente de {p} %. Quel est son nouveau prix ?",
        reponse=euros(r),
        # le montant de la hausse, le prix plus le pourcentage, la hausse retranchée
        distracteurs=distracteurs(euros(r), [euros(m), euros(x + p), euros(x - m), euros(r + 5)]),
        explication=f"L'augmentation est de {p} % de {x} €, soit {x} × {p} ÷ 100 = {m} €. Le nouveau prix est "
                    f"{x} + {m} = {r} €.",
        cle=("augmentation", p, x),
        habillable=True,
        obligatoires=(HAUSSE,),
        interdits=(BAISSE, NEGATION),
        demande=(PRIX,),
        demande_interdits=(MONTANT, r"quelle (?:est|sera) l'(?:augmentation|hausse)|combien de plus"),
    )


def en_pourcentage(rng: random.Random) -> Squelette:
    if rng.random() < 0.5:  # une fraction dont le dénominateur divise 100
        b = rng.choice([2, 4, 5, 10, 20, 25, 50])
        a = rng.randint(1, b - 1)
        p = a * 100 // b
        depart, explication = f"{a}/{b}", f"{a}/{b} = {a * (100 // b)}/100, c'est-à-dire {p} %."
        candidats = [f"{a}{b} %", f"{ecrire(Fraction(a, b))} %", f"{b}{a} %", f"{a} %", f"{p + 10} %"]
    else:  # un décimal
        p = rng.randrange(5, 100, 5)
        decimal = ecrire(Fraction(p, 100))
        depart, explication = decimal, f"{decimal} = {p}/100, c'est-à-dire {p} %."
        candidats = [f"{decimal} %", f"{ecrire(Fraction(p, 10))} %", f"{p * 10} %", f"{p + 10} %"]
    reponse = f"{p} %"
    return Squelette(
        genre=f"{NOM}.en_pourcentage",
        enonce=f"Écris {depart} en pourcentage.",
        reponse=reponse,
        distracteurs=distracteurs(reponse, candidats),
        explication=explication,
        cle=("en_pourcentage", depart),
    )


def taux(rng: random.Random) -> Squelette:
    n = rng.choice([10, 20, 25, 50])  # des diviseurs de 100 : le pourcentage est entier
    k = rng.randint(1, n - 1)
    p = k * 100 // n
    reponse = f"{p} %"
    return Squelette(
        genre=f"{NOM}.taux",
        enonce=f"Un élève a obtenu {k} bonnes réponses sur {n}. Quel est son pourcentage de réussite ?",
        reponse=reponse,
        # le nombre de réussites pris pour un pourcentage, le pourcentage d'échecs, un voisin
        distracteurs=distracteurs(reponse, [f"{k} %", f"{100 - p} %", f"{p + 10} %", f"{p - 10} %", f"{n - k} %"]),
        explication=f"{k} sur {n}, c'est {k}/{n} = {p}/100, soit {p} %.",
        cle=("taux", k, n),
        habillable=True,
        interdits=(r"\b(?:erreurs?|échecs?|rat\w*|manqu\w*|perd\w*|faux|fausses?|mauvais\w*)\b", NEGATION),
        demande=(r"pourcentage|%|taux",),
    )


GENRES = (pourcentage_de, remise, augmentation, en_pourcentage, taux)
# les attendus du programme que chaque genre travaille (E2.5)
_APPLIQUER = {"6e": ("maths.6e.fractions.17",),          # Appliquer un pourcentage à une grandeur ou à un nombre
              "5e": ("maths.5e.proportionnalite.02",)}   # Calculer, appliquer des proportions, des pourcentages.
ATTENDUS = {
    "pourcentage_de": _APPLIQUER, "remise": _APPLIQUER, "augmentation": _APPLIQUER,
    "en_pourcentage": {"6e": ("maths.6e.nombres-decimaux.06",),   # Associer et utiliser différentes écritures…
                       "5e": ("maths.5e.proportionnalite.01",)},  # Utiliser des proportions, des pourcentages.
    "taux": {"6e": ("maths.6e.fractions.16",),                     # Calculer une proportion… sous forme de pourcentage
             "5e": ("maths.5e.proportionnalite.02",)},
}
