"""N3 — l'exercice est-il pédagogiquement cohérent ?

Contrôles déterministes, sans appel au modèle, sur une instance qui a déjà passé N2.
Deux gravités :
- **bloquant** : l'exercice est faux ou inutilisable (deux bonnes réponses possibles, énoncé recopié…) → rejet ;
- **avertissement** : défaut probable mais pas certain (indice de longueur, bonne réponse toujours
  à la même place…) → l'exercice passe, marqué « à relire » pour l'enseignant.

Ce que N3 ne fait pas : vérifier qu'un calcul est juste. C'est le rôle de N4.
"""

import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from fractions import Fraction

from generateur.moteur.validation import ErreurValidation


@dataclass(frozen=True)
class Constat:
    message: str
    bloquant: bool
    question: int | None = None  # numéro à partir de 1 ; None si le défaut concerne tout l'exercice


# --- normalisation -------------------------------------------------------------------------------

ESPACES = re.compile(r"\s+")


def normaliser(texte: str) -> str:
    """Forme de comparaison : casse, espaces (y compris insécables) et ponctuation finale ignorés."""
    texte = unicodedata.normalize("NFKC", texte).replace("’", "'")
    return ESPACES.sub(" ", texte).strip().rstrip(".!;:").strip().lower()


def similarite(a: str, b: str) -> float:
    return SequenceMatcher(None, normaliser(a), normaliser(b)).ratio()


# --- valeurs numériques --------------------------------------------------------------------------
# « 3/4 », « 0,75 », « 75 % » et « 6/8 » désignent la même valeur : deux de ces propositions dans une
# même question donnent deux bonnes réponses. Idem pour « 1 m » et « 100 cm ».

# unité → (grandeur, facteur vers l'unité de base) ; les unités carrées et cubes sont dérivées plus bas
UNITES = {
    **{u: ("longueur", Fraction(f)) for u, f in
       [("mm", "0.001"), ("cm", "0.01"), ("dm", "0.1"), ("m", 1), ("dam", 10), ("hm", 100), ("km", 1000)]},
    **{u: ("masse", Fraction(f)) for u, f in
       [("mg", "0.001"), ("cg", "0.01"), ("dg", "0.1"), ("g", 1), ("dag", 10), ("hg", 100), ("kg", 1000), ("t", 1000000)]},
    **{u: ("contenance", Fraction(f)) for u, f in
       [("ml", "0.001"), ("cl", "0.01"), ("dl", "0.1"), ("l", 1), ("dal", 10), ("hl", 100)]},
    **{u: ("duree", Fraction(f)) for u, f in [("s", 1), ("min", 60), ("h", 3600)]},
    "°": ("angle", Fraction(1)),
    "%": ("", Fraction(1, 100)),  # un pourcentage se compare à un nombre sans unité : 75 % = 0,75
}

NOMBRE = r"[+\-−]?\d+(?:[.,]\d+)?"
# NFKC a déjà transformé « m² » en « m2 » : le chiffre final éventuel appartient à l'unité
VALEUR = re.compile(rf"^(?P<num>{NOMBRE})(?:\s*/\s*(?P<den>{NOMBRE}))?\s*(?P<unite>[^\d\s/]*[23]?)$")
# « 1 000 » → « 1000 » ; \s couvre aussi les espaces insécables
SEPARATEUR_MILLIERS = re.compile(r"(?<=\d)\s(?=\d{3}(?!\d))")


def _nombre(texte: str) -> Fraction:
    return Fraction(texte.replace(",", ".").replace("−", "-"))


def valeur(proposition: str) -> tuple[str, Fraction] | None:
    """(grandeur, valeur dans l'unité de base) si la proposition n'est qu'un nombre, sinon None.

    >>> valeur("6/8") == valeur("0,75") == valeur("75 %")
    True
    """
    texte = SEPARATEUR_MILLIERS.sub("", normaliser(proposition))
    m = VALEUR.match(texte)
    if not m:
        return None
    try:
        nombre = _nombre(m["num"])
        if m["den"] is not None:
            nombre /= _nombre(m["den"])
    except ZeroDivisionError:
        return None

    unite = m["unite"].replace("2", "²").replace("3", "³")
    puissance = 1
    if unite.endswith(("²", "³")):
        puissance = 2 if unite.endswith("²") else 3
        unite = unite[:-1]
    if unite == "":
        return ("", nombre)
    if unite in UNITES:
        grandeur, facteur = UNITES[unite]
        if puissance > 1:
            grandeur = f"{grandeur}^{puissance}"
        return (grandeur, nombre * facteur ** puissance)
    # unité inconnue (« 5 élèves ») : comparable seulement à la même unité
    return (f"{unite}^{puissance}", nombre)


def cle_de_comparaison(proposition: str) -> tuple:
    v = valeur(proposition)
    return ("valeur", *v) if v is not None else ("texte", normaliser(proposition))


FRACTION_ECRITE = re.compile(r"^(\d+) ?/ ?(\d+)$")

# « irréductible », mais aussi « à sa forme la plus simple », « simplifie au maximum » (cas réel du 06/10) ;
# « simplifiée » seul n'en fait pas partie : 2/4 et 1/2 sont toutes deux des simplifications de 4/8
IRREDUCTIBLE = re.compile(
    r"irréductible|(?:forme|écriture|fraction)s? (?:\w+ )?la plus simple"
    r"|simplifi\w* (?:\S+ ){0,3}?(?:au maximum|le plus possible|au plus simple|complètement)")


def irreductible_demandee(enonce: str) -> bool:
    """« Quelle est la forme irréductible de 4/8 ? », « Simplifie 6/12 à sa forme la plus simple. » : oui."""
    return IRREDUCTIBLE.search(normaliser(enonce)) is not None


def forme_irreductible(proposition: str) -> bool:
    """« 1/2 » ou « 3 » : oui ; « 2/4 », « 0,5 » ou « 6/3 » : non."""
    texte = normaliser(proposition)
    if texte.isdigit():
        return True
    m = FRACTION_ECRITE.match(texte)
    return m is not None and int(m[2]) > 1 and math.gcd(int(m[1]), int(m[2])) == 1


# --- règles --------------------------------------------------------------------------------------

def _liste(elements: list[str]) -> str:
    elements = [f"« {e} »" for e in elements]
    return elements[0] if len(elements) == 1 else ", ".join(elements[:-1]) + " et " + elements[-1]


def propositions_vides(n: int, q: dict) -> list[Constat]:
    vides = [i for i, p in enumerate(q["propositions"], start=1) if not p.strip()]
    if vides:
        return [Constat(f"question {n} : proposition(s) {', '.join(map(str, vides))} vide(s)", True, n)]
    return []


FRACTION_DANS_TEXTE = re.compile(r"(?<![\d/,.])\d+ ?/ ?\d+(?![\d/]|[.,]\d)")


def _sans_espaces(texte: str) -> str:
    return normaliser(texte).replace(" ", "")


def fraction_a_simplifier(enonce: str) -> str | None:
    """« Simplifier la fraction 6/12 donne : » → « 6/12 » ; None si l'énoncé ne demande pas de simplifier
    une seule fraction citée."""
    if "simplifi" not in normaliser(enonce):
        return None
    fractions = FRACTION_DANS_TEXTE.findall(enonce)
    return _sans_espaces(fractions[0]) if len(fractions) == 1 else None


def propositions_equivalentes(n: int, q: dict) -> list[Constat]:
    """Doublons exacts, et valeurs égales écrites différemment (3/4 et 6/8, 1 m et 100 cm).

    - doublon exact (« Paris » deux fois) : toujours bloquant ;
    - valeurs égales **dont la bonne réponse** (« 3/4 » annoncée, « 6/8 » proposée) : bloquant, car il y a
      deux bonnes réponses ;
    - valeurs égales **entre mauvaises réponses** seulement (« 2/4 » et « 1/2 » quand la réponse est 3/4) :
      avertissement. Le QCM est juste, mais un élève peut éliminer les deux d'un coup (cas réel du 03/10).
      Si c'est en fait la réponse annoncée qui est fausse, N4 le verra en recalculant.

    Exceptions, où des valeurs égales sont les distracteurs naturels de la question et non une ambiguïté :
    - l'énoncé demande la forme irréductible (ou « la plus simple ») : « 2/4 » et « 1/2 » ont la même valeur,
      une seule est irréductible ;
    - l'énoncé demande de simplifier une fraction : la recopier telle quelle (« 6/12 » pour « Simplifier 6/12 »)
      n'est pas la simplifier (cas réel du 05/10). Une autre simplification (« 2/4 ») reste, elle, juste.
    """
    irreductible = irreductible_demandee(q["enonce"])
    depart = fraction_a_simplifier(q["enonce"])
    groupes = defaultdict(list)
    for i, p in enumerate(q["propositions"]):
        if p.strip():  # les propositions vides relèvent de propositions_vides
            groupes[cle_de_comparaison(p)].append(i)
    constats = []
    for indices in groupes.values():
        if len(indices) < 2:
            continue
        membres = [q["propositions"][i] for i in indices]
        if len({normaliser(m) for m in membres}) == 1:
            constats.append(Constat(f"question {n} : la proposition « {membres[0]} » apparaît "
                                    f"{len(membres)} fois", True, n))
            continue
        if depart is not None:
            recopies = [i for i in indices if _sans_espaces(q["propositions"][i]) == depart]
            if len(recopies) > 1:  # « 6/12 » et « 6 / 12 » : un doublon que l'espace a masqué
                constats.append(Constat(f"question {n} : la proposition « {q['propositions'][recopies[0]]} » "
                                        f"apparaît {len(recopies)} fois", True, n))
            indices = [i for i in indices if i not in recopies]
            membres = [q["propositions"][i] for i in indices]
            if len(indices) < 2:
                continue
        if irreductible and sum(forme_irreductible(m) for m in membres) <= 1:
            continue
        elif q["index_correct"] in indices:
            constats.append(Constat(f"question {n} : les propositions {_liste(membres)} ont la même valeur ; "
                                    "une seule proposition peut être juste, les autres doivent être fausses", True, n))
        else:
            constats.append(Constat(f"question {n} : les mauvaises réponses {_liste(membres)} ont la même valeur ; "
                                    "un élève peut les éliminer ensemble sans connaître la notion", False, n))
    return constats


FORMULES_INTERDITES = re.compile(
    r"\b(toutes? (les|ces) (réponses|propositions)|aucune (des|de ces) (réponses|propositions)"
    r"|aucune réponse n'est|toutes les réponses sont)\b", re.IGNORECASE)


def formules_interdites(n: int, q: dict) -> list[Constat]:
    for p in q["propositions"]:
        if FORMULES_INTERDITES.search(p):
            return [Constat(f"question {n} : la proposition « {p} » renvoie aux autres propositions ; "
                            "chaque proposition doit se suffire à elle-même", True, n)]
    return []


def explication_recopiee(n: int, q: dict) -> list[Constat]:
    explication, enonce = q["explication"], q["enonce"]
    bonne = q["propositions"][q["index_correct"]]
    if similarite(explication, enonce) >= 0.85 or normaliser(explication) in normaliser(enonce):
        return [Constat(f"question {n} : l'explication recopie l'énoncé au lieu de justifier la réponse", True, n)]
    if normaliser(explication) == normaliser(bonne):
        return [Constat(f"question {n} : l'explication se contente de répéter la bonne réponse", True, n)]
    return []


def bonne_reponse_trop_longue(n: int, q: dict) -> list[Constat]:
    bonne = q["propositions"][q["index_correct"]]
    autres = [p for i, p in enumerate(q["propositions"]) if i != q["index_correct"]]
    plus_longue = max(len(p) for p in autres)
    if len(bonne) >= 2 * plus_longue and len(bonne) - plus_longue >= 20:
        return [Constat(f"question {n} : la bonne réponse est nettement plus longue que les autres "
                        "propositions, ce qui la trahit", False, n)]
    return []


def bonne_reponse_contenue(n: int, q: dict) -> list[Constat]:
    """« 3 parts sur 4 parts » et « 3 parts sur 4 parts coloriées » : si la bonne réponse est contenue dans
    une autre proposition (ou l'inverse), les deux sont souvent justes (cas réels du 03/10). Pas toujours :
    « Paris » et « Paris est en Italie » ne le sont pas. D'où un avertissement, pas un rejet."""
    bonne = normaliser(q["propositions"][q["index_correct"]])
    if not bonne:
        return []
    for i, p in enumerate(q["propositions"]):
        autre = normaliser(p)
        if i == q["index_correct"] or not autre or autre == bonne:
            continue
        if valeur(bonne) is not None and valeur(autre) is not None:
            continue  # « 25 % » et « 0,25 % » : deux nombres, égaux ou non, relèvent de propositions_equivalentes
        courte, longue = sorted((bonne, autre), key=len)
        if re.search(rf"(?<!\w){re.escape(courte)}(?!\w)", longue):
            return [Constat(f"question {n} : la bonne réponse « {q['propositions'][q['index_correct']]} » et la "
                            f"proposition « {p} » se recoupent ; vérifier qu'une seule des deux est juste", False, n)]
    return []


MOTS_FLOUS = re.compile(r"\b(généralement|en général|souvent|parfois|peut-être|la plupart|habituellement)\b",
                        re.IGNORECASE)


def enonce_flou(n: int, q: dict) -> list[Constat]:
    m = MOTS_FLOUS.search(q["enonce"])
    if m:
        return [Constat(f"question {n} : « {m.group(0)} » dans l'énoncé peut rendre plusieurs réponses "
                        "défendables", False, n)]
    return []


# « la figure ci-jointe », « le schéma suivant » : l'exercice n'est que du texte, la figure n'existe pas.
# Seulement un support visuel suivi d'un renvoi : « les fractions ci-dessous » désigne les propositions, et
# « une figure divisée en 8 parts, dont 3 coloriées » décrit la figure au lieu d'y renvoyer.
SUPPORT_VISUEL = r"(?:figure|schéma|dessin|image|illustration|graphique|croquis|droite graduée)s?"
FIGURE_ABSENTE = re.compile(
    rf"\b{SUPPORT_VISUEL} (?:suivante?s?|ci-(?:jointe?s?|dessous|dessus|contre))\b"
    rf"|\b(?:regarde|observe)z? (?:la|le|les|cette|ce|ces) {SUPPORT_VISUEL}\b", re.IGNORECASE)


def figure_absente(n: int, q: dict) -> list[Constat]:
    m = FIGURE_ABSENTE.search(q["enonce"])
    if m:
        return [Constat(f"question {n} : l'énoncé renvoie à « {m.group(0)} », mais l'exercice ne contient "
                        "aucune image ; décrire la situation en mots", True, n)]
    return []


REGLES_PAR_QUESTION = (propositions_vides, propositions_equivalentes, formules_interdites,
                       explication_recopiee, bonne_reponse_trop_longue, bonne_reponse_contenue, enonce_flou,
                       figure_absente)


def enonces_dupliques(questions: list[dict]) -> list[Constat]:
    constats = []
    vus: dict[str, int] = {}
    for n, q in enumerate(questions, start=1):
        cle = normaliser(q["enonce"])
        if cle in vus:
            constats.append(Constat(f"question {n} : même énoncé que la question {vus[cle]}", True, n))
        else:
            vus[cle] = n
    return constats


def position_constante(questions: list[dict]) -> list[Constat]:
    positions = {q["index_correct"] for q in questions}
    if len(questions) >= 3 and len(positions) == 1:
        return [Constat(f"la bonne réponse est toujours en position {positions.pop() + 1} ; le gabarit mélange "
                        "les propositions à l'affichage, mais c'est le signe d'un exercice peu travaillé", False)]
    return []


def toujours_la_plus_longue(questions: list[dict]) -> list[Constat]:
    def la_plus_longue(q: dict) -> bool:
        bonne = len(q["propositions"][q["index_correct"]])
        return all(bonne > len(p) for i, p in enumerate(q["propositions"]) if i != q["index_correct"])

    if len(questions) >= 3 and all(la_plus_longue(q) for q in questions):
        return [Constat("la bonne réponse est toujours la proposition la plus longue : "
                        "un élève peut la deviner sans connaître la notion", False)]
    return []


COURRIEL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
TELEPHONE = re.compile(r"(?:\+33\s?|\b0)[1-9](?:[\s.-]?\d{2}){4}\b")
ADRESSE_WEB = re.compile(r"https?://|\bwww\.", re.IGNORECASE)


def donnees_personnelles(instance: dict) -> list[Constat]:
    """Adresses électroniques, numéros de téléphone et liens : interdits, même inventés."""
    textes = [(None, instance.get("titre", "")), (None, instance.get("consigne") or "")]
    for n, q in enumerate(instance["questions"], start=1):
        textes += [(n, q["enonce"]), (n, q["explication"])] + [(n, p) for p in q["propositions"]]
    constats = []
    for n, texte in textes:
        for motif, nature in ((COURRIEL, "une adresse électronique"), (TELEPHONE, "un numéro de téléphone"),
                              (ADRESSE_WEB, "un lien web")):
            if motif.search(texte):
                ou = f"question {n}" if n else "exercice"
                constats.append(Constat(f"{ou} : contient {nature}, interdit dans un exercice", True, n))
    return constats


# --- point d'entrée ------------------------------------------------------------------------------

def verifier(instance: dict) -> list[Constat]:
    """Tous les constats, bloquants ou non : ceux de l'exercice entier d'abord, puis question par question."""
    questions = instance["questions"]
    constats = [c for n, q in enumerate(questions, start=1) for regle in REGLES_PAR_QUESTION for c in regle(n, q)]
    constats += enonces_dupliques(questions)
    constats += donnees_personnelles(instance)
    constats += position_constante(questions) + toujours_la_plus_longue(questions)
    return sorted(constats, key=lambda c: c.question or 0)


def valider(instance: dict) -> list[str]:
    """Lève ErreurValidation si un défaut bloquant est trouvé ; sinon renvoie les avertissements."""
    constats = verifier(instance)
    bloquants = [c for c in constats if c.bloquant]
    if bloquants:
        questions = tuple(sorted({c.question for c in bloquants if c.question}))
        raise ErreurValidation("N3", [c.message for c in bloquants], questions)
    return [c.message for c in constats]
