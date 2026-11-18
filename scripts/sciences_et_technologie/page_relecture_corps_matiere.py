"""La page de relecture des tables du corps humain, de la matière et des objets (lot 2, étape 2.3) : quatorze tables,
chacune avec ses sources, ce que le générateur en tire, ce qui n'est jamais demandé, et la commande qui la valide.

Usage : python -I page_relecture_corps_matiere.py <generateur/procedural/donnees> <page.md>"""
import sys
from pathlib import Path

import yaml

donnees, page = Path(sys.argv[1]), Path(sys.argv[2])
MATIERE = "sciences-et-technologie"

# (partie, [(table, titre, ce que le générateur en fait et ce qu'il ne demande jamais, colonnes affichées)])
PARTIES = [
    ("Le corps humain (`corps.py`)", [
        ("aliments", "Les aliments : catégorie, origine, transformés (CP)",
         "« Dans quelle catégorie d'aliments range-t-on le yaourt ? » → les produits laitiers ; « Lequel de ces aliments "
         "fait partie des matières grasses ? » ; « La pomme est un aliment d'origine… » → végétale ; « Lequel de ces "
         "aliments est un produit transformé ? » (les mauvaises réponses : « non »). **« - »** : jamais demandé ni "
         "proposé pour cette propriété. **Écartés** : la pomme de terre et la banane (des féculents pour Wikipédia), le "
         "beurre, les petits pois, les légumes secs, le maïs ; le lait n'a pas de catégorie (produit laitier et "
         "boisson).",
         ("aliment", "categorie", "origine", "transforme", "source", "note")),
        ("articulations", "Les articulations (CP ; CE2 pour les gestes)",
         "« Quelle articulation se trouve entre le bras et l'avant-bras ? » → le coude ; « Quelle articulation permet de "
         "tourner la tête ? » → le cou (les mauvaises réponses : jamais de la même `partie`). **Jamais** « rotation ou "
         "flexion ? » (le classement du programme) : l'épaule, le poignet, la cheville, la hanche plient aussi, et le "
         "genou tourne un peu quand il est plié.",
         ("articulation", "entre", "geste", "partie", "source", "note")),
        ("os", "Quelques os (CP)",
         "« Quel est l'os de la cuisse ? » → le fémur ; « Dans le squelette, qu'est-ce qui protège le cerveau ? » → le "
         "crâne. Pas d'os de la jambe ni de l'avant-bras (deux chacun).",
         ("os", "lieu", "role", "source")),
        ("dents", "Les dents (CE1)",
         "« Quelle partie de la dent est implantée dans l'os ? » → la racine (`jamais` : la pulpe, qui descend dans la "
         "racine) ; « Combien de dents de lait l'humain possède-t-il ? » → 20 ; « Les dents définitives sont… » → plus "
         "grandes et plus solides (les pièges disent l'inverse). **Jamais** le rôle des canines ni des prémolaires "
         "(aucune page lue ne le dit).",
         ("element", "sorte", "description", "jamais", "source")),
        ("muscles", "Les muscles du bras (CE2)",
         "« Quel muscle permet de plier le bras ? » → le biceps ; « Que fait le triceps quand il se contracte ? » → il "
         "tend le bras. Le quadriceps n'est qu'une mauvaise réponse ; jamais « il tourne le bras » (le biceps tourne "
         "aussi l'avant-bras).",
         ("muscle", "infinitif", "present", "demande", "source")),
        ("effort", "Le cœur pendant l'effort (CE2) : des questions écrites",
         "Chaque ligne est une question entière. **Jamais** la respiration ni la transpiration : aucune page lue ne dit "
         "dans quel sens elles changent pendant l'effort (« elle peut varier »).",
         ("question", "reponse", "faux", "source")),
    ]),
    ("La matière et les objets (`matiere.py`)", [
        ("etats_eau", "L'eau dans la nature : solide ou liquide (CP)",
         "« Où l'eau est-elle solide : pluie, mer, neige, lac ? » → neige. **Écartés** : le nuage et le brouillard "
         "(des gouttelettes, parfois de la glace), la cascade (aucune page ne dit son état ; elle gèle en hiver).",
         ("nom", "etat", "source")),
        ("changements", "Les changements d'état (CE1)",
         "« Quand la glace fond, comment s'appelle ce changement d'état ? » → la fusion (mauvaises réponses : la "
         "solidification, la congélation ; **jamais « la fonte »**, `proche` de la fusion).",
         ("nom", "sorte", "quand", "de", "vers", "proche", "source")),
        ("conservation", "La masse et la place de l'eau (CE1)",
         "« Quand l'eau gèle, sa masse… » → ne change pas ; « Quand l'eau gèle, elle prend… » → plus de place (les "
         "mauvaises réponses : les deux autres valeurs).",
         ("quand", "grandeur", "valeur", "source")),
        ("materiaux", "Conducteurs et isolants (CE1)",
         "« Quel matériau laisse passer le courant : verre, fer, papier, plastique ? » → fer. **Écartés** : le graphite "
         "(la mine du crayon conduit), l'eau (conductrice dès qu'elle a des impuretés), le bois humide (le bois est dit "
         "« sec »).",
         ("materiau", "nature", "source")),
        ("circuit", "Le circuit électrique (CE1) : des questions écrites",
         "Chaque ligne est une question entière, tirée du programme (une pile, un interrupteur, une ampoule ; ouvert ou "
         "fermé).",
         ("question", "reponse", "faux", "source")),
        ("objets", "Objets techniques ; objets électriques (CP, CE1)",
         "« Lequel est un objet technique : stylo, galet, branche d'arbre, feuille d'arbre ? » (CP) ; « Lequel utilise "
         "l'énergie électrique : … ? » ; « Quel objet électrique fait le même travail qu'un tournevis ? » → une visseuse "
         "électrique (CE1). **Écartés** : « matériau brut → objet » (l'argile, le bois, la laine donnent chacun plusieurs "
         "objets) ; les vélos (« vélo » seul ne dit pas s'il a une assistance électrique).",
         ("objet", "technique", "electrique", "jumeau", "source", "note")),
        ("solides_liquides", "Solides et liquides (CE2)",
         "« Lequel est un liquide : lait, fer, glace, verre ? » ; « Un solide a… » → une forme propre et un volume propre ; "
         "« La surface d'un liquide au repos est… » → horizontale. **Écartés** : le sable, le sel, le sucre en poudre "
         "(des solides qui s'écoulent).",
         ("element", "sorte", "etat", "source", "note")),
        ("ordinateur", "L'ordinateur : saisir, traiter, restituer (CE2)",
         "« À quoi sert le clavier ? » → à saisir des informations ; « Lequel sert à traiter les informations : … ? » → "
         "processeur. L'écran est le moniteur (un écran tactile sert aussi à saisir).",
         ("element", "role", "source")),
    ]),
]

t = ["# Relecture : les tables du corps humain, de la matière et des objets (sciences et technologie)", "",
     "> Page générée depuis les tables (`scripts/sciences_et_technologie/page_relecture_corps_matiere.py`). **À relire,",
     "> puis à valider** (depuis `Arrera-School-IA`), table par table : la commande est sous chaque titre. Le programme",
     "> est la première source (sciences et technologie de 2026, BO n° 24 du 11 juin 2026) ; sinon Wikipédia ou le",
     "> Wiktionnaire, lus le 18/11 par un agent de lecture : la phrase qui fonde chaque fait est citée dans la source.",
     "> Ce qu'il faut regarder : **chaque fait**, et **ce qui n'est jamais demandé** (dit sous chaque titre). Les grammes",
     "> et les kilogrammes (CE2) se calculent : pas de table.", ""]
total = nombre = 0
for partie, tables_ in PARTIES:
    t += [f"## {partie}", ""]
    for nom, titre, texte, colonnes in tables_:
        table = yaml.safe_load((donnees / MATIERE / f"{nom}.yaml").read_text(encoding="utf-8"))
        total, nombre = total + len(table["lignes"]), nombre + 1
        t += [f"### {titre} ({len(table['lignes'])})", "",
              f"`.venv/bin/python -m generateur.procedural.tables relire {MATIERE}/{nom} --par \"…\"`", "", f"> {texte}",
              "", "Sources :"]
        t += [f"- `{ident}` : {s['nom']} — <{s['url']}>" for ident, s in table["sources"].items()]
        t += ["", "| " + " | ".join(colonnes) + " |", "|" + "---|" * len(colonnes)]
        t += ["| " + " | ".join(str(l.get(c, "")).replace("|", "\\|") for c in colonnes) + " |" for l in table["lignes"]]
        t.append("")
page.write_text("\n".join(t), encoding="utf-8")
print(f"{page} : {nombre} tables, {total} lignes")
