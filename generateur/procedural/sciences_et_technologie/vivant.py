"""Le vivant, du CP au CE2 (lot 2, étape 2.2 : docs/Generateur-Procedural/lot-2-questionner-le-monde.md §6). Le
programme de sciences et technologie de 2026 : au CP, ce qui est vivant, non vivant ou élaboré par des êtres vivants ;
au CE1, le régime alimentaire des animaux, les organes des sens, la plante (ses organes, ses besoins) ; au CE2, la
classification, la vie d'une plante à fleurs, les larves et les jeunes, la locomotion, la chaîne alimentaire.

Tout se lit dans neuf tables relues par l'enseignant (donnees/sciences-et-technologie/), en monde fermé : une
mauvaise réponse est fausse pour la propriété demandée (un herbivore ne mange jamais le lapin ; une fleur n'est jamais
proposée quand on demande ce qui contient les graines). Les mauvaises réponses viennent d'abord des confusions des
élèves (le dauphin « poisson », la chauve-souris « oiseau », l'araignée « insecte »).
"""

import random

from generateur.procedural import Precision, Squelette, distracteurs, tables
from generateur.procedural.sciences_et_technologie import CYCLE_2

NOM, TITRE, NOTION, NIVEAU = "vivant", "Le vivant", "le vivant", "CE1"
MATIERE, NIVEAUX = "sciences-et-technologie", CYCLE_2  # NIVEAU : la classe par défaut ; NIVEAUX : celles où il s'applique
MOTS_CLES = ("vivant", "animaux", "animal", "plante", "vegetal", "regime alimentaire", "herbivore", "carnivore",
             "omnivore", "chaine alimentaire", "les sens", "cinq sens", "organes des sens", "larve", "metamorphose",
             "tetard", "chenille", "mue", "locomotion", "classification", "mammifere", "oiseau", "poisson", "insecte",
             "reptile", "germination", "graine", "racine", "fleur")
# « l'origine animale ou végétale des aliments » est du corps humain (corps.py), pas du vivant
EXCLUS = ("aliments", "alimentation", "corps humain")
TABLES = ("etres_vivants", "animaux", "regimes", "sens", "plante", "cycle_plante", "petits", "locomotion", "chaines")
# les notions précises, de la plus précise à la plus générale (« la vie d'une plante » avant « la plante »)
PRECISIONS = (
    Precision(r"chaines? alimentaires?|qui mange qui", "la chaîne alimentaire", ("chaine",)),
    Precision(r"regimes? alimentaires?|herbivores?|carnivores?|omnivores?", "le régime alimentaire", ("regime",)),
    Precision(r"larves?|metamorphose|tetard|chenille|\bmues?\b|petits? des animaux|jeunes? animaux",
              "les petits des animaux", ("petits",)),
    Precision(r"locomotion|deplacements?|se deplacer", "la locomotion", ("locomotion",)),
    Precision(r"cycle de vie|vie d'une plante|etapes de la vie|germination", "la vie d'une plante", ("cycle_plante",)),
    Precision(r"plantes?|vegeta|racines?|\btiges?\b|feuilles?", "la plante", ("plante", "cycle_plante")),
    Precision(r"organes? des sens|cinq sens|les sens\b|\bvue\b|ouie|odorat|\bgout\b|toucher", "les sens", ("sens",)),
    Precision(r"classification|groupes? d'animaux|mammiferes?|reptiles?|amphibiens?|insectes?",
              "la classification", ("classification",)),
    Precision(r"vivant ou non|non[ -]vivant|ce qui est vivant|elabore", "vivant ou non vivant", ("etre_vivant",)),
)


def _table(nom: str) -> tables.Table:
    return tables.charger(MATIERE, nom)


def majuscule(texte: str) -> str:
    return texte[:1].upper() + texte[1:]


def de(nom: str) -> str:
    """« le moineau » → « du moineau » ; « la truite » → « de la truite » ; « l'abeille » → « de l'abeille »."""
    return "du " + nom[3:] if nom.startswith("le ") else "des " + nom[4:] if nom.startswith("les ") else "de " + nom


def a(nom: str) -> str:
    """« le cheval » → « au cheval » ; « la truite » → « à la truite »."""
    return "au " + nom[3:] if nom.startswith("le ") else "aux " + nom[4:] if nom.startswith("les ") else "à " + nom


def un(nom: str) -> str:
    """« le cheval » → « un cheval » ; « la poule » → « une poule » (les noms des adultes de la table des petits)."""
    return "un " + nom[3:] if nom.startswith("le ") else "une " + nom[3:] if nom.startswith("la ") else nom


def il(nom: str) -> str:
    """Le pronom d'un nom de la table (les noms en « l' » des tables qui en ont besoin sont masculins)."""
    return "elle" if nom.startswith("la ") else "il"


def _citer(mots: list[str]) -> str:
    return ", ".join(f"« {m} »" for m in mots)


# --- CP : vivant, non vivant, élaboré ------------------------------------------------------------------------

def etre_vivant(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Lequel est vivant : chat, sable, laine, eau ? » ; « Lequel est fabriqué par un être vivant : … ? » ;
    « Lequel n'est pas vivant : … ? ». Les éléments dans l'énoncé : deux questions n'ont jamais le même."""
    lignes = _table("etres_vivants").lignes
    par = {c: [l for l in lignes if l["categorie"] == c] for c in ("vivant", "non_vivant", "elabore")}
    forme = rng.choice(("vivant", "fabrique", "pas_vivant"))
    if forme == "vivant":
        bon = rng.choice(par["vivant"])
        faux = rng.sample(par["non_vivant"], 2) + rng.sample(par["elabore"], 1)
        enonce_debut = "Lequel est vivant"
        e = "e" if bon["genre"] == "f" else ""
        explication = (f"« {bon['element']} » est vivant{e} : {'elle' if e else 'il'} naît, grandit, se nourrit et se "
                       f"reproduit. {_citer([f['element'] for f in faux])} ne sont pas vivants.")
    elif forme == "fabrique":
        un_mot = [l for l in lignes if " " not in l["element"]]  # l'énoncé reste court (12 mots)
        bon = rng.choice([l for l in un_mot if l["categorie"] == "elabore"])
        faux = (rng.sample([l for l in un_mot if l["categorie"] == "vivant"], 1)
                + rng.sample([l for l in un_mot if l["categorie"] == "non_vivant"], 2))
        enonce_debut = "Lequel est fabriqué par un être vivant"
        e = "e" if bon["genre"] == "f" else ""
        explication = (f"« {bon['element']} » est fabriqué{e} par un être vivant, mais n'est pas vivant{e}. "
                       f"« {faux[0]['element']} » est un être vivant ; {_citer([f['element'] for f in faux[1:]])} "
                       "ne sont pas vivants et ne viennent pas d'un être vivant.")
    else:
        bon = rng.choice(par["non_vivant"] + par["elabore"])
        faux = rng.sample(par["vivant"], 3)
        enonce_debut = "Lequel n'est pas vivant"
        e = "e" if bon["genre"] == "f" else ""
        explication = (f"« {bon['element']} » n'est pas vivant{e}. {_citer([f['element'] for f in faux])} sont des "
                       "êtres vivants : ils naissent, grandissent, se nourrissent et se reproduisent.")
    elements = [bon["element"]] + [f["element"] for f in faux]
    ordre = rng.sample(elements, len(elements))
    return Squelette(
        genre=f"{NOM}.etre_vivant", enonce=f"{enonce_debut} : {', '.join(ordre)} ?", reponse=bon["element"],
        distracteurs=tuple(f["element"] for f in faux), explication=explication,
        cle=("etre_vivant", forme, frozenset(elements)))


# --- CE1, CE2 : le régime alimentaire -------------------------------------------------------------------------

def regime(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Le lion est… » → carnivore ; « Lequel de ces animaux est herbivore ? » ; « Un animal omnivore mange… » ; « Un
    animal qui mange seulement des plantes est… ». Jamais un animal au régime discuté (l'araignée, l'escargot)."""
    animaux = [x for x in _table("animaux").lignes if x["regime"] != "-"]
    mange = {r["regime"]: r["mange"] for r in _table("regimes").lignes}
    regimes = list(mange)
    forme = rng.choice(("animal", "animal", "lequel", "definition", "nom"))
    if forme == "animal":
        x = rng.choice(animaux)
        return Squelette(
            genre=f"{NOM}.regime", enonce=f"{majuscule(x['nom'])} est…", reponse=x["regime"],
            distracteurs=tuple(r for r in regimes if r != x["regime"]),
            explication=f"{majuscule(x['nom'])} est {x['regime']} : un animal {x['regime']} mange {mange[x['regime']]}.",
            cle=("regime", "animal", x["nom"]))
    r = rng.choice(regimes)
    if forme == "lequel":
        bon = rng.choice([x for x in animaux if x["regime"] == r])
        faux = rng.sample([x for x in animaux if x["regime"] != r], 3)
        return Squelette(
            genre=f"{NOM}.regime", enonce=f"Lequel de ces animaux est {r} ?", reponse=bon["nom"],
            distracteurs=tuple(x["nom"] for x in faux),
            explication=(f"{majuscule(bon['nom'])} est {r} : un animal {r} mange {mange[r]}. "
                         + " ; ".join(f"{x['nom']} est {x['regime']}" for x in faux) + "."),
            cle=("regime", "lequel", r))
    if forme == "definition":
        return Squelette(
            genre=f"{NOM}.regime", enonce=f"Un animal {r} mange…", reponse=mange[r],
            distracteurs=tuple(mange[s] for s in regimes if s != r),
            explication=f"Un animal {r} mange {mange[r]}. " + " ; ".join(
                f"un animal {s} mange {mange[s]}" for s in regimes if s != r) + ".",
            cle=("regime", "definition", r))
    return Squelette(
        genre=f"{NOM}.regime", enonce=f"Un animal qui mange {mange[r]} est…", reponse=r,
        distracteurs=tuple(s for s in regimes if s != r),
        explication=f"Un animal qui mange {mange[r]} est {r}.", cle=("regime", "nom", r))


# --- CE1 : les sens, la plante --------------------------------------------------------------------------------

def sens(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel est l'organe de l'odorat ? » → le nez ; « Avec quel organe peut-on entendre ? » → l'oreille. Jamais « à
    quoi sert l'oreille ? » (aussi à l'équilibre)."""
    lignes = _table("sens").lignes
    l = rng.choice(lignes)
    formulations = [f"Quel est l'organe {de(l['sens'])} ?"]
    if l["permet"] != "-":
        formulations += [f"Avec quel organe peut-on {l['permet']} ?", f"Quel organe sert à {l['permet']} ?"]
    enonce = rng.choice(formulations)
    autres = [x["organe"] for x in lignes if x is not l]
    rng.shuffle(autres)
    explication = f"{majuscule(l['organe'])} est l'organe {de(l['sens'])}"
    explication += f" : on s'en sert pour {l['permet']}." if l["permet"] != "-" else "."
    return Squelette(genre=f"{NOM}.sens", enonce=enonce, reponse=l["organe"],
                     distracteurs=distracteurs(l["organe"], autres), explication=explication,
                     cle=("sens", enonce), sujet=("sens", l["sens"]))


def plante(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quelle partie de la plante puise l'eau dans le sol ? » → la racine ; « De quoi une plante verte a-t-elle besoin
    pour grandir ? » → d'eau et de lumière."""
    lignes = _table("plante").lignes
    if rng.random() < 0.2:
        bon = next(l["element"] for l in lignes if l["sorte"] == "besoin")
        enonce = rng.choice(("De quoi une plante verte a-t-elle besoin pour grandir ?",
                             "Pour grandir, une plante verte a besoin…"))
        return Squelette(
            genre=f"{NOM}.plante", enonce=enonce, reponse=bon,
            distracteurs=tuple(l["element"] for l in lignes if l["sorte"] == "piege"),
            explication=(f"Une plante verte a besoin {bon} pour grandir : on le voit en cultivant des plantes avec ou "
                         "sans eau, avec ou sans lumière."),
            cle=("plante", enonce), sujet=("plante", "besoin"))
    l = rng.choice([x for x in lignes if x["sorte"] == "partie" and x["role"] != "-"])
    pieges = [x["element"] for x in lignes if x["sorte"] == "partie" and x is not l
              and x["element"] in ("la racine", "la tige", "la feuille", "la fleur")]
    if l["element"] in ("le fruit", "la graine"):  # une fleur qui fane porte déjà ses graines
        pieges.remove("la fleur")
    rng.shuffle(pieges)
    enonce = rng.choice((f"Quelle partie de la plante {l['role']} ?", f"Dans une plante, qu'est-ce qui {l['role']} ?"))
    return Squelette(genre=f"{NOM}.plante", enonce=enonce, reponse=l["element"],
                     distracteurs=distracteurs(l["element"], pieges),
                     explication=f"{majuscule(l['element'])} {l['role']}.",
                     cle=("plante", enonce), sujet=("plante", l["element"]))


# --- CE2 : la classification, la vie d'une plante, les petits, la locomotion, la chaîne alimentaire -------------

def classification(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Dans quel groupe d'animaux range-t-on le dauphin ? » → un mammifère (d'abord la confusion : un poisson) ;
    « Lequel de ces animaux est un insecte ? » (d'abord l'araignée et l'escargot)."""
    animaux = _table("animaux").lignes
    groupes = list(dict.fromkeys(x["groupe"] for x in animaux))
    if rng.random() < 0.6:
        x = rng.choice(animaux)
        autres = [g for g in groupes if g not in (x["groupe"], x["confusion"])]
        rng.shuffle(autres)
        candidats = ([x["confusion"]] if x["confusion"] != "-" else []) + autres
        explication = f"{majuscule(x['nom'])} est un {x['groupe']}"
        explication += f", pas un {x['confusion']}." if x["confusion"] != "-" else "."
        return Squelette(
            genre=f"{NOM}.classification", enonce=f"Dans quel groupe d'animaux range-t-on {x['nom']} ?",
            reponse=f"un {x['groupe']}", distracteurs=distracteurs(f"un {x['groupe']}", [f"un {g}" for g in candidats]),
            explication=explication, cle=("classification", "groupe", x["nom"]))
    g = rng.choice(groupes)
    bon = rng.choice([x for x in animaux if x["groupe"] == g])
    pieges = [x for x in animaux if x["groupe"] != g and x["confusion"] == g]
    autres = [x for x in animaux if x["groupe"] != g and x["confusion"] != g]
    rng.shuffle(pieges)
    rng.shuffle(autres)
    faux = (pieges + autres)[:3]
    return Squelette(
        genre=f"{NOM}.classification", enonce=f"Lequel de ces animaux est un {g} ?", reponse=bon["nom"],
        distracteurs=tuple(x["nom"] for x in faux),
        explication=(f"{majuscule(bon['nom'])} est un {g}. "
                     + majuscule(" ; ".join(f"{x['nom']} est un {x['groupe']}" for x in faux)) + "."),
        cle=("classification", "lequel", g))


def cycle_plante(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """La vie d'une plante à fleurs, dans l'ordre du programme : l'étape juste après la croissance ; la première de
    quatre étapes."""
    etapes = [l["etape"] for l in sorted(_table("cycle_plante").lignes, key=lambda l: l["rang"])]
    ordre = f"La vie d'une plante à fleurs, dans l'ordre : {', '.join(etapes)}."
    forme = rng.choice(("apres", "avant", "premiere", "derniere"))
    if forme in ("apres", "avant"):
        i = rng.randrange(len(etapes) - 1) + (1 if forme == "avant" else 0)
        j = i + (1 if forme == "apres" else -1)
        mot = "après" if forme == "apres" else "avant"
        return Squelette(
            genre=f"{NOM}.cycle_plante", enonce=f"Quelle étape vient juste {mot} {etapes[i]} ?",
            reponse=etapes[j], distracteurs=tuple(e for k, e in enumerate(etapes) if k not in (i, j)),
            explication=f"{ordre} Juste {mot} {etapes[i]} vient {etapes[j]}.", cle=("cycle_plante", forme, i))
    choisies = sorted(rng.sample(range(len(etapes)), 4))
    bon = etapes[choisies[0] if forme == "premiere" else choisies[-1]]
    return Squelette(
        genre=f"{NOM}.cycle_plante",
        enonce=f"Quelle étape de la vie d'une plante vient en {'premier' if forme == 'premiere' else 'dernier'} ?",
        reponse=bon, distracteurs=tuple(etapes[k] for k in choisies if etapes[k] != bon),
        explication=f"{ordre} Parmi les étapes proposées, {bon} vient en {'premier' if forme == 'premiere' else 'dernier'}.",
        cle=("cycle_plante", forme, tuple(choisies)))


LARVE, JEUNE, ADULTE = "une larve", "un jeune qui ressemble déjà à l'adulte", "un adulte"


def petits(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Le têtard devient… » → la grenouille ; « Le têtard est… » → une larve ; « Lequel grandit en faisant des
    mues ? » → la chenille (les mauvaises réponses : des petits de mammifères)."""
    lignes = _table("petits").lignes
    forme = rng.choice(("devient", "devient", "forme", "forme", "mues", "sans_mues"))
    if forme in ("devient", "forme"):
        l = rng.choice(lignes)
        larve = l["forme"] == "larve"
        explication = (f"{majuscule(l['jeune'])} est la larve {de(l['adulte'])} : en grandissant, {il(l['jeune'])} change "
                       "beaucoup de forme (une métamorphose)." if larve
                       else f"{majuscule(l['jeune'])} est le petit {de(l['adulte'])} : {il(l['jeune'])} lui ressemble déjà.")
        if forme == "devient":
            autres = [un(x["adulte"]) for x in lignes if x is not l]
            rng.shuffle(autres)
            return Squelette(genre=f"{NOM}.petits", enonce=f"{majuscule(l['jeune'])} devient…", reponse=un(l["adulte"]),
                             distracteurs=distracteurs(un(l["adulte"]), autres), explication=explication,
                             cle=("petits", "devient", l["jeune"]))
        bon = LARVE if larve else JEUNE
        return Squelette(genre=f"{NOM}.petits", enonce=f"{majuscule(l['jeune'])} est…", reponse=bon,
                         distracteurs=tuple(x for x in (LARVE, JEUNE, ADULTE) if x != bon), explication=explication,
                         cle=("petits", "forme", l["jeune"]))
    avec = [l["jeune"] for l in lignes if l["mues"] == "oui"]
    sans = [l["jeune"] for l in lignes if l["mues"] == "non"]
    explication = (f"{majuscule(' et '.join(avec))} sont des larves d'insectes : elles grandissent en faisant des mues "
                   f"(elles changent de peau). {majuscule(', '.join(sans))} sont des petits de mammifères : ils "
                   "grandissent sans mue.")
    if forme == "mues":
        bon = rng.choice(avec)
        return Squelette(genre=f"{NOM}.petits", enonce="Lequel grandit en faisant des mues ?", reponse=bon,
                         distracteurs=tuple(rng.sample(sans, 3)), explication=explication, cle=("petits", "mues"))
    bon = rng.choice(sans)
    return Squelette(genre=f"{NOM}.petits", enonce="Lequel grandit sans faire de mues ?", reponse=bon,
                     distracteurs=tuple(avec), explication=explication, cle=("petits", "sans_mues"))


def locomotion(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« À quoi servent les ailes de l'abeille ? » → à voler ; « Quel organe permet à la truite de nager ? » → les
    nageoires."""
    lignes = _table("locomotion").lignes
    l = rng.choice(lignes)
    modes = list(dict.fromkeys(x["mode"] for x in lignes))
    organes = list(dict.fromkeys(x["organe"] for x in lignes))
    explication = f"{majuscule(l['animal'])} a des {l['organe']} : elles lui permettent de {l['mode']}."
    if rng.random() < 0.5:
        return Squelette(
            genre=f"{NOM}.locomotion", enonce=f"À quoi servent les {l['organe']} {de(l['animal'])} ?",
            reponse=f"à {l['mode']}", distracteurs=tuple(f"à {m}" for m in modes if m != l["mode"]),
            explication=explication, cle=("locomotion", "sert", l["animal"]))
    return Squelette(
        genre=f"{NOM}.locomotion", enonce=f"Quel organe permet {a(l['animal'])} de {l['mode']} ?",
        reponse=f"les {l['organe']}", distracteurs=tuple(f"les {o}" for o in organes if o != l["organe"]),
        explication=explication, cle=("locomotion", "organe", l["animal"]))


def chaine(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Les graines sont mangées par la mésange, qui est mangée par… » → l'épervier (les mauvaises réponses : des
    herbivores) ; « La mésange est mangée par l'épervier. Que mange la mésange ? » → les graines."""
    chaines = _table("chaines").lignes
    c = rng.choice(chaines)
    explication = (f"Dans cette chaîne alimentaire, {c['bas']} {c['bas_verbe']} par {c['milieu']}, et {c['milieu']} "
                   f"{c['milieu_verbe']} par {c['haut']}.")
    if rng.random() < 0.5:
        herbivores = [x["nom"] for x in _table("animaux").lignes if x["regime"] == "herbivore"]
        faux = rng.sample(herbivores, 3)
        return Squelette(
            genre=f"{NOM}.chaine",
            enonce=f"{majuscule(c['bas'])} {c['bas_verbe']} par {c['milieu']}, qui {c['milieu_verbe']} par…",
            reponse=c["haut"], distracteurs=tuple(faux),
            explication=explication + f" {majuscule(', '.join(faux))} sont herbivores : ils ne mangent pas d'animaux.",
            cle=("chaine", "haut", c["milieu"]))
    autres = [x["haut"] for x in chaines if x is not c]
    return Squelette(
        genre=f"{NOM}.chaine", enonce=f"{majuscule(c['milieu'])} {c['milieu_verbe']} par {c['haut']}. Que mange {c['milieu']} ?",
        reponse=c["bas"], distracteurs=tuple(autres), explication=explication, cle=("chaine", "bas", c["milieu"]))


GENRES = (etre_vivant, regime, sens, plante, classification, cycle_plante, petits, locomotion, chaine)
CLASSES_DU_GENRE = {"etre_vivant": ("CP",), "regime": ("CE1", "CE2"), "sens": ("CE1",), "plante": ("CE1",),
                    "classification": ("CE2",), "cycle_plante": ("CE2",), "petits": ("CE2",), "locomotion": ("CE2",),
                    "chaine": ("CE2",)}
S = "sciences-et-technologie"
ATTENDUS = {
    "etre_vivant": {"CP": (f"{S}.cp.diversite-vivant.01",)},
    "regime": {"CE1": (f"{S}.ce1.nutrition.03",), "CE2": (f"{S}.ce2.environnement-proche.02",)},
    "sens": {"CE1": (f"{S}.ce1.sens-perception.01",)},
    "plante": {"CE1": (f"{S}.ce1.nutrition.01", f"{S}.ce1.nutrition.02")},
    "classification": {"CE2": (f"{S}.ce2.diversite-vivant.01",)},
    "cycle_plante": {"CE2": (f"{S}.ce2.reproduction-croissance.01",)},
    "petits": {"CE2": (f"{S}.ce2.reproduction-croissance.03",)},
    "locomotion": {"CE2": (f"{S}.ce2.locomotion.01", f"{S}.ce2.locomotion.02")},
    "chaine": {"CE2": (f"{S}.ce2.environnement-proche.02",)},
}
