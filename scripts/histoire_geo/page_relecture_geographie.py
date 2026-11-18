"""La page de relecture des tables de la géographie sans carte (lot 2, étape 2.4) : sept tables, chacune avec ses
sources, ce que le générateur en tire, ce qui n'est jamais demandé, et la commande qui la valide.

Usage : python -I page_relecture_geographie.py <generateur/procedural/donnees> <page.md>"""
import sys
from pathlib import Path

import yaml

donnees, page = Path(sys.argv[1]), Path(sys.argv[2])
MATIERE = "histoire-geo"

# (table, titre, ce que le générateur en fait et ce qu'il ne demande jamais, colonnes affichées)
TABLES = [
    ("monde", "Continents, océans, la France (CP)",
     "« Lequel est le nom d'un océan ? » → Atlantique (les mauvaises réponses : des continents, la France ; l'Océanie "
     "est un piège) ; « L'Afrique est… » → un continent ; « Sur quel continent se trouve la France hexagonale ? » → en "
     "Europe. Les continents : ceux du modèle utilisé en France. **Jamais** : combien de continents ; l'Amérique et "
     "l'Océanie comme bonne réponse ni proposées pour « continent » (`demande: non`) ; l'Antarctique, l'Australie ; "
     "« L'océan Indien est… » (le mot donnerait la réponse).",
     ("nom", "le", "sorte", "demande", "ou", "source", "note")),
    ("points_cardinaux", "Les points cardinaux (CP)",
     "« Quel point cardinal est à l'opposé du nord ? » → le sud ; « Sur une rose des vents, que veut dire la lettre "
     "O ? » → l'ouest ; « Lequel est un point cardinal ? » (les mauvaises réponses : à gauche, devant, au-dessus…, "
     "les termes du programme pour se positionner). **Jamais** : où se lève le soleil ; « W ».",
     ("nom", "sorte", "lettre", "oppose", "source")),
    ("lieux", "Les lieux du monde (CE1)",
     "« Où se trouve l'Himalaya ? » → en Asie (sans le mot « continent » : l'Amérique en est un ou deux) ; « Lequel "
     "est un désert ? » → le Sahara ; « Lequel de ces lieux se trouve en Afrique ? » → le Nil. **Jamais** : le plus "
     "long fleuve du monde ; « où se trouve l'Antarctique » (c'est un continent).",
     ("nom", "sorte", "ou", "source", "note")),
    ("mots", "Les mots de la géographie (CE1) : relief, végétation, fleuve et rivière",
     "« Une grande étendue plate, c'est… » → une plaine ; « Une forêt, c'est… » → une grande étendue couverte "
     "d'arbres ; « Un cours d'eau qui se jette dans un autre, c'est… » → une rivière. Les définitions sont **écrites "
     "pour un élève de CE1** d'après les sources : à relire de près. **Jamais ensemble** (`jamais`) : la plaine et le "
     "plateau (l'altitude ne les distingue pas), la montagne et la vallée. Le fleuve et la rivière : la définition des "
     "géographes (en français courant, une rivière est seulement plus petite).",
     ("mot", "sorte", "definition", "jamais", "source", "note")),
    ("climats", "Les zones climatiques et les territoires français (CE1)",
     "« Dans la zone tropicale… » → il fait chaud toute l'année ; « Dans quelle zone climatique se trouve la "
     "Guyane ? » → la zone tropicale ; « Lequel de ces territoires est dans la zone froide ? » → la terre Adélie. La "
     "Guyane a un climat équatorial, rangé dans la zone tropicale (la zone chaude). **Écartés** : le Sahara, "
     "Saint-Pierre-et-Miquelon, la Nouvelle-Calédonie, la Polynésie.",
     ("nom", "sorte", "zone", "climat", "source", "note")),
    ("france", "Les massifs et les grands fleuves français (CE2) ; trois rivières",
     "« Lequel de ces massifs est en France ? » → les Vosges (l'Himalaya, les Andes, l'Atlas) ; « Lequel est un des "
     "grands fleuves français ? » ; « La Saône se jette dans le Rhône, un fleuve : c'est… » → une rivière (CE1). "
     "**Écartés** : la Corse (un élève y voit une île), le massif ultramarin au choix ; la Seine dans « se jette… : "
     "c'est… » (« dans la Manche » : l'élève ne sait pas que c'est une mer).",
     ("nom", "sorte", "se_jette", "source", "note")),
    ("villes", "Les villes et leur fleuve (CE2)",
     "« Quel fleuve passe à Lyon ? » → le Rhône ; « Par quelle ville passe la Garonne ? » → Toulouse. Un seul grand "
     "fleuve par ville ; les rivières de la ville (la Saône à Lyon, le Cher à Tours) ne sont jamais proposées.",
     ("ville", "fleuve", "source", "note")),
]

t = ["# Relecture : les tables de la géographie sans carte (histoire-géographie)", "",
     "> Page générée depuis les tables (`scripts/histoire_geo/page_relecture_geographie.py`). **À relire, puis à",
     "> valider** (depuis `Arrera-School-IA`), table par table : la commande est sous chaque titre. Le programme est la",
     "> première source (histoire-géographie de 2026, annexe 3 du BO n° 22 du 28 mai 2026 : ses repères) ; sinon",
     "> Wikipédia ou le Wiktionnaire, lus le 18/11 par un agent de lecture : la phrase qui fonde chaque fait est citée",
     "> dans la source. Ce qu'il faut regarder : **chaque fait**, **les définitions écrites pour le CE1** (table `mots`)",
     "> et **ce qui n'est jamais demandé** (dit sous chaque titre).", ""]
total = 0
for nom, titre, texte, colonnes in TABLES:
    table = yaml.safe_load((donnees / MATIERE / f"{nom}.yaml").read_text(encoding="utf-8"))
    total += len(table["lignes"])
    t += [f"## {titre} ({len(table['lignes'])})", "",
          f"`.venv/bin/python -m generateur.procedural.tables relire {MATIERE}/{nom} --par \"…\"`", "", f"> {texte}",
          "", "Sources :"]
    t += [f"- `{ident}` : {s['nom']} — <{s['url']}>" for ident, s in table["sources"].items()]
    t += ["", "| " + " | ".join(colonnes) + " |", "|" + "---|" * len(colonnes)]
    t += ["| " + " | ".join(str(l.get(c, "")).replace("|", "\\|") for c in colonnes) + " |" for l in table["lignes"]]
    t.append("")
page.write_text("\n".join(t), encoding="utf-8")
print(f"{page} : {len(TABLES)} tables, {total} lignes")
