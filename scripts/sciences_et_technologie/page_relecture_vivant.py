"""La page de relecture des tables du vivant (lot 2, étape 2.2) : neuf tables, chacune avec ses sources, ce que le
générateur en tire, ce qui n'est jamais demandé, et la commande qui la valide.

Usage : python -I page_relecture_vivant.py <generateur/procedural/donnees> <page.md>"""
import sys
from pathlib import Path

import yaml

donnees, page = Path(sys.argv[1]), Path(sys.argv[2])
MATIERE = "sciences-et-technologie"

# (table, titre, ce que le générateur en fait et ce qu'il ne demande jamais, colonnes affichées)
TABLES = [
    ("etres_vivants", "Vivant, non vivant, élaboré (CP)",
     "« Lequel est vivant : chat, sable, laine, eau ? » ; « Lequel est fabriqué par un être vivant : … ? » ; « Lequel "
     "n'est pas vivant : … ? » (un élaboré n'est pas vivant non plus : les mauvaises réponses sont alors toutes "
     "vivantes). **Écartés** : l'œuf (un œuf fécondé contient un être vivant), tout objet fabriqué par l'humain.",
     ("element", "categorie", "genre", "source", "note")),
    ("animaux", "Les animaux : groupe et régime (CE1, CE2)",
     "« Le lion est… » → carnivore ; « Lequel de ces animaux est herbivore ? » ; « Dans quel groupe d'animaux range-t-on "
     "le dauphin ? » (la confusion « poisson » toujours proposée) ; « Lequel de ces animaux est un insecte ? » "
     "(l'araignée et l'escargot d'abord). **Régime « - »** : jamais demandé (discuté ou variable).",
     ("nom", "groupe", "regime", "confusion", "source")),
    ("regimes", "Les régimes alimentaires (CE1, CE2)",
     "« Un animal omnivore mange… » ; « Un animal qui mange seulement des plantes est… ».",
     ("regime", "mange", "source")),
    ("sens", "Les sens et leurs organes (CE1)",
     "« Quel est l'organe de l'odorat ? » ; « Avec quel organe peut-on entendre ? ». **Jamais** « à quoi sert "
     "l'oreille ? » (aussi à l'équilibre) ; le toucher seulement par son nom (la langue sent aussi ce qu'elle touche).",
     ("sens", "organe", "permet", "source")),
    ("plante", "La plante : ses parties, ses besoins (CE1)",
     "« Quelle partie de la plante puise l'eau dans le sol ? » ; « De quoi une plante verte a-t-elle besoin pour "
     "grandir ? ». La fleur n'est jamais une mauvaise réponse pour le fruit ou la graine.",
     ("element", "sorte", "role", "source")),
    ("cycle_plante", "La vie d'une plante à fleurs (CE2)",
     "« Quelle étape vient juste après la croissance ? » ; « Quelle étape de la vie d'une plante vient en premier ? ».",
     ("rang", "etape", "source")),
    ("petits", "Larves et jeunes ; les mues (CE2)",
     "« Le têtard devient… » → une grenouille ; « Le têtard est… » → une larve ; « Lequel grandit en faisant des "
     "mues ? » → la chenille. **Mues « - »** : jamais demandé (le têtard, le poussin).",
     ("jeune", "adulte", "forme", "mues", "source")),
    ("locomotion", "La locomotion (CE2)",
     "« À quoi servent les ailes de l'abeille ? » → à voler ; « Quel organe permet à la truite de nager ? ». "
     "**Écartés** : le canard, le manchot, la grenouille (un organe, deux façons de se déplacer).",
     ("animal", "organe", "mode", "source")),
    ("chaines", "Les chaînes alimentaires (CE2)",
     "« Les graines sont mangées par la mésange, qui est mangée par… » → l'épervier (les mauvaises réponses : des "
     "herbivores) ; « La mésange est mangée par l'épervier. Que mange la mésange ? ». **Écartée** : « les feuilles → la "
     "chenille » (la page ne le dit pas).",
     ("bas", "milieu", "haut", "source")),
]

t = ["# Relecture : les tables du vivant (sciences et technologie)", "",
     "> Page générée depuis les tables (`scripts/sciences_et_technologie/page_relecture_vivant.py`). **À relire, puis",
     "> à valider** (depuis `Arrera-School-IA`), table par table : la commande est sous chaque titre. Le programme est",
     "> la première source (sciences et technologie de 2026, BO n° 24 du 11 juin 2026) ; sinon Wikipédia ou le",
     "> Wiktionnaire, lus le 16/11 (Vikidia refuse les accès automatisés) : la phrase qui fonde chaque fait est citée",
     "> dans la source. Ce qu'il faut regarder : **chaque fait**, et **ce qui n'est jamais demandé** (dit sous chaque",
     "> titre).", ""]
total = 0
for nom, titre, texte, colonnes in TABLES:
    table = yaml.safe_load((donnees / MATIERE / f"{nom}.yaml").read_text(encoding="utf-8"))
    total += len(table["lignes"])
    t += [f"## {titre} ({len(table['lignes'])})", "",
          f"`.venv/bin/python -m generateur.procedural.tables relire {MATIERE}/{nom} --par \"…\"`", "", f"> {texte}", "",
          "Sources :"]
    t += [f"- `{ident}` : {s['nom']} — <{s['url']}>" for ident, s in table["sources"].items()]
    t += ["", "| " + " | ".join(colonnes) + " |", "|" + "---|" * len(colonnes)]
    t += ["| " + " | ".join(str(l.get(c, "")) for c in colonnes) + " |" for l in table["lignes"]]
    t.append("")
page.write_text("\n".join(t), encoding="utf-8")
print(f"{page} : {len(TABLES)} tables, {total} lignes")
