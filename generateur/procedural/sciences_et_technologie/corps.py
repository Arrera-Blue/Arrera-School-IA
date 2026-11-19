"""Le corps humain, du CP au CE2 (lot 2, étape 2.3 : docs/Generateur-Procedural/lot-2-questionner-le-monde.md §7). Le
programme de sciences et technologie de 2026 : au CP, les catégories d'aliments et leur origine, les articulations et
quelques os ; au CE1, les dents ; au CE2, les muscles du bras et le cœur pendant l'effort. Pas de QCM sur l'hygiène ni
sur la santé (décision 5 du 16/11) : le programme demande de les aborder sans juger, et les recommandations varient.

Tout se lit dans six tables relues par l'enseignant (donnees/sciences-et-technologie/), en monde fermé : une mauvaise
réponse est fausse pour la propriété demandée (pour « plier le bras », jamais une articulation du bras ; pour « la
partie visible de la dent », jamais l'émail, qui se voit aussi). Un fait discuté n'est jamais demandé : un aliment à
deux catégories (la pomme de terre, le beurre), le classement « rotation ou flexion » des articulations (l'épaule
plie aussi), la respiration pendant l'effort (aucune source lue ne dit dans quel sens elle change).
"""

import random

from generateur.procedural import Precision, Squelette, distracteurs, tables
from generateur.procedural.sciences_et_technologie import CYCLE_2
from generateur.procedural.sciences_et_technologie.vivant import de, majuscule

NOM, TITRE, NOTION, NIVEAU = "corps", "Le corps humain", "le corps humain", "CP"
MATIERE, NIVEAUX = "sciences-et-technologie", CYCLE_2  # NIVEAU : la classe par défaut ; NIVEAUX : celles où il s'applique
MOTS_CLES = ("corps humain", "aliments", "alimentation", "produits laitiers", "feculent", "squelette", "articulation",
             "les os", "des os", "dents", "dentition", "la dent", "muscle", "biceps", "triceps", "pouls", "effort",
             "activite physique", "rythme cardiaque")
TABLES = ("aliments", "articulations", "os", "dents", "muscles", "effort")
# les notions précises, de la plus précise à la plus générale (« l'origine des aliments » avant « les aliments »)
PRECISIONS = (
    Precision(r"origines? (?:des aliments|animale|vegetale|minerale)|produits? transformes?|d'ou viennent les aliments",
              "l'origine des aliments", ("origine",)),
    Precision(r"categories? d'aliments|aliments?\b|alimentation|produits? laitiers?|feculents?|matieres? grasses?",
              "les aliments", ("aliments", "origine")),
    Precision(r"\bdents?\b|dentition", "les dents", ("dents",)),
    Precision(r"efforts?|activite physique|pouls|rythme cardiaque|\bcoeur\b", "l'effort", ("effort",)),
    Precision(r"muscles?|biceps|triceps", "les muscles", ("muscles",)),
    Precision(r"squelette|articulations?|\bos\b", "le squelette", ("squelette", "muscles")),
)
ORIGINES = {"animale": "vient d'un animal", "végétale": "vient d'une plante",
            "minérale": "ne vient ni d'un animal ni d'une plante"}


def _table(nom: str) -> tables.Table:
    return tables.charger(MATIERE, nom)


def _liste(mots: list[str]) -> str:
    """« a, b et c »."""
    return mots[0] if len(mots) == 1 else f"{', '.join(mots[:-1])} et {mots[-1]}"


def _question_ecrite(nom_genre: str, l: dict) -> Squelette:
    """Une ligne d'une table de questions écrites (effort) : sa question, sa réponse, ses mauvaises réponses."""
    faux = [f.strip() for f in l["faux"].split(";")]
    return Squelette(genre=f"{NOM}.{nom_genre}", enonce=l["question"], reponse=l["reponse"],
                     distracteurs=distracteurs(l["reponse"], faux, nombre=len(faux)), explication=l["explication"],
                     cle=(nom_genre, l["question"]), sujet=(nom_genre, l["sujet"]))


# --- CP : les aliments, leur origine ---------------------------------------------------------------------------

def aliments(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Dans quelle catégorie d'aliments range-t-on le yaourt ? » → les produits laitiers ; « Lequel de ces aliments
    fait partie des matières grasses ? » (les 6 catégories du programme)."""
    lignes = [l for l in _table("aliments").lignes if l["categorie"] != "-"]
    categories = list(dict.fromkeys(l["categorie"] for l in lignes))
    if rng.random() < 0.6:
        l = rng.choice(lignes)
        autres = [c for c in categories if c != l["categorie"]]
        rng.shuffle(autres)
        return Squelette(
            genre=f"{NOM}.aliments", enonce=f"Dans quelle catégorie d'aliments range-t-on {l['aliment']} ?",
            reponse=l["categorie"], distracteurs=tuple(autres[:3]),
            explication=f"{majuscule(l['aliment'])} fait partie {de(l['categorie'])}.",
            cle=("aliments", "categorie", l["aliment"]), sujet=("aliment", l["aliment"]))
    c = rng.choice(categories)
    bon = rng.choice([l for l in lignes if l["categorie"] == c])
    faux = rng.sample([l for l in lignes if l["categorie"] != c], 3)
    return Squelette(
        genre=f"{NOM}.aliments", enonce=f"Lequel de ces aliments fait partie {de(c)} ?", reponse=bon["aliment"],
        distracteurs=tuple(x["aliment"] for x in faux),
        explication=(f"{majuscule(bon['aliment'])} fait partie {de(c)}. "
                     + majuscule(" ; ".join(f"{x['aliment']} fait partie {de(x['categorie'])}" for x in faux)) + "."),
        cle=("aliments", "lequel", c))


def origine(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« La pomme est un aliment d'origine… » → végétale ; « Lequel de ces aliments est d'origine animale ? » ;
    « Lequel de ces aliments est un produit transformé ? » (les mauvaises réponses : des aliments qu'on récolte ou
    qu'on ramasse). Jamais l'origine d'un aliment fait de plusieurs produits (le pain : farine, eau, sel)."""
    lignes = _table("aliments").lignes
    avec = [l for l in lignes if l["origine"] != "-"]
    forme = rng.choice(("aliment", "aliment", "lequel", "transforme"))
    if forme == "aliment":
        l = rng.choice(avec)
        o = l["origine"]
        return Squelette(
            genre=f"{NOM}.origine", enonce=f"{majuscule(l['aliment'])} est un aliment d'origine…", reponse=o,
            distracteurs=tuple(x for x in ORIGINES if x != o),
            explication=f"{majuscule(l['aliment'])} est d'origine {o} : un aliment d'origine {o} {ORIGINES[o]}.",
            cle=("origine", "aliment", l["aliment"]), sujet=("aliment", l["aliment"]))
    if forme == "lequel":
        o = rng.choice(list(ORIGINES))
        bon = rng.choice([l for l in avec if l["origine"] == o])
        faux = rng.sample([l for l in avec if l["origine"] != o], 3)
        return Squelette(
            genre=f"{NOM}.origine", enonce=f"Lequel de ces aliments est d'origine {o} ?", reponse=bon["aliment"],
            distracteurs=tuple(x["aliment"] for x in faux),
            explication=(f"{majuscule(bon['aliment'])} est d'origine {o} : un aliment d'origine {o} {ORIGINES[o]}. "
                         + majuscule(" ; ".join(f"{x['aliment']} est d'origine {x['origine']}" for x in faux)) + "."),
            cle=("origine", "lequel", o))
    bon = rng.choice([l for l in lignes if l["transforme"] == "oui"])
    faux = rng.sample([l for l in lignes if l["transforme"] == "non"], 3)
    return Squelette(
        genre=f"{NOM}.origine", enonce="Lequel de ces aliments est un produit transformé ?", reponse=bon["aliment"],
        distracteurs=tuple(x["aliment"] for x in faux),
        explication=(f"Un produit transformé est fabriqué à partir d'autres produits : c'est le cas {de(bon['aliment'])}. "
                     f"{majuscule(_liste([x['aliment'] for x in faux]))} ne sont pas des produits transformés."),
        cle=("origine", "transforme"))


# --- CP : le squelette ------------------------------------------------------------------------------------------

def _accorder(phrase: str, pluriel: bool) -> str:
    """« protège le cerveau » → « protègent le cerveau » quand le sujet est au pluriel (les côtes)."""
    verbe, _, reste = phrase.partition(" ")
    if pluriel:
        verbe = verbe + "nt" if verbe.endswith("e") else verbe.replace("tient", "tiennent")
    return f"{verbe} {reste}"


def squelette(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quelle articulation se trouve entre le bras et l'avant-bras ? » → le coude ; « Quelle articulation permet de
    tourner la tête ? » → le cou ; « Quel est l'os de la cuisse ? » → le fémur ; « Dans le squelette, qu'est-ce qui
    protège le cerveau ? » → le crâne."""
    arts, os_ = _table("articulations").lignes, _table("os").lignes
    forme = rng.choice(("entre", "entre", "geste", "lieu", "role"))
    if forme in ("entre", "geste"):
        if forme == "entre":
            l = rng.choice(arts)
            autres = [x["articulation"] for x in arts if x is not l]
            enonce = f"Quelle articulation se trouve entre {l['entre']} ?"
            explication = f"{majuscule(l['articulation'])} se trouve entre {l['entre']}."
        else:  # jamais une articulation de la même partie du corps (l'épaule bouge aussi le bras)
            l = rng.choice([x for x in arts if x["geste"] != "-"])
            autres = [x["articulation"] for x in arts if x["partie"] != l["partie"]]
            enonce = f"Quelle articulation permet de {l['geste']} ?"
            explication = f"On se sert {de(l['articulation'])} pour {l['geste']}."
        rng.shuffle(autres)
        return Squelette(genre=f"{NOM}.squelette", enonce=enonce, reponse=l["articulation"],
                         distracteurs=tuple(autres[:3]), explication=explication,
                         cle=("squelette", forme, l["articulation"]), sujet=("squelette", l["articulation"]))
    sorte = "lieu" if forme == "lieu" else "role"
    l = rng.choice([x for x in os_ if x[sorte] != "-"])
    autres = [x["os"] for x in os_ if x is not l]
    rng.shuffle(autres)
    if sorte == "lieu":
        enonce, explication = f"Quel est l'os {de(l['lieu'])} ?", f"{majuscule(l['os'])} est l'os {de(l['lieu'])}."
    else:
        enonce = f"Dans le squelette, qu'est-ce qui {l['role']} ?"
        explication = f"{majuscule(l['os'])} {_accorder(l['role'], l['os'].startswith('les '))}."
    return Squelette(genre=f"{NOM}.squelette", enonce=enonce, reponse=l["os"], distracteurs=tuple(autres[:3]),
                     explication=explication, cle=("squelette", sorte, l["os"]), sujet=("squelette", l["os"]))


# --- CE1 : les dents --------------------------------------------------------------------------------------------

def dents(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quelle partie de la dent est implantée dans l'os ? » → la racine (jamais la pulpe parmi les mauvaises
    réponses : elle descend dans la racine) ; « Combien de dents de lait l'humain possède-t-il ? » → 20 ; « Les dents
    définitives sont… » → plus grandes et plus solides que les dents de lait ; « Dans une dent, la racine… » → est
    implantée dans l'os. `jamais` vaut dans les deux sens : la racine et la pulpe ne sont jamais proposées ensemble."""
    lignes = _table("dents").lignes
    forme = rng.choice(("partie",) * 4 + ("decrire",) * 3 + ("nombre", "definitives"))
    if forme in ("partie", "decrire"):
        parties = [l for l in lignes if l["sorte"] == "partie"]
        l = rng.choice(parties)
        autres = [x for x in parties if x is not l and x["element"] != l["jamais"] and x["jamais"] != l["element"]]
        rng.shuffle(autres)
        explication = f"Dans une dent, {l['element']} {l['description']}."
        if forme == "decrire":
            return Squelette(genre=f"{NOM}.dents", enonce=f"Dans une dent, {l['element']}…", reponse=l["description"],
                             distracteurs=tuple(x["description"] for x in autres[:3]), explication=explication,
                             cle=("dents", "decrire", l["element"]), sujet=("dents", l["element"]))
        return Squelette(genre=f"{NOM}.dents", enonce=f"Quelle partie de la dent {l['description']} ?",
                         reponse=l["element"], distracteurs=tuple(x["element"] for x in autres[:3]),
                         explication=explication, cle=("dents", l["element"]), sujet=("dents", l["element"]))
    if forme == "nombre":
        n = int(next(l["element"] for l in lignes if l["sorte"] == "nombre_de_lait"))
        candidats = [str(x) for x in (n - 10, n + 12, n - 4, n + 8)]
        rng.shuffle(candidats)
        return Squelette(
            genre=f"{NOM}.dents", enonce=rng.choice(("Combien de dents de lait l'humain possède-t-il ?",
                                                     "Combien de dents de lait a-t-on en tout ?")),
            reponse=str(n), distracteurs=distracteurs(str(n), candidats),
            explication=f"L'humain possède {n} dents de lait ; elles tombent pour laisser la place aux dents définitives.",
            cle=("dents", "nombre"), sujet=("dents", "lait"))
    bon = next(l["element"] for l in lignes if l["sorte"] == "definitives")
    return Squelette(genre=f"{NOM}.dents", enonce="Les dents définitives sont…", reponse=bon,
                     distracteurs=tuple(l["element"] for l in lignes if l["sorte"] == "piege"),
                     explication="Les dents de lait sont plus petites ; les dents définitives sont plus grandes et plus "
                                 "solides.", cle=("dents", "definitives"), sujet=("dents", "lait"))


# --- CE2 : les muscles, l'effort ---------------------------------------------------------------------------------

def muscles(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel muscle permet de plier le bras ? » → le biceps ; « Que fait le triceps quand il se contracte ? » → il
    tend le bras ; « Quand on plie le bras, quelle articulation bouge ? » → le coude."""
    lignes = _table("muscles").lignes
    demandes = [l for l in lignes if l["demande"] == "oui"]
    forme = rng.choice(("quel", "que_fait", "articulation"))
    if forme == "articulation":
        arts = _table("articulations").lignes
        l = rng.choice([x for x in arts if x["geste"] != "-"])
        autres = [x["articulation"] for x in arts if x["partie"] != l["partie"]]
        rng.shuffle(autres)
        verbe, _, reste = l["geste"].partition(" ")
        return Squelette(genre=f"{NOM}.muscles", enonce=f"Quand on {verbe[:-1]} {reste}, quelle articulation bouge ?",
                         reponse=l["articulation"], distracteurs=tuple(autres[:3]),
                         explication=f"On se sert {de(l['articulation'])} pour {l['geste']}.",
                         cle=("muscles", "articulation", l["articulation"]))
    l = rng.choice(demandes)
    autres = [x for x in lignes if x is not l]
    explication = majuscule(" ; ".join(f"{x['muscle']} permet de {x['infinitif']}" for x in [l] + [
        x for x in demandes if x is not l])) + "."
    if forme == "quel":
        return Squelette(genre=f"{NOM}.muscles", enonce=f"Quel muscle permet de {l['infinitif']} ?", reponse=l["muscle"],
                         distracteurs=tuple(x["muscle"] for x in autres), explication=explication,
                         cle=("muscles", "quel", l["muscle"]), sujet=("muscles", l["muscle"]))
    return Squelette(genre=f"{NOM}.muscles", enonce=f"Que fait {l['muscle']} quand il se contracte ?",
                     reponse=f"il {l['present']}", distracteurs=tuple(f"il {x['present']}" for x in autres),
                     explication=explication, cle=("muscles", "que_fait", l["muscle"]), sujet=("muscles", l["muscle"]))


def effort(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Pendant une course, le cœur bat… » → plus vite qu'au repos ; « Que mesure-t-on en prenant le pouls ? » → les
    battements du cœur (une table de questions écrites, chacune sourcée)."""
    return _question_ecrite("effort", rng.choice(_table("effort").lignes))


GENRES = (aliments, origine, squelette, dents, muscles, effort)
CLASSES_DU_GENRE = {"aliments": ("CP",), "origine": ("CP",), "squelette": ("CP",), "dents": ("CE1",),
                    "muscles": ("CE2",), "effort": ("CE2",)}
S = "sciences-et-technologie"
ATTENDUS = {
    "aliments": {"CP": (f"{S}.cp.alimentation.01",)},
    "origine": {"CP": (f"{S}.cp.alimentation.01",)},
    "squelette": {"CP": (f"{S}.cp.croissance-mouvement.01",)},
    "dents": {"CE1": (f"{S}.ce1.croissance-mouvement.03",)},
    "muscles": {"CE2": (f"{S}.ce2.croissance-mouvement.01",)},
    "effort": {"CE2": (f"{S}.ce2.croissance-mouvement.03",)},
}
