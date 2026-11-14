"""La phrase, du CP au CE2 (lot 1, étape 1.3 : docs/Generateur-Procedural/lot-1-francais.md §5).

Ce que le programme demande (« Se repérer dans la phrase simple ») : les trois types de phrases à partir de la
ponctuation (CP .03, CE1 .02, CE2 .02) ; les formes négative et exclamative (CP .04, CE1 .03, CE2 .03) ; les classes de
mots : noms, verbes, déterminants, adjectifs, pronoms personnels au CP (.05), le nom propre en plus au CE1 (.04),
l'adverbe au CE2 (.04) ; la ponctuation de fin de phrase au CE2 (.05). Les phrases et la nature de chacun de leurs mots
se lisent dans la table `francais/phrases`, relue par l'enseignant ; on ne demande jamais la nature d'un mot hors du
programme de la classe (« ne », « où ») ni d'un mot qui revient deux fois dans la phrase.
"""

import random

from generateur.procedural import Precision, Retirer, Squelette, distracteurs, tables
from generateur.procedural.francais import CYCLE_2, avant_ou_egale, une

NOM, TITRE, NOTION, NIVEAU = "phrase", "La phrase", "phrase", "CE1"
MATIERE, NIVEAUX = "francais", CYCLE_2  # NIVEAU : la classe par défaut ; NIVEAUX : celles où il s'applique
MOTS_CLES = ("type de phrase", "types de phrases", "phrase declarative", "phrase interrogative", "phrase imperative",
             "phrases declaratives", "phrases interrogatives", "phrases imperatives", "exclamative", "forme negative",
             "formes negative", "phrase negative", "nature des mots", "nature d'un mot", "classe de mots",
             "classes de mots", "classe grammaticale", "classes grammaticales", "ponctuation", "point d'interrogation",
             "point d'exclamation")
TABLES = ("phrases",)
# les notions précises, de la plus précise à la plus générale (« le point d'exclamation » est la ponctuation, pas la
# phrase exclamative) ; la négation se reconnaît en cherchant la phrase négative, ou la seule qui ne l'est pas
PRECISIONS = (
    Precision(r"ponctuation|point d'interrogation|point d'exclamation|signes? de fin", "la ponctuation", ("ponctuation",)),
    Precision(r"formes? negatives?|phrases? negatives?|\bnegation", "la forme négative", ("forme",),
              (("forme", ("negative", "affirmative")),)),
    Precision(r"formes? affirmatives?|phrases? affirmatives?", "la forme affirmative", ("forme",),
              (("forme", ("affirmative", "negative")),)),
    Precision(r"exclamati", "la phrase exclamative", ("forme",), (("forme", ("exclamative",)),)),
    Precision(r"types? de phrases?|declarative|interrogative|imperative", "les types de phrases", ("type_de_phrase",)),
    Precision(r"\bnature|classes? (?:de|des) mots|classes? grammaticales?", "la nature des mots", ("nature",)),
    Precision(r"formes? de (?:la )?phrases?", "les formes de phrases", ("forme",)),
)

# les classes de mots du programme, classe par classe (le nom propre au CE1, l'adverbe au CE2)
LIBELLES = {
    "CP": {"determinant": "un déterminant", "nom": "un nom", "adjectif": "un adjectif", "verbe": "un verbe",
           "pronom": "un pronom"},
    "CE1": {"determinant": "un déterminant", "nom": "un nom commun", "nom_propre": "un nom propre",
            "adjectif": "un adjectif", "verbe": "un verbe", "pronom": "un pronom personnel"},
}
LIBELLES["CE2"] = {**LIBELLES["CE1"], "adverbe": "un adverbe"}
# pourquoi ; l'explication finit par le libellé de la classe (« un nom commun » au CE1, « un nom » au CP)
POURQUOI = {
    "determinant": "présente un nom",
    "nom": "désigne une personne, un animal ou une chose (on peut mettre « le » ou « un » devant)",
    "nom_propre": "commence par une majuscule et désigne un lieu précis",
    "adjectif": "dit comment est le nom qu'il accompagne",
    "verbe": "change avec le temps (hier, demain) et avec la personne",
    "pronom": "dit qui fait l'action (je, tu, il, elle, nous, vous, ils, elles)",
    "adverbe": "précise le verbe (comment, quand, où) et ne s'accorde jamais",
}
TYPES = {"declarative": "déclarative", "interrogative": "interrogative", "imperative": "impérative"}
POURQUOI_TYPE = {
    "declarative": "dit quelque chose et se termine par un point : elle est déclarative",
    "interrogative": "pose une question et se termine par un point d'interrogation : elle est interrogative",
    "imperative": "donne un ordre ; le verbe n'a pas de sujet écrit : elle est impérative",
}
SIGNES = {".": "le point (.)", "?": "le point d'interrogation (?)", "!": "le point d'exclamation (!)"}
# plusieurs formulations : deux questions d'un exercice n'ont jamais le même énoncé (N3 le refuserait)
FORMULES_FORME = {
    # neuf chacune : une notion seule (« la forme négative » : la négative et l'affirmative) doit pouvoir donner 15
    # questions différentes (critère de fin du lot 1 : six n'en donnaient que 12)
    "negative": ("Quelle phrase est à la forme négative ?", "Laquelle de ces phrases est négative ?",
                 "Trouve la phrase à la forme négative.", "Quelle phrase contient une négation ?",
                 "Une seule phrase est négative : laquelle ?", "Quelle phrase est écrite à la forme négative ?",
                 "Parmi ces phrases, laquelle est négative ?", "Choisis la phrase à la forme négative.",
                 "Repère la phrase négative."),
    "affirmative": ("Quelle phrase est à la forme affirmative ?", "Laquelle de ces phrases est affirmative ?",
                    "Trouve la phrase à la forme affirmative.", "Quelle phrase n'est pas négative ?",
                    "Une seule phrase est affirmative : laquelle ?", "Quelle phrase est écrite à la forme affirmative ?",
                    "Parmi ces phrases, laquelle est affirmative ?", "Choisis la phrase à la forme affirmative.",
                    "Repère la phrase affirmative."),
    "exclamative": ("Quelle phrase est exclamative ?", "Laquelle de ces phrases est exclamative ?",
                    "Trouve la phrase exclamative.", "Quelle phrase exprime une émotion ?",
                    "Une seule phrase est exclamative : laquelle ?", "Quelle phrase se dit avec une émotion ?",
                    "Parmi ces phrases, laquelle est exclamative ?", "Choisis la phrase exclamative.",
                    "Repère la phrase exclamative."),
}


def phrases(niveau: str, **criteres) -> list[dict]:
    return [p for p in tables.charger(MATIERE, "phrases").filtrer(**criteres) if avant_ou_egale(niveau, p["depuis"])]


def mots(phrase: dict) -> list[tuple[str, str]]:
    """[(mot, nature)…], sans le signe final."""
    return [tuple(j.split("/")) for j in phrase["mots"].split() if "/" in j]


def sans_signe(phrase: dict) -> str:
    return phrase["phrase"].rstrip(" .?!")


# --- les genres --------------------------------------------------------------------------------------------

def type_de_phrase(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel type de phrase : « Range ta chambre. » ? » → impérative ; les mauvaises réponses : les deux autres types.
    Pas de phrase exclamative (« Quel beau jardin ! » : une forme, pour le programme). Le type est tiré d'abord, puis une
    phrase de ce type : sinon la déclarative, la plus fréquente de la table, était la réponse 5 fois sur 5."""
    p = une(rng, phrases(niveau, exclamative="non", type=rng.choice(sorted(TYPES))))
    return Squelette(
        genre=f"{NOM}.type_de_phrase",
        enonce=f"Quel type de phrase : « {p['phrase']} » ?",
        reponse=TYPES[p["type"]],
        distracteurs=tuple(v for k, v in TYPES.items() if k != p["type"]),
        explication=f"« {p['phrase']} » {POURQUOI_TYPE[p['type']]}.",
        cle=("type_de_phrase", p["phrase"]),
    )


def forme(rng: random.Random, niveau: str = NIVEAU, criteres: dict | None = None) -> Squelette:
    """« Quelle phrase est à la forme négative ? » → Je ne mange pas. ; trois phrases affirmatives (ou l'inverse) ; ou
    « Quelle phrase est exclamative ? ». Au CP, pour la négation, seulement des phrases déclaratives sans exclamation :
    la négation seule les distingue (« Tu aimes les bonbons ? », affirmative, troublait). `criteres` : {"forme":
    (…)}, les formes cherchées (une notion précise : « la phrase négative »)."""
    cherche = une(rng, [c for c in FORMULES_FORME if c in (criteres or {}).get("forme", (c,))])
    oui = {"negative": {"negative": "oui"}, "affirmative": {"negative": "non"}, "exclamative": {"exclamative": "oui"}}
    non = {"negative": {"negative": "non"}, "affirmative": {"negative": "oui"}, "exclamative": {"exclamative": "non"}}
    simples = {"type": "declarative", "exclamative": "non"} if niveau == "CP" and cherche != "exclamative" else {}
    bonne = rng.choice(phrases(niveau, **oui[cherche], **simples))
    fausses = rng.sample(phrases(niveau, **non[cherche], **simples), 3)
    enonce = rng.choice(FORMULES_FORME[cherche])
    if cherche == "negative":
        negation = [m for m, n in mots(bonne) if n == "negation"]
        explication = (f"Dans « {bonne['phrase']} », les mots « {negation[0]} … {negation[-1]} » entourent le verbe : "
                       "la phrase est à la forme négative.")
    elif cherche == "affirmative":
        explication = (f"« {bonne['phrase']} » n'a pas de « ne … pas » : elle est à la forme affirmative ; les autres "
                       "phrases sont négatives.")
    else:
        explication = (f"« {bonne['phrase']} » exprime une émotion et se termine par un point d'exclamation : elle est "
                       "exclamative.")
    return Squelette(
        genre=f"{NOM}.forme",
        enonce=enonce,
        reponse=bonne["phrase"],
        distracteurs=tuple(p["phrase"] for p in fausses),
        explication=explication,
        cle=("forme", enonce),
    )


def nature(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Dans « Le petit chat dort. », le mot « petit » est : » → un adjectif ; les mauvaises réponses : d'autres classes
    de mots du programme de la classe. (« quelle est la nature de… » dépassait 12 mots avec une phrase de 6.) La classe
    de mots est tirée d'abord, puis un mot de cette classe : sinon le verbe, présent dans chaque phrase, revenait 7
    fois sur 10."""
    libelles = LIBELLES[niveau]
    sa_nature = rng.choice(sorted(libelles))
    candidats = [(p, m) for p in phrases(niveau) for m, n in mots(p) if n == sa_nature
                 and sum(x.lower() == m.lower() for x, _ in mots(p)) == 1]
    if not candidats:
        raise Retirer("aucun mot de cette classe dans les phrases de la classe")
    p, mot = rng.choice(candidats)
    autres = [v for k, v in libelles.items() if k != sa_nature]
    rng.shuffle(autres)
    return Squelette(
        genre=f"{NOM}.nature",
        enonce=f"Dans « {p['phrase']} », le mot « {mot} » est :",
        reponse=libelles[sa_nature],
        distracteurs=distracteurs(libelles[sa_nature], autres),
        explication=f"Dans cette phrase, « {mot} » {POURQUOI[sa_nature]} : c'est {libelles[sa_nature]}.",
        cle=("nature", p["phrase"], mot),
    )


def ponctuation(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel signe termine cette phrase : « Où est le chat … » ? » → le point d'interrogation ; seulement les phrases
    dont le signe est imposé par un mot (« Où », « Quel ») : « Il fait beau » irait avec un point ou un point
    d'exclamation."""
    p = rng.choice(phrases(niveau, signe_impose="oui"))
    signe = p["phrase"][-1]
    indice = next(m for m, n in mots(p) if n in ("interrogatif", "exclamatif", "determinant"))
    pourquoi = ("pose une question : la phrase se termine par un point d'interrogation" if signe == "?"
                else "marque une exclamation (une émotion) : la phrase se termine par un point d'exclamation")
    return Squelette(
        genre=f"{NOM}.ponctuation",
        enonce=f"Quel signe termine cette phrase : « {sans_signe(p)} … » ?",
        reponse=SIGNES[signe],
        distracteurs=tuple(v for k, v in SIGNES.items() if k != signe),
        explication=f"« {indice} » {pourquoi} (« {p['phrase']} »).",
        cle=("ponctuation", p["phrase"]),
    )


GENRES = (type_de_phrase, forme, nature, ponctuation)
CLASSES_DU_GENRE = {"type_de_phrase": CYCLE_2, "forme": CYCLE_2, "nature": CYCLE_2, "ponctuation": ("CE2",)}
ATTENDUS = {
    "type_de_phrase": {"CP": ("francais.cp.phrase-simple.03",), "CE1": ("francais.ce1.phrase-simple.02",),
                       "CE2": ("francais.ce2.phrase-simple.02",)},
    "forme": {"CP": ("francais.cp.phrase-simple.04",), "CE1": ("francais.ce1.phrase-simple.03",),
              "CE2": ("francais.ce2.phrase-simple.03",)},
    "nature": {"CP": ("francais.cp.phrase-simple.05",), "CE1": ("francais.ce1.phrase-simple.04",),
               "CE2": ("francais.ce2.phrase-simple.04",)},
    "ponctuation": {"CE2": ("francais.ce2.phrase-simple.05",)},
}
