"""Les tables des accords (lot 1, étape 1.2 : docs/Generateur-Procedural/lot-1-francais.md §4), écrites à la main par
Claude (décision 2 : une liste de mots fréquents à l'école) :

- `francais/noms` : des noms d'un seul genre (pas « élève », « enfant »), leur pluriel, leur article défini (« le »
  devant un h aspiré : le hibou), leur sorte (pour qu'un adjectif ou un verbe aille avec), et la première classe où ils
  servent (les pluriels irréguliers au CE2, comme le programme) ;
- `francais/adjectifs` : quatre formes **toutes différentes** (petit, petite, petits, petites), leur place (avant ou
  après le nom) et les sortes de noms qu'ils qualifient ;
- `francais/pluriels_irreguliers` et `francais/feminins` (CE2) : la forme juste, la règle, et **l'erreur typique** de
  l'élève (décision 4 : « chevals », « lecteuse », écrites ici à la main, jamais fabriquées par le programme).

Usage : python -I construire_accords.py <generateur/procedural/donnees>
Puis : verifier_accords.py (chaque genre, chaque pluriel, chaque forme comparés à Lexique 3)."""
import sys
from pathlib import Path

import yaml

# nom : (genre, pluriel, article, sorte) ; le pluriel en « + s » s'écrit "+s"
NOMS = {
    # des personnes
    "garçon": ("m", "+s", "le", "personne"), "fille": ("f", "+s", "la", "personne"),
    "maman": ("f", "+s", "la", "personne"), "papa": ("m", "+s", "le", "personne"),
    "frère": ("m", "+s", "le", "personne"), "sœur": ("f", "+s", "la", "personne"),
    "maître": ("m", "+s", "le", "personne"), "maîtresse": ("f", "+s", "la", "personne"),
    "voisin": ("m", "+s", "le", "personne"), "voisine": ("f", "+s", "la", "personne"),
    "cousin": ("m", "+s", "le", "personne"), "cousine": ("f", "+s", "la", "personne"),
    "ami": ("m", "+s", "l'", "personne"), "amie": ("f", "+s", "l'", "personne"),
    "roi": ("m", "+s", "le", "personne"), "reine": ("f", "+s", "la", "personne"),
    "prince": ("m", "+s", "le", "personne"), "princesse": ("f", "+s", "la", "personne"),
    "boulanger": ("m", "+s", "le", "personne"), "boulangère": ("f", "+s", "la", "personne"),
    "fermier": ("m", "+s", "le", "personne"), "fermière": ("f", "+s", "la", "personne"),
    "pompier": ("m", "+s", "le", "personne"), "facteur": ("m", "+s", "le", "personne"),
    # des animaux
    "chat": ("m", "+s", "le", "animal"), "chien": ("m", "+s", "le", "animal"), "lapin": ("m", "+s", "le", "animal"),
    "vache": ("f", "+s", "la", "animal"), "poule": ("f", "+s", "la", "animal"),
    "souris": ("f", "souris", "la", "animal"), "poisson": ("m", "+s", "le", "animal"),
    "mouton": ("m", "+s", "le", "animal"), "canard": ("m", "+s", "le", "animal"),
    "cochon": ("m", "+s", "le", "animal"), "renard": ("m", "+s", "le", "animal"), "loup": ("m", "+s", "le", "animal"),
    "ours": ("m", "ours", "l'", "animal"), "tortue": ("f", "+s", "la", "animal"),
    "grenouille": ("f", "+s", "la", "animal"), "abeille": ("f", "+s", "l'", "animal"),
    "fourmi": ("f", "+s", "la", "animal"), "girafe": ("f", "+s", "la", "animal"), "lion": ("m", "+s", "le", "animal"),
    "tigre": ("m", "+s", "le", "animal"), "éléphant": ("m", "+s", "l'", "animal"), "âne": ("m", "+s", "l'", "animal"),
    "escargot": ("m", "+s", "l'", "animal"), "araignée": ("f", "+s", "l'", "animal"),
    "oiseau": ("m", "oiseaux", "l'", "animal"), "cheval": ("m", "chevaux", "le", "animal"),
    "animal": ("m", "animaux", "l'", "animal"), "hibou": ("m", "hiboux", "le", "animal"),
    # des objets
    "table": ("f", "+s", "la", "objet"), "chaise": ("f", "+s", "la", "objet"), "livre": ("m", "+s", "le", "objet"),
    "crayon": ("m", "+s", "le", "objet"), "cahier": ("m", "+s", "le", "objet"), "stylo": ("m", "+s", "le", "objet"),
    "ballon": ("m", "+s", "le", "objet"), "vélo": ("m", "+s", "le", "objet"), "voiture": ("f", "+s", "la", "objet"),
    "train": ("m", "+s", "le", "objet"), "avion": ("m", "+s", "l'", "objet"), "porte": ("f", "+s", "la", "objet"),
    "fenêtre": ("f", "+s", "la", "objet"), "lit": ("m", "+s", "le", "objet"), "sac": ("m", "+s", "le", "objet"),
    "robe": ("f", "+s", "la", "objet"), "chaussure": ("f", "+s", "la", "objet"), "lampe": ("f", "+s", "la", "objet"),
    "cartable": ("m", "+s", "le", "objet"), "gomme": ("f", "+s", "la", "objet"), "jouet": ("m", "+s", "le", "objet"),
    "poupée": ("f", "+s", "la", "objet"), "tapis": ("m", "tapis", "le", "objet"),
    "bateau": ("m", "bateaux", "le", "objet"), "chapeau": ("m", "chapeaux", "le", "objet"),
    "cadeau": ("m", "cadeaux", "le", "objet"), "bijou": ("m", "bijoux", "le", "objet"),
    "journal": ("m", "journaux", "le", "objet"), "jeu": ("m", "jeux", "le", "objet"),
    # des lieux
    "maison": ("f", "+s", "la", "lieu"), "école": ("f", "+s", "l'", "lieu"), "classe": ("f", "+s", "la", "lieu"),
    "ville": ("f", "+s", "la", "lieu"), "jardin": ("m", "+s", "le", "lieu"), "parc": ("m", "+s", "le", "lieu"),
    "forêt": ("f", "+s", "la", "lieu"), "rue": ("f", "+s", "la", "lieu"), "plage": ("f", "+s", "la", "lieu"),
    "montagne": ("f", "+s", "la", "lieu"), "rivière": ("f", "+s", "la", "lieu"), "village": ("m", "+s", "le", "lieu"),
    "cuisine": ("f", "+s", "la", "lieu"), "chambre": ("f", "+s", "la", "lieu"),
    "château": ("m", "châteaux", "le", "lieu"), "hôpital": ("m", "hôpitaux", "l'", "lieu"),
    # des aliments
    "pomme": ("f", "+s", "la", "aliment"), "poire": ("f", "+s", "la", "aliment"), "banane": ("f", "+s", "la", "aliment"),
    "pain": ("m", "+s", "le", "aliment"), "fromage": ("m", "+s", "le", "aliment"), "carotte": ("f", "+s", "la", "aliment"),
    "tomate": ("f", "+s", "la", "aliment"), "soupe": ("f", "+s", "la", "aliment"), "bonbon": ("m", "+s", "le", "aliment"),
    "fraise": ("f", "+s", "la", "aliment"), "cerise": ("f", "+s", "la", "aliment"),
    "gâteau": ("m", "gâteaux", "le", "aliment"),
    # la nature
    "fleur": ("f", "+s", "la", "nature"), "arbre": ("m", "+s", "l'", "nature"), "feuille": ("f", "+s", "la", "nature"),
    "soleil": ("m", "+s", "le", "nature"), "lune": ("f", "+s", "la", "nature"), "étoile": ("f", "+s", "l'", "nature"),
    "nuage": ("m", "+s", "le", "nature"), "pierre": ("f", "+s", "la", "nature"), "caillou": ("m", "cailloux", "le", "nature"),
    "feu": ("m", "feux", "le", "nature"),
}

# ms, fs, mp, fp ; place ; les sortes de noms qu'il qualifie (« tout » : toutes)
ADJECTIFS = [
    ("petit", "petite", "petits", "petites", "avant", "tout"),
    ("grand", "grande", "grands", "grandes", "avant", "tout"),
    ("joli", "jolie", "jolis", "jolies", "avant", "tout"),
    ("long", "longue", "longs", "longues", "avant", "lieu"),
    ("gentil", "gentille", "gentils", "gentilles", "avant", "personne animal"),
    ("noir", "noire", "noirs", "noires", "apres", "animal objet nature"),
    ("blanc", "blanche", "blancs", "blanches", "apres", "animal objet nature"),
    ("vert", "verte", "verts", "vertes", "apres", "objet nature"),
    ("bleu", "bleue", "bleus", "bleues", "apres", "objet nature"),
    ("rond", "ronde", "ronds", "rondes", "apres", "objet nature"),
    ("lourd", "lourde", "lourds", "lourdes", "apres", "objet"),
    ("content", "contente", "contents", "contentes", "apres", "personne animal"),
    ("méchant", "méchante", "méchants", "méchantes", "apres", "animal"),
    ("fort", "forte", "forts", "fortes", "apres", "personne animal"),
]

# singulier : (pluriel, règle, erreur typique)
PLURIELS = {
    "cheval": ("chevaux", "-al → -aux", "chevals"), "animal": ("animaux", "-al → -aux", "animals"),
    "journal": ("journaux", "-al → -aux", "journals"), "hôpital": ("hôpitaux", "-al → -aux", "hôpitals"),
    "oiseau": ("oiseaux", "-eau → -eaux", "oiseaus"), "bateau": ("bateaux", "-eau → -eaux", "bateaus"),
    "château": ("châteaux", "-eau → -eaux", "châteaus"), "gâteau": ("gâteaux", "-eau → -eaux", "gâteaus"),
    "cadeau": ("cadeaux", "-eau → -eaux", "cadeaus"), "chapeau": ("chapeaux", "-eau → -eaux", "chapeaus"),
    "jeu": ("jeux", "-eu → -eux", "jeus"), "feu": ("feux", "-eu → -eux", "feus"),
    "cheveu": ("cheveux", "-eu → -eux", "cheveus"),
    "bijou": ("bijoux", "-ou → -oux (bijou, caillou, chou, genou, hibou, joujou, pou)", "bijous"),
    "caillou": ("cailloux", "-ou → -oux (bijou, caillou, chou, genou, hibou, joujou, pou)", "caillous"),
    "genou": ("genoux", "-ou → -oux (bijou, caillou, chou, genou, hibou, joujou, pou)", "genous"),
    "hibou": ("hiboux", "-ou → -oux (bijou, caillou, chou, genou, hibou, joujou, pou)", "hibous"),
    "chou": ("choux", "-ou → -oux (bijou, caillou, chou, genou, hibou, joujou, pou)", "chous"),
}

# masculin : (féminin, nature, règle, erreur typique)
FEMININS = {
    "lecteur": ("lectrice", "nom", "-teur → -trice", "lecteuse"),
    "acteur": ("actrice", "nom", "-teur → -trice", "acteuse"),
    "directeur": ("directrice", "nom", "-teur → -trice", "directeuse"),
    "conducteur": ("conductrice", "nom", "-teur → -trice", "conducteuse"),
    "boulanger": ("boulangère", "nom", "-er → -ère", "boulangere"),
    "fermier": ("fermière", "nom", "-er → -ère", "fermiere"),
    "épicier": ("épicière", "nom", "-er → -ère", "épiciere"),
    "lion": ("lionne", "nom", "-on → -onne", "lione"),
    "champion": ("championne", "nom", "-on → -onne", "champione"),
    "gardien": ("gardienne", "nom", "-en → -enne", "gardiene"),
    "musicien": ("musicienne", "nom", "-en → -enne", "musiciene"),
    "joyeux": ("joyeuse", "adjectif", "-eux → -euse", "joyeuxe"),
    "heureux": ("heureuse", "adjectif", "-eux → -euse", "heureuxe"),
    "peureux": ("peureuse", "adjectif", "-eux → -euse", "peureuxe"),
    "sportif": ("sportive", "adjectif", "-f → -ve", "sportife"),
    "neuf": ("neuve", "adjectif", "-f → -ve", "neufe"),
    "premier": ("première", "adjectif", "-er → -ère", "premiere"),
    "léger": ("légère", "adjectif", "-er → -ère", "légere"),
    "gentil": ("gentille", "adjectif", "-il → -ille", "gentile"),
    "bon": ("bonne", "adjectif", "-on → -onne", "bone"),
}

SOURCES = {"claude": {"nom": "Liste écrite par Claude ; genres, pluriels et formes comparés à Lexique 3.83",
                      "url": "http://www.lexique.org", "consulte": "2026-11-11",
                      "licence": "CC BY-SA 4.0 (Lexique 3), pour la comparaison seulement"}}
SORTES = ["personne", "animal", "objet", "lieu", "aliment", "nature"]


def tables() -> dict[str, dict]:
    noms = []
    for nom, (genre, pluriel, article, sorte) in NOMS.items():
        pluriel = nom + "s" if pluriel == "+s" else pluriel
        noms.append({"nom": nom, "genre": genre, "pluriel": pluriel, "article": article, "sorte": sorte,
                     "depuis": "CE2" if nom in PLURIELS else "CP", "source": "claude"})
    adjectifs = [{"ms": ms, "fs": fs, "mp": mp, "fp": fp, "place": place, "pour": pour, "source": "claude"}
                 for ms, fs, mp, fp, place, pour in ADJECTIFS]
    pluriels = [{"singulier": s, "pluriel": p, "regle": r, "erreur": e, "source": "claude"}
                for s, (p, r, e) in PLURIELS.items()]
    feminins = [{"masculin": m, "feminin": f, "nature": n, "regle": r, "erreur": e, "source": "claude"}
                for m, (f, n, r, e) in FEMININS.items()]
    return {
        "noms": {"description": "Des noms fréquents à l'école, d'un seul genre, avec leur pluriel et leur article "
                                "défini (« le » devant un h aspiré) ; « depuis » : la première classe où ils servent "
                                "(les pluriels irréguliers au CE2).",
                 "sources": SOURCES,
                 "proprietes": {"nom": "texte", "genre": ["m", "f"], "pluriel": "texte", "article": ["le", "la", "l'"],
                                "sorte": SORTES, "depuis": ["CP", "CE1", "CE2"]},
                 "cle": ["nom"], "lignes": noms},
        "adjectifs": {"description": "Des adjectifs aux quatre formes toutes différentes ; leur place par rapport au "
                                     "nom ; les sortes de noms qu'ils qualifient (« tout », ou une liste).",
                      "sources": SOURCES,
                      "proprietes": {"ms": "texte", "fs": "texte", "mp": "texte", "fp": "texte",
                                     "place": ["avant", "apres"], "pour": "texte"},
                      "cle": ["ms"], "lignes": adjectifs},
        "pluriels_irreguliers": {"description": "Les pluriels irréguliers du CE2 (-al/-aux, -eau/-eaux, -eu/-eux, "
                                                "-ou/-oux) ; l'erreur typique de l'élève (le pluriel en -s), écrite "
                                                "à la main.",
                                 "sources": SOURCES,
                                 "proprietes": {"singulier": "texte", "pluriel": "texte", "regle": "texte",
                                                "erreur": "texte"},
                                 "cle": ["singulier"], "lignes": pluriels},
        "feminins": {"description": "Des féminins qui s'entendent, de noms (lecteur/lectrice) et d'adjectifs "
                                    "(joyeux/joyeuse), au CE2 ; l'erreur typique de l'élève, écrite à la main.",
                     "sources": SOURCES,
                     "proprietes": {"masculin": "texte", "feminin": "texte", "nature": ["nom", "adjectif"],
                                    "regle": "texte", "erreur": "texte"},
                     "cle": ["masculin"], "lignes": feminins},
    }


def ecrire(dossier: Path) -> None:
    (dossier / "francais").mkdir(parents=True, exist_ok=True)
    entete = ("# Table de référence (générateur procédural du français, lot 1, étape 1.2), écrite par Claude avec\n"
              "# scripts/accords/construire_accords.py, comparée à Lexique 3.83 (scripts/accords/verifier_accords.py).\n"
              "# À relire par l'utilisateur : python -m generateur.procedural.tables relire francais/{nom} --par \"…\"\n")
    for nom, donnees in tables().items():
        texte = entete.format(nom=nom) + yaml.safe_dump(donnees, allow_unicode=True, sort_keys=False, width=120)
        (dossier / "francais" / f"{nom}.yaml").write_text(texte, encoding="utf-8")
        print(f"francais/{nom}.yaml : {len(donnees['lignes'])} lignes")


if __name__ == "__main__":
    ecrire(Path(sys.argv[1]))
