"""La géographie sans carte, du CP au CE2 (lot 2, étape 2.4 : docs/Generateur-Procedural/lot-2-questionner-le-monde.md
§5). Le programme d'histoire-géographie de 2026 : au CP, les continents et les océans, les points cardinaux ; au CE1,
les repères du monde (cinq massifs, trois fleuves, deux déserts), les mots du relief et de la végétation, le fleuve et
la rivière, les trois zones climatiques et les territoires français ; au CE2, les massifs et les grands fleuves
français.

Sans carte ni image : on demande ce qu'est un lieu et où il se trouve, jamais de le montrer. Tout se lit dans sept
tables relues par l'enseignant (donnees/histoire-geo/), en monde fermé ; « à l'opposé du nord » et « une rivière »
(un cours d'eau qui se jette dans un autre) se déduisent des tables. Un fait discuté n'est jamais demandé : combien
de continents, si l'Amérique ou l'Océanie en sont, le plus long fleuve du monde, la plaine et le plateau par
l'altitude (« il existe des plateaux en basse altitude »).
"""

import random

from generateur.procedural import Precision, Retirer, Squelette, tables
from generateur.procedural.histoire_geo import CYCLE_2
from generateur.procedural.histoire_geo.histoire import majuscule

NOM, TITRE, NOTION, NIVEAU = "geographie", "La géographie", "la géographie", "CE1"
MATIERE, NIVEAUX = "histoire-geo", CYCLE_2  # NIVEAU : la classe par défaut ; NIVEAUX : celles où il s'applique
MOTS_CLES = ("geographi", "continent", "ocean", "point cardinal", "points cardinaux", "rose des vents", "relief",
             "montagne", "massif", "plaine", "plateau", "vallee", "fleuve", "riviere", "cours d'eau", "climat",
             "desert", "vegetation", "foret", "prairie", "himalaya", "sahara", "amazone", "mississippi", "alpes",
             "pyrenees", "vosges", "le jura", "massif central", "la seine", "la loire", "la garonne", "le rhone",
             "le rhin", "le maroni", "le nil", "les andes", "l'atlas", "rocheuses")
TABLES = ("monde", "points_cardinaux", "lieux", "mots", "climats", "france", "villes")
# les notions précises, de la plus précise à la plus générale (« les fleuves de France » avant « les fleuves »,
# « les montagnes du monde » avant « les montagnes »)
PRECISIONS = (
    # « les massifs et les fleuves de France » : les deux mots d'un coup (sinon « massifs » serait relu seul)
    Precision(r"(?:massifs?|montagnes?|chaines? de montagnes?|fleuves?)"
              r"(?: et (?:les |des )?(?:massifs?|montagnes?|fleuves?))?(?: de (?:la )?france| francais)|"
              r"massif central|pyrenees|vosges|\bjura\b|\bseine\b|\bloire\b|garonne|\brhone\b|\brhin\b|maroni",
              "les massifs et les fleuves de France", ("france",)),
    Precision(r"fleuves? (?:et|ou) (?:les |la |une )?rivieres?|rivieres?|cours d'eau", "le fleuve et la rivière",
              ("cours_eau",)),
    # « les montagnes, les fleuves et les déserts du monde » : « du monde » vaut pour toute la liste
    Precision(r"(?:(?:les |des )?(?:fleuves?|montagnes?|massifs?|chaines? de montagnes?|deserts?|lieux)(?:, | et | ou ))*"
              r"(?:les |des )?(?:fleuves?|montagnes?|massifs?|chaines? de montagnes?|deserts?|lieux) du monde|himalaya|andes|"
              r"\batlas\b|rocheuses|sahara|\bnil\b|amazone|mississippi", "les lieux du monde", ("lieux",)),
    Precision(r"\balpes\b", "les Alpes", ("lieux", "france")),
    Precision(r"points? cardinaux|point cardinal|rose des vents|\bnord\b|\bouest\b", "les points cardinaux",
              ("points_cardinaux",)),
    Precision(r"zones? climatiques?|climats?\b|zones? (?:tropicale|temperee|froide)s?", "les zones climatiques",
              ("climat",)),
    Precision(r"relief|plaines?|plateaux?|vallees?", "le relief", ("relief",)),
    Precision(r"vegetation|forets?|prairies?", "la végétation", ("vegetation",)),
    Precision(r"deserts?", "les déserts", ("vegetation", "lieux")),
    Precision(r"continents?|oceans?", "les continents et les océans", ("continents", "lieux")),
    Precision(r"montagnes?|massifs?|chaines? de montagnes?", "les montagnes", ("relief", "lieux", "france")),
    Precision(r"fleuves?", "les fleuves", ("cours_eau", "lieux", "france")),
    Precision(r"\bfrance\b", "la France", ("france", "continents", "climat")),
)
# où peut se trouver un lieu du monde : dit sans le mot « continent » (l'Amérique en est un ou deux selon le modèle)
REGIONS = ("en Afrique", "en Amérique du Nord", "en Amérique du Sud", "en Asie", "en Europe", "en Océanie")
SORTES_MONDE = {"ocean": ("un océan", "des océans"), "continent": ("un continent", "des continents"),
                "pays": ("un pays", "des pays")}
SORTES_LIEUX = {"chaine": "une chaîne de montagnes", "fleuve": "un fleuve", "desert": "un désert"}


def _table(nom: str) -> tables.Table:
    return tables.charger(MATIERE, nom)


def _liste(mots: list[str]) -> str:
    """« a », « a et b », « a, b et c »."""
    return mots[0] if len(mots) == 1 else f"{', '.join(mots[:-1])} et {mots[-1]}"


def _pluriel(nom: str) -> bool:
    return nom.startswith("les ")


def _du(nom: str) -> str:
    """« le nord » → « du nord » ; « l'est » → « de l'est »."""
    return "du " + nom[3:] if nom.startswith("le ") else "de " + nom


def _quelques(rng: random.Random, candidats: list[str], nombre: int = 3) -> tuple[str, ...]:
    """Jusqu'à `nombre` mauvaises réponses, distinctes, tirées au sort ; deux au moins (3 propositions)."""
    candidats = list(dict.fromkeys(candidats))
    if len(candidats) < 2:
        raise Retirer("pas assez de mauvaises réponses")
    return tuple(rng.sample(candidats, min(nombre, len(candidats))))


# --- les genres --------------------------------------------------------------------------------------------

def continents(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Lequel est le nom d'un océan ? » → Atlantique (Afrique, Europe, Océanie) ; « L'Afrique est… » → un
    continent ; « Sur quel continent se trouve la France hexagonale ? » → en Europe. L'Amérique et l'Océanie ne sont
    jamais une bonne réponse, ni proposées pour « continent »."""
    lignes = _table("monde").lignes
    forme = rng.choice(("nom", "nom", "est", "est", "france"))
    if forme == "nom":
        sorte = rng.choice(tuple(SORTES_MONDE))
        bon = rng.choice([l for l in lignes if l["sorte"] == sorte and l["demande"] == "oui"])
        # « continent » ou « pays » : jamais l'Amérique ni l'Océanie (des continents pour certains, pas pour d'autres)
        autres = [l for l in lignes if l["sorte"] != sorte and (sorte == "ocean" or l["demande"] == "oui")]
        choisis = rng.sample(autres, 3)
        par_sorte = {s: [l["le"] for l in (bon, *choisis) if l["sorte"] == s] for s in SORTES_MONDE}
        explication = " ; ".join(f"{_liste(noms)} {'est' if len(noms) == 1 else 'sont'} "
                                 f"{SORTES_MONDE[s][0] if len(noms) == 1 else SORTES_MONDE[s][1]}"
                                 for s, noms in par_sorte.items() if noms)
        return Squelette(
            genre=f"{NOM}.continents", enonce=f"Lequel est le nom d'{SORTES_MONDE[sorte][0]} ?",
            reponse=bon["nom"], distracteurs=tuple(l["nom"] for l in choisis),
            explication=majuscule(explication) + ".", cle=("continents", "nom", sorte), sujet=("continents", bon["nom"]))
    if forme == "est":
        # « L'océan Indien est… » : le mot « océan » donnerait la réponse
        l = rng.choice([x for x in lignes if x["demande"] == "oui" and "océan" not in x["le"]])
        bon = SORTES_MONDE[l["sorte"]][0]
        return Squelette(
            genre=f"{NOM}.continents", enonce=f"{majuscule(l['le'])} est…", reponse=bon,
            distracteurs=tuple(s[0] for s in SORTES_MONDE.values() if s[0] != bon),
            explication=f"{majuscule(l['le'])} est {bon}.", cle=("continents", "est", l["nom"]),
            sujet=("continents", l["nom"]))
    l = rng.choice([x for x in lignes if x["ou"] != "-"])
    autres = [f"en {x['nom']}" for x in lignes if x["sorte"] == "continent" and x["demande"] == "oui"
              and f"en {x['nom']}" != l["ou"]]
    return Squelette(
        genre=f"{NOM}.continents", enonce=f"Sur quel continent se trouve {l['le']} hexagonale ?", reponse=l["ou"],
        distracteurs=_quelques(rng, autres),
        explication=f"{majuscule(l['le'])} hexagonale se trouve {l['ou']}, à l'ouest.",
        cle=("continents", "ou", l["nom"]), sujet=("continents", l["nom"]))


def points_cardinaux(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel point cardinal est à l'opposé du nord ? » → le sud ; « Sur une rose des vents, que veut dire la lettre
    O ? » → l'ouest ; « Lequel est un point cardinal ? » → le nord (à gauche, devant, au-dessus)."""
    t = _table("points_cardinaux")
    points = t.filtrer(sorte="point")
    noms = [p["nom"] for p in points]
    rose = "Sur une rose des vents : " + ", ".join(f"{p['lettre']} pour {p['nom']}" for p in points) + "."
    forme = rng.choice(("oppose", "lettre", "lequel"))
    if forme == "oppose":
        p = rng.choice(points)
        return Squelette(
            genre=f"{NOM}.points_cardinaux", enonce=f"Quel point cardinal est à l'opposé {_du(p['nom'])} ?",
            reponse=p["oppose"], distracteurs=tuple(n for n in noms if n != p["oppose"]),
            explication=(f"Le nord et le sud sont opposés, comme l'est et l'ouest. À l'opposé {_du(p['nom'])}, il y a "
                         f"{p['oppose']}."),
            cle=("points", "oppose", p["nom"]), sujet=("points", tuple(sorted((p["nom"], p["oppose"])))))
    if forme == "lettre":
        p = rng.choice(points)
        return Squelette(
            genre=f"{NOM}.points_cardinaux", enonce=f"Sur une rose des vents, que veut dire la lettre {p['lettre']} ?",
            reponse=p["nom"], distracteurs=tuple(n for n in noms if n != p["nom"]), explication=rose,
            cle=("points", "lettre", p["lettre"]))
    bon = rng.choice(noms)
    pieges = _quelques(rng, [l["nom"] for l in t.filtrer(sorte="position")])
    return Squelette(
        genre=f"{NOM}.points_cardinaux", enonce="Lequel est un point cardinal ?", reponse=bon, distracteurs=pieges,
        explication=(f"Les quatre points cardinaux sont {_liste(noms)}. {_liste([f'« {majuscule(p) if i == 0 else p} »' for i, p in enumerate(pieges)])} disent "
                     "où l'on est par rapport à quelque chose : ce ne sont pas des points cardinaux."),
        cle=("points", "lequel"))


def _verbe(l: dict) -> str:
    return "coule" if l["sorte"] == "fleuve" else "se trouvent" if _pluriel(l["nom"]) else "se trouve"


def lieux(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """Les repères du monde du CE1 : « Où se trouve l'Himalaya ? » → en Asie ; « Lequel est un désert ? » → le
    Sahara ; « Lequel de ces lieux se trouve en Afrique ? » → le Nil. Jamais « le plus long fleuve »."""
    lignes = list(_table("lieux").lignes)
    situes = [l for l in lignes if l["ou"] != "-"]
    forme = rng.choice(("ou", "ou", "sorte", "region"))
    if forme == "ou":
        l = rng.choice(situes)
        return Squelette(
            genre=f"{NOM}.lieux", enonce=f"Où {_verbe(l)} {l['nom']} ?", reponse=l["ou"],
            distracteurs=_quelques(rng, [r for r in REGIONS if r != l["ou"]]),
            explication=f"{majuscule(l['nom'])} {_verbe(l)} {l['ou']}.",
            cle=("lieux", "ou", l["nom"]), sujet=("lieux", l["nom"]))
    if forme == "sorte":
        sorte = rng.choice(tuple(SORTES_LIEUX))
        bon = rng.choice([l for l in lignes if l["sorte"] == sorte])
        choisis = rng.sample([l for l in lignes if l["sorte"] != sorte], 3)
        explication = " ; ".join(f"{l['nom']} {'sont' if _pluriel(l['nom']) else 'est'} {SORTES_LIEUX[l['sorte']]}"
                                 for l in (bon, *choisis))
        return Squelette(
            genre=f"{NOM}.lieux", enonce=f"Lequel est {SORTES_LIEUX[sorte]} ?", reponse=bon["nom"],
            distracteurs=tuple(l["nom"] for l in choisis), explication=majuscule(explication) + ".",
            cle=("lieux", "sorte", sorte))
    region = rng.choice(sorted({l["ou"] for l in situes}))
    bon = rng.choice([l for l in situes if l["ou"] == region])
    choisis = rng.sample([l for l in lignes if l["ou"] != region], 3)
    explication = " ; ".join(f"{l['nom']} {_verbe(l)} {l['ou']}" if l["ou"] != "-"
                             else f"{l['nom']} est un désert, sur le continent du même nom" for l in (bon, *choisis))
    return Squelette(
        genre=f"{NOM}.lieux", enonce=f"Lequel de ces lieux se trouve {region} ?", reponse=bon["nom"],
        distracteurs=tuple(l["nom"] for l in choisis), explication=majuscule(explication) + ".",
        cle=("lieux", "region", region))


def _ensemble(a: dict, b: dict) -> bool:
    """Deux mots qu'on peut proposer ensemble : aucun des deux n'exclut l'autre (`jamais`)."""
    return a["jamais"] != b["mot"] and b["jamais"] != a["mot"]


def _mot(rng: random.Random, sorte: str) -> Squelette:
    """« Une grande étendue plate, c'est… » → une plaine ; « Une plaine, c'est… » → une grande étendue plate. Jamais
    deux mots qu'une même définition pourrait désigner (la plaine et le plateau)."""
    lignes = _table("mots").filtrer(sorte=sorte)
    l = rng.choice(lignes)
    autres = [x for x in lignes if x is not l and _ensemble(l, x)]
    choisis = _quelques(rng, [x["mot"] for x in autres])
    choisies = [x for x in autres if x["mot"] in choisis]
    explication = " ".join(f"{majuscule(x['mot'])} : {x['definition']}." for x in (l, *choisies))
    if rng.random() < 0.5:
        return Squelette(
            genre=f"{NOM}.{sorte}", enonce=f"{majuscule(l['definition'])}, c'est…", reponse=l["mot"],
            distracteurs=tuple(x["mot"] for x in choisies), explication=explication,
            cle=(sorte, "mot", l["mot"]), sujet=(sorte, l["mot"]))
    return Squelette(
        genre=f"{NOM}.{sorte}", enonce=f"{majuscule(l['mot'])}, c'est…", reponse=l["definition"],
        distracteurs=tuple(x["definition"] for x in choisies), explication=explication,
        cle=(sorte, "definition", l["mot"]), sujet=(sorte, l["mot"]))


def relief(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """Montagne, plaine, plateau, vallée : le mot et sa définition."""
    return _mot(rng, "relief")


def vegetation(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """Forêt, prairie, désert : le mot et sa définition."""
    return _mot(rng, "vegetation")


def cours_eau(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """Le fleuve et la rivière : « Un cours d'eau qui se jette dans un autre, c'est… » → une rivière ; « La Saône se
    jette dans le Rhône, un fleuve : c'est… » → une rivière. Un fleuve précis n'est demandé que s'il se jette dans la
    mer ou l'océan (la Seine, « dans la Manche » : un élève ne sait pas que c'est une mer)."""
    mots = _table("mots")
    eaux = {l["mot"]: l for l in mots.filtrer(sorte="cours_eau")}
    fleuve, riviere = eaux["un fleuve"], eaux["une rivière"]
    vallee = next(l for l in mots.filtrer(sorte="relief") if l["mot"] == "une vallée")
    regle = (f"{majuscule(fleuve['mot'])}, c'est {fleuve['definition']} ou l'océan ; "
             f"{riviere['mot']}, {riviere['definition']}.")
    # le fleuve ou la rivière d'abord (une chance sur deux), puis la forme : sinon les fleuves nommés, plus nombreux,
    # l'emportaient (4 questions sur 5 au critère de fin du lot 2)
    l = rng.choice((fleuve, riviere))
    autre = riviere if l is fleuve else fleuve
    equilibre = (l["mot"], (fleuve["mot"], riviere["mot"]))  # autant de fleuves que de rivières, à une près
    forme = rng.choice(("mot", "definition", "nomme", "nomme"))
    if forme in ("mot", "definition"):
        if forme == "mot":
            return Squelette(
                genre=f"{NOM}.cours_eau", enonce=f"{majuscule(l['definition'])}, c'est…", reponse=l["mot"],
                distracteurs=(autre["mot"], vallee["mot"]), explication=regle,
                cle=("cours_eau", "mot", l["mot"]), sujet=("cours_eau", l["mot"]), equilibre=equilibre)
        return Squelette(
            genre=f"{NOM}.cours_eau", enonce=f"{majuscule(l['mot'])}, c'est…", reponse=l["definition"],
            distracteurs=(autre["definition"], vallee["definition"]), explication=regle,
            cle=("cours_eau", "definition", l["mot"]), sujet=("cours_eau", l["mot"]), equilibre=equilibre)
    france = {l["nom"]: l for l in _table("france").lignes}
    sorte = "fleuve" if l is fleuve else "riviere"
    nommes = [x for x in france.values() if x["sorte"] == sorte
              and (("mer" in x["se_jette"] or "océan" in x["se_jette"]) if sorte == "fleuve"
                   else x["se_jette"].removeprefix("dans ") in france)]
    l = rng.choice(nommes)
    if l["sorte"] == "fleuve":
        enonce, bon = f"{majuscule(l['nom'])} se jette {l['se_jette']} : c'est…", fleuve["mot"]
    else:
        receveur = france[l["se_jette"].removeprefix("dans ")]
        if receveur["sorte"] not in ("fleuve", "riviere"):
            raise Retirer("une rivière se jette dans un cours d'eau")
        nature = fleuve["mot"] if receveur["sorte"] == "fleuve" else riviere["mot"]
        enonce, bon = f"{majuscule(l['nom'])} se jette {l['se_jette']}, {nature} : c'est…", riviere["mot"]
    autre = riviere["mot"] if bon == fleuve["mot"] else fleuve["mot"]
    return Squelette(
        genre=f"{NOM}.cours_eau", enonce=enonce, reponse=bon, distracteurs=(autre, vallee["mot"]),
        explication=f"{majuscule(l['nom'])} se jette {l['se_jette']} : c'est {bon}. {regle}",
        cle=("cours_eau", "nomme", l["nom"]), sujet=("cours_eau", l["nom"]), equilibre=equilibre)


def climat(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """Les trois zones climatiques : « Dans la zone tropicale… » → il fait chaud toute l'année ; « Dans quelle zone
    climatique se trouve la Guyane ? » → la zone tropicale ; « Lequel de ces territoires est dans la zone froide ? » →
    la terre Adélie."""
    t = _table("climats")
    zones = {l["zone"]: l for l in t.filtrer(sorte="zone")}
    territoires = t.filtrer(sorte="territoire")
    forme = rng.choice(("climat", "zone", "territoire", "territoire", "lequel"))
    if forme in ("climat", "zone"):
        z = rng.choice(list(zones.values()))
        autres = [x for x in zones.values() if x is not z]
        explication = " ".join(f"Dans {x['nom']}, {x['climat']}." for x in zones.values())
        if forme == "climat":
            return Squelette(
                genre=f"{NOM}.climat", enonce=f"Dans {z['nom']}…", reponse=z["climat"],
                distracteurs=tuple(x["climat"] for x in autres), explication=explication,
                cle=("climat", "climat", z["zone"]), sujet=("climat", z["zone"]))
        return Squelette(
            genre=f"{NOM}.climat", enonce=f"{majuscule(z['climat'])} : dans quelle zone ?", reponse=z["nom"],
            distracteurs=tuple(x["nom"] for x in autres), explication=explication,
            cle=("climat", "zone", z["zone"]), sujet=("climat", z["zone"]))
    if forme == "territoire":
        l = rng.choice(territoires)
        z = zones[l["zone"]]
        return Squelette(
            genre=f"{NOM}.climat", enonce=f"Dans quelle zone climatique se trouve {l['nom']} ?", reponse=z["nom"],
            distracteurs=tuple(x["nom"] for x in zones.values() if x is not z),
            explication=f"{majuscule(l['nom'])} se trouve dans {z['nom']} : {z['climat']}.",
            cle=("climat", "territoire", l["nom"]), sujet=("climat", l["nom"]))
    z = rng.choice(list(zones.values()))
    bon = rng.choice([l for l in territoires if l["zone"] == z["zone"]])
    choisis = _quelques(rng, [l["nom"] for l in territoires if l["zone"] != z["zone"]])
    explication = " ; ".join(f"{l['nom']} : {zones[l['zone']]['nom']}" for l in territoires
                             if l is bon or l["nom"] in choisis)
    return Squelette(
        genre=f"{NOM}.climat", enonce=f"Lequel de ces territoires est dans {z['nom']} ?", reponse=bon["nom"],
        distracteurs=choisis, explication=majuscule(explication) + ".", cle=("climat", "lequel", z["zone"]),
        sujet=("climat", bon["nom"]))


def france(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """Les massifs et les grands fleuves français : « Lequel de ces massifs est en France ? » → les Vosges
    (l'Himalaya, les Andes, l'Atlas) ; « Lequel est un fleuve ? » ; « Quel fleuve passe à Lyon ? » → le Rhône ;
    « Par quelle ville passe la Garonne ? » → Toulouse."""
    lignes = _table("france").lignes
    massifs = [l["nom"] for l in lignes if l["sorte"] == "massif"]
    fleuves = [l["nom"] for l in lignes if l["sorte"] == "fleuve"]
    monde = _table("lieux").lignes
    villes = _table("villes").lignes
    forme = rng.choice(("massif", "fleuve", "nom", "ville", "ville", "ville", "par"))
    if forme in ("massif", "fleuve"):
        sorte_monde = "chaine" if forme == "massif" else "fleuve"
        bon = rng.choice(massifs if forme == "massif" else fleuves)
        ailleurs = [l for l in monde if l["sorte"] == sorte_monde and l["nom"] not in massifs + fleuves]
        choisis = rng.sample(ailleurs, min(3, len(ailleurs)))
        explication = ((f"{majuscule(bon)} {'sont' if _pluriel(bon) else 'est'} en France. " if forme == "massif"
                        else f"{majuscule(bon)} est un des grands fleuves français. ")
                       + majuscule(" ; ".join(f"{l['nom']} {_verbe(l)} {l['ou']}" for l in choisis)) + ".")
        enonce = "Lequel de ces massifs est en France ?" if forme == "massif" else "Lequel est un des grands fleuves français ?"
        return Squelette(
            genre=f"{NOM}.france", enonce=enonce, reponse=bon, distracteurs=tuple(l["nom"] for l in choisis),
            explication=explication, cle=("france", forme))
    if forme == "nom":
        sorte = rng.choice(("massif", "fleuve"))
        bons, autres = (massifs, fleuves) if sorte == "massif" else (fleuves, massifs)
        bon, choisis = rng.choice(bons), rng.sample(autres, 3)
        explication = (f"{majuscule(_liste([n for n in [bon, *choisis] if n in massifs]))} : "
                       f"{'des massifs' if sum(n in massifs for n in [bon, *choisis]) > 1 else 'un massif'} ; "
                       f"{_liste([n for n in [bon, *choisis] if n in fleuves])} : "
                       f"{'des fleuves' if sum(n in fleuves for n in [bon, *choisis]) > 1 else 'un fleuve'}.")
        return Squelette(
            genre=f"{NOM}.france",
            enonce="Lequel est un massif de montagnes ?" if sorte == "massif" else "Lequel est un fleuve ?",
            reponse=bon, distracteurs=tuple(choisis), explication=explication, cle=("france", "nom", sorte))
    if forme == "ville":
        v = rng.choice(villes)
        meme = [x["ville"] for x in villes if x["fleuve"] == v["fleuve"]]
        return Squelette(
            genre=f"{NOM}.france", enonce=f"Quel fleuve passe à {v['ville']} ?", reponse=v["fleuve"],
            distracteurs=_quelques(rng, [f for f in fleuves if f != v["fleuve"]]),
            explication=f"{majuscule(v['fleuve'])} passe à {_liste(meme)}.",
            cle=("france", "ville", v["ville"]), sujet=("france", v["fleuve"]))
    fleuve = rng.choice(sorted({x["fleuve"] for x in villes}))
    bon = rng.choice([x["ville"] for x in villes if x["fleuve"] == fleuve])
    autres = [x for x in villes if x["fleuve"] != fleuve]
    choisies = rng.sample(autres, 3)
    explication = (f"{majuscule(fleuve)} passe à {_liste([x['ville'] for x in villes if x['fleuve'] == fleuve])}. "
                   + majuscule(" ; ".join(f"à {x['ville']} passe {x['fleuve']}" for x in choisies)) + ".")
    return Squelette(
        genre=f"{NOM}.france", enonce=f"Par quelle ville passe {fleuve} ?", reponse=bon,
        distracteurs=tuple(x["ville"] for x in choisies), explication=explication,
        cle=("france", "par", fleuve), sujet=("france", fleuve))


GENRES = (continents, points_cardinaux, lieux, relief, vegetation, cours_eau, climat, france)
CLASSES_DU_GENRE = {"continents": ("CP",), "points_cardinaux": ("CP",), "lieux": ("CE1",), "relief": ("CE1",),
                    "vegetation": ("CE1",), "cours_eau": ("CE1",), "climat": ("CE1",), "france": ("CE2",)}
ATTENDUS = {
    "continents": {"CP": ("histoire-geo.cp.representations-monde.01",)},
    "relief": {"CE1": ("histoire-geo.ce1.lieux-de-vie.03", "histoire-geo.ce1.lieux-de-vie.06")},
    "vegetation": {"CE1": ("histoire-geo.ce1.lieux-de-vie.02", "histoire-geo.ce1.lieux-de-vie.06")},
    "cours_eau": {"CE1": ("histoire-geo.ce1.lieux-de-vie.04",)},
    "climat": {"CE1": ("histoire-geo.ce1.lieux-de-vie.01", "histoire-geo.ce1.lieux-de-vie.06")},
    "france": {"CE2": ("histoire-geo.ce2.repartition-population.04",)},
}
