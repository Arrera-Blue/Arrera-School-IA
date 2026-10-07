"""Générateur procédural pour les maths (étape 1.7) : les nombres pour le programme, la langue pour le modèle.

Pour les notions couvertes (calcul mental, pourcentages, Pythagore), le programme tire les nombres, calcule
la réponse et fabrique les distracteurs à partir d'erreurs typiques d'élèves. Le modèle ne fait que réécrire
l'énoncé, sous contrôle (habillage.py). Le calcul est juste par construction, au lieu d'être vérifié après
coup. Conception : docs/etapes/etape-1.7-procedural.md.
"""

import random
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction

from generateur.moteur.validation.n3_pedagogie import cle_de_comparaison, valeur


@dataclass(frozen=True)
class Squelette:
    """Une question tirée : juste par construction, prête à être habillée puis assemblée."""
    genre: str                      # « pourcentages.remise »
    enonce: str                     # énoncé-gabarit, reconnu par N4 quand c'est possible
    reponse: str
    distracteurs: tuple[str, ...]   # 3 mauvaises réponses, distinctes en valeur
    explication: str
    cle: tuple                      # deux questions de même clé ne figurent pas dans un même exercice
    # habillage par le modèle : interdit pour le calcul mental (une histoire changerait l'opération) et
    # les conversions ; sinon, motifs que l'énoncé réécrit doit tous contenir, ou ne doit pas contenir
    habillable: bool = False
    obligatoires: tuple[str, ...] = field(default=())
    interdits: tuple[str, ...] = field(default=())
    # les mêmes, pour la seule question finale : « Quel est son nouveau prix ? », pas « le montant de la remise »
    demande: tuple[str, ...] = field(default=())
    demande_interdits: tuple[str, ...] = field(default=())


class Retirer(Exception):
    """Tirage inutilisable (distracteurs trop peu nombreux, résultat non entier…) : on tire à nouveau."""


Genre = Callable[[random.Random], Squelette]


# --- écriture des nombres ------------------------------------------------------------------------

def ecrire(x: Fraction | int) -> str:
    """35 → « 35 » ; 7,5 → « 7,5 » (virgule décimale, à la française)."""
    x = Fraction(x)
    if x.denominator == 1:
        return str(x.numerator)
    texte = f"{float(x):.6f}".rstrip("0").rstrip(".")
    if Fraction(texte) != x:
        raise Retirer(f"{x} n'a pas d'écriture décimale courte")
    return texte.replace(".", ",")


def distracteurs(reponse: str, candidats: list[str], nombre: int = 3) -> tuple[str, ...]:
    """Les premiers candidats valables, dans l'ordre (le plus plausible d'abord) : distincts en valeur entre eux
    et de la réponse (sinon N3 rejetterait le QCM), et jamais nuls ni négatifs."""
    vus, retenus = {cle_de_comparaison(reponse)}, []
    for candidat in candidats:
        v = valeur(candidat)
        cle = cle_de_comparaison(candidat)
        if cle in vus or (v is not None and v[1] <= 0):
            continue
        vus.add(cle)
        retenus.append(candidat)
        if len(retenus) == nombre:
            return tuple(retenus)
    raise Retirer("pas assez de distracteurs distincts")


# --- aiguillage ----------------------------------------------------------------------------------

def sans_accents(texte: str) -> str:
    return unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()


# d'autres notions de maths : si la demande en cite une, elle n'est pas couverte en entier par un générateur ;
# en début de mot (« aire » n'est pas dans « scolaire », ni « angle » dans « triangle »)
AUTRES_NOTIONS = re.compile(r"\b(?:fraction|decima|equation|relatif|proportionnal|aires?\b|perimetre|volume|"
                            r"puissance|racine|statisti|probabilit|thales|trigonometr|fonction|geometr|symetr|"
                            r"conversion|division euclidienne)")


def notions() -> dict:
    """Les générateurs disponibles, par nom. Import local : le paquet reste léger à charger."""
    from generateur.procedural import calcul_mental, pourcentages, pythagore
    return {m.NOM: m for m in (calcul_mental, pourcentages, pythagore)}


def aiguiller(demande: dict) -> str | None:
    """Le générateur qui couvre la demande, ou None pour la chaîne habituelle (modèle → N1…N4 → reprise).

    Une seule notion couverte, et aucune autre notion de maths citée : « les pourcentages » → oui ;
    « les fractions », « fractions et pourcentages » → non."""
    if demande.get("matiere") not in (None, "maths"):
        return None
    texte = sans_accents(" ".join(str(demande.get(c) or "") for c in ("notion", "demande_enseignant")))
    couvertes = [nom for nom, module in notions().items() if any(m in texte for m in module.MOTS_CLES)]
    if len(couvertes) != 1 or AUTRES_NOTIONS.search(texte):
        return None
    return couvertes[0]


# --- tirage et assemblage ------------------------------------------------------------------------

ESSAIS_MAX = 200


def tirer_une(genre: Genre, rng: random.Random, deja: set) -> Squelette:
    """Une question du genre, différente de celles déjà tirées."""
    for _ in range(ESSAIS_MAX):
        try:
            squelette = genre(rng)
        except Retirer:
            continue
        if squelette.cle not in deja:
            deja.add(squelette.cle)
            return squelette
    raise RuntimeError("le générateur ne trouve plus de question nouvelle : demander moins de questions")


def tirer(notion: str, nombre: int, rng: random.Random) -> list[Squelette]:
    """`nombre` questions de la notion, de genres variés : chaque genre une fois, dans un ordre tiré au sort,
    avant qu'un genre revienne."""
    genres = list(notions()[notion].GENRES)
    ordre: list[Genre] = []
    while len(ordre) < nombre:
        ordre += rng.sample(genres, len(genres))
    deja: set = set()
    return [tirer_une(g, rng, deja) for g in ordre[:nombre]]


def question(squelette: Squelette, enonce: str, rng: random.Random) -> dict:
    """La question QCM : les propositions mélangées, la position de la bonne réponse retenue."""
    propositions = [squelette.reponse, *squelette.distracteurs]
    rng.shuffle(propositions)
    return {"enonce": enonce, "propositions": propositions, "index_correct": propositions.index(squelette.reponse),
            "explication": squelette.explication}


def assembler(notion: str, niveau: str, squelettes: list[Squelette], enonces: list[str],
              rng: random.Random) -> dict:
    module = notions()[notion]
    return {"type": "qcm", "titre": module.TITRE, "matiere": "maths", "niveau": niveau, "notion": module.NOTION,
            "questions": [question(s, e, rng) for s, e in zip(squelettes, enonces)]}
