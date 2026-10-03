"""N4 — les calculs des questions de maths sont-ils justes ?

Règle d'architecture n° 4 : l'IA n'est jamais seule juge d'un calcul. Pour chaque question, N4 essaie de
reconnaître un genre de question qu'elle sait recalculer (calcul direct, comparaison, égalité,
simplification, Pythagore), refait le calcul en valeurs exactes, et compare le résultat aux propositions.

Trois verdicts par question :
- « verifie »  : calcul refait, la réponse annoncée est juste ;
- « faux »     : calcul refait, la réponse annoncée est fausse (ou aucune / plusieurs propositions justes) → rejet ;
- « a_relire » : question non reconnue, incalculable, ou hors maths. JAMAIS « verifie » par défaut.

Deux principes de prudence :
- **un faux « faux » est aussi grave qu'un faux « vérifié »** : le message de rejet sera renvoyé au modèle
  (reprise sur erreur), qui « corrigerait » alors une bonne réponse. Les reconnaisseurs sont donc ancrés
  sur des formulations précises (« Calcule 3 + 4. », « Quelle fraction est égale à 3/4 ? ») et
  renoncent dès que l'énoncé transforme les nombres (« le double de », « si on multiplie »…) ;
- le texte vient du modèle et n'est **jamais exécuté** : les expressions sont lues avec le module `ast`
  (analyse sans exécution), sur une liste blanche de caractères et d'opérations, avec des bornes.
"""

import ast
import math
import re
from dataclasses import dataclass
from fractions import Fraction

from generateur.moteur.validation import ErreurValidation
from generateur.moteur.validation.n3_pedagogie import (SEPARATEUR_MILLIERS, UNITES, forme_irreductible,
                                                       normaliser, valeur)

VERIFIE, FAUX, A_RELIRE = "verifie", "faux", "a_relire"


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

LISTE_BLANCHE = re.compile(r"^[\d+\-*/(). ]+$")
OPERATIONS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
              ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}


def nettoyer(expression: str) -> str:
    """Écriture scolaire → écriture Python : « 3² × 0,5 » → « 3**2 * 0.5 »."""
    e = re.sub(r"\s+", " ", expression)  # espaces insécables et fines, fréquents en typographie française
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

def preparer(enonce: str) -> str:
    """Forme de travail de l'énoncé : apostrophes droites, espaces simples, « 3 x 4 » → « 3×4 »."""
    e = re.sub(r"\s+", " ", enonce.replace("’", "'")).strip()
    return re.sub(r"(?<=\d) ?[xX] ?(?=\d)", "×", e)


NOMBRE = r"\d+(?:[.,]\d+)?"
# une valeur citée : nombre, décimal, fraction (« 3/4 ») ou pourcentage, isolée du reste du texte
VALEUR_TEXTE = rf"[+\-−]?{NOMBRE}(?: ?/ ?{NOMBRE})?(?: ?%)?"
VALEUR_ENONCE = re.compile(rf"(?<![\w/.,]){VALEUR_TEXTE}(?![\w/]|[.,]\d)")
# une expression : chiffres, opérateurs et parenthèses, commençant et finissant proprement
EXPRESSION = r"[\d(−\-](?:[\d .,+\-−×*·÷:/()²³^]*[\d)²³])?"
OPERATEUR = re.compile(r"[+\-−×*·÷:/^²³]")
CALCUL_HORS_FRACTION = re.compile(r"[+\-−×*·÷:^²³]")  # une barre seule (« 2/5 ») est une fraction, pas un calcul
LONGUEUR = re.compile(rf"({NOMBRE}) ?(mm|cm|dm|km|m)\b")

# une question négative ou approchée se lit à l'envers ou tolère un écart : N4 ne s'y risque pas
PRUDENCE = re.compile(r"\b(pas|jamais|aucune?|environ|arrondi\w*|approch\w*|presque)\b|≈", re.IGNORECASE)
# des mots qui transforment les nombres cités : la réponse n'est plus l'un d'eux, ni leur valeur brute
TRANSFORMATION = re.compile(
    r"\b(double|triple|moitié|tiers|quart|inverse|opposée?|carrée?|cube|racine|fois|multipli\w*|divis\w*|"
    r"ajout\w*|additionn\w*|soustr\w*|retranch\w*|enl[eè]v\w*|somme|différence|produit|quotient|reste|"
    r"si on|si l'on|après)\b", re.IGNORECASE)
# début d'une question directe : « Quelle fraction est », « Quel nombre est », « Parmi ces fractions, laquelle est »
QUESTION_DIRECTE = (r"(?:^|[.!?] )(?:parmi [^,?]{1,40}, )?(?:quel|quelle|quels|quelles|lequel|laquelle)"
                    r"(?: [a-zàâçéèêëîïôûùüÿœ'-]+){0,4}? (?:est|sont)")


def valeurs_enonce(enonce: str) -> list[Fraction]:
    return [valeur(m.group(0))[1] for m in VALEUR_ENONCE.finditer(enonce)]


def expressions(enonce: str) -> list[str]:
    """Les expressions qui contiennent au moins une opération (« 1/2 + 1/3 », « 3² »…)."""
    resultat = []
    for m in re.finditer(EXPRESSION, enonce):
        texte = m.group(0).strip()
        if OPERATEUR.search(texte.lstrip("-−")):
            resultat.append(texte)
    return resultat


def calculs(enonce: str) -> list[str]:
    """Les expressions qui contiennent une vraie opération, pas seulement une barre de fraction."""
    return [e for e in expressions(enonce) if CALCUL_HORS_FRACTION.search(e.lstrip("-−"))]


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
# Chacun reçoit l'énoncé préparé. Il renvoie None s'il ne reconnaît pas la question, un Verdict sinon.
# Le premier qui reconnaît gagne.

HYPOTENUSE = re.compile(r"(longueur|mesure) (de )?l'hypoténuse", re.IGNORECASE)


def pythagore_hypotenuse(n: int, q: dict, enonce: str) -> Verdict | None:
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


EST_RECTANGLE = re.compile(r"est-il (un triangle )?rectangle", re.IGNORECASE)


def pythagore_reciproque(n: int, q: dict, enonce: str) -> Verdict | None:
    if not EST_RECTANGLE.search(enonce):
        return None
    longueurs = LONGUEUR.findall(enonce)
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
FRACTION_ENTIERE = re.compile(r"^(\d+) ?/ ?(\d+)$")


def simplification(n: int, q: dict, enonce: str) -> Verdict | None:
    """« Quelle est la forme irréductible de 4/8 ? » → 1/2 seulement.
    « Simplifie 4/8. » → toute fraction obtenue en divisant 4 et 8 par un même entier (2/4 ou 1/2)."""
    if not SIMPLIFICATION.search(enonce):
        return None
    if TRANSFORMATION.search(enonce) or calculs(enonce):
        return Verdict(A_RELIRE)
    fractions = [m.group(0) for m in VALEUR_ENONCE.finditer(enonce) if "/" in m.group(0)]
    depart = FRACTION_ENTIERE.match(normaliser(fractions[0])) if len(fractions) == 1 else None
    if depart is None:
        return Verdict(A_RELIRE)
    num, den = int(depart[1]), int(depart[2])
    cible = Fraction(num, den)
    irreductible_demandee = "irréductible" in enonce.lower()

    def convient(p: str) -> bool:
        texte = normaliser(p)
        if irreductible_demandee:
            return forme_irreductible(p) and valeur(p) == ("", cible)
        m = FRACTION_ENTIERE.match(texte)
        a, b = (int(m[1]), int(m[2])) if m else (int(texte), 1) if texte.isdigit() else (0, 0)
        # une simplification divise les deux termes par un même entier : 4/8 → 2/4 ou 1/2, mais pas 3/6
        return a > 0 and Fraction(a, b) == cible and a < num and num % a == 0 and den % b == 0

    justes = [i for i, p in enumerate(q["propositions"]) if convient(p)]
    illisibles = [i for i, p in enumerate(q["propositions"]) if valeur(p) is None]
    if irreductible_demandee:
        attendu = f"la forme irréductible de {num}/{den} est {formater(cible)}"
    else:
        attendu = f"une simplification de {num}/{den} divise ses deux termes par un même nombre"
    return trancher(n, q, justes, illisibles, attendu)


EGALITE = re.compile(rf"{QUESTION_DIRECTE} (?:égale?s?|équivalente?s?) (?:à|a) (?P<x>{VALEUR_TEXTE}) ?\?$",
                     re.IGNORECASE)


def egalite(n: int, q: dict, enonce: str) -> Verdict | None:
    """« Quelle fraction est égale à 3/4 ? » — formulation directe uniquement."""
    m = EGALITE.search(enonce)
    if not m:
        return None
    if TRANSFORMATION.search(enonce):
        return Verdict(A_RELIRE)
    cible = valeur(m["x"])[1]
    return _selon_valeur(n, q, cible, f"la proposition égale à {m['x'].strip()} doit valoir {formater(cible)}")


COMPARAISON = re.compile(r"\b(plus|moins) (grand|petit)e?s?\b", re.IGNORECASE)
SEUIL = re.compile(rf"{QUESTION_DIRECTE} (?P<sens>plus|moins) (?P<adj>grand|petit)e?s? que (?P<x>{VALEUR_TEXTE}) ?\?$",
                   re.IGNORECASE)


def comparaison(n: int, q: dict, enonce: str) -> Verdict | None:
    trouves = list(COMPARAISON.finditer(enonce))
    if not trouves:
        return None
    # plusieurs comparaisons, des calculs à comparer (« 1/2 + 1/4 ou 2/3 ? ») ou des nombres transformés
    # (« le double de… ») : la réponse n'est plus directement l'une des valeurs citées
    if len(trouves) > 1 or calculs(enonce) or TRANSFORMATION.search(enonce):
        return Verdict(A_RELIRE)
    vals = valeurs_nues(q)
    illisibles = [i for i, v in enumerate(vals) if v is None]

    seuil = SEUIL.search(enonce)
    if seuil:  # « Quelle fraction est plus grande que 1/2 ? » : les propositions qui dépassent le seuil
        cherche_max = (seuil["sens"].lower() == "plus") == (seuil["adj"].lower() == "grand")
        x = valeur(seuil["x"])[1]
        justes = [i for i, v in enumerate(vals) if v is not None and (v > x if cherche_max else v < x)]
        sens = "plus grande" if cherche_max else "plus petite"
        return trancher(n, q, justes, illisibles, f"la proposition doit être {sens} que {formater(x)}")
    if re.search(r"\bque\b", enonce[trouves[0].end():], re.IGNORECASE):
        return Verdict(A_RELIRE)  # seuil formulé autrement : pas assez sûr de la lecture

    # « la plus grande entre 2/5 et 3/7 » : la réponse est l'une des valeurs citées
    m = trouves[0]
    cherche_max = (m[1].lower() == "plus") == (m[2].lower() == "grand")
    nombres = valeurs_enonce(enonce)
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


# l'expression suit directement la demande de calcul et termine l'énoncé : « Calcule 7 × 8. »,
# « Quel est le résultat de 1/2 + 1/3 ? », « Combien font 3² + 4² ? », « Complète : 3 + 4 = ? »
DEMANDE_DE_CALCUL = (r"(?:résultat (?:de|du)|calcule[rz]?|effectue[rz]?|combien (?:font|fait|vaut|valent|donne)|"
                     r"que (?:vaut|valent|donne)|valeur de)")
SUPPORT = (r"(?: (?:l'|la |le |du |de l')?(?:opération|expression|calcul|addition|soustraction|multiplication|"
           r"division)(?: suivante?)?)?")
CALCUL_DIRECT = re.compile(rf"\b{DEMANDE_DE_CALCUL}{SUPPORT} ?:? ?(?P<expr>{EXPRESSION}) ?(?:= ?)?[?.!]?$",
                           re.IGNORECASE)
CALCUL_A_COMPLETER = re.compile(rf"(?:^|[:.!?] )(?P<expr>{EXPRESSION}) ?= ?(?:\?|\.\.\.|…)$")


def calcul_direct(n: int, q: dict, enonce: str) -> Verdict | None:
    m = CALCUL_DIRECT.search(enonce) or CALCUL_A_COMPLETER.search(enonce)
    if not m:
        return None
    expression = m["expr"].strip()
    if not OPERATEUR.search(expression.lstrip("-−")) or len(expressions(enonce)) != 1:
        return Verdict(A_RELIRE)
    try:
        resultat = evaluer(expression)
    except Incalculable:
        return Verdict(A_RELIRE)
    en_fraction = "/" in expression
    return _selon_valeur(n, q, resultat, f"{expression} = {formater(resultat, en_fraction)}")


RECONNAISSEURS = (pythagore_hypotenuse, pythagore_reciproque, simplification, egalite, comparaison, calcul_direct)


# --- point d'entrée ------------------------------------------------------------------------------

def verifier_question(n: int, q: dict) -> Verdict:
    enonce = preparer(q["enonce"])
    if PRUDENCE.search(enonce):
        return Verdict(A_RELIRE)
    for reconnaisseur in RECONNAISSEURS:
        try:
            verdict = reconnaisseur(n, q, enonce)
        except (Incalculable, ValueError, ZeroDivisionError, TypeError, IndexError):
            return Verdict(A_RELIRE)
        if verdict is not None:
            return verdict
    return Verdict(A_RELIRE)


def verifier(instance: dict) -> list[Verdict]:
    """Un verdict par question. Hors maths, rien n'est recalculé : tout est « à relire » (architecture §9.4)."""
    if instance.get("matiere") != "maths":
        return [Verdict(A_RELIRE) for _ in instance["questions"]]
    return [verifier_question(n, q) for n, q in enumerate(instance["questions"], start=1)]


def valider(instance: dict) -> dict:
    """Lève ErreurValidation si un calcul est faux ; sinon renvoie le bilan à ranger dans meta.validation."""
    verdicts = verifier(instance)
    faux = [(n, v) for n, v in enumerate(verdicts, start=1) if v.statut == FAUX]
    if faux:
        raise ErreurValidation("N4", [v.message for _, v in faux], tuple(n for n, _ in faux))
    statuts = [v.statut for v in verdicts]
    return {"n4": VERIFIE if all(s == VERIFIE for s in statuts) else A_RELIRE, "n4_questions": statuts}
