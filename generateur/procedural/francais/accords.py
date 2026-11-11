"""Les accords, du CP au CE2 (lot 1, étape 1.2 : docs/Generateur-Procedural/lot-1-francais.md §4).

Ce que le programme demande : masculin et féminin, singulier et pluriel, la « chaine d'accords » dans le groupe
nominal (CP .01 à .03, CE1 .01, CE2 .01), la relation sujet-verbe (CP .04, CE1 .02, CE2 .02) ; au CE2, les pluriels
irréguliers (-x, -al/-aux) et les féminins qui s'entendent (lecteur/lectrice, joyeux/joyeuse). Les mots se lisent dans
les tables `francais/noms`, `adjectifs`, `pluriels_irreguliers`, `feminins` (et les conjugaisons pour le verbe) ; les
mauvaises réponses sont d'autres formes du même mot, prises dans les tables, ou l'erreur typique écrite et relue
(« chevals », décision 4) ; jamais une forme fabriquée par le programme.
"""

import random

from generateur.procedural import Retirer, Squelette, distracteurs, tables
from generateur.procedural.francais import CYCLE_2, avant_ou_egale

NOM, TITRE, NOTION, NIVEAU = "accords", "Les accords", "accords", "CE1"
MATIERE, NIVEAUX = "francais", CYCLE_2  # NIVEAU : la classe par défaut ; NIVEAUX : celles où il s'applique
MOTS_CLES = ("accord", "accorder", "masculin", "feminin", "singulier", "pluriel", "chaine d'accords",
             "groupe nominal", "determinant", "sujet et le verbe", "sujet-verbe", "sujet et verbe")
TABLES = ("noms", "adjectifs", "pluriels_irreguliers", "feminins", "conjugaisons", "terminaisons")

GENRE = {"m": "masculin", "f": "féminin"}
FORME = {("m", "s"): "ms", ("f", "s"): "fs", ("m", "p"): "mp", ("f", "p"): "fp"}
ARTICLES = ("le", "la", "l'", "les")
# les verbes qui vont avec un sujet de cette sorte, sans complément (« les enfants jouent », « le chat mange »)
VERBES = {"personne": ("chanter", "jouer", "parler", "danser", "marcher", "écouter", "arriver", "manger", "regarder"),
          "animal": ("marcher", "manger", "arriver")}
# le pronom qui remplace le sujet : il, elle, ils, elles (le verbe se conjugue comme avec il, ils)
PRONOM = {("m", False): "il", ("f", False): "elle", ("m", True): "ils", ("f", True): "elles"}
TEMPS = {"present": "au présent", "imparfait": "à l'imparfait", "futur": "au futur", "passe_compose": "au passé composé"}


def _table(nom: str) -> tables.Table:
    return tables.charger(MATIERE, nom)


def noms(niveau: str, **criteres) -> list[dict]:
    return [n for n in _table("noms").filtrer(**criteres) if avant_ou_egale(niveau, n["depuis"])]


def avec_l_article(article: str, nom: str) -> str:
    return f"l'{nom}" if article == "l'" else f"{article} {nom}"


def invariable(nom: dict) -> bool:
    return nom["pluriel"] == nom["nom"]


# --- les genres --------------------------------------------------------------------------------------------

def determinant(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Choisis le bon mot : … école » → l' ; les mauvaises réponses : les trois autres (le, la, les). Pas de nom
    invariable : « … souris » irait avec la et les."""
    nom = rng.choice([n for n in noms(niveau) if not invariable(n)])
    pluriel = rng.random() < 1 / 3
    forme, bonne = (nom["pluriel"], "les") if pluriel else (nom["nom"], nom["article"])
    if pluriel:
        explication = f"« {forme} » est au pluriel : on écrit les {forme}."
    elif bonne == "l'":
        explication = (f"« {forme} » est un nom {GENRE[nom['genre']]} qui commence par une voyelle : le ou la devient "
                       f"l' : l'{forme}.")
    else:
        explication = f"« {forme} » est un nom {GENRE[nom['genre']]} singulier : on écrit {bonne} {forme}."
    return Squelette(
        genre=f"{NOM}.determinant",
        enonce=f"Choisis le bon mot : … {forme}",
        reponse=bonne,
        distracteurs=tuple(a for a in ARTICLES if a != bonne),
        explication=explication,
        cle=("determinant", forme),
    )


# plusieurs formulations : deux questions d'un même exercice n'ont jamais le même énoncé (N3 le refuserait)
FORMULES_GENRE = ("Quel nom est {g} ? (on dit « {un} … »)", "Lequel de ces noms est {g} ?",
                  "Trouve le nom {g} (on dit « {un} … »).", "Quel mot est un nom {g} ?")
FORMULES_NOMBRE = ("Quel groupe de mots est au {n} ?", "Lequel de ces groupes est au {n} ?",
                   "Trouve le groupe de mots au {n}.", "Quel groupe de mots est écrit au {n} ?")


def masculin_feminin(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel nom est féminin ? (on dit « une … ») » → table ; les mauvaises réponses : trois noms masculins (ou
    l'inverse)."""
    cherche = rng.choice(("f", "m"))
    autre = "m" if cherche == "f" else "f"
    bon = rng.choice(noms(niveau, genre=cherche))
    faux = rng.sample(noms(niveau, genre=autre), 3)
    un, un_autre = ("une", "un") if cherche == "f" else ("un", "une")
    enonce = rng.choice(FORMULES_GENRE).format(g=GENRE[cherche], un=un)
    return Squelette(
        genre=f"{NOM}.masculin_feminin",
        enonce=enonce,
        reponse=bon["nom"],
        distracteurs=tuple(n["nom"] for n in faux),
        explication=(f"On dit « {un} {bon['nom']} » : {bon['nom']} est {GENRE[cherche]}. On dit "
                     + ", ".join(f"« {un_autre} {n['nom']} »" for n in faux) + f" : ils sont {GENRE[autre]}s."),
        cle=("masculin_feminin", enonce),
    )


def _groupe(rng: random.Random, nom: dict, pluriel: bool) -> tuple[str, str]:
    """(groupe nominal, déterminant) : « les pommes », « une table », « l'arbre »."""
    if pluriel:
        det = rng.choice(("les", "des"))
        return f"{det} {nom['pluriel']}", det
    det = rng.choice((nom["article"], "un" if nom["genre"] == "m" else "une"))
    return avec_l_article(det, nom["nom"]), det


def singulier_pluriel(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel groupe de mots est au pluriel ? » → les pommes ; trois groupes au singulier, dont si possible un nom qui
    finit par -s ou -x (la souris) : le s n'est pas le seul indice. Ou l'inverse (« au singulier »)."""
    au_pluriel = rng.random() < 0.5
    tous = noms(niveau)
    bon = rng.choice(tous)
    autres = [n for n in tous if n["nom"] != bon["nom"]]
    rng.shuffle(autres)
    if au_pluriel:  # le piège d'abord : un singulier qui finit par s ou x
        autres.sort(key=lambda n: not n["nom"].endswith(("s", "x")))
    groupe, det = _groupe(rng, bon, au_pluriel)
    faux = [_groupe(rng, n, not au_pluriel)[0] for n in autres[:3]]
    if au_pluriel:
        indice = ("le nom ne change pas, c'est le déterminant qui le dit" if invariable(bon)
                  else f"le nom prend la marque du pluriel ({bon['pluriel'][len(bon['nom']):] or 's'})")
        explication = f"« {groupe} » : le déterminant « {det} » dit qu'il y en a plusieurs ; {indice}."
    else:
        explication = f"« {groupe} » : le déterminant « {det} » dit qu'il n'y en a qu'un : c'est le singulier."
    enonce = rng.choice(FORMULES_NOMBRE).format(n="pluriel" if au_pluriel else "singulier")
    return Squelette(
        genre=f"{NOM}.singulier_pluriel",
        enonce=enonce,
        reponse=groupe,
        distracteurs=distracteurs(groupe, faux),
        explication=explication,
        cle=("singulier_pluriel", au_pluriel, enonce),
    )


def _regulier(adjectif: dict) -> bool:
    ms = adjectif["ms"]
    return (adjectif["fs"], adjectif["mp"], adjectif["fp"]) == (ms + "e", ms + "s", ms + "es")


def accord_gn(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Complète : les chattes … (noir) » → noires ; les mauvaises réponses : les trois autres formes de l'adjectif
    (toutes différentes, par construction de la table). Au CP, seulement les accords réguliers (+e, +s)."""
    adjectifs = [a for a in _table("adjectifs").lignes if niveau != "CP" or _regulier(a)]
    adjectif = rng.choice(adjectifs)
    sortes = adjectif["pour"].split()
    nom = rng.choice([n for n in noms(niveau) if "tout" in sortes or n["sorte"] in sortes])
    nombre = rng.choice(("s", "p"))
    bonne = adjectif[FORME[(nom["genre"], nombre)]]
    forme_nom = nom["pluriel"] if nombre == "p" else nom["nom"]
    det = "les" if nombre == "p" else ("un" if nom["genre"] == "m" else "une")
    if adjectif["place"] == "avant":
        trou, complet = f"{det} … {forme_nom}", f"{det} {bonne} {forme_nom}"
    else:
        trou, complet = f"{det} {forme_nom} …", f"{det} {forme_nom} {bonne}"
    return Squelette(
        genre=f"{NOM}.accord_gn",
        enonce=f"Complète : {trou} ({adjectif['ms']})",
        reponse=bonne,
        distracteurs=tuple(adjectif[f] for f in ("ms", "fs", "mp", "fp") if adjectif[f] != bonne),
        explication=(f"« {forme_nom} » est {GENRE[nom['genre']]} {'pluriel' if nombre == 'p' else 'singulier'} : "
                     f"l'adjectif {adjectif['ms']} s'accorde avec le nom : {complet}."),
        cle=("accord_gn", adjectif["ms"], nom["nom"], nombre),
    )


def pluriel_irregulier(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Écris au pluriel : cheval → … » → chevaux ; les mauvaises réponses : l'erreur typique (chevals) et le
    singulier. Trois propositions : il n'y a pas d'autre forme vraisemblable."""
    l = rng.choice(_table("pluriels_irreguliers").lignes)
    return Squelette(
        genre=f"{NOM}.pluriel_irregulier",
        enonce=f"Écris au pluriel : {l['singulier']} → …",
        reponse=l["pluriel"],
        distracteurs=distracteurs(l["pluriel"], [l["erreur"], l["singulier"]], 2),
        explication=f"Règle : {l['regle']}. Donc {l['singulier']} → {l['pluriel']}, et non « {l['erreur']} ».",
        cle=("pluriel_irregulier", l["singulier"]),
    )


def feminin_irregulier(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Écris au féminin : un lecteur → une … » → lectrice ; les mauvaises réponses : l'erreur typique (lecteuse) et le
    masculin."""
    l = rng.choice(_table("feminins").lignes)
    enonce = (f"Écris au féminin : un {l['masculin']} → une …" if l["nature"] == "nom"
              else f"Écris au féminin : {l['masculin']} → …")
    return Squelette(
        genre=f"{NOM}.feminin_irregulier",
        enonce=enonce,
        reponse=l["feminin"],
        distracteurs=distracteurs(l["feminin"], [l["erreur"], l["masculin"]], 2),
        explication=f"Règle : {l['regle']}. Donc {l['masculin']} → {l['feminin']}, et non « {l['erreur']} ».",
        cle=("feminin_irregulier", l["masculin"]),
    )


def sujet_verbe(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Complète au présent : les enfants … (jouer) » → jouent ; les mauvaises réponses : le même verbe, au même temps,
    à d'autres personnes (joue, joues, jouons). Au CP, le présent avec il et ils seulement (« le chat miaule / les
    chats miaulent », l'exemple du programme) ; ensuite les 4 temps, sauf le passé composé avec être (allé / allée)."""
    nom = rng.choice([n for n in noms(niveau) if n["sorte"] in VERBES])
    infinitif = rng.choice(VERBES[nom["sorte"]])
    temps = "present" if niveau == "CP" else rng.choice(tuple(TEMPS))
    if temps == "passe_compose" and infinitif == "arriver":
        raise Retirer("passé composé avec être : l'accord du participe dépend du genre")
    pluriel = rng.random() < 0.5
    personne = "ils" if pluriel else "il"
    conj = _table("conjugaisons")
    bonne = conj.filtrer(infinitif=infinitif, temps=temps, personne=personne)[0]["forme"]
    autres = [l["forme"] for l in conj.filtrer(infinitif=infinitif, temps=temps) if l["personne"] != personne]
    rng.shuffle(autres)
    autres.sort(key=lambda f: f != conj.filtrer(infinitif=infinitif, temps=temps,
                                                personne="il" if pluriel else "ils")[0]["forme"])
    groupe = (f"les {nom['pluriel']}" if pluriel else avec_l_article(nom["article"], nom["nom"]))
    if temps == "passe_compose":
        regle = f"au passé composé, l'auxiliaire avoir s'accorde avec lui ({bonne.split()[0]})"
    else:
        fin = _table("terminaisons").filtrer(temps=temps, personne=personne)[0]["terminaison"]
        regle = f"{TEMPS[temps]}, le verbe se termine par {fin}"
    return Squelette(
        genre=f"{NOM}.sujet_verbe",
        enonce=f"Complète {TEMPS[temps]} : {groupe} … ({infinitif})",
        reponse=bonne,
        distracteurs=distracteurs(bonne, autres),
        explication=(f"Le sujet « {groupe} » est au {'pluriel' if pluriel else 'singulier'} (on peut dire "
                     f"« {PRONOM[(nom['genre'], pluriel)]} ») ; {regle} : {groupe} {bonne}."),
        cle=("sujet_verbe", nom["nom"], pluriel, infinitif, temps),
    )


GENRES = (determinant, masculin_feminin, singulier_pluriel, accord_gn, pluriel_irregulier, feminin_irregulier,
          sujet_verbe)
CLASSES_DU_GENRE = {"determinant": CYCLE_2, "masculin_feminin": ("CP",), "singulier_pluriel": ("CP",),
                    "accord_gn": CYCLE_2, "pluriel_irregulier": ("CE2",), "feminin_irregulier": ("CE2",),
                    "sujet_verbe": CYCLE_2}
# les objectifs du programme (francais-cp.yaml…)
_GN = {"CE1": ("francais.ce1.orthographe-grammaticale.01",), "CE2": ("francais.ce2.orthographe-grammaticale.01",)}
ATTENDUS = {
    "determinant": {"CP": ("francais.cp.orthographe-grammaticale.01", "francais.cp.orthographe-grammaticale.02"), **_GN},
    "masculin_feminin": {"CP": ("francais.cp.orthographe-grammaticale.01",)},
    "singulier_pluriel": {"CP": ("francais.cp.orthographe-grammaticale.02",)},
    "accord_gn": {"CP": ("francais.cp.orthographe-grammaticale.03",), **_GN},
    "pluriel_irregulier": {"CE2": ("francais.ce2.orthographe-grammaticale.01",)},
    "feminin_irregulier": {"CE2": ("francais.ce2.orthographe-grammaticale.01",)},
    "sujet_verbe": {"CP": ("francais.cp.orthographe-grammaticale.04",), "CE1": ("francais.ce1.orthographe-grammaticale.02",),
                    "CE2": ("francais.ce2.orthographe-grammaticale.02",)},
}
