"""N4 du français : les formes verbales inventées et l'ordre alphabétique (16/11/2026 ;
docs/Generateur-Procedural/controle-du-modele.md).

Hors des maths, N4 ne recalculait rien : tout était « à relire ». Pour le français, deux contrôles sûrs :

- **une forme verbale inventée** (« je parleons », « nous sommesons », « ils ontent ») : après un pronom sujet, un mot
  absent de toute la liste de Lexique 3.83 (`lexique/mots.txt`), et qui ne s'explique pas comme une forme régulière
  d'un verbe en -er ou en -ir de Lexique (« ils étayent » y manque, mais vient d'« étayer ») → « faux » : la question
  revient au modèle. Mesuré sur 182 exercices réels : 17 questions avec une forme inventée, aucune fausse alerte.
  Garde-fous : une espace après le pronom (« tutoiement » n'est pas « tu » + « toiement ») ; un mot suivi d'un tiret
  ou d'un « + » est une coupe voulue (« nous finiss-ions ») ; un mot à majuscule, un nom propre ou un sigle. Limite :
  un vrai mot employé comme une forme (« il chant ») n'est pas vu ;
- **l'ordre alphabétique**, recalculé quand l'énoncé, ou le titre de l'exercice, en parle : le premier ou le dernier
  mot, celui qui vient juste après ou juste avant un mot, ranger des mots → « vérifié » ou « faux ».

Le reste : « à relire », comme avant. Les principes de N4 (n4_calcul.py) valent ici : jamais « vérifié » par défaut ;
un faux « faux » est aussi grave qu'un faux « vérifié » (le modèle « corrigerait » une bonne réponse) : les
reconnaisseurs sont ancrés sur des formulations précises, et renoncent au moindre doute.
"""

import re
import unicodedata
from functools import cache
from pathlib import Path

from generateur.moteur.validation.n4_calcul import A_RELIRE, FAUX, Verdict, trancher

LEXIQUE = Path(__file__).parent / "lexique" / "mots.txt"


@cache
def mots() -> frozenset[str]:
    """Les mots de Lexique 3.83 (toutes les formes), chargés une fois."""
    return frozenset(m for m in LEXIQUE.read_text(encoding="utf-8").split("\n") if m)


def connu(mot: str) -> bool:
    m = mot.lower()
    return m in mots() or m.replace("œ", "oe").replace("æ", "ae") in mots()


# Lexique ne donne pas toutes les formes des verbes rares (« ils étayent » y manque) : un mot qui s'explique comme le
# radical d'un verbe en -er ou en -ir de Lexique, suivi d'une terminaison régulière de son groupe, est une vraie forme.
# Une forme inventée ne s'explique pas ainsi (« parle » + « ons » ferait un verbe « parleer »).
TERMINAISONS = {
    "er": ("e", "es", "ent", "ons", "ez", "ais", "ait", "ions", "iez", "aient", "ai", "as", "a", "âmes", "âtes", "èrent",
           "erai", "eras", "era", "erons", "erez", "eront", "erais", "erait", "erions", "eriez", "eraient", "asse", "asses",
           "ât", "assions", "assiez", "assent", "é", "ée", "és", "ées", "ant"),
    "ir": ("is", "it", "issons", "issez", "issent", "issais", "issait", "issions", "issiez", "issaient", "îmes", "îtes",
           "irent", "irai", "iras", "ira", "irons", "irez", "iront", "irais", "irait", "irions", "iriez", "iraient", "isse",
           "isses", "ît", "i", "ie", "ies", "issant"),
}


def forme_reguliere(mot: str) -> bool:
    m = mot.lower()
    return any(m.endswith(fin) and len(m) > len(fin) + 1 and connu(m[:-len(fin)] + groupe)
               for groupe, fins in TERMINAISONS.items() for fin in fins)


# --- les formes verbales inventées ------------------------------------------------------------------------

LETTRES = "a-zàâäçéèêëîïôöûùüÿœæ"
# un pronom sujet, une espace (ou l'apostrophe de j'), puis un mot en minuscules qui n'est pas coupé (« finiss-ions »)
APRES_PRONOM = re.compile(rf"(?<![{LETTRES}'’-])(?:(?:je|tu|il|elle|on|nous|vous|ils|elles)\s+|j['’]\s*)"
                          rf"([{LETTRES}]+)(?![{LETTRES}A-Z]|\s*[-+])", re.IGNORECASE)


def formes_inventees(texte: str) -> list[str]:
    """Les mots qui, après un pronom sujet, ne sont pas du français (« je parleons » → ["parleons"])."""
    return [m.group(1) for m in APRES_PRONOM.finditer(texte) if m.group(1).islower() and len(m.group(1)) >= 3
            and not connu(m.group(1)) and not forme_reguliere(m.group(1))]


def inventee(n: int, q: dict) -> Verdict | None:
    """La première forme inventée de la question (l'énoncé, les propositions, l'explication), ou None."""
    endroits = [("l'énoncé", q.get("enonce") or "")]
    endroits += [(f"la proposition « {p} »", p) for p in q.get("propositions") or []]
    endroits.append(("l'explication", q.get("explication") or ""))
    for ou, texte in endroits:
        if trouvees := formes_inventees(texte):
            return Verdict(FAUX, f"question {n} : « {trouvees[0]} », dans {ou}, n'est pas une forme française ; "
                                 "n'écris que de vraies formes du verbe")
    return None


# --- l'ordre alphabétique ---------------------------------------------------------------------------------

ALPHABETIQUE = re.compile(r"alphab[ée]tique", re.IGNORECASE)
# ce que N4 ne sait pas trancher : l'ordre inverse, la 2e place, une lettre, les mots d'une phrase
PRUDENCE = re.compile(r"invers|à l'envers|deuxième|troisième|second|avant-dernier|lettre|phrase|syllabe", re.IGNORECASE)
PREMIER_DERNIER = re.compile(r"\b(premier|première|dernier|dernière)\b", re.IGNORECASE)
JUSTE = re.compile(rf"juste (après|avant)\s*:?\s*[«\"'“]?\s*([{LETTRES}]+)", re.IGNORECASE)
RANGER = re.compile(r"\brange[rz]?\b|\bclasse[rz]?\b|\bdans l'ordre\b", re.IGNORECASE)
UN_MOT = re.compile(rf"^[{LETTRES}]+$", re.IGNORECASE)


def cle(mot: str) -> str:
    """« école » se range comme « ecole », « sœur » comme « soeur » (le tri du dictionnaire)."""
    mot = mot.lower().replace("œ", "oe").replace("æ", "ae")
    return "".join(c for c in unicodedata.normalize("NFD", mot) if not unicodedata.combining(c))


def nettoyer(texte: str) -> str:
    return texte.strip().strip("«»\"'“”.?!").strip()


def mots_de_l_enonce(enonce: str) -> list[str] | None:
    """Les mots cités après les deux-points (« … : roi, nuage, maison ? »), ou None s'il n'y en a pas au moins trois."""
    if ":" not in enonce:
        return None
    liste = [nettoyer(m) for m in re.split(r",|\bet\b", enonce.rsplit(":", 1)[1])]
    liste = [m for m in liste if m]
    return liste if len(liste) >= 3 and all(UN_MOT.match(m) for m in liste) else None


def premier_ou_dernier(n: int, q: dict, enonce: str) -> Verdict | None:
    if not (m := PREMIER_DERNIER.search(enonce)):
        return None
    propositions = [nettoyer(p) for p in q["propositions"]]
    candidats = mots_de_l_enonce(enonce) or propositions
    if not all(UN_MOT.match(c) for c in candidats) or len({cle(c) for c in candidats}) < len(candidats):
        return None  # un groupe de mots, ou deux mots qui se rangent pareil : à relire
    premier = m.group(1).lower().startswith("premi")
    attendu = (min if premier else max)(candidats, key=cle)
    justes = [i for i, p in enumerate(propositions) if cle(p) == cle(attendu)]
    return trancher(n, q, justes, [], f"dans l'ordre alphabétique, le {'premier' if premier else 'dernier'} mot est "
                                     f"« {attendu} »")


def juste_apres_ou_avant(n: int, q: dict, enonce: str) -> Verdict | None:
    if not (m := JUSTE.search(enonce)):
        return None
    sens, repere = m.group(1).lower(), m.group(2)
    propositions = [nettoyer(p) for p in q["propositions"]]
    if not all(UN_MOT.match(p) for p in propositions) or len({cle(p) for p in propositions}) < len(propositions):
        return None
    if sens == "après":
        restent = [p for p in propositions if cle(p) > cle(repere)]
        attendu = min(restent, key=cle) if restent else None
    else:
        restent = [p for p in propositions if cle(p) < cle(repere)]
        attendu = max(restent, key=cle) if restent else None
    if attendu is None:
        return None
    justes = [i for i, p in enumerate(propositions) if p == attendu]
    return trancher(n, q, justes, [], f"parmi les propositions, le mot qui vient juste {sens} « {repere} » dans l'ordre "
                                     f"alphabétique est « {attendu} »")


def ranger(n: int, q: dict, enonce: str) -> Verdict | None:
    if not RANGER.search(enonce):
        return None
    listes = [[nettoyer(m) for m in p.split(",")] for p in q["propositions"]]
    if any(len(l) < 2 or not all(UN_MOT.match(m) for m in l) for l in listes):
        return None
    reference = mots_de_l_enonce(enonce) or listes[0]
    if any(sorted(map(cle, l)) != sorted(map(cle, reference)) for l in listes) or len(set(map(cle, reference))) < len(reference):
        return None  # pas les mêmes mots partout, ou deux mots qui se rangent pareil : à relire
    attendu = sorted(reference, key=cle)
    justes = [i for i, l in enumerate(listes) if [cle(m) for m in l] == [cle(m) for m in attendu]]
    return trancher(n, q, justes, [], f"dans l'ordre alphabétique : « {', '.join(attendu)} »")


def ordre_alphabetique(n: int, q: dict, contexte: str) -> Verdict | None:
    """L'ordre alphabétique, si l'énoncé ou le titre de l'exercice en parle ; None sinon (ou au moindre doute)."""
    enonce = q.get("enonce") or ""
    if not (ALPHABETIQUE.search(enonce) or ALPHABETIQUE.search(contexte)) or PRUDENCE.search(enonce):
        return None
    for reconnaisseur in (juste_apres_ou_avant, ranger, premier_ou_dernier):
        if (verdict := reconnaisseur(n, q, enonce)) is not None:
            return verdict
    return None


# --- point d'entrée ---------------------------------------------------------------------------------------

def verifier_question(n: int, q: dict, contexte: str = "") -> Verdict:
    """« faux » pour une forme inventée ; l'ordre alphabétique recalculé ; sinon « à relire »."""
    return inventee(n, q) or ordre_alphabetique(n, q, contexte) or Verdict(A_RELIRE)


def verifier(instance: dict) -> list[Verdict]:
    contexte = " ".join(str(instance.get(c) or "") for c in ("titre", "notion"))
    return [verifier_question(n, q, contexte) for n, q in enumerate(instance["questions"], start=1)]
