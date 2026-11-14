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
Un générateur large (la conjugaison, le vocabulaire) déclare ses notions précises (`PRECISIONS`, `Precision`) : « les
contraires » ne tire que des contraires, « l'imparfait » que l'imparfait (critère de fin du lot 1, 13/11).
Ce paquet-ci est commun : le squelette d'une question, les distracteurs, l'aiguillage, le tirage, l'assemblage.
"""

import inspect
import random
import re
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
    # ce dont parle la question (la paire allumer / éteindre, le trio boulot / travail / labeur) : deux questions du
    # même sujet ne viennent dans un exercice que s'il ne reste pas assez d'autres sujets (pas de redondance : l'une
    # donnerait la réponse de l'autre)
    sujet: tuple | None = None


@dataclass(frozen=True)
class Precision:
    """Une notion plus précise que son générateur : « les contraires » dans le vocabulaire, « l'imparfait » dans la
    conjugaison. `motif` : les mots qui la nomment (texte sans accents) ; `titre` : ajouté au titre de l'exercice ;
    `genres` : les genres qui la travaillent (vide : elle n'en écarte aucun) ; `criteres` : ce que leurs questions
    doivent respecter ((("temps", ("imparfait",)),) : une ligne de la table dont le temps est l'imparfait), donné à
    ces genres (`genre(rng, niveau, criteres)`), à eux seuls (« l'imparfait et l'infinitif » : l'infinitif de
    n'importe quelle forme)."""
    motif: str
    titre: str
    genres: tuple[str, ...] = ()
    criteres: tuple[tuple[str, tuple[str, ...]], ...] = ()


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


def texte_de(demande: dict) -> str:
    """La notion et la phrase de l'enseignant, sans accents : ce que lisent les mots-clés et les notions précises."""
    return sans_accents(" ".join(str(demande.get(c) or "") for c in ("notion", "demande_enseignant")))


def preciser(module, demande: dict) -> list[Precision]:
    """Les notions précises que la demande nomme, de la plus précise à la plus générale (l'ordre de `PRECISIONS`) : ce
    qu'une notion a lu ne compte plus pour les suivantes (« les pluriels en -aux » n'est pas aussi « le pluriel »)."""
    texte, trouvees = texte_de(demande), []
    for precision in getattr(module, "PRECISIONS", ()):
        motif = re.compile(precision.motif)
        if motif.search(texte):
            trouvees.append(precision)
            texte = motif.sub(" ", texte)
    return trouvees


@dataclass(frozen=True)
class Selection:
    """Ce que le générateur tire pour une demande : les genres, les critères de chacun ({nom du genre : critères}),
    les notions précises nommées."""
    genres: list
    criteres: dict[str, dict]
    titres: list[str]


def _utilisable(genre: Genre, niveau: str | None, criteres: dict) -> bool:
    """Le genre sait-il tirer une question qui respecte les critères (« être et avoir » : pas de terminaison, les
    terminaisons n'étant demandées qu'aux verbes en -er) ?"""
    if "criteres" not in inspect.signature(genre).parameters:
        return False
    rng = random.Random(0)
    for _ in range(50):
        try:
            _appeler(genre, rng, niveau, criteres)
            return True
        except Retirer:
            continue
    return False


def selection(module, demande: dict, niveau: str | None) -> Selection:
    """Les genres de la classe ; ceux de l'attendu du programme, s'il y en a un ; ceux des notions précises nommées
    (« les contraires »), s'il y en a. Vide : le générateur ne sait pas faire cette demande (« la ponctuation » au CP :
    la demande part au modèle)."""
    genres = [g for g in module.GENRES if niveau is None or niveau in classes_du_genre(module, g)]
    if cible := demande.get("attendu"):
        du_programme = genres_pour(module, cible, niveau)
        genres = [g for g in genres if g in du_programme]
    precisions = preciser(module, demande)
    if noms := {n for p in precisions for n in p.genres}:
        genres = [g for g in genres if g.__name__ in noms]
    criteres: dict[str, dict] = {}
    for g in genres:  # « le présent et le futur » : les deux temps ; « le futur des verbes en -er » : les deux critères
        siens: dict[str, tuple] = {}
        for p in precisions:
            if not p.genres or g.__name__ in p.genres:
                for cle, valeurs in p.criteres:
                    siens[cle] = tuple(dict.fromkeys((*siens.get(cle, ()), *valeurs)))
        if siens:
            criteres[g.__name__] = siens
    genres = [g for g in genres if g.__name__ not in criteres or _utilisable(g, niveau, criteres[g.__name__])]
    # au titre, une notion déjà comprise dans une autre n'est pas répétée (« les pluriels et les féminins
    # particuliers » dans la notion, « les pluriels en -aux » dans la phrase)
    titres = [p.titre for i, p in enumerate(precisions)
              if p.criteres or not p.genres or not any(set(p.genres) <= set(q.genres) for q in precisions[:i])]
    return Selection(genres, {n: c for n, c in criteres.items() if n in {g.__name__ for g in genres}},
                     list(dict.fromkeys(titres)))


def titre(module, titres: list[str]) -> str:
    """« Le vocabulaire : les contraires », « La conjugaison : le futur, les verbes en -er » ; le titre du générateur
    seul s'il est trop long pour le schéma (80)."""
    if not titres:
        return module.TITRE
    complet = f"{module.TITRE} : {', '.join(titres)}"
    return complet if len(complet) <= 80 else module.TITRE


def aiguiller(demande: dict) -> str | None:
    """Le générateur qui couvre la demande, ou None pour la chaîne habituelle (modèle → N1…N4 → reprise).

    Avec un attendu du programme (E2) : le générateur qui en travaille le plus d'attendus distincts (« Les
    fractions » de 6e : les fractions plutôt que les pourcentages, rangés dans le même thème) ; aucun → le modèle.

    Sans attendu : une seule notion couverte, et aucune autre notion de sa matière citée : « les pourcentages »,
    « l'addition de fractions » → oui ; « fractions et pourcentages », « les nombres décimaux » → non. Un générateur
    peut déclarer des mots qui l'excluent (EXCLUS) : « addition » désigne le calcul mental, sauf s'il s'agit de
    fractions.

    Seuls les générateurs de la matière et de la classe demandées comptent (`candidats`) : « le calcul mental »
    pour des CP n'est pas celui de 6e. Une notion précise que le générateur n'a pas dans cette classe (« la
    ponctuation » au CP) part au modèle (`selection` vide)."""
    modules = candidats(demande)
    if not modules:
        return None
    niveau = demande.get("niveau")
    if cible := demande.get("attendu"):
        scores = []
        for nom, module in modules.items():
            genres = selection(module, demande, niveau).genres
            distincts = {a for g in genres for a in attendus_du_genre(module, g.__name__, niveau)}
            scores.append((len(distincts), len(genres), nom))
        meilleur = max(scores)
        return meilleur[2] if meilleur[1] else None
    texte = texte_de(demande)
    couvertes = [nom for nom, module in modules.items()
                 if any(m in texte for m in module.MOTS_CLES) and not any(x in texte for x in getattr(module, "EXCLUS", ()))]
    if len(couvertes) != 1 or matieres()[modules[couvertes[0]].MATIERE].AUTRES_NOTIONS.search(texte):
        return None
    return couvertes[0] if selection(modules[couvertes[0]], demande, niveau).genres else None


# --- tirage et assemblage ------------------------------------------------------------------------

ESSAIS_MAX = 200


def _appeler(genre: Genre, rng: random.Random, niveau: str | None, criteres: dict | None = None) -> Squelette:
    """Le genre, avec la classe s'il la demande (`genre(rng, niveau)`) ; les genres des maths ne la demandent pas. Les
    critères d'une notion précise, s'il y en a (`genre(rng, niveau, criteres)`)."""
    parametres = inspect.signature(genre).parameters
    options = {}
    if niveau is not None and "niveau" in parametres:
        options["niveau"] = niveau
    if criteres and "criteres" in parametres:
        options["criteres"] = criteres
    return genre(rng, **options)


def classes_du_genre(module, genre: Genre) -> tuple[str, ...]:
    """Les classes où le genre sert (toutes celles du module, s'il ne dit rien)."""
    return tuple(getattr(module, "CLASSES_DU_GENRE", {}).get(genre.__name__, module.NIVEAUX))


def tirer_une(genre: Genre, rng: random.Random, deja: set, niveau: str | None = None,
              criteres: dict | None = None) -> Squelette:
    """Une question du genre, différente de celles déjà tirées ; d'un autre sujet, tant que c'est possible (la moitié
    des essais : ensuite, une question nouvelle d'un sujet déjà vu vaut mieux que pas de question)."""
    secours = None
    for essai in range(ESSAIS_MAX):
        try:
            squelette = _appeler(genre, rng, niveau, criteres)
        except Retirer:
            continue
        if squelette.cle in deja:
            continue
        if squelette.sujet is not None and ("sujet", squelette.sujet) in deja and essai < ESSAIS_MAX // 2:
            secours = secours or squelette
            continue
        return _retenir(squelette, deja)
    if secours is not None:
        return _retenir(secours, deja)
    raise RuntimeError("le générateur ne trouve plus de question nouvelle : demander moins de questions")


def _retenir(squelette: Squelette, deja: set) -> Squelette:
    deja.add(squelette.cle)
    if squelette.sujet is not None:
        deja.add(("sujet", squelette.sujet))
    return squelette


def tirer(notion: str, nombre: int, rng: random.Random, genres: list[Genre] | None = None,
          niveau: str | None = None, criteres: dict[str, dict] | None = None) -> list[Squelette]:
    """`nombre` questions de la notion, de genres variés : chaque genre une fois, dans un ordre tiré au sort,
    avant qu'un genre revienne. `genres` : seulement ceux-là (`selection`). `niveau` : la classe, donnée aux genres qui
    la demandent ; seuls servent les genres de cette classe. `criteres` : ceux des notions précises, genre par genre
    (`selection`)."""
    module = notions()[notion]
    genres = [g for g in (genres or module.GENRES) if niveau is None or niveau in classes_du_genre(module, g)]
    if not genres:
        raise RuntimeError(f"aucune question de « {module.NOTION} » pour la classe {niveau}")
    ordre: list[Genre] = []
    while len(ordre) < nombre:
        ordre += rng.sample(genres, len(genres))
    deja: set = set()
    return [tirer_une(g, rng, deja, niveau, (criteres or {}).get(g.__name__)) for g in ordre[:nombre]]


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
              rng: random.Random, titres: list[str] | None = None) -> dict:
    module = notions()[notion]
    return {"type": "qcm", "titre": titre(module, titres or []), "matiere": module.MATIERE, "niveau": niveau, "notion": module.NOTION,
            "questions": [question(s, e, rng) for s, e in zip(squelettes, enonces)]}
