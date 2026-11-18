"""La matière et les objets, du CP au CE2 (lot 2, étape 2.3 : docs/Generateur-Procedural/lot-2-questionner-le-monde.md
§8). Le programme de sciences et technologie de 2026 : au CP, l'état de l'eau dans la nature, l'objet technique ; au
CE1, les changements d'état (leur nom, la masse qui ne change pas, la glace qui prend plus de place), les conducteurs
et les isolants, le circuit à une boucle, les objets électriques ; au CE2, les solides et les liquides, l'ordinateur
(saisir, traiter, restituer), les grammes et les kilogrammes (un calcul).

Tout le reste se lit dans huit tables relues par l'enseignant (donnees/sciences-et-technologie/), en monde fermé. Un
fait discuté n'est jamais demandé : l'eau d'un nuage ou du brouillard (des gouttelettes, parfois de la glace), la
mine du crayon (elle conduit le courant), l'eau « isolante » (elle conduit dès qu'elle a des impuretés), le sable
(un solide qui s'écoule).
"""

import random
import re

from generateur.procedural import Precision, Retirer, Squelette, distracteurs, tables
from generateur.procedural.sciences_et_technologie import CYCLE_2
from generateur.procedural.sciences_et_technologie.vivant import majuscule

NOM, TITRE, NOTION, NIVEAU = "matiere", "La matière et les objets", "la matière et les objets", "CE1"
MATIERE, NIVEAUX = "sciences-et-technologie", CYCLE_2  # NIVEAU : la classe par défaut ; NIVEAUX : celles où il s'applique
MOTS_CLES = ("etat de l'eau", "etats de l'eau", "etat physique", "etats physiques", "etats de la matiere", "solide",
             "liquide", "glace", "fusion", "solidification", "changement d'etat", "changements d'etat", "conducteur",
             "isolant", "electricite", "electrique", "circuit", "ampoule", "interrupteur", "objet technique",
             "objets techniques", "ordinateur", "clavier", "informatique", "masse", "gramme", "la matiere", "materiau")
TABLES = ("etats_eau", "changements", "conservation", "materiaux", "circuit", "objets", "solides_liquides",
          "ordinateur")
# les notions précises, de la plus précise à la plus générale (« la masse de l'eau qui gèle » avant « les masses »,
# « les objets électriques » avant « l'électricité » et « les objets techniques »)
PRECISIONS = (
    Precision(r"conservation|(?:masse|volume) (?:de l'eau|de la glace)(?: qui (?:gele|fond))?|prend plus de place",
              "la masse et le volume de l'eau", ("conservation",)),
    Precision(r"changements? d'etat|fusion|solidification|fondre|\bfond\b|geler|\bgele\b|congel",
              "les changements d'état", ("changement_etat", "conservation")),
    Precision(r"masses?\b|grammes?|kilogrammes?|\bkg\b|unites? de masse", "les masses", ("masses",)),
    Precision(r"etats? (?:physiques? )?(?:de l'eau|de la matiere)|etats? physiques?|solides?|liquides?|forme propre|"
              r"glace|neige|grele|banquise|glacier",
              "les états de la matière", ("etat_eau", "changement_etat", "conservation", "solide_liquide")),
    Precision(r"objets? (?:techniques? )?electriques?|energie electrique|fonctionnent? (?:a|avec) l'electricite",
              "les objets électriques", ("objet_electrique",)),
    Precision(r"(?:conducteurs?|isolants?)(?: electriques?)?", "conducteurs et isolants", ("conducteur",)),
    Precision(r"circuits?(?: electriques?)?|ampoules?|interrupteurs?|\bpiles?\b", "le circuit électrique", ("circuit",)),
    Precision(r"electri", "l'électricité", ("conducteur", "circuit")),
    Precision(r"ordinateurs?|informatique|clavier|ecran|processeur|numerique|saisie|restitution", "l'ordinateur",
              ("ordinateur",)),
    Precision(r"objets? techniques?|objets? fabriques?", "les objets techniques",
              ("objet_technique", "objet_electrique", "ordinateur")),
)
MOTS_MAX = 12  # un énoncé qui cite ses propositions reste court
# « (1 kg = 1 000 g) » (Wikipédia, « Gramme ») ; « L'élève réalise des conversions entre les unités gramme et
# kilogramme. » (programme du CE2)
GRAMMES_PAR_KILOGRAMME = 1000
ROLES = {"saisir": "à saisir des informations", "traiter": "à traiter les informations",
         "restituer": "à restituer les informations"}
VALEURS = {"masse": ("ne change pas", "augmente", "diminue"), "place": ("plus de place", "moins de place", "autant de place")}


def _table(nom: str) -> tables.Table:
    return tables.charger(MATIERE, nom)


def nu(nom: str) -> str:
    """Sans son article : « la grêle » → « grêle » ; « l'océan » → « océan » ; « une branche d'arbre » → « branche
    d'arbre »."""
    return re.sub(r"^(?:le |la |les |l'|un |une |des )", "", nom)


def _liste(mots: list[str]) -> str:
    """« a, b et c »."""
    return mots[0] if len(mots) == 1 else f"{', '.join(mots[:-1])} et {mots[-1]}"


def _accord(nom: str, singulier: str, pluriel: str) -> str:
    """Le verbe accordé à son sujet : « des lunettes fonctionnent », « un tournevis fonctionne »."""
    return pluriel if nom.startswith(("les ", "des ")) else singulier


def _mots(texte: str) -> int:
    return len([t for t in texte.split() if re.search(r"\w", t)])


def _citer(rng: random.Random, debut: str, bon: str, faux: list[str]) -> tuple[str, frozenset]:
    """« Où l'eau est-elle solide : pluie, mer, neige, lac ? » : les propositions dans l'énoncé, dans le désordre (deux
    questions n'ont jamais le même) ; trop long pour 12 mots : on tire à nouveau."""
    noms = [bon, *faux]
    enonce = f"{debut} : {', '.join(rng.sample(noms, len(noms)))} ?"
    if _mots(enonce) > MOTS_MAX:
        raise Retirer("énoncé trop long")
    return enonce, frozenset(noms)


def _question_ecrite(nom_genre: str, l: dict) -> Squelette:
    """Une ligne d'une table de questions écrites (le circuit) : sa question, sa réponse, ses mauvaises réponses."""
    faux = [f.strip() for f in l["faux"].split(";")]
    return Squelette(genre=f"{NOM}.{nom_genre}", enonce=l["question"], reponse=l["reponse"],
                     distracteurs=distracteurs(l["reponse"], faux, nombre=len(faux)), explication=l["explication"],
                     cle=(nom_genre, l["question"]), sujet=(nom_genre, l["sujet"]))


# --- CP : l'eau dans la nature, l'objet technique ------------------------------------------------------------

def etat_eau(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Où l'eau est-elle solide : pluie, mer, neige, lac ? » → neige (jamais le nuage ni le brouillard)."""
    lignes = _table("etats_eau").lignes
    etat = rng.choice(("solide", "liquide"))
    autre = "liquide" if etat == "solide" else "solide"
    bon = rng.choice([l for l in lignes if l["etat"] == etat])
    faux = rng.sample([l for l in lignes if l["etat"] == autre], 3)
    enonce, noms = _citer(rng, f"Où l'eau est-elle {etat}", nu(bon["nom"]), [nu(f["nom"]) for f in faux])
    return Squelette(
        genre=f"{NOM}.etat_eau", enonce=enonce, reponse=nu(bon["nom"]), distracteurs=tuple(nu(f["nom"]) for f in faux),
        explication=(f"Dans {bon['nom']}, l'eau est {etat}. "
                     f"Dans {_liste([f['nom'] for f in faux])}, l'eau est {autre}."),
        cle=("etat_eau", etat, noms))


def objet_technique(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Lequel est un objet technique : stylo, galet, branche d'arbre, feuille d'arbre ? » → stylo ; « Lequel n'est
    pas un objet technique : … ? » (les exemples du programme)."""
    lignes = [l for l in _table("objets").lignes if l["electrique"] == "-"]
    techniques = [l["objet"] for l in lignes if l["technique"] == "oui"]
    naturels = [l["objet"] for l in lignes if l["technique"] == "non"]
    if rng.random() < 0.6:
        bon, faux = rng.choice(techniques), rng.sample(naturels, 3)
        enonce, noms = _citer(rng, "Lequel est un objet technique", nu(bon), [nu(f) for f in faux])
        explication = (f"{majuscule(bon)} est un objet technique : un objet obtenu par intervention humaine. "
                       f"{majuscule(_liste(faux))} sont des objets naturels.")
        forme = "technique"
    else:
        bon, faux = rng.choice(naturels), rng.sample(techniques, 3)
        enonce, noms = _citer(rng, "Lequel n'est pas un objet technique", nu(bon), [nu(f) for f in faux])
        explication = (f"{majuscule(bon)} est un objet naturel. {majuscule(_liste(faux))} sont des objets techniques : "
                       "des objets obtenus par intervention humaine.")
        forme = "naturel"
    return Squelette(genre=f"{NOM}.objet_technique", enonce=enonce, reponse=nu(bon),
                     distracteurs=tuple(nu(f) for f in faux), explication=explication,
                     cle=("objet_technique", forme, noms))


# --- CE1 : les changements d'état, l'électricité, les objets électriques -------------------------------------

def changement_etat(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quand la glace fond, comment s'appelle ce changement d'état ? » → la fusion (jamais « la fonte » parmi les
    mauvaises réponses : la fonte des glaces est une fusion)."""
    lignes = _table("changements").lignes
    l = rng.choice([x for x in lignes if x["sorte"] == "changement"])
    faux = [x["nom"] for x in lignes if x is not l and x["proche"] != l["nom"]]
    rng.shuffle(faux)
    forme = rng.choice(("quand", "passage", "devient"))
    enonce = {"quand": f"Quand {l['quand']}, comment s'appelle ce changement d'état ?",
              "passage": f"Comment s'appelle le passage de l'état {l['de']} à l'état {l['vers']} ?",
              "devient": f"L'eau {l['de']} devient {l['vers']} : comment s'appelle ce changement ?"}[forme]
    return Squelette(
        genre=f"{NOM}.changement_etat", enonce=enonce, reponse=l["nom"], distracteurs=tuple(faux),
        explication=(f"Quand {l['quand']}, l'eau passe de l'état {l['de']} à l'état {l['vers']} : "
                     f"ce changement d'état s'appelle {l['nom']}."),
        cle=("changement_etat", forme, l["nom"]), sujet=("changement_etat", l["nom"]))


def conservation(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quand l'eau gèle, sa masse… » → ne change pas ; « Quand l'eau gèle, elle prend… » → plus de place."""
    l = rng.choice(_table("conservation").lignes)
    if l["grandeur"] == "masse":
        enonce = f"Quand {l['quand']}, sa masse…"
        explication = (f"Quand {l['quand']}, sa masse ne change pas : on le constate en pesant l'eau avant et après "
                       "le changement d'état.")
    else:
        enonce = f"Quand {l['quand']}, " + ("elle prend…" if l["quand"] == "l'eau gèle" else "l'eau obtenue prend…")
        explication = (f"Quand {l['quand']}, " + ("elle" if l["quand"] == "l'eau gèle" else "l'eau obtenue")
                       + f" prend {l['valeur']} : la glace prend plus de place que la même masse d'eau liquide.")
    return Squelette(genre=f"{NOM}.conservation", enonce=enonce, reponse=l["valeur"],
                     distracteurs=tuple(v for v in VALEURS[l["grandeur"]] if v != l["valeur"]), explication=explication,
                     cle=("conservation", l["quand"], l["grandeur"]), sujet=("conservation", l["grandeur"]))


def conducteur(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Quel matériau laisse passer le courant : verre, fer, papier, plastique ? » → fer ; « Quel matériau est un
    isolant électrique : … ? » (jamais la mine du crayon, ni l'eau)."""
    lignes = _table("materiaux").lignes
    nature = rng.choice(("conducteur", "isolant"))
    autre = "isolant" if nature == "conducteur" else "conducteur"
    bon = rng.choice([l["materiau"] for l in lignes if l["nature"] == nature])
    faux = rng.sample([l["materiau"] for l in lignes if l["nature"] == autre], 3)
    debut = "Quel matériau laisse passer le courant" if nature == "conducteur" else "Quel matériau est un isolant électrique"
    enonce, noms = _citer(rng, debut, nu(bon), [nu(f) for f in faux])
    explication = {"conducteur": f"{majuscule(bon)} est un conducteur : il laisse passer le courant électrique. "
                                 f"{majuscule(_liste(faux))} sont des isolants : ils ne le laissent pas passer.",
                   "isolant": f"{majuscule(bon)} est un isolant : il ne laisse pas passer le courant électrique. "
                              f"{majuscule(_liste(faux))} sont des conducteurs : ils le laissent passer."}[nature]
    return Squelette(genre=f"{NOM}.conducteur", enonce=enonce, reponse=nu(bon), distracteurs=tuple(nu(f) for f in faux),
                     explication=explication, cle=("conducteur", nature, noms))


def circuit(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Dans un circuit électrique, quel élément est le générateur ? » → la pile ; « L'interrupteur est ouvert :
    l'ampoule… » → reste éteinte (une table de questions écrites, tirées du programme)."""
    return _question_ecrite("circuit", rng.choice(_table("circuit").lignes))


def objet_electrique(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Lequel utilise l'énergie électrique : lunettes, tournevis, ordinateur, batteur manuel ? » → ordinateur ;
    « Quel objet électrique fait le même travail qu'un tournevis ? » → une visseuse électrique."""
    lignes = [l for l in _table("objets").lignes if l["electrique"] != "-"]
    oui = [l["objet"] for l in lignes if l["electrique"] == "oui"]
    non = [l["objet"] for l in lignes if l["electrique"] == "non"]
    forme = rng.choice(("utilise", "utilise", "sans", "jumeau"))
    if forme == "jumeau":
        l = rng.choice([x for x in lignes if x["jumeau"] != "-"])
        faux = rng.sample([o for o in oui if o != l["jumeau"]], 3)
        return Squelette(
            genre=f"{NOM}.objet_electrique", enonce=f"Quel objet électrique fait le même travail qu'{l['objet']} ?",
            reponse=l["jumeau"], distracteurs=tuple(faux),
            explication=f"{majuscule(l['jumeau'])} fait le même travail qu'{l['objet']}, avec l'énergie électrique.",
            cle=("objet_electrique", "jumeau", l["objet"]))
    if forme == "utilise":
        bon, faux = rng.choice(oui), rng.sample(non, 3)
        enonce, noms = _citer(rng, "Lequel utilise l'énergie électrique", nu(bon), [nu(f) for f in faux])
        explication = (f"{majuscule(bon)} {_accord(bon, 'utilise', 'utilisent')} l'énergie électrique pour fonctionner. "
                       f"{majuscule(_liste(faux))} fonctionnent sans énergie électrique.")
    else:
        bon, faux = rng.choice(non), rng.sample(oui, 3)
        enonce, noms = _citer(rng, "Lequel fonctionne sans énergie électrique", nu(bon), [nu(f) for f in faux])
        explication = (f"{majuscule(bon)} {_accord(bon, 'fonctionne', 'fonctionnent')} sans énergie électrique. "
                       f"{majuscule(_liste(faux))} utilisent l'énergie électrique pour fonctionner.")
    return Squelette(genre=f"{NOM}.objet_electrique", enonce=enonce, reponse=nu(bon),
                     distracteurs=tuple(nu(f) for f in faux), explication=explication,
                     cle=("objet_electrique", forme, noms))


# --- CE2 : les solides et les liquides, l'ordinateur, les masses -----------------------------------------------

def solide_liquide(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« Lequel est un liquide : lait, fer, glace, verre ? » → lait ; « Un solide a… » → une forme propre et un volume
    propre ; « La surface d'un liquide au repos est… » → horizontale."""
    lignes = _table("solides_liquides").lignes
    par = {s: [l for l in lignes if l["sorte"] == s] for s in ("exemple", "propriete", "surface", "piege_propriete",
                                                                  "piege_surface")}
    proprietes = {l["etat"]: l["element"] for l in par["propriete"]}
    definition = (f"un solide a {proprietes['solide']} ; un liquide a {proprietes['liquide']} : "
                  "il prend la forme de son récipient")
    forme = rng.choice(("exemple", "exemple", "propriete", "surface"))
    if forme == "exemple":
        etat = rng.choice(("solide", "liquide"))
        autre = "liquide" if etat == "solide" else "solide"
        bon = rng.choice([l["element"] for l in par["exemple"] if l["etat"] == etat])
        faux = rng.sample([l["element"] for l in par["exemple"] if l["etat"] == autre], 3)
        enonce, noms = _citer(rng, f"Lequel est un {etat}", nu(bon), [nu(f) for f in faux])
        return Squelette(
            genre=f"{NOM}.solide_liquide", enonce=enonce, reponse=nu(bon), distracteurs=tuple(nu(f) for f in faux),
            explication=(f"{majuscule(bon)} est un {etat} ; {_liste(faux)} sont des {autre}s. "
                         f"{majuscule(definition)}."),
            cle=("solide_liquide", etat, noms))
    if forme == "propriete":
        etat = rng.choice(("solide", "liquide"))
        autre = "liquide" if etat == "solide" else "solide"
        return Squelette(
            genre=f"{NOM}.solide_liquide", enonce=f"Un {etat} a…", reponse=proprietes[etat],
            distracteurs=(proprietes[autre], *(l["element"] for l in par["piege_propriete"])),
            explication=f"{majuscule(definition)}.", cle=("solide_liquide", "propriete", etat),
            sujet=("solide_liquide", "propriete"))
    bon = par["surface"][0]["element"]
    return Squelette(genre=f"{NOM}.solide_liquide", enonce="La surface d'un liquide au repos est…", reponse=bon,
                     distracteurs=tuple(l["element"] for l in par["piege_surface"]),
                     explication=f"La surface d'un liquide au repos est {bon}.", cle=("solide_liquide", "surface"))


def ordinateur(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """« À quoi sert le clavier ? » → à saisir des informations ; « Lequel sert à traiter les informations : écran,
    processeur, souris, imprimante ? » → processeur (saisir, traiter, restituer : les mots du programme)."""
    lignes = _table("ordinateur").lignes

    def sert(element: str) -> str:
        return "servent" if element.startswith("les ") else "sert"

    if rng.random() < 0.6:
        l = rng.choice(lignes)
        return Squelette(
            genre=f"{NOM}.ordinateur", enonce=f"À quoi {sert(l['element'])} {l['element']} ?", reponse=ROLES[l["role"]],
            distracteurs=tuple(r for k, r in ROLES.items() if k != l["role"]),
            explication=f"{majuscule(l['element'])} {sert(l['element'])} {ROLES[l['role']]}.",
            cle=("ordinateur", "sert", l["element"]), sujet=("ordinateur", l["element"]))
    role = rng.choice(list(ROLES))
    bon = rng.choice([l for l in lignes if l["role"] == role])
    faux = rng.sample([l for l in lignes if l["role"] != role], 3)
    enonce, noms = _citer(rng, f"Lequel sert {ROLES[role]}", nu(bon["element"]), [nu(f["element"]) for f in faux])
    return Squelette(
        genre=f"{NOM}.ordinateur", enonce=enonce, reponse=nu(bon["element"]),
        distracteurs=tuple(nu(f["element"]) for f in faux),
        explication=(f"{majuscule(bon['element'])} {sert(bon['element'])} {ROLES[role]}. "
                     + majuscule(" ; ".join(f"{f['element']} {sert(f['element'])} {ROLES[f['role']]}" for f in faux))
                     + "."),
        cle=("ordinateur", "lequel", noms))


def nombre(n: int) -> str:
    """3000 → « 3 000 » (une espace fine insécable entre les milliers, comme à l'école)."""
    return f"{n:,}".replace(",", " ")


def unite(n: int, mot: str) -> str:
    """« 1 kilogramme », « 3 000 grammes »."""
    return f"{nombre(n)} {mot}{'s' if n > 1 else ''}"


def masses(rng: random.Random, niveau: str = NIVEAU) -> Squelette:
    """Un calcul : « Combien de grammes font 3 kilogrammes ? » → 3 000 grammes (les erreurs : ×100, ×10, ×10 000) ;
    « Combien de kilogrammes font 4 000 grammes ? » ; « Combien de grammes font 2 kilogrammes et 50 grammes ? » →
    2 050 grammes (les erreurs : 2 500, 250, 20 050)."""
    g = GRAMMES_PAR_KILOGRAMME
    regle = f"1 kilogramme = {unite(g, 'gramme')}"
    forme = rng.choice(("kg_en_g", "g_en_kg", "mixte"))
    if forme == "kg_en_g":
        n = rng.randint(1, 9)
        reponse, candidats = unite(n * g, "gramme"), [unite(n * f, "gramme") for f in (100, 10, 10 * g, 1)]
        enonce = f"Combien de grammes {'fait' if n == 1 else 'font'} {unite(n, 'kilogramme')} ?"
        explication = f"{regle}, donc {unite(n, 'kilogramme')} = {reponse}."
        cle = ("masses", forme, n)
    elif forme == "g_en_kg":
        n = rng.randint(2, 9)
        reponse, candidats = unite(n, "kilogramme"), [unite(n * f, "kilogramme") for f in (10, 100, g)]
        enonce = f"Combien de kilogrammes font {unite(n * g, 'gramme')} ?"
        explication = f"{regle}, donc {unite(n * g, 'gramme')} = {reponse}."
        cle = ("masses", forme, n)
    else:
        a, b = rng.randint(1, 5), rng.choice((5, 50, 80, 250, 300, 500, 750))
        total = a * g + b
        reponse = unite(total, "gramme")
        candidats = [unite(x, "gramme") for x in (int(f"{a}{b}"), a * 100 + b, a * g + b * 10, a * 10 * g + b)]
        enonce = f"Combien de grammes font {unite(a, 'kilogramme')} et {unite(b, 'gramme')} ?"
        explication = f"{regle}, donc {unite(a, 'kilogramme')} = {unite(a * g, 'gramme')} ; {nombre(a * g)} + {b} = {nombre(total)}."
        cle = ("masses", forme, a, b)
    rng.shuffle(candidats)
    return Squelette(genre=f"{NOM}.masses", enonce=enonce, reponse=reponse, distracteurs=distracteurs(reponse, candidats),
                     explication=explication, cle=cle)


GENRES = (etat_eau, objet_technique, changement_etat, conservation, conducteur, circuit, objet_electrique,
          solide_liquide, ordinateur, masses)
CLASSES_DU_GENRE = {"etat_eau": ("CP",), "objet_technique": ("CP",), "changement_etat": ("CE1",),
                    "conservation": ("CE1",), "conducteur": ("CE1",), "circuit": ("CE1",), "objet_electrique": ("CE1",),
                    "solide_liquide": ("CE2",), "ordinateur": ("CE2",), "masses": ("CE2",)}
S = "sciences-et-technologie"
ATTENDUS = {
    "etat_eau": {"CP": (f"{S}.cp.etats-matiere.01",)},
    "objet_technique": {"CP": (f"{S}.cp.objets-techniques.01",)},
    "changement_etat": {"CE1": (f"{S}.ce1.etats-matiere.02",)},
    "conservation": {"CE1": (f"{S}.ce1.etats-matiere.03", f"{S}.ce1.etats-matiere.04")},
    "conducteur": {"CE1": (f"{S}.ce1.electricite.02",)},
    "circuit": {"CE1": (f"{S}.ce1.electricite.01",)},
    "objet_electrique": {"CE1": (f"{S}.ce1.objets-techniques.02",)},
    "solide_liquide": {"CE2": (f"{S}.ce2.etats-matiere.01",)},
    "ordinateur": {"CE2": (f"{S}.ce2.objets-techniques.01",)},
    "masses": {"CE2": (f"{S}.ce2.masse-volumes-temps.01",)},
}
