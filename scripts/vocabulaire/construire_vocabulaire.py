"""Les tables du vocabulaire (lot 1, étape 1.4 : docs/Generateur-Procedural/lot-1-francais.md §6), écrites à la main
par Claude :

- `contraires` : des paires de contraires (grand/petit, entrer/sortir…), leur classe, leur **champ de sens** (taille,
  température…) : les mauvaises réponses viennent d'un autre champ (« triste » n'est jamais proposé contre
  « content ») ;
- `prefixes` : un mot, le préfixe qui fait son contraire (im- + possible), et **les préfixes pièges** : seulement ceux
  qui ne font aucun vrai mot selon Lexique 3 (« impropre » existe : im- n'est pas proposé pour « propre ») ;
- `familles` : un mot, un mot de sa famille (dent, dentiste), et des pièges qui lui ressemblent sans en être (danse,
  dinde, dans), écrits à la main ;
- `lettres_muettes` : un mot, sa lettre muette finale, le mot de la famille qui la fait entendre (chat, t, chaton), et
  **les lettres pièges** : seulement celles qui ne font aucun vrai mot (« chas » existe : s n'est pas proposé) ;
- `categories` : des mots rangés sous un terme générique (pomme : un fruit), un seul pour chaque mot ;
- `niveaux_de_langue` : des trios familier, courant, soutenu (bagnole, voiture, automobile).

Usage : python -I construire_vocabulaire.py <Lexique383.tsv> <generateur/procedural/donnees>
(Lexique 3.83 sert à choisir les pièges qui ne sont pas de vrais mots ; puis verifier_vocabulaire.py.)"""
import csv
import sys
from pathlib import Path

import yaml

# classe : {champ de sens : [(mot, contraire, depuis)…]}
CONTRAIRES = {
    "adjectif": {
        "taille": [("grand", "petit"), ("haut", "bas"), ("long", "court"), ("gros", "mince")],
        "température": [("chaud", "froid")], "poids": [("lourd", "léger")], "vitesse": [("rapide", "lent")],
        "âge": [("jeune", "vieux")], "propreté": [("propre", "sale")], "contenance": [("plein", "vide")],
        "ouverture": [("ouvert", "fermé")], "caractère": [("gentil", "méchant")], "humeur": [("joyeux", "triste")],
        "force": [("fort", "faible")], "dureté": [("dur", "mou")], "difficulté": [("facile", "difficile")],
        "lumière": [("clair", "sombre")], "richesse": [("riche", "pauvre")], "beauté": [("beau", "laid")],
        "humidité": [("sec", "mouillé")],
    },
    "verbe": {
        "direction": [("entrer", "sortir"), ("monter", "descendre")], "ouverture": [("ouvrir", "fermer")],
        "lumière": [("allumer", "éteindre")], "sentiment": [("aimer", "détester")], "jeu": [("gagner", "perdre")],
        "émotion": [("rire", "pleurer")], "échange": [("donner", "recevoir")], "commerce": [("acheter", "vendre")],
    },
    "nom": {"moment": [("jour", "nuit"), ("matin", "soir")], "durée": [("début", "fin")]},
    "adverbe": {
        "position": [("devant", "derrière"), ("dessus", "dessous"), ("dedans", "dehors")],
        "distance": [("loin", "près")], "moment": [("tôt", "tard"), ("avant", "après")],
        "fréquence": [("toujours", "jamais")], "quantité": [("beaucoup", "peu")],
    },
}
# mot : (préfixe, contraire, depuis) ; les préfixes pièges sont calculés avec Lexique
PREFIXES = {
    "possible": ("im-", "impossible", "CE1"), "patient": ("im-", "impatient", "CE1"), "poli": ("im-", "impoli", "CE1"),
    "juste": ("in-", "injuste", "CE1"), "utile": ("in-", "inutile", "CE1"), "connu": ("in-", "inconnu", "CE1"),
    "visible": ("in-", "invisible", "CE1"), "capable": ("in-", "incapable", "CE1"),
    "lisible": ("il-", "illisible", "CE2"), "régulier": ("ir-", "irrégulier", "CE2"),
    "faire": ("dé-", "défaire", "CE1"), "coller": ("dé-", "décoller", "CE1"), "plier": ("dé-", "déplier", "CE1"),
    "boucher": ("dé-", "déboucher", "CE1"), "habiller": ("dés-", "déshabiller", "CE1"),
    "heureux": ("mal-", "malheureux", "CE1"), "adroit": ("mal-", "maladroit", "CE2"),
    "honnête": ("mal-", "malhonnête", "CE2"), "propre": ("mal-", "malpropre", "CE2"),
    "content": ("mé-", "mécontent", "CE1"),
}
TOUS_PREFIXES = ("in-", "im-", "il-", "ir-", "dé-", "dés-", "mal-", "mé-")
# mot : (mot de la famille, pièges qui lui ressemblent sans en être, depuis)
FAMILLES = {
    "dent": ("dentiste", ("danse", "dinde", "dans"), "CP"), "fleur": ("fleuriste", ("flamme", "flûte", "fleuve"), "CP"),
    "lait": ("laitier", ("laine", "lettre", "laid"), "CP"), "jardin": ("jardinier", ("jambon", "jaune", "garçon"), "CP"),
    "chant": ("chanteur", ("champ", "chance", "chameau"), "CP"), "glace": ("glacier", ("glisser", "grâce", "place"), "CP"),
    "neige": ("neiger", ("nez", "nage", "nièce"), "CP"), "ami": ("amitié", ("amande", "ampoule", "ambulance"), "CP"),
    "école": ("écolier", ("échelle", "écureuil", "éclair"), "CP"), "terre": ("terrier", ("tarte", "tête", "terrible"), "CE1"),
    "mer": ("marin", ("mère", "maire", "merci"), "CE1"), "boulanger": ("boulangerie", ("boule", "boulon", "bouleau"), "CE1"),
    "lent": ("lentement", ("lentille", "lampe", "lion"), "CE1"), "froid": ("refroidir", ("fraise", "frère", "froisser"), "CE1"),
    "cheval": ("chevalier", ("cheveu", "chèvre", "chevreuil"), "CE1"), "long": ("longueur", ("loup", "lourd", "louche"), "CE1"),
    "sel": ("salière", ("selle", "sale", "seul"), "CE2"), "livre": ("livret", ("lièvre", "ligne", "lime"), "CE2"),
    # ajoutés pour le CP (un objectif seul : 15 questions différentes)
    "chat": ("chaton", ("château", "chapeau", "chance"), "CP"), "nuage": ("nuageux", ("nager", "neige", "nouveau"), "CP"),
    "soleil": ("ensoleillé", ("sommeil", "solide", "sorcier"), "CP"), "jour": ("journée", ("jouer", "joue", "jouet"), "CP"),
    "porte": ("portail", ("poste", "poche", "perle"), "CP"), "pomme": ("pommier", ("pompier", "paume", "poème"), "CP"),
}
# mot : (lettre muette, mot de la famille qui la fait entendre, depuis)
LETTRES_MUETTES = {
    "chat": ("t", "chaton", "CP"), "petit": ("t", "petite", "CP"), "grand": ("d", "grande", "CP"),
    "gros": ("s", "grosse", "CP"), "blanc": ("c", "blanche", "CP"), "lait": ("t", "laitier", "CP"),
    "dent": ("t", "dentiste", "CP"), "chaud": ("d", "chaude", "CP"), "gris": ("s", "grise", "CP"),
    "rond": ("d", "ronde", "CP"), "plat": ("t", "plate", "CP"), "froid": ("d", "froide", "CP"),
    "sport": ("t", "sportif", "CE1"), "tapis": ("s", "tapisser", "CE1"), "camp": ("p", "camper", "CE1"),
    "galop": ("p", "galoper", "CE1"), "bord": ("d", "border", "CE1"), "bavard": ("d", "bavarder", "CE1"),
    "retard": ("d", "retarder", "CE1"), "marchand": ("d", "marchande", "CE1"), "haut": ("t", "hauteur", "CE1"),
    "fruit": ("t", "fruitier", "CE1"), "toit": ("t", "toiture", "CE1"),
    # ajoutés pour le CP (un objectif seul : 15 questions différentes)
    "lourd": ("d", "lourde", "CP"), "court": ("t", "courte", "CP"), "fort": ("t", "forte", "CP"),
    "vert": ("t", "verte", "CP"), "lent": ("t", "lente", "CP"), "bas": ("s", "basse", "CP"),
}
LETTRES = ("t", "d", "s", "x", "p", "c")
# terme générique (singulier, pluriel) : mots
CATEGORIES = {
    ("fruit", "fruits"): ("pomme", "poire", "banane", "cerise", "fraise", "abricot", "raisin", "prune"),
    ("légume", "légumes"): ("carotte", "poireau", "navet", "radis", "chou", "haricot"),
    ("meuble", "meubles"): ("table", "chaise", "armoire", "lit", "canapé", "étagère"),
    ("vêtement", "vêtements"): ("pantalon", "robe", "chemise", "manteau", "jupe", "chaussette"),
    ("instrument de musique", "instruments de musique"): ("piano", "guitare", "violon", "flûte", "tambour", "trompette"),
    ("oiseau", "oiseaux"): ("moineau", "pigeon", "merle", "aigle", "hibou", "corbeau"),
    ("insecte", "insectes"): ("abeille", "fourmi", "mouche", "papillon", "coccinelle", "moustique"),
    ("outil", "outils"): ("marteau", "scie", "tournevis", "pince", "râteau", "pelle"),
}
NIVEAUX_DE_LANGUE = [  # (familier, courant, soutenu)
    ("bagnole", "voiture", "automobile"), ("bouquin", "livre", "ouvrage"), ("boulot", "travail", "labeur"),
    ("baraque", "maison", "demeure"), ("godasse", "chaussure", "soulier"), ("trouille", "peur", "effroi"),
    ("moche", "laid", "disgracieux"), ("bouffer", "manger", "se restaurer"),
]

SOURCE = {"claude": {"nom": "Listes écrites par Claude ; mots, classes et pièges comparés à Lexique 3.83",
                     "url": "http://www.lexique.org", "consulte": "2026-11-12",
                     "licence": "CC BY-SA 4.0 (Lexique 3), pour la comparaison seulement"}}
CLASSES = ["CP", "CE1", "CE2"]


def tables(mots_de_lexique: set[str]) -> dict[str, dict]:
    contraires = [{"mot": m, "contraire": c, "classe": classe, "sens": sens, "source": "claude"}
                  for classe, champs in CONTRAIRES.items() for sens, paires in champs.items() for m, c in paires]
    prefixes = []
    for mot, (prefixe, contraire, depuis) in PREFIXES.items():
        pieges = [p for p in TOUS_PREFIXES if p != prefixe and (p[:-1] + mot) not in mots_de_lexique]
        pieges.sort(key=lambda p: p not in ("in-", "im-", "dé-", "mal-"))  # les plus courants d'abord
        prefixes.append({"mot": mot, "prefixe": prefixe, "contraire": contraire, "pieges": " ".join(pieges[:3]),
                         "depuis": depuis, "source": "claude"})
    familles = [{"mot": m, "parent": p, "pieges": " ".join(pi), "depuis": d, "source": "claude"}
                for m, (p, pi, d) in FAMILLES.items()]
    muettes = []
    for mot, (lettre, famille, depuis) in LETTRES_MUETTES.items():
        radical = mot[:-1]
        pieges = [l for l in LETTRES if l != lettre and (radical + l) not in mots_de_lexique]
        muettes.append({"mot": mot, "lettre": lettre, "famille": famille, "pieges": " ".join(pieges[:3]),
                        "depuis": depuis, "source": "claude"})
    categories = [{"mot": m, "categorie": s, "pluriel": p, "source": "claude"}
                  for (s, p), mots in CATEGORIES.items() for m in mots]
    niveaux = [{"familier": f, "courant": c, "soutenu": s, "source": "claude"} for f, c, s in NIVEAUX_DE_LANGUE]

    def table(description, proprietes, cle, lignes):
        return {"description": description, "sources": SOURCE, "proprietes": proprietes, "cle": cle, "lignes": lignes}
    return {
        "contraires": table("Des paires de contraires, leur classe et leur champ de sens : les mauvaises réponses "
                            "viennent d'un autre champ.",
                            {"mot": "texte", "contraire": "texte", "classe": ["adjectif", "verbe", "nom", "adverbe"],
                             "sens": "texte"}, ["mot"], contraires),
        "prefixes": table("Des mots et le préfixe qui fait leur contraire ; les préfixes pièges ne font aucun vrai mot "
                          "(Lexique 3.83).",
                          {"mot": "texte", "prefixe": list(TOUS_PREFIXES), "contraire": "texte", "pieges": "texte",
                           "depuis": CLASSES}, ["mot"], prefixes),
        "familles": table("Un mot, un mot de sa famille, et des pièges qui lui ressemblent sans en être (écrits à la "
                          "main).", {"mot": "texte", "parent": "texte", "pieges": "texte", "depuis": CLASSES},
                          ["mot"], familles),
        "lettres_muettes": table("Un mot, sa lettre muette finale, le mot de la famille qui la fait entendre ; les "
                                 "lettres pièges ne font aucun vrai mot (Lexique 3.83).",
                                 {"mot": "texte", "lettre": list(LETTRES), "famille": "texte", "pieges": "texte",
                                  "depuis": CLASSES}, ["mot"], muettes),
        "categories": table("Des mots rangés sous un terme générique (un seul par mot).",
                            {"mot": "texte", "categorie": "texte", "pluriel": "texte"}, ["mot"], categories),
        "niveaux_de_langue": table("Des trios familier, courant, soutenu.",
                                   {"familier": "texte", "courant": "texte", "soutenu": "texte"}, ["courant"], niveaux),
    }


def ecrire(lexique: Path, dossier: Path) -> None:
    with open(lexique, encoding="utf-8") as f:
        mots = {l["ortho"] for l in csv.DictReader(f, delimiter="\t")}
    (dossier / "francais").mkdir(parents=True, exist_ok=True)
    entete = ("# Table de référence (générateur procédural du français, lot 1, étape 1.4), écrite par Claude avec\n"
              "# scripts/vocabulaire/construire_vocabulaire.py, comparée à Lexique 3.83 "
              "(scripts/vocabulaire/verifier_vocabulaire.py).\n"
              "# À relire par l'utilisateur : python -m generateur.procedural.tables relire francais/{nom} --par \"…\"\n")
    for nom, donnees in tables(mots).items():
        texte = entete.format(nom=nom) + yaml.safe_dump(donnees, allow_unicode=True, sort_keys=False, width=120)
        (dossier / "francais" / f"{nom}.yaml").write_text(texte, encoding="utf-8")
        print(f"francais/{nom}.yaml : {len(donnees['lignes'])} lignes")


if __name__ == "__main__":
    ecrire(Path(sys.argv[1]), Path(sys.argv[2]))
