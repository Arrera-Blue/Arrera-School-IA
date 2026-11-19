"""Le temps et l'histoire, du CP au CE2 (lot 2, étape 2.1 : docs/Generateur-Procedural/lot-2-questionner-le-monde.md
§4). Le programme d'histoire-géographie de 2026 : au CP, se repérer dans le temps (les jours, les mois, les saisons,
hier et demain, l'année de 12 mois) ; au CE1, les durées longues (décennie, siècle, millénaire) et les cinq grandes
périodes ; au CE2, les repères datés et la Préhistoire.

Presque tout se calcule (le jour d'après-demain, l'année dans sa période, le plus ancien de deux repères) ; les faits
se lisent dans cinq tables relues par l'enseignant (donnees/histoire-geo/) : le calendrier, les durées, les périodes,
les repères, la Préhistoire. Un fait discuté n'est jamais demandé : le premier jour de la semaine (le lundi pour la
norme ISO, le dimanche ailleurs), le nombre de saisons, une année proche d'une limite de période, l'ordre de deux
repères trop proches pour leur incertitude (Ötzi et l'écriture).
"""

import random

from generateur.procedural import Precision, Retirer, Squelette, distracteurs, tables
from generateur.procedural.histoire_geo import CYCLE_2

NOM, TITRE, NOTION, NIVEAU = "histoire", "Le temps et l'histoire", "le temps et l'histoire", "CE1"
MATIERE, NIVEAUX = "histoire-geo", CYCLE_2  # NIVEAU : la classe par défaut ; NIVEAUX : celles où il s'applique
MOTS_CLES = ("histoire", "le temps", "calendrier", "jours de la semaine", "jour de la semaine", "les mois", "mois de l'annee",
             "saison", "hier", "demain", "siecle", "decennie", "millenaire", "periode", "moyen age", "antiquite",
             "temps modernes", "epoque contemporaine", "prehistoire", "paleolithique", "neolithique", "repere", "frise",
             "chronologi")
TABLES = ("calendrier", "durees", "periodes", "reperes", "prehistoire")
# les notions précises, de la plus précise à la plus générale (« les dates de la Préhistoire » : les deux)
PRECISIONS = (
    Precision(r"prehistoire|paleolithique|neolithique", "la Préhistoire", ("prehistoire",)),
    Precision(r"reperes?|\bdates?\b|chronologi", "les repères datés", ("repere",)),
    Precision(r"periodes?|moyen age|antiquite|temps modernes|epoque contemporaine", "les grandes périodes", ("periode",)),
    Precision(r"siecles?|decennies?|millenaires?", "les siècles", ("duree",)),
    Precision(r"saisons?", "les saisons", ("saison",)),
    Precision(r"jours? de la semaine|avant-hier|apres-demain|\bhier\b|\bdemain\b", "les jours de la semaine", ("jour",)),
    Precision(r"\bmois\b", "les mois", ("mois",)),
    Precision(r"calendrier", "le calendrier", ("jour", "mois", "calendrier")),
)

ORDINAUX = ("premier", "deuxième", "troisième", "quatrième", "cinquième", "sixième", "septième", "huitième",
            "neuvième", "dixième", "onzième", "douzième")
VOYELLES = "aàâeéèêiîoôuûhAÀÂEÉÈÊIÎOÔUÛH"


def _table(nom: str) -> tables.Table:
    return tables.charger(MATIERE, nom)


def _suite(suite: str) -> list[str]:
    """Les jours, les mois ou les saisons, dans l'ordre."""
    return [l["nom"] for l in sorted(_table("calendrier").filtrer(suite=suite), key=lambda l: l["rang"])]


def de(mot: str) -> str:
    """« de mois », « d'heures »."""
    return f"d'{mot}" if mot[0] in VOYELLES else f"de {mot}"


def le(mot: str) -> str:
    """« le printemps », « l'été », « l'hiver »."""
    return f"l'{mot}" if mot[0] in VOYELLES else f"le {mot}"


def majuscule(texte: str) -> str:
    return texte[:1].upper() + texte[1:]


def accord(nom: str, singulier: str, pluriel: str) -> str:
    """« les Temps modernes vont », « le Moyen Âge va »."""
    return pluriel if nom.startswith("les ") else singulier


def annee_texte(annee: int) -> str:
    """-52 → « 52 av. J.-C. » ; 100 → « l'an 100 » ; 1200 → « 1200 »."""
    if annee < 0:
        return f"{-annee} av. J.-C."
    return f"l'an {annee}" if annee < 1000 else str(annee)


def _compter(noms: list[str], depart: int, pas: int) -> tuple[str, list[str], bool]:
    """La réponse, les noms traversés, et si la suite recommence (après dimanche, lundi)."""
    sens = 1 if pas > 0 else -1
    chemin = [noms[(depart + sens * j) % len(noms)] for j in range(1, abs(pas) + 1)]
    recommence = not 0 <= depart + pas < len(noms)
    return chemin[-1], chemin, recommence


def _voisins(noms: list[str], depart: int, pas: int) -> list[str]:
    """Les erreurs typiques, de la plus plausible à la moins plausible : compter un de trop, un de moins (pas le jour
    de départ : « juste après mardi » ne propose pas mardi), partir dans l'autre sens, deux de trop ; le jour de départ
    en dernier recours."""
    sens = 1 if pas > 0 else -1
    rangs = [depart + pas + sens, depart + pas - sens, depart - pas, depart + pas + 2 * sens]
    return [noms[r % len(noms)] for r in rangs if r % len(noms) != depart % len(noms)] + [noms[depart]]


def _explication(noms: list[str], depart: int, pas: int, libelle: str, unite: str, verbe: str = "c'est") -> str:
    """« Juste après mardi vient mercredi. » ; « Hier, c'était le jour juste avant mardi : lundi. » ; « On avance de 4
    jours à partir de mardi : mercredi, jeudi, vendredi, samedi. Dans 4 jours, c'est samedi. »."""
    bon, chemin, recommence = _compter(noms, depart, pas)
    mot = "après" if pas > 0 else "avant"
    if abs(pas) == 1:
        texte = (f"{libelle}, {verbe} le jour juste {mot} {noms[depart]} : {bon}." if libelle
                 else f"Juste {mot} {noms[depart]} vient {bon}.")
    else:
        texte = (f"On {'avance' if pas > 0 else 'recule'} de {abs(pas)} {unite} à partir de {noms[depart]} : "
                 f"{', '.join(chemin)}. {libelle}, {verbe} {bon}.")
    if recommence:
        texte += f" Après {noms[-1]}, on recommence à {noms[0]}."
    return texte


# --- les genres --------------------------------------------------------------------------------------------

def jour(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Aujourd'hui, c'est mardi. Quel jour serons-nous après-demain ? » → jeudi ; au CE1, « dans 4 jours », « il y a
    3 jours ». Jamais « le premier jour de la semaine » (le lundi ou le dimanche selon la convention)."""
    noms = _suite("jour")
    formes = [("demain", 1), ("après-demain", 2), ("hier", -1), ("avant-hier", -2), ("après", 1), ("avant", -1)]
    if niveau != "CP":
        formes += [("dans", n) for n in range(3, 7)] + [("il y a", -n) for n in range(3, 7)]
    forme, pas = rng.choice(formes)
    depart = rng.randrange(len(noms))
    d = noms[depart]
    if forme in ("demain", "après-demain"):
        enonce, libelle = f"Aujourd'hui, c'est {d}. Quel jour serons-nous {forme} ?", majuscule(forme)
    elif forme in ("hier", "avant-hier"):
        enonce, libelle = f"Aujourd'hui, c'est {d}. Quel jour était-ce {forme} ?", majuscule(forme)
    elif forme in ("après", "avant"):
        enonce, libelle = f"Quel jour vient juste {forme} {d} ?", ""
    elif forme == "dans":
        enonce, libelle = f"Aujourd'hui, c'est {d}. Quel jour serons-nous dans {pas} jours ?", f"Dans {pas} jours"
    else:
        enonce, libelle = f"Aujourd'hui, c'est {d}. Quel jour était-ce il y a {-pas} jours ?", f"Il y a {-pas} jours"
    bon = _compter(noms, depart, pas)[0]
    return Squelette(
        genre=f"{NOM}.jour", enonce=enonce, reponse=bon,
        distracteurs=distracteurs(bon, _voisins(noms, depart, pas)),
        explication=_explication(noms, depart, pas, libelle, "jours", "c'est" if pas > 0 else "c'était"),
        cle=("jour", forme, d, pas), sujet=("jour", tuple(sorted((d, bon)))))  # « après mardi », « demain (mardi) »


def mois(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel mois vient juste après mars ? » → avril ; au CE1, « Quel est le cinquième mois de l'année ? », « Nous
    sommes en mars. En quel mois serons-nous dans 3 mois ? »."""
    noms = _suite("mois")
    formes = ["après", "avant"] + (["rang", "dans"] if niveau != "CP" else [])
    forme = rng.choice(formes)
    if forme == "rang":
        rang = rng.randrange(len(noms))
        bon = noms[rang]
        return Squelette(
            genre=f"{NOM}.mois", enonce=f"Quel est le {ORDINAUX[rang]} mois de l'année ?", reponse=bon,
            distracteurs=distracteurs(bon, [noms[(rang + d) % 12] for d in (1, -1, 2, -2)]),
            explication=f"Les mois, dans l'ordre : {', '.join(noms[:rang + 1])}. Le {ORDINAUX[rang]} est {bon}.",
            cle=("mois", "rang", rang))
    depart = rng.randrange(len(noms))
    pas = {"après": 1, "avant": -1}.get(forme) or rng.randrange(2, 6)
    if forme == "dans":
        enonce = f"Nous sommes en {noms[depart]}. En quel mois serons-nous dans {pas} mois ?"
    else:
        enonce = f"Quel mois vient juste {forme} {noms[depart]} ?"
    bon = _compter(noms, depart, pas)[0]
    return Squelette(
        genre=f"{NOM}.mois", enonce=enonce, reponse=bon,
        distracteurs=distracteurs(bon, _voisins(noms, depart, pas)),
        explication=_explication(noms, depart, pas, f"Dans {pas} mois" if forme == "dans" else "", "mois", "ce sera"),
        cle=("mois", forme, depart, pas), sujet=("mois", tuple(sorted((noms[depart], bon)))))


def saison(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Dans l'ordre des saisons, laquelle vient juste après l'été ? » → l'automne ; « Le printemps, l'été,
    l'automne… Quelle saison vient ensuite ? » ; la saison qui manque dans la suite. Seulement l'ordre : le nombre de
    saisons dépend du lieu (saison sèche et saison des pluies sous les tropiques)."""
    noms = [le(n) for n in _suite("saison")]
    ordre = (f"Les saisons se suivent toujours dans le même ordre : {', '.join(noms)}, puis de nouveau {noms[0]}.")
    depart = rng.randrange(len(noms))
    suite = [noms[(depart + k) % len(noms)] for k in range(len(noms))]  # quatre saisons, à partir de `depart`
    forme = rng.choice(("après", "avant", "ensuite", "manque"))
    if forme == "ensuite":
        bon, autres = suite[3], suite[:3]
        enonce = f"{majuscule(suite[0])}, {suite[1]}, {suite[2]}… Quelle saison vient ensuite ?"
        fin_explication = f"Après {suite[2]} vient {bon}."
    elif forme == "manque":
        bon, autres = suite[1], [suite[3], suite[0], suite[2]]
        enonce = f"Dans l'ordre : {suite[0]}, …, {suite[2]}. Quelle saison manque ?"
        fin_explication = f"Entre {suite[0]} et {suite[2]}, il y a {bon}."
    else:
        pas = 1 if forme == "après" else -1
        bon = noms[(depart + pas) % len(noms)]
        autres = [n for i, n in enumerate(noms) if i not in (depart, (depart + pas) % len(noms))]
        enonce = f"Dans l'ordre des saisons, laquelle vient juste {forme} {noms[depart]} ?"
        fin_explication = f"Juste {forme} {noms[depart]} vient {bon}."
    rng.shuffle(autres)
    return Squelette(
        genre=f"{NOM}.saison", enonce=enonce, reponse=bon, distracteurs=tuple(autres),
        explication=f"{ordre} {fin_explication}", cle=("saison", forme, depart))


PIEGES_CP = (5, 10, 30, 60)  # faux pour chaque unité du CP (une semaine n'a pas 5 jours : 5, ce sont les jours d'école)


def calendrier(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Combien de jours y a-t-il dans une semaine ? » → 7 ; « Dans une année, il y a 12… » → mois."""
    lignes = _table("durees").lignes
    du_cp = [l for l in lignes if l["depuis"] == "CP"]
    l = rng.choice(du_cp)
    explication = f"{majuscule(l['article'])} {l['unite']} compte {l['nombre']} {l['contient']}"
    explication += {"semaine": " : " + ", ".join(_suite("jour")), "année": ", de janvier à décembre"}.get(l["unite"], "")
    if rng.random() < 0.5:
        bon = str(l["nombre"])
        candidats = [str(x["nombre"]) for x in du_cp if x is not l] + [str(p) for p in PIEGES_CP]
        return Squelette(
            genre=f"{NOM}.calendrier",
            enonce=f"Combien {de(l['contient'])} y a-t-il dans {l['article']} {l['unite']} ?",
            reponse=bon, distracteurs=distracteurs(bon, candidats), explication=explication + ".",
            cle=("calendrier", "nombre", l["unite"]))
    autres = list(dict.fromkeys(x["contient"] for x in lignes if x["contient"] != l["contient"]))
    rng.shuffle(autres)
    return Squelette(
        genre=f"{NOM}.calendrier",
        enonce=f"Dans {l['article']} {l['unite']}, il y a {l['nombre']}…",
        reponse=l["contient"], distracteurs=distracteurs(l["contient"], autres), explication=explication + ".",
        cle=("calendrier", "unite", l["unite"]))


def duree(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Combien d'années y a-t-il dans 3 siècles ? » → 300 ; « Combien de décennies y a-t-il dans un siècle ? » → 10.
    Les mauvaises réponses confondent 10, 100 et 1000."""
    longues = sorted((l for l in _table("durees").lignes if l["depuis"] == "CE1"), key=lambda l: l["nombre"])
    forme = rng.choice(("une", "plusieurs", "plusieurs", "dans"))
    if forme == "dans":
        petite, grande = sorted(rng.sample(longues, 2), key=lambda l: l["nombre"])
        n = grande["nombre"] // petite["nombre"]
        bon = str(n)
        candidats = [str(x["nombre"]) for x in longues] + ["20", "50"]
        return Squelette(
            genre=f"{NOM}.duree",
            enonce=f"Combien {de(petite['unite'] + 's')} y a-t-il dans {grande['article']} {grande['unite']} ?",
            reponse=bon, distracteurs=distracteurs(bon, candidats),
            explication=(f"{majuscule(grande['article'])} {grande['unite']} dure {grande['nombre']} ans et "
                         f"{petite['article']} {petite['unite']} {petite['nombre']} ans : {grande['nombre']} = {n} fois "
                         f"{petite['nombre']}, donc il y a {n} {petite['unite']}s dans {grande['article']} "
                         f"{grande['unite']}."),
            cle=("duree", "dans", petite["unite"], grande["unite"]))
    l = rng.choice(longues)
    if forme == "une":
        bon = str(l["nombre"])
        candidats = [str(x["nombre"]) for x in longues] + ["12", "50", "365"]
        return Squelette(
            genre=f"{NOM}.duree",
            enonce=f"Combien d'années y a-t-il dans {l['article']} {l['unite']} ?",
            reponse=bon, distracteurs=distracteurs(bon, candidats),
            explication=(f"{majuscule(l['article'])} {l['unite']} dure {l['nombre']} ans : il y a {l['nombre']} années "
                         f"dans {l['article']} {l['unite']}."),
            cle=("duree", "une", l["unite"]))
    k = rng.randrange(2, 10)
    bon = str(k * l["nombre"])
    candidats = [str(k * x["nombre"]) for x in longues] + [str(k + l["nombre"]), str(l["nombre"])]
    return Squelette(
        genre=f"{NOM}.duree",
        enonce=f"Combien d'années y a-t-il dans {k} {l['unite']}s ?",
        reponse=bon, distracteurs=distracteurs(bon, candidats),
        explication=(f"{majuscule(l['article'])} {l['unite']} dure {l['nombre']} ans : {k} {l['unite']}s, c'est {k} fois "
                     f"{l['nombre']} ans, soit {bon} ans."),
        cle=("duree", "plusieurs", l["unite"], k))


def _periodes() -> list[dict]:
    return sorted(_table("periodes").lignes, key=lambda l: l["rang"])


def _marge(date: str) -> int:
    """Une limite « environ » est floue : on reste à 500 ans d'elle ; une date précise, à 50 ans."""
    return 500 if date.startswith(("environ", "il y a")) else 50


def _annees(p: dict) -> list[int]:
    """Les années qu'on peut demander dans la période : rondes, loin de ses limites, ni l'an 0 ni avant 10000 av. J.-C.,
    ni après 2000."""
    bas = max(p["debut_annee"] + _marge(p["debut"]), -10000)
    haut = min(p["fin_annee"] - _marge(p["fin"]), 2000)
    return [a for a in range(-10000, 2001, 100) if bas <= a <= haut and a != 0 and (a > -3000 or a % 1000 == 0)]


def periode(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """Les cinq grandes périodes (par convention, en Europe) : laquelle vient juste après le Moyen Âge ; la plus
    ancienne de quatre ; en quelle année commence le Moyen Âge ; « En 1200, dans quelle période sommes-nous ? »."""
    periodes = _periodes()
    noms = [p["nom"] for p in periodes]
    ordre = f"Les grandes périodes, dans l'ordre : {', '.join(noms)}."
    forme = rng.choice(("apres", "avant", "ancienne", "recente", "debut", "fin", "annee", "annee"))
    if forme in ("apres", "avant"):
        i = rng.randrange(len(noms) - 1) + (1 if forme == "avant" else 0)
        j = i + (1 if forme == "apres" else -1)
        autres = [n for k, n in enumerate(noms) if k not in (i, j)]
        mot = "après" if forme == "apres" else "avant"
        return Squelette(
            genre=f"{NOM}.periode", enonce=f"Quelle période vient juste {mot} {noms[i]} ?", reponse=noms[j],
            distracteurs=distracteurs(noms[j], autres),
            explication=f"{ordre} Juste {mot} {noms[i]} {accord(noms[j], 'vient', 'viennent')} {noms[j]}.",
            cle=("periode", forme, i))
    if forme in ("ancienne", "recente"):
        choisies = sorted(rng.sample(range(len(noms)), 4))
        bon = noms[choisies[0] if forme == "ancienne" else choisies[-1]]
        return Squelette(
            genre=f"{NOM}.periode",
            enonce=f"Quelle est la plus {'ancienne' if forme == 'ancienne' else 'récente'} de ces périodes ?",
            reponse=bon, distracteurs=tuple(noms[k] for k in choisies if noms[k] != bon),
            explication=(f"De la plus ancienne à la plus récente : {', '.join(noms[k] for k in choisies)}. La plus "
                         f"{'ancienne' if forme == 'ancienne' else 'récente'} est {bon}."),
            cle=("periode", forme))  # l'énoncé ne cite pas les périodes : une seule question de cette forme
    if forme in ("debut", "fin"):
        # seulement les limites précises (pas « environ 3000 av. J.-C. »)
        possibles = [p for p in periodes if p[forme][0].isdigit() and not p[forme].endswith("av. J.-C.")]
        p = rng.choice(possibles)
        limites = list(dict.fromkeys(x["fin"] for x in periodes if x["fin"][0].isdigit()))
        bon = p[forme]
        verbe = (accord(p["nom"], "commence", "commencent") if forme == "debut"
                 else accord(p["nom"], "se termine", "se terminent"))
        return Squelette(
            genre=f"{NOM}.periode", enonce=f"En quelle année {verbe} {p['nom']} ?", reponse=bon,
            distracteurs=distracteurs(bon, [x for x in limites if x != bon]),
            explication=f"{majuscule(p['nom'])} {accord(p['nom'], 'va', 'vont')} {de(p['debut'])} à {p['fin']}.",
            cle=("periode", forme, p["rang"]))
    p = rng.choice(periodes)
    annee = rng.choice(_annees(p))
    i = periodes.index(p)
    voisines = sorted((k for k in range(len(noms)) if k != i), key=lambda k: abs(k - i))
    texte = annee_texte(annee)
    explication = (f"{majuscule(p['nom'])} {accord(p['nom'], 'va', 'vont')} {de(p['debut'])} à {p['fin']} : {texte} "
                   "est entre les deux.")
    if annee < 0:
        explication += " Avant J.-C., on compte à rebours : plus le nombre est grand, plus c'est ancien."
    return Squelette(
        genre=f"{NOM}.periode",
        enonce=f"En {texte}, dans quelle période de l'histoire sommes-nous ?",
        reponse=p["nom"], distracteurs=distracteurs(p["nom"], [noms[k] for k in voisines]),
        explication=explication, cle=("periode", "annee", annee), sujet=("periode", "annee", p["rang"]))


def _comparables(a: dict, b: dict) -> bool:
    """Deux repères se rangent sans doute possible : leur écart dépasse leurs incertitudes."""
    return abs(a["annee"] - b["annee"]) > a["marge"] + b["marge"]


def repere(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """Les repères datés du CE2 : « Quel repère correspond à « 987 » ? » → l'élection d'Hugues Capet ; « Quelle date va
    avec « la guerre de Cent Ans » ? » ; « Lequel de ces repères est le plus ancien ? »."""
    lignes = list(_table("reperes").lignes)
    forme = rng.choice(("evenement", "date", "ancien", "recent"))
    if forme in ("evenement", "date"):
        l = rng.choice(lignes)
        # jamais un repère trop proche pour son incertitude : « 3200 av. J.-C. » (Ötzi) n'est pas faux pour l'écriture
        autres = [x for x in lignes if x is not l and _comparables(x, l)]
        rng.shuffle(autres)
        explication = f"Repère : {l['date']}, {l['evenement']}."
        if forme == "evenement":
            return Squelette(
                genre=f"{NOM}.repere", enonce=f"Quel repère correspond à « {l['date']} » ?", reponse=l["evenement"],
                distracteurs=distracteurs(l["evenement"], [x["evenement"] for x in autres]),
                explication=explication, cle=("repere", "evenement", l["evenement"]),
                sujet=("repere", l["evenement"]))
        return Squelette(
            genre=f"{NOM}.repere", enonce=f"Quelle date va avec « {l['evenement']} » ?", reponse=l["date"],
            distracteurs=distracteurs(l["date"], [x["date"] for x in autres]),
            explication=explication, cle=("repere", "date", l["evenement"]), sujet=("repere", l["evenement"]))
    for nombre in (4, 3):
        choisis = rng.sample(lignes, nombre)
        if all(_comparables(a, b) for i, a in enumerate(choisis) for b in choisis[i + 1:]):
            break
    else:
        raise Retirer("des repères trop proches pour être rangés sans doute")
    ranges = sorted(choisis, key=lambda x: x["annee"])
    bon = (ranges[0] if forme == "ancien" else ranges[-1])["evenement"]
    explication = ("Du plus ancien au plus récent : " + " ; ".join(f"{x['evenement']} ({x['date']})" for x in ranges)
                   + f". Le plus {'ancien' if forme == 'ancien' else 'récent'} est {bon}.")
    if sum(x["annee"] < 0 for x in ranges) >= 2:
        explication += " Avant J.-C., plus le nombre est grand, plus c'est ancien."
    return Squelette(
        genre=f"{NOM}.repere",
        enonce=f"Lequel de ces repères est le plus {'ancien' if forme == 'ancien' else 'récent'} ?",
        reponse=bon, distracteurs=tuple(x["evenement"] for x in choisis if x["evenement"] != bon),
        explication=explication, cle=("repere", forme))  # l'énoncé ne cite pas les repères : une seule


AUTRES_EPOQUES = ("dans l'Antiquité", "au Moyen Âge")  # bien après le Paléolithique et le Néolithique


def prehistoire(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """Le Paléolithique et le Néolithique : nomades ou sédentaires ; ce qui apparaît au Néolithique ; ce qui existe
    déjà au Paléolithique ; « À quelle période apparaît l'élevage ? »."""
    t = _table("prehistoire")
    forme = rng.choice(("nomades", "sedentaires", "nouveaute", "deja", "quand", "quand", "quand"))
    if forme == "nomades":
        pieges = [l["texte"] for l in t.filtrer(periode="Néolithique") if l["sorte"] in ("mode_de_vie", "metier")]
        return Squelette(
            genre=f"{NOM}.prehistoire", enonce="Au Paléolithique, les êtres humains sont surtout…", reponse="nomades",
            distracteurs=distracteurs("nomades", pieges),
            explication=("Au Paléolithique, les êtres humains sont surtout nomades : ils se déplacent pour chasser, "
                         "pêcher et cueillir. Ils deviennent sédentaires au Néolithique, avec l'agriculture."),
            cle=("prehistoire", "nomades"), sujet=("prehistoire", "mode de vie"))
    if forme == "sedentaires":
        pieges = [l["texte"] for l in t.filtrer(periode="Paléolithique") if l["sorte"] in ("mode_de_vie", "metier")]
        return Squelette(
            genre=f"{NOM}.prehistoire", enonce="Au Néolithique, beaucoup d'êtres humains deviennent…",
            reponse="sédentaires", distracteurs=distracteurs("sédentaires", pieges),
            explication=("Au Néolithique, beaucoup d'êtres humains deviennent sédentaires : ils restent au même endroit "
                         "pour cultiver la terre et élever des animaux. Avant, au Paléolithique, ils étaient nomades."),
            cle=("prehistoire", "sedentaires"), sujet=("prehistoire", "mode de vie"))
    nouveautes = [l["texte"] for l in t.filtrer(sorte="nouveaute")]
    anciennes = [l["texte"] for l in t.filtrer(sorte="activite")]
    if forme in ("nouveaute", "deja"):
        bons, pieges = (nouveautes, anciennes) if forme == "nouveaute" else (anciennes, nouveautes)
        bon, faux = rng.choice(bons), rng.sample(pieges, 3)
        if forme == "nouveaute":
            enonce = "Qu'est-ce qui apparaît au Néolithique ?"
            explication = (f"Au Néolithique apparaissent de nouvelles choses, comme {bon}. En revanche, {faux[0]}, "
                           f"{faux[1]} et {faux[2]} existaient déjà au Paléolithique.")
        else:
            enonce = "Qu'est-ce qui existait déjà au Paléolithique ?"
            explication = (f"Au Paléolithique, on connaissait déjà {bon}. En revanche, {faux[0]}, {faux[1]} et {faux[2]} "
                           "n'apparaissent qu'au Néolithique.")
        return Squelette(genre=f"{NOM}.prehistoire", enonce=enonce, reponse=bon, distracteurs=tuple(faux),
                         explication=explication, cle=("prehistoire", forme), sujet=("prehistoire", bon))
    l = rng.choice(t.filtrer(apparait="oui"))
    pluriel = l["texte"].startswith("les ")
    bon = f"au {l['periode']}"
    autre = "au Néolithique" if l["periode"] == "Paléolithique" else "au Paléolithique"
    explication = f"{majuscule(l['texte'])} {'apparaissent' if pluriel else 'apparaît'} {bon}."
    if l["periode"] == "Néolithique":
        explication += " Au Paléolithique, avant, les êtres humains vivaient de la chasse, de la pêche et de la cueillette."
    explication += " L'Antiquité et le Moyen Âge viennent bien plus tard."
    return Squelette(
        genre=f"{NOM}.prehistoire",
        enonce=f"À quelle période {'apparaissent' if pluriel else 'apparaît'} {l['texte']} ?",
        reponse=bon, distracteurs=(autre, *AUTRES_EPOQUES), explication=explication,
        cle=("prehistoire", "quand", l["texte"]), sujet=("prehistoire", l["texte"]))


GENRES = (jour, mois, saison, calendrier, duree, periode, repere, prehistoire)
CLASSES_DU_GENRE = {"jour": ("CP", "CE1"), "mois": ("CP", "CE1"), "saison": ("CP",), "calendrier": ("CP",),
                    "duree": ("CE1", "CE2"), "periode": ("CE1", "CE2"), "repere": ("CE2",), "prehistoire": ("CE2",)}
ATTENDUS = {
    "jour": {"CP": ("histoire-geo.cp.representations-temps.05", "histoire-geo.cp.situer-evenements.03"),
             "CE1": ("histoire-geo.ce1.passe-proche-lointain.02",)},
    "mois": {"CP": ("histoire-geo.cp.representations-temps.01", "histoire-geo.cp.representations-temps.04"),
             "CE1": ("histoire-geo.ce1.passe-proche-lointain.02",)},
    "saison": {"CP": ("histoire-geo.cp.manifestations-temps.03",)},
    "calendrier": {"CP": ("histoire-geo.cp.representations-temps.01", "histoire-geo.cp.representations-temps.04")},
    "duree": {"CE1": ("histoire-geo.ce1.passe-proche-lointain.02",)},
    "periode": {"CE1": ("histoire-geo.ce1.grandes-periodes.01", "histoire-geo.ce1.grandes-periodes.04")},
    "prehistoire": {"CE2": ("histoire-geo.ce2.prehistoire.01", "histoire-geo.ce2.prehistoire.02")},
}
