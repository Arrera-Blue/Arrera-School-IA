"""La conjugaison, du CP au CE2 (lot 1, étape 1.1 : docs/Generateur-Procedural/lot-1-francais.md §3).

Ce que le programme demande, et rien de plus : au CP, être et avoir au présent ; au CE1, le présent, l'imparfait, le
futur et le passé composé de l'indicatif, d'être, d'avoir et des verbes en -er ; au CE2, en plus, faire, aller, dire,
venir, pouvoir, voir, vouloir, prendre. Les formes se lisent dans la table `francais/conjugaisons` (relue par
l'enseignant, chaque forme comparée à Verbiste) ; les mauvaises réponses sont d'autres formes **du même verbe**, prises
dans la table (jamais une forme inventée) ; l'explication sort de la règle (`francais/terminaisons`).
"""

import random

from generateur.procedural import Retirer, Squelette, distracteurs, tables
from generateur.procedural.francais import CYCLE_2, avant_ou_egale

NOM, TITRE, NOTION, NIVEAU = "conjugaison", "La conjugaison", "conjugaison", "CE1"
MATIERE, NIVEAUX = "francais", CYCLE_2  # NIVEAU : la classe par défaut ; NIVEAUX : celles où il s'applique
MOTS_CLES = ("conjugaison", "conjuguer", "conjugue", "present de l'indicatif", "au present", "imparfait", "futur",
             "passe compose", "verbe etre", "verbe avoir", "etre et avoir", "terminaison", "infinitif")
TABLES = ("conjugaisons", "terminaisons")

TEMPS = {"present": ("au présent", "le présent"), "imparfait": ("à l'imparfait", "l'imparfait"),
         "futur": ("au futur", "le futur"), "passe_compose": ("au passé composé", "le passé composé")}
VOYELLES = "aeéèêiîoôuy"
# « elle » et « elles » lisent les lignes de il et ils, sauf au passé composé avec être (allé / allée)
AUSSI = {"il": "elle", "ils": "elles"}


def _table(nom: str) -> tables.Table:
    return tables.charger(MATIERE, nom)


def lignes(niveau: str, **criteres) -> list[dict]:
    """Les lignes de la table des conjugaisons qui servent à cette classe."""
    return [l for l in _table("conjugaisons").filtrer(**criteres) if avant_ou_egale(niveau, l["depuis"])]


def avec_le_pronom(pronom: str, forme: str) -> str:
    """« je » + « aime » → « j'aime » ; « nous » + « chantons » → « nous chantons »."""
    return f"j'{forme}" if pronom == "je" and forme[0] in VOYELLES else f"{pronom} {forme}"


def pronom_du_trou(pronom: str, forme: str) -> str:
    """Le pronom devant le trou de l'énoncé : « j'… » devant une voyelle, « je … » sinon."""
    return "j'…" if pronom == "je" and forme[0] in VOYELLES else f"{pronom} …"


def _pronom(rng: random.Random, ligne: dict) -> str:
    etre = ligne["temps"] == "passe_compose" and ligne["forme"].split()[0] in ("est", "sont")
    if ligne["personne"] in AUSSI and not etre:
        return rng.choice((ligne["personne"], AUSSI[ligne["personne"]]))
    return ligne["personne"]


def _terminaison(temps: str, personne: str) -> str:
    return _table("terminaisons").filtrer(temps=temps, personne=personne)[0]["terminaison"]


def regle(ligne: dict, pronom: str) -> str:
    """La règle qui donne la forme : pour une explication."""
    temps, forme, groupe = ligne["temps"], ligne["forme"], ligne["groupe"]
    ecrite = avec_le_pronom(pronom, forme)
    if temps == "passe_compose":
        auxiliaire, participe = forme.split(" ", 1)
        aux = "être" if auxiliaire in ("est", "sont") else "avoir"
        return (f"Au passé composé, on écrit l'auxiliaire {aux} au présent ({auxiliaire}), puis le participe passé "
                f"{participe} : {ecrite}.")
    if groupe == "1":
        return (f"{TEMPS[temps][0].capitalize()}, avec « {pronom} », les verbes en -er se terminent par "
                f"{_terminaison(temps, ligne['personne'])} : {ecrite}.")
    sorte = "est irrégulier : il s'apprend par cœur" if groupe == "3" else "s'apprend par cœur"
    return f"Le verbe {ligne['infinitif']} {sorte}. {TEMPS[temps][0].capitalize()}, avec « {pronom} » : {ecrite}."


# --- les genres --------------------------------------------------------------------------------------------

def forme(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Complète au présent : nous … (chanter) » → chantons ; les mauvaises réponses : les autres personnes du
    même temps (chante, chantez, chantent : l'erreur la plus fréquente), puis la même personne à un autre temps."""
    ligne = rng.choice(lignes(niveau))
    pronom = _pronom(rng, ligne)
    meme_temps = [l["forme"] for l in lignes(niveau, infinitif=ligne["infinitif"], temps=ligne["temps"])
                  if l["personne"] != ligne["personne"]]
    autres_temps = [l["forme"] for l in lignes(niveau, infinitif=ligne["infinitif"], personne=ligne["personne"])
                    if l["temps"] != ligne["temps"]]
    rng.shuffle(meme_temps)
    rng.shuffle(autres_temps)
    return Squelette(
        genre=f"{NOM}.forme",
        enonce=f"Complète {TEMPS[ligne['temps']][0]} : {pronom_du_trou(pronom, ligne['forme'])} ({ligne['infinitif']})",
        reponse=ligne["forme"],
        distracteurs=distracteurs(ligne["forme"], meme_temps + autres_temps),
        explication=regle(ligne, pronom),
        cle=("forme", ligne["infinitif"], ligne["temps"], pronom),
    )


def temps(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« À quel temps est le verbe : nous chanterons ? » → le futur ; les mauvaises réponses : les trois autres temps.
    Une forme que la même personne écrit pareil à un autre temps serait ambiguë : tirée à nouveau."""
    ligne = rng.choice(lignes(niveau))
    autres = lignes(niveau, infinitif=ligne["infinitif"], personne=ligne["personne"])
    if [l["temps"] for l in autres if l["forme"] == ligne["forme"]] != [ligne["temps"]]:
        raise Retirer("la même forme à deux temps")
    pronom = _pronom(rng, ligne)
    ecrite = avec_le_pronom(pronom, ligne["forme"])
    return Squelette(
        genre=f"{NOM}.temps",
        enonce=f"À quel temps est le verbe : {ecrite} ?",
        reponse=TEMPS[ligne["temps"]][1],
        distracteurs=tuple(TEMPS[t][1] for t in TEMPS if t != ligne["temps"]),
        explication=f"« {ecrite} » est {TEMPS[ligne['temps']][0]}. " + regle(ligne, pronom),
        cle=("temps", ligne["infinitif"], ligne["temps"], ligne["personne"]),
    )


def infinitif(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel est l'infinitif du verbe : ils jouaient ? » → jouer ; les mauvaises réponses : d'autres formes du même
    verbe (joue, jouait, jouons), qui ne sont pas l'infinitif."""
    ligne = rng.choice(lignes(niveau))
    pronom = _pronom(rng, ligne)
    autres = [l["forme"] for l in lignes(niveau, infinitif=ligne["infinitif"]) if l["forme"] != ligne["forme"]]
    rng.shuffle(autres)
    ecrite = avec_le_pronom(pronom, ligne["forme"])
    return Squelette(
        genre=f"{NOM}.infinitif",
        enonce=f"Quel est l'infinitif du verbe : {ecrite} ?",
        reponse=ligne["infinitif"],
        distracteurs=distracteurs(ligne["infinitif"], autres),
        explication=(f"L'infinitif est le nom du verbe, celui du dictionnaire : « {ecrite} » est une forme du verbe "
                     f"{ligne['infinitif']}."),
        cle=("infinitif", ligne["infinitif"], ligne["temps"], ligne["personne"]),
    )


def terminaison(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quelle est la terminaison de : vous chantez ? » → -ez ; verbes en -er, au présent et à l'imparfait (au futur,
    les manuels ne coupent pas tous le mot au même endroit) ; les mauvaises réponses : les terminaisons des autres
    personnes au même temps."""
    temps_ = rng.choice(("present", "imparfait"))
    ligne = rng.choice(lignes(niveau, groupe="1", temps=temps_))
    pronom = _pronom(rng, ligne)
    bonne = _terminaison(temps_, ligne["personne"])
    autres = [t["terminaison"] for t in _table("terminaisons").filtrer(temps=temps_) if t["terminaison"] != bonne]
    rng.shuffle(autres)
    radical = ligne["forme"][: -len(bonne) + 1]
    return Squelette(
        genre=f"{NOM}.terminaison",
        enonce=f"Quelle est la terminaison de : {avec_le_pronom(pronom, ligne['forme'])} ?",
        reponse=bonne,
        distracteurs=distracteurs(bonne, autres),
        explication=f"Le radical est « {radical} », la terminaison {bonne}. " + regle(ligne, pronom),
        cle=("terminaison", ligne["infinitif"], temps_, ligne["personne"]),
    )


GENRES = (forme, temps, infinitif, terminaison)
# au CP, seulement conjuguer être et avoir au présent
CLASSES_DU_GENRE = {"forme": CYCLE_2, "temps": ("CE1", "CE2"), "infinitif": ("CE1", "CE2"),
                    "terminaison": ("CE1", "CE2")}
# les objectifs du programme (francais-cp.yaml…) : conjuguer ; identifier le radical et la terminaison, trouver
# l'infinitif
ATTENDUS = {
    "forme": {"CP": ("francais.cp.orthographe-grammaticale.06",), "CE1": ("francais.ce1.orthographe-grammaticale.04",),
              "CE2": ("francais.ce2.orthographe-grammaticale.03",)},
    "temps": {"CE1": ("francais.ce1.orthographe-grammaticale.04",), "CE2": ("francais.ce2.orthographe-grammaticale.03",)},
    "infinitif": {"CE1": ("francais.ce1.orthographe-grammaticale.03",),
                  "CE2": ("francais.ce2.orthographe-grammaticale.04",)},
    "terminaison": {"CE1": ("francais.ce1.orthographe-grammaticale.03",),
                    "CE2": ("francais.ce2.orthographe-grammaticale.04",)},
}
