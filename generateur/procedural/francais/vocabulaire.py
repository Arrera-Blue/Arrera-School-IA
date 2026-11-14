"""Le vocabulaire, du CP au CE2 (lot 1, étape 1.4 : docs/Generateur-Procedural/lot-1-francais.md §6).

Ce que le programme demande : l'ordre alphabétique (CP vocabulaire.03) ; synonymes et antonymes (CP relations-mots.03 :
les contraires seulement, décision 6) ; les familles de mots et les dérivés par préfixe (CP relations-mots.01, CE1 .04,
CE2 .05) ; les termes génériques (CP .02, CE1 .01, CE2 .02) ; les niveaux de langue (CP reemployer.03, CE1
relations-mots.02, CE2 .03) ; la lettre muette finale par un mot de la même famille (CP et CE1 orthographe-lexicale.04).
L'ordre alphabétique se calcule (sur les noms déjà relus) ; tout le reste se lit dans des tables relues par
l'enseignant, dont les pièges ont été choisis pour n'être jamais justes (Lexique 3, scripts/vocabulaire/).
"""

import random
import unicodedata

from generateur.procedural import Precision, Retirer, Squelette, distracteurs, tables
from generateur.procedural.francais import CYCLE_2, avant_ou_egale

NOM, TITRE, NOTION, NIVEAU = "vocabulaire", "Le vocabulaire", "vocabulaire", "CE1"
MATIERE, NIVEAUX = "francais", CYCLE_2  # NIVEAU : la classe par défaut ; NIVEAUX : celles où il s'applique
MOTS_CLES = ("vocabulaire", "ordre alphabetique", "dictionnaire", "contraire", "antonyme", "famille de mots",
             "familles de mots", "meme famille", "generique", "categorie", "niveau de langue", "niveaux de langue",
             "langage familier", "langage soutenu", "familier", "soutenu", "lettre muette", "lettres muettes",
             "prefixe")
TABLES = ("noms", "contraires", "prefixes", "familles", "lettres_muettes", "categories", "niveaux_de_langue")
# les notions précises, de la plus précise à la plus générale (« les contraires avec un préfixe » : les préfixes seuls)
PRECISIONS = (
    Precision(r"ordre alphabetique|dictionnaire", "l'ordre alphabétique", ("ordre_alphabetique",)),
    Precision(r"lettres? muettes?|lettres? finales?", "les lettres muettes", ("lettre_muette",)),
    Precision(r"contraires? (?:avec|par|grace a) (?:un |des |les )?prefixes?|prefixes?", "les préfixes",
              ("contraire_prefixe",)),
    Precision(r"contraires?|antonymes?", "les contraires", ("contraire", "contraire_prefixe")),
    Precision(r"familles? de mots|meme famille", "les familles de mots", ("famille",)),
    Precision(r"generiques?|categories?", "les mots génériques", ("generique",)),
    Precision(r"niveaux? de langue|registres? de langue|langage (?:familier|courant|soutenu)|\bfamilier|\bsoutenu",
              "les niveaux de langue", ("niveau_de_langue",)),
)

REGISTRES = ("familier", "courant", "soutenu")


def _table(nom: str) -> tables.Table:
    return tables.charger(MATIERE, nom)


def _de_la_classe(nom: str, niveau: str) -> list[dict]:
    return [l for l in _table(nom).lignes if "depuis" not in l or avant_ou_egale(niveau, l["depuis"])]


def cle_alphabetique(mot: str) -> str:
    """« école » se range comme « ecole », « sœur » comme « soeur »."""
    mot = mot.lower().replace("œ", "oe").replace("æ", "ae")
    return "".join(c for c in unicodedata.normalize("NFD", mot) if not unicodedata.combining(c))


# --- les genres --------------------------------------------------------------------------------------------

def ordre_alphabetique(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel mot vient en premier dans l'ordre alphabétique ? » ; au CP, quatre mots aux premières lettres
    différentes ; au CE1 et au CE2, la même première lettre (la deuxième, ou plus loin, décide)."""
    noms = [n["nom"] for n in _de_la_classe("noms", niveau)]
    if niveau == "CP":
        par_initiale: dict[str, list[str]] = {}
        for nom in noms:
            par_initiale.setdefault(cle_alphabetique(nom)[0], []).append(nom)
        initiales = rng.sample(sorted(par_initiale), 4)
        mots = [rng.choice(par_initiale[i]) for i in initiales]
    else:
        initiale = rng.choice(sorted({cle_alphabetique(n)[0] for n in noms}))
        meme = [n for n in noms if cle_alphabetique(n)[0] == initiale]
        if len(meme) < 4:
            raise Retirer("pas assez de mots avec cette initiale")
        mots = rng.sample(meme, 4)
    if len({cle_alphabetique(m) for m in mots}) < 4:
        raise Retirer("deux mots se rangent au même endroit")
    sens = rng.choice(("premier", "dernier"))
    ranges = sorted(mots, key=cle_alphabetique)
    bon = ranges[0] if sens == "premier" else ranges[-1]
    # les mots dans l'énoncé : deux questions d'un exercice n'ont jamais le même (N3 le refuserait)
    enonce = f"Dans l'ordre alphabétique, quel mot vient en {sens} : {', '.join(mots)} ?"
    comment = "la première lettre" if niveau == "CP" else "les lettres une à une, après la première, qui est la même"
    return Squelette(
        genre=f"{NOM}.ordre_alphabetique",
        enonce=enonce,
        reponse=bon,
        distracteurs=tuple(m for m in mots if m != bon),
        explication=(f"On compare {comment} : l'ordre alphabétique est {', '.join(ranges)}. « {bon} » vient en {sens}."),
        cle=("ordre_alphabetique", tuple(sorted(mots)), sens),
    )


def contraire(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel est le contraire de « grand » ? » → petit ; les mauvaises réponses : des mots de la même classe, pris
    dans d'autres champs de sens (jamais un autre mot de la taille, comme « court »)."""
    lignes = _table("contraires").lignes
    l = rng.choice(lignes)
    mot, bon = (l["mot"], l["contraire"]) if rng.random() < 0.5 else (l["contraire"], l["mot"])
    autres = [m for x in lignes if x["classe"] == l["classe"] and x["sens"] != l["sens"]
              for m in (x["mot"], x["contraire"])]
    rng.shuffle(autres)
    if len(autres) < 2:
        raise Retirer("pas assez de mots d'un autre champ")
    return Squelette(
        genre=f"{NOM}.contraire",
        enonce=f"Quel est le contraire de « {mot} » ?",
        reponse=bon,
        distracteurs=distracteurs(bon, autres, min(3, len(autres))),
        explication=f"« {mot} » et « {bon} » ont des sens opposés : ce sont des contraires.",
        cle=("contraire", mot),
        sujet=("contraire", l["mot"]),  # « allumer » puis « éteindre » : la même paire
    )


def contraire_prefixe(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel préfixe donne le contraire de « possible » ? » → im- ; les préfixes pièges ne font aucun vrai mot avec
    « possible » (vérifié avec Lexique 3 à la construction de la table)."""
    l = rng.choice(_de_la_classe("prefixes", niveau))
    regle = {"im-": " (devant p, b ou m, in- s'écrit im-)", "il-": " (devant l, in- s'écrit il-)",
             "ir-": " (devant r, in- s'écrit ir-)"}.get(l["prefixe"], "")
    return Squelette(
        genre=f"{NOM}.contraire_prefixe",
        enonce=f"Quel préfixe donne le contraire de « {l['mot']} » ?",
        reponse=l["prefixe"],
        distracteurs=tuple(l["pieges"].split()),
        explication=(f"{l['prefixe'][:-1]} + {l['mot']} = {l['contraire']} : c'est le contraire de « {l['mot']} »"
                     f"{regle}."),
        cle=("contraire_prefixe", l["mot"]),
    )


def famille(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel mot est de la même famille que « dent » ? » → dentiste ; les pièges lui ressemblent sans en être (danse,
    dinde, dans), écrits à la main."""
    l = rng.choice(_de_la_classe("familles", niveau))
    return Squelette(
        genre=f"{NOM}.famille",
        enonce=f"Quel mot est de la même famille que « {l['mot']} » ?",
        reponse=l["parent"],
        distracteurs=tuple(l["pieges"].split()),
        explication=(f"« {l['parent']} » est de la même famille que « {l['mot']} » : un radical commun et un sens lié. "
                     "Les autres mots lui ressemblent seulement par le son ou l'écriture."),
        cle=("famille", l["mot"]),
    )


def generique(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Lequel de ces mots est un fruit ? » → pomme (trois mots d'autres catégories) ; ou « Pomme, poire, cerise : ce
    sont des… » → fruits (trois autres termes génériques)."""
    lignes = _table("categories").lignes
    par_categorie: dict[str, list[dict]] = {}
    for l in lignes:
        par_categorie.setdefault(l["categorie"], []).append(l)
    categorie = rng.choice(sorted(par_categorie))
    autres = [c for c in sorted(par_categorie) if c != categorie]
    if rng.random() < 0.5:
        bon = rng.choice(par_categorie[categorie])["mot"]
        faux_cat = rng.sample(autres, 3)
        faux = [rng.choice(par_categorie[c])["mot"] for c in faux_cat]
        enonce = f"Lequel de ces mots est un {categorie} ?"
        return Squelette(
            genre=f"{NOM}.generique", enonce=enonce, reponse=bon, distracteurs=tuple(faux),
            explication=(f"« {bon} » est un {categorie}. "
                         + ", ".join(f"« {m} » est un {c}" for m, c in zip(faux, faux_cat)) + "."),
            cle=("generique", enonce))
    exemples = rng.sample(par_categorie[categorie], 3)
    pluriel = exemples[0]["pluriel"]
    noms = [e["mot"] for e in exemples]
    enonce = f"{noms[0].capitalize()}, {noms[1]}, {noms[2]} : ce sont des…"
    return Squelette(
        genre=f"{NOM}.generique", enonce=enonce, reponse=pluriel,
        distracteurs=tuple(par_categorie[c][0]["pluriel"] for c in rng.sample(autres, 3)),
        explication=f"« {pluriel} » est le mot générique : il désigne {', '.join(noms)} et d'autres encore.",
        cle=("generique", enonce))


def niveau_de_langue(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel mot familier veut dire « voiture » ? » → bagnole ; « En classe, on ne dit pas « bagnole » mais : » →
    voiture ; « Quel mot soutenu veut dire « voiture » ? » → automobile (pas au CP : deux niveaux seulement). Une seule
    réponse a le bon sens **et** le bon niveau : les pièges ont le bon sens et un autre niveau (automobile), ou le bon
    niveau et un autre sens (bouquin). Un mot qui a aussi ce sens (la colonne « aussi » : « ouvrage » veut aussi dire
    travail) n'est jamais un piège."""
    trios = _table("niveaux_de_langue").lignes
    trio = rng.choice(trios)
    autres = [t for t in trios if t is not trio]
    rng.shuffle(autres)
    cherche = rng.choice(("familier", "courant") if niveau == "CP" else REGISTRES)
    if cherche == "courant":  # en classe : ni le mot familier du même sens, ni un mot d'un autre sens
        enonce = f"En classe, on ne dit pas « {trio['familier']} » mais :"
        pieges = [t["familier"] for t in autres]
    else:
        enonce = f"Quel mot {cherche} veut dire « {trio['courant']} » ?"
        meme_sens = [] if niveau == "CP" else [trio[r] for r in REGISTRES if r not in (cherche, "courant")]
        pieges = meme_sens + [t[cherche] for t in autres]
    pieges = [p for p in pieges if p not in trio["aussi"].split()]
    bon = trio[cherche]
    niveaux = ("familier", "courant") if niveau == "CP" else REGISTRES
    return Squelette(
        genre=f"{NOM}.niveau_de_langue",
        enonce=enonce,
        reponse=bon,
        distracteurs=distracteurs(bon, pieges),
        # « En classe… » : « laid est le mot courant qui veut dire laid » tournait en rond (critère de fin, 13/11)
        explication=((f"« {trio['familier']} » est un mot familier ; en classe, on dit « {bon} », le mot courant."
                      if cherche == "courant" else f"« {bon} » est le mot {cherche} qui veut dire « {trio['courant']} ».")
                     + " Pour dire la même chose : " + ", ".join(f"« {trio[r]} » ({r})" for r in niveaux) + "."),
        cle=("niveau_de_langue", enonce),
        sujet=("niveau_de_langue", trio["courant"]),  # « boulot » puis « labeur » : le même sens
    )


def lettre_muette(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Pense à « chaton » : quelle lettre muette finit « cha… » ? » → t ; les lettres pièges ne font aucun vrai mot
    (« chas » existe : s n'est jamais proposé pour chat)."""
    l = rng.choice(_de_la_classe("lettres_muettes", niveau))
    return Squelette(
        genre=f"{NOM}.lettre_muette",
        enonce=f"Pense à « {l['famille']} » : quelle lettre muette finit « {l['mot'][:-1]}… » ?",
        reponse=l["lettre"],
        distracteurs=tuple(l["pieges"].split()),
        explication=(f"On entend le « {l['lettre']} » dans « {l['famille']} » : on l'écrit à la fin de « {l['mot']} », "
                     "même si on ne l'entend pas."),
        cle=("lettre_muette", l["mot"]),
    )


GENRES = (ordre_alphabetique, contraire, contraire_prefixe, famille, generique, niveau_de_langue, lettre_muette)
CLASSES_DU_GENRE = {"ordre_alphabetique": CYCLE_2, "contraire": CYCLE_2, "contraire_prefixe": ("CE1", "CE2"),
                    "famille": CYCLE_2, "generique": CYCLE_2, "niveau_de_langue": CYCLE_2,
                    "lettre_muette": ("CP", "CE1")}
ATTENDUS = {
    "ordre_alphabetique": {"CP": ("francais.cp.vocabulaire.03",)},
    "contraire": {"CP": ("francais.cp.relations-mots.03",)},
    "contraire_prefixe": {"CE1": ("francais.ce1.relations-mots.04",), "CE2": ("francais.ce2.relations-mots.05",)},
    "famille": {"CP": ("francais.cp.relations-mots.01",), "CE1": ("francais.ce1.relations-mots.04",),
                "CE2": ("francais.ce2.relations-mots.05",)},
    "generique": {"CP": ("francais.cp.relations-mots.02",), "CE1": ("francais.ce1.relations-mots.01",),
                  "CE2": ("francais.ce2.relations-mots.02",)},
    "niveau_de_langue": {"CP": ("francais.cp.reemployer.03",), "CE1": ("francais.ce1.relations-mots.02",),
                         "CE2": ("francais.ce2.relations-mots.03", "francais.ce2.reemployer.03")},
    "lettre_muette": {"CP": ("francais.cp.orthographe-lexicale.04",), "CE1": ("francais.ce1.orthographe-lexicale.04",)},
}
