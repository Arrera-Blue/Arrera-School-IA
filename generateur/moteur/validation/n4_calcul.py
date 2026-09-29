"""N4 — les calculs des questions de maths sont-ils justes ?

Règle d'architecture n° 4 : l'IA n'est jamais seule juge d'un calcul. Pour chaque question, N4 essaie de
reconnaître un genre de question qu'elle sait recalculer (calcul direct, comparaison, égalité,
simplification, Pythagore), refait le calcul en valeurs exactes, et compare le résultat aux propositions.

Trois verdicts par question :
- « verifie » : calcul refait, la réponse annoncée est juste ;
- « faux »    : calcul refait, la réponse annoncée est fausse (ou aucune / plusieurs propositions justes) → rejet ;
- « a_relire » : question non reconnue ou incalculable. JAMAIS « verifie » par défaut.

Sécurité : le texte vient du modèle et n'est jamais exécuté. Les expressions sont lues avec le module
`ast` (analyse sans exécution), sur une liste blanche de caractères et d'opérations, avec des bornes.
"""

import ast
import math
import re
from dataclasses import dataclass
from fractions import Fraction

from generateur.moteur.validation import ErreurValidation
from generateur.moteur.validation.n3_pedagogie import SEPARATEUR_MILLIERS, UNITES, normaliser, valeur

VERIFIE, FAUX, A_RELIRE, NON_APPLICABLE = "verifie", "faux", "a_relire", "non_applicable"


@dataclass(frozen=True)
class Verdict:
    statut: str
    message: str = ""


class Incalculable(Exception):
    """Expression que N4 refuse de calculer : caractère inattendu, division par zéro, nombre démesuré…"""


# --- calcul sûr ----------------------------------------------------------------------------------

EXPOSANT_MAX = 10
CHIFFRES_MAX = 12      # par nombre écrit dans l'expression
CHIFFRES_RESULTAT_MAX = 30

LISTE_BLANCHE = re.compile(r"^[\d+\-*/().\s]+$")
OPERATIONS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
              ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}


def nettoyer(expression: str) -> str:
    """Écriture scolaire → écriture Python : « 3² × 0,5 » → « 3**2 * 0.5 »."""
    e = expression
    for avant, apres in (("×", "*"), ("·", "*"), ("÷", "/"), (":", "/"), ("−", "-"), ("–", "-"),
                         ("²", "**2"), ("³", "**3"), ("^", "**")):
        e = e.replace(avant, apres)
    e = SEPARATEUR_MILLIERS.sub("", e)  # « 1 000 + 250 » → « 1000 + 250 »
    return re.sub(r"(?<=\d),(?=\d)", ".", e)


def _taille(f: Fraction) -> int:
    return max(len(str(abs(f.numerator))), len(str(f.denominator)))


def evaluer(expression: str) -> Fraction:
    """Valeur exacte d'une expression arithmétique écrite par le modèle, sans jamais l'exécuter."""
    source = nettoyer(expression).strip()
    if not source or not LISTE_BLANCHE.match(source):
        raise Incalculable(f"caractère non autorisé dans « {expression} »")
    try:
        arbre = ast.parse(source, mode="eval")
    except SyntaxError as e:
        raise Incalculable(f"expression illisible : « {expression} »") from e

    def calculer(noeud: ast.AST) -> Fraction:
        match noeud:
            case ast.Constant(value=int() | float()):
                texte = ast.get_source_segment(source, noeud)
                if texte is None or len(texte.replace(".", "")) > CHIFFRES_MAX:
                    raise Incalculable("nombre trop long")
                return Fraction(texte)  # depuis le texte : « 0.1 » reste exactement 1/10
            case ast.UnaryOp(op=ast.USub(), operand=x):
                return -calculer(x)
            case ast.UnaryOp(op=ast.UAdd(), operand=x):
                return calculer(x)
            case ast.BinOp(left=g, op=ast.Pow(), right=d):
                base, exposant = calculer(g), calculer(d)
                if exposant.denominator != 1 or abs(exposant) > EXPOSANT_MAX:
                    raise Incalculable("exposant non entier ou trop grand")
                if _taille(base) * abs(exposant) > CHIFFRES_RESULTAT_MAX:
                    raise Incalculable("résultat démesuré")
                if base == 0 and exposant < 0:
                    raise Incalculable("division par zéro")
                resultat = base ** int(exposant)
            case ast.BinOp(left=g, op=op, right=d) if type(op) in OPERATIONS:
                try:
                    resultat = OPERATIONS[type(op)](calculer(g), calculer(d))
                except ZeroDivisionError as e:
                    raise Incalculable("division par zéro") from e
            case _:
                raise Incalculable(f"opération non autorisée dans « {expression} »")
        if _taille(resultat) > CHIFFRES_RESULTAT_MAX:
            raise Incalculable("résultat démesuré")
        return resultat

    return calculer(arbre.body)


def racine_exacte(f: Fraction) -> Fraction | None:
    """√f si c'est un nombre rationnel (√25 = 5, √(9/4) = 3/2), sinon None."""
    if f < 0:
        return None
    n, d = math.isqrt(f.numerator), math.isqrt(f.denominator)
    return Fraction(n, d) if n * n == f.numerator and d * d == f.denominator else None


def formater(f: Fraction, en_fraction: bool = True) -> str:
    """5/6 → « 5/6 » ; 56 → « 56 » ; 3/4 hors fractions → « 0,75 »."""
    if f.denominator == 1:
        return str(f.numerator)
    d = f.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if not en_fraction and d == 1:
        entier, reste = divmod(abs(f.numerator) * 10 ** 12 // f.denominator, 10 ** 12)
        signe = "-" if f < 0 else ""
        return f"{signe}{entier},{str(reste).rjust(12, '0').rstrip('0')}"
    return f"{f.numerator}/{f.denominator}"


# --- lecture de l'énoncé -------------------------------------------------------------------------

NOMBRE = r"\d+(?:[.,]\d+)?"
# une valeur écrite dans l'énoncé : nombre, décimal ou fraction (« 3/4 »), isolé du reste du texte
VALEUR_ENONCE = re.compile(rf"(?<![\w/.,])[+\-−]?{NOMBRE}(?:\s*/\s*{NOMBRE})?(?![\w/]|[.,]\d)")
# une expression candidate : chiffres, opérateurs et parenthèses, commençant et finissant proprement
EXPRESSION = re.compile(r"[\d(−\-](?:[\d\s.,+\-−×*·÷:/()²³^]*[\d)²³])?")
OPERATEUR = re.compile(r"[+\-−×*·÷:/^²³]")
CALCUL_HORS_FRACTION = re.compile(r"[+\-−×*·÷:^²³]")  # une barre seule (« 2/5 ») est une fraction, pas un calcul
LONGUEUR = re.compile(rf"({NOMBRE})\s*(mm|cm|dm|km|m)\b")

# une question négative ou approchée se lit à l'envers ou tolère un écart : N4 ne s'y risque pas
PRUDENCE = re.compile(r"\b(pas|jamais|aucune?|environ|arrondi\w*|approch\w*|presque)\b|≈", re.IGNORECASE)


def valeurs_enonce(enonce: str) -> list[Fraction]:
    return [valeur(m.group(0))[1] for m in VALEUR_ENONCE.finditer(enonce)]


def expressions(enonce: str) -> list[str]:
    """Les expressions qui contiennent au moins une opération (« 1/2 + 1/3 », « 3² »…)."""
    resultat = []
    for m in EXPRESSION.finditer(enonce):
        texte = m.group(0).strip()
        if OPERATEUR.search(texte.lstrip("-−")):
            resultat.append(texte)
    return resultat


def valeurs_nues(q: dict) -> list[Fraction | None]:
    """Valeur de chaque proposition si c'est un nombre sans unité (« 5/6 », « 0,5 », « 50 % »), sinon None."""
    vals = []
    for p in q["propositions"]:
        v = valeur(p)
        vals.append(v[1] if v is not None and v[0] == "" else None)
    return vals


# --- verdict commun ------------------------------------------------------------------------------

def trancher(n: int, q: dict, justes: list[int], illisibles: list[int], attendu: str) -> Verdict:
    """Compare les propositions reconnues justes par le calcul à la réponse annoncée par le modèle."""
    annoncee = q["index_correct"]
    propositions = q["propositions"]
    if len(justes) == 1 and justes[0] == annoncee:
        return Verdict(VERIFIE)
    # prudence : une proposition illisible (« cinq sixièmes ») pourrait être la bonne réponse
    if annoncee in illisibles or (not justes and illisibles):
        return Verdict(A_RELIRE)
    if not justes:
        return Verdict(FAUX, f"question {n} : {attendu}, et aucune proposition ne correspond")
    if len(justes) > 1:
        liste = ", ".join(f"« {propositions[i]} »" for i in justes)
        return Verdict(FAUX, f"question {n} : {attendu}, et plusieurs propositions conviennent ({liste}) ; "
                             "une seule doit être juste")
    return Verdict(FAUX, f"question {n} : {attendu}, mais la réponse annoncée est « {propositions[annoncee]} » "
                         f"au lieu de « {propositions[justes[0]]} »")


def _selon_valeur(n: int, q: dict, cible: Fraction, attendu: str) -> Verdict:
    vals = valeurs_nues(q)
    justes = [i for i, v in enumerate(vals) if v is not None and v == cible]
    illisibles = [i for i, v in enumerate(vals) if v is None]
    return trancher(n, q, justes, illisibles, attendu)


# --- reconnaisseurs ------------------------------------------------------------------------------
# Chacun renvoie None s'il ne reconnaît pas la question, un Verdict sinon. Le premier qui reconnaît gagne.

HYPOTENUSE = re.compile(r"(longueur|mesure)\s+(de\s+)?l'hypoténuse", re.IGNORECASE)


def pythagore_hypotenuse(n: int, q: dict) -> Verdict | None:
    enonce = q["enonce"].replace("’", "'")
    if not (HYPOTENUSE.search(enonce) and "angle droit" in enonce.lower()):
        return None
    longueurs = LONGUEUR.findall(enonce)
    if len(longueurs) != 2 or longueurs[0][1] != longueurs[1][1]:
        return Verdict(A_RELIRE)
    unite = longueurs[0][1]
    a, b = (Fraction(x.replace(",", ".")) for x, _ in longueurs)
    c = racine_exacte(a * a + b * b)
    if c is None:  # hypoténuse non entière : réponse forcément arrondie, hors du champ de N4
        return Verdict(A_RELIRE)
    cible = ("longueur", c * UNITES[unite][1])
    justes = [i for i, p in enumerate(q["propositions"]) if valeur(p) == cible]
    illisibles = [i for i, p in enumerate(q["propositions"]) if valeur(p) is None]
    attendu = (f"l'hypoténuse mesure √({formater(a, False)}² + {formater(b, False)}²) = "
               f"{formater(c, False)} {unite}")
    return trancher(n, q, justes, illisibles, attendu)


EST_RECTANGLE = re.compile(r"est-il\s+(un\s+triangle\s+)?rectangle", re.IGNORECASE)


def pythagore_reciproque(n: int, q: dict) -> Verdict | None:
    if not EST_RECTANGLE.search(q["enonce"]):
        return None
    longueurs = LONGUEUR.findall(q["enonce"])
    if len(longueurs) != 3 or len({u for _, u in longueurs}) != 1:
        return Verdict(A_RELIRE)
    a, b, c = sorted(Fraction(x.replace(",", ".")) for x, _ in longueurs)
    rectangle = a * a + b * b == c * c
    attendu_mot, autre_mot = ("oui", "non") if rectangle else ("non", "oui")

    def commence_par(p: str, mot: str) -> bool:
        return re.match(rf"{mot}\b", normaliser(p)) is not None

    avec_attendu = [i for i, p in enumerate(q["propositions"]) if commence_par(p, attendu_mot)]
    annoncee = q["propositions"][q["index_correct"]]
    if avec_attendu == [q["index_correct"]]:
        return Verdict(VERIFIE)
    if commence_par(annoncee, autre_mot):
        signe, conclusion = ("=", "est") if rectangle else ("≠", "n'est pas")
        f = lambda x: formater(x, False)  # noqa: E731
        return Verdict(FAUX, f"question {n} : {f(a)}² + {f(b)}² = {f(a * a + b * b)} {signe} {f(c)}² = "
                             f"{f(c * c)}, donc le triangle {conclusion} rectangle, "
                             f"mais la réponse annoncée est « {annoncee} »")
    return Verdict(A_RELIRE)


SIMPLIFICATION = re.compile(r"simplifi|irréductible", re.IGNORECASE)
FRACTION_SEULE = re.compile(r"^(\d+)\s*/\s*(\d+)$")


def simplification(n: int, q: dict) -> Verdict | None:
    if not SIMPLIFICATION.search(q["enonce"]):
        return None
    fractions = [m.group(0) for m in VALEUR_ENONCE.finditer(q["enonce"]) if "/" in m.group(0)]
    if len(fractions) != 1:
        return Verdict(A_RELIRE)
    cible = valeur(fractions[0])[1]

    def irreductible(p: str) -> bool:
        texte = normaliser(p)
        if cible.denominator == 1:
            return texte == str(cible.numerator)
        m = FRACTION_SEULE.match(texte)
        return m is not None and Fraction(int(m[1]), int(m[2])) == cible and math.gcd(int(m[1]), int(m[2])) == 1

    justes = [i for i, p in enumerate(q["propositions"]) if irreductible(p)]
    return trancher(n, q, justes, [], f"la forme irréductible de {fractions[0]} est {formater(cible)}")


EGALITE = re.compile(rf"(?:égale?s?|équivalente?s?|la même valeur)\s+(?:à|que)\s+"
                     rf"(?P<x>[+\-−]?{NOMBRE}(?:\s*/\s*{NOMBRE})?(?:\s*%)?)(?!\s*[\d+\-−×*·÷:^/])", re.IGNORECASE)


def egalite(n: int, q: dict) -> Verdict | None:
    m = EGALITE.search(q["enonce"])
    if not m:
        return None
    cible = valeur(m["x"])[1]
    return _selon_valeur(n, q, cible, f"la proposition égale à {m['x'].strip()} doit valoir {formater(cible)}")


COMPARAISON = re.compile(r"\b(plus|moins)\s+(grand|petit)e?s?\b(?P<que>\s+que\b)?", re.IGNORECASE)


def comparaison(n: int, q: dict) -> Verdict | None:
    trouves = list(COMPARAISON.finditer(q["enonce"]))
    if not trouves:
        return None
    # plusieurs comparaisons, ou des calculs à comparer (« 1/2 + 1/4 ou 2/3 ? ») : trop risqué
    calculs = [e for e in expressions(q["enonce"]) if CALCUL_HORS_FRACTION.search(e.lstrip("-−"))]
    if len(trouves) > 1 or calculs:
        return Verdict(A_RELIRE)
    m = trouves[0]
    cherche_max = (m[1].lower() == "plus") == (m[2].lower() == "grand")
    vals = valeurs_nues(q)
    illisibles = [i for i, v in enumerate(vals) if v is None]
    nombres = valeurs_enonce(q["enonce"])

    if m["que"]:  # « plus grande que 1/2 » : les propositions qui dépassent le seuil
        if len(nombres) != 1:
            return Verdict(A_RELIRE)
        seuil = nombres[0]
        justes = [i for i, v in enumerate(vals) if v is not None and (v > seuil if cherche_max else v < seuil)]
        sens = "plus grande" if cherche_max else "plus petite"
        return trancher(n, q, justes, illisibles, f"la proposition doit être {sens} que {formater(seuil)}")

    # « la plus grande entre 2/5 et 3/7 » : la réponse est l'une des valeurs citées
    if len(nombres) < 2:
        return Verdict(A_RELIRE)  # comparaison entre les seules propositions : non traitée pour l'instant
    extreme = max(nombres) if cherche_max else min(nombres)
    if nombres.count(extreme) > 1:
        return Verdict(A_RELIRE)
    annoncee = vals[q["index_correct"]]
    # prudence : si la réponse annoncée n'est pas une des valeurs citées, l'énoncé est peut-être un
    # intervalle (« le plus grand entier entre 3 et 7 ») : on ne tranche pas
    if annoncee is None or annoncee not in nombres or extreme not in vals:
        return Verdict(A_RELIRE)
    justes = [i for i, v in enumerate(vals) if v == extreme]
    qualificatif = "grande" if cherche_max else "petite"
    return trancher(n, q, justes, illisibles, f"la plus {qualificatif} valeur est {formater(extreme)}")


CALCUL = re.compile(r"résultat|calcul|combien\s+(font|fait|vaut|valent)|que\s+va(ut|lent)|"
                    r"quelle\s+est\s+la\s+(somme|différence|valeur)|quel\s+est\s+le\s+(produit|quotient)|=\s*\?",
                    re.IGNORECASE)


def calcul_direct(n: int, q: dict) -> Verdict | None:
    if not CALCUL.search(q["enonce"]):
        return None
    candidates = expressions(q["enonce"])
    if len(candidates) != 1:
        return Verdict(A_RELIRE)
    expression = candidates[0]
    try:
        resultat = evaluer(expression)
    except Incalculable:
        return Verdict(A_RELIRE)
    en_fraction = "/" in expression
    return _selon_valeur(n, q, resultat, f"{' '.join(expression.split())} = {formater(resultat, en_fraction)}")


RECONNAISSEURS = (pythagore_hypotenuse, pythagore_reciproque, simplification, egalite, comparaison, calcul_direct)


# --- point d'entrée ------------------------------------------------------------------------------

def verifier_question(n: int, q: dict) -> Verdict:
    if PRUDENCE.search(q["enonce"]):
        return Verdict(A_RELIRE)
    for reconnaisseur in RECONNAISSEURS:
        try:
            verdict = reconnaisseur(n, q)
        except (Incalculable, ValueError, ZeroDivisionError, TypeError, IndexError):
            return Verdict(A_RELIRE)
        if verdict is not None:
            return verdict
    return Verdict(A_RELIRE)


def verifier(instance: dict) -> list[Verdict]:
    if instance.get("matiere") != "maths":
        return [Verdict(NON_APPLICABLE) for _ in instance["questions"]]
    return [verifier_question(n, q) for n, q in enumerate(instance["questions"], start=1)]


def valider(instance: dict) -> dict:
    """Lève ErreurValidation si un calcul est faux ; sinon renvoie le bilan à ranger dans meta.validation."""
    verdicts = verifier(instance)
    faux = [(n, v) for n, v in enumerate(verdicts, start=1) if v.statut == FAUX]
    if faux:
        raise ErreurValidation("N4", [v.message for _, v in faux], tuple(n for n, _ in faux))
    statuts = [v.statut for v in verdicts]
    if all(s == NON_APPLICABLE for s in statuts):
        global_ = NON_APPLICABLE
    elif A_RELIRE in statuts:
        global_ = A_RELIRE
    else:
        global_ = VERIFIE
    return {"n4": global_, "n4_questions": statuts}
