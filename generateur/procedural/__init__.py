"""Générateur procédural (étape 1.7) : la réponse pour le programme, la langue pour le modèle.

Pour les notions couvertes, le programme tire la question, connaît la réponse (il la calcule) et fabrique les
distracteurs à partir d'erreurs typiques d'élèves. En maths, le modèle peut réécrire l'énoncé, sous contrôle
(habillage.py). La réponse est juste par construction, au lieu d'être vérifiée après coup. Conception :
docs/etapes/etape-1.7-procedural.md.

Un sous-dossier par matière (`maths/` ; le cycle 2 : docs/Generateur-Procedural/cycle-2-cp-ce1-ce2.md) : son
`__init__` déclare `MATIERE`, `AUTRES_NOTIONS` (les notions de la matière qu'aucun générateur ne couvre) et
`generateurs()` ; chaque module de générateur, `NOM` (unique, toutes matières), `MATIERE`, `NIVEAU` (la classe par
défaut), `NIVEAUX` (celles où il s'applique), `MOTS_CLES`, `GENRES`, `ATTENDUS`, et `TABLES` s'il lit ses réponses
dans des tables de référence (tables.py). Un genre peut recevoir la classe (`genre(rng, niveau)` : la conjugaison du
CP n'est pas celle du CE2) et ne servir qu'à certaines classes (`CLASSES_DU_GENRE = {nom du genre: (classes…)}`).
Ce paquet-ci est commun : le squelette d'une question, les distracteurs, l'aiguillage, le tirage, l'assemblage.
"""

import inspect
import random
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction

from generateur import programmes
from generateur.moteur.validation.n3_pedagogie import cle_de_comparaison, normaliser, valeur


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


def distracteurs(reponse: str, candidats: list[str], nombre: int = 3,
                 egales_permises: bool = False) -> tuple[str, ...]:
    """Les premiers candidats valables, dans l'ordre (le plus plausible d'abord) : distincts en valeur entre eux
    et de la réponse (sinon N3 rejetterait le QCM), et jamais nuls ni négatifs.

    `egales_permises` : des écritures différentes d'une même valeur sont admises (« 6/9 » pour la forme
    irréductible 2/3 de 12/18 : N3 l'accepte quand l'énoncé demande la forme irréductible)."""
    vus, retenus = {cle_de_comparaison(reponse), normaliser(reponse)}, []
    for candidat in candidats:
        v = valeur(candidat)
        cle = normaliser(candidat) if egales_permises else cle_de_comparaison(candidat)
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


def matieres() -> dict:
    """Les matières qui ont des générateurs : {matière : son paquet}. Import local : le paquet reste léger à charger."""
    from generateur.procedural import francais, maths
    return {p.MATIERE: p for p in (maths, francais)}


def notions() -> dict:
    """Les générateurs disponibles, toutes matières, par nom."""
    return {m.NOM: m for paquet in matieres().values() for m in paquet.generateurs()}


def candidats(demande: dict) -> dict:
    """Les générateurs de la matière et de la classe demandées (toutes, si la demande ne les dit pas), dont les tables
    de référence sont relues : un générateur dont une table n'a pas été validée n'est jamais proposé."""
    from generateur.procedural import tables  # import local : `python -m generateur.procedural.tables` reste propre
    matiere, niveau = demande.get("matiere"), demande.get("niveau")
    return {nom: m for nom, m in notions().items()
            if (matiere is None or m.MATIERE == matiere) and (niveau is None or niveau in m.NIVEAUX)
            and tables.relues(m.MATIERE, getattr(m, "TABLES", ()))}


# --- programmes officiels (évolution E2.5) ----------------------------------------------------------
# Chaque générateur déclare, genre par genre et classe par classe, les attendus du programme qu'il travaille
# (ATTENDUS = {genre: {classe: (identifiants…)}}) : un genre sans attendu (le calcul mental de tables, un
# automatisme ; la « partie d'un tout », vue au cours moyen) n'est rattaché à rien.

def attendus_du_genre(module, genre: str, niveau: str | None) -> tuple[str, ...]:
    return tuple(getattr(module, "ATTENDUS", {}).get(genre, {}).get(niveau, ()))


def genres_pour(module, cible: str, niveau: str | None) -> list[Genre]:
    """Les genres du module qui travaillent l'attendu, ou un attendu du thème, `cible`, à cette classe."""
    return [g for g in module.GENRES
            if any(programmes.couvre(cible, a) for a in attendus_du_genre(module, g.__name__, niveau))]


def aiguiller(demande: dict) -> str | None:
    """Le générateur qui couvre la demande, ou None pour la chaîne habituelle (modèle → N1…N4 → reprise).

    Avec un attendu du programme (E2) : le générateur qui en travaille le plus d'attendus distincts (« Les
    fractions » de 6e : les fractions plutôt que les pourcentages, rangés dans le même thème) ; aucun → le modèle.

    Sans attendu : une seule notion couverte, et aucune autre notion de sa matière citée : « les pourcentages »,
    « l'addition de fractions » → oui ; « fractions et pourcentages », « les nombres décimaux » → non. Un générateur
    peut déclarer des mots qui l'excluent (EXCLUS) : « addition » désigne le calcul mental, sauf s'il s'agit de
    fractions.

    Seuls les générateurs de la matière et de la classe demandées comptent (`candidats`) : « le calcul mental »
    pour des CP n'est pas celui de 6e."""
    modules = candidats(demande)
    if not modules:
        return None
    if cible := demande.get("attendu"):
        niveau = demande.get("niveau")
        scores = []
        for nom, module in modules.items():
            genres = genres_pour(module, cible, niveau)
            distincts = {a for g in genres for a in attendus_du_genre(module, g.__name__, niveau)}
            scores.append((len(distincts), len(genres), nom))
        meilleur = max(scores)
        return meilleur[2] if meilleur[1] else None
    texte = sans_accents(" ".join(str(demande.get(c) or "") for c in ("notion", "demande_enseignant")))
    couvertes = [nom for nom, module in modules.items()
                 if any(m in texte for m in module.MOTS_CLES) and not any(x in texte for x in getattr(module, "EXCLUS", ()))]
    if len(couvertes) != 1 or matieres()[modules[couvertes[0]].MATIERE].AUTRES_NOTIONS.search(texte):
        return None
    return couvertes[0]


# --- tirage et assemblage ------------------------------------------------------------------------

ESSAIS_MAX = 200


def _appeler(genre: Genre, rng: random.Random, niveau: str | None) -> Squelette:
    """Le genre, avec la classe s'il la demande (`genre(rng, niveau)`) ; les genres des maths ne la demandent pas."""
    if niveau is not None and "niveau" in inspect.signature(genre).parameters:
        return genre(rng, niveau=niveau)
    return genre(rng)


def classes_du_genre(module, genre: Genre) -> tuple[str, ...]:
    """Les classes où le genre sert (toutes celles du module, s'il ne dit rien)."""
    return tuple(getattr(module, "CLASSES_DU_GENRE", {}).get(genre.__name__, module.NIVEAUX))


def tirer_une(genre: Genre, rng: random.Random, deja: set, niveau: str | None = None) -> Squelette:
    """Une question du genre, différente de celles déjà tirées."""
    for _ in range(ESSAIS_MAX):
        try:
            squelette = _appeler(genre, rng, niveau)
        except Retirer:
            continue
        if squelette.cle not in deja:
            deja.add(squelette.cle)
            return squelette
    raise RuntimeError("le générateur ne trouve plus de question nouvelle : demander moins de questions")


def tirer(notion: str, nombre: int, rng: random.Random, genres: list[Genre] | None = None,
          niveau: str | None = None) -> list[Squelette]:
    """`nombre` questions de la notion, de genres variés : chaque genre une fois, dans un ordre tiré au sort,
    avant qu'un genre revienne. `genres` : seulement ceux-là (ceux d'un attendu du programme). `niveau` : la classe,
    donnée aux genres qui la demandent ; seuls servent les genres de cette classe."""
    module = notions()[notion]
    genres = [g for g in (genres or module.GENRES) if niveau is None or niveau in classes_du_genre(module, g)]
    if not genres:
        raise RuntimeError(f"aucune question de « {module.NOTION} » pour la classe {niveau}")
    ordre: list[Genre] = []
    while len(ordre) < nombre:
        ordre += rng.sample(genres, len(genres))
    deja: set = set()
    return [tirer_une(g, rng, deja, niveau) for g in ordre[:nombre]]


def empreintes_des_tables(module) -> dict[str, str]:
    """{« francais/conjugaisons » : empreinte} : de quelle version des tables l'exercice est tiré."""
    from generateur.procedural import tables
    return {f"{module.MATIERE}/{nom}": tables.charger(module.MATIERE, nom).empreinte
            for nom in getattr(module, "TABLES", ())}


def question(squelette: Squelette, enonce: str, rng: random.Random) -> dict:
    """La question QCM : les propositions mélangées, la position de la bonne réponse retenue."""
    propositions = [squelette.reponse, *squelette.distracteurs]
    rng.shuffle(propositions)
    return {"enonce": enonce, "propositions": propositions, "index_correct": propositions.index(squelette.reponse),
            "explication": squelette.explication}


def assembler(notion: str, niveau: str, squelettes: list[Squelette], enonces: list[str],
              rng: random.Random) -> dict:
    module = notions()[notion]
    return {"type": "qcm", "titre": module.TITRE, "matiere": module.MATIERE, "niveau": niveau, "notion": module.NOTION,
            "questions": [question(s, e, rng) for s, e in zip(squelettes, enonces)]}
