"""La page de relecture des tables de l'histoire (lot 2, étape 2.1) : le calendrier, les durées, les périodes, les
repères datés, la Préhistoire, pour que l'enseignant les relise avant de les valider. Chaque table avec ses sources,
ce que le générateur en tire, et la commande qui la valide.

Usage : python -I page_relecture_histoire.py <generateur/procedural/donnees> <page.md>"""
import sys
from pathlib import Path

import yaml

donnees, page = Path(sys.argv[1]), Path(sys.argv[2])


def charger(nom: str) -> dict:
    return yaml.safe_load((donnees / "histoire-geo" / f"{nom}.yaml").read_text(encoding="utf-8"))


def titre(nom: str, texte: str, table: dict) -> list[str]:
    t = [f"## {texte} ({len(table['lignes'])})", "",
         f"`.venv/bin/python -m generateur.procedural.tables relire histoire-geo/{nom} --par \"…\"`", "",
         "Sources :"]
    t += [f"- `{ident}` : {s['nom']} — <{s['url']}> (consulté le {s['consulte']}"
          + (f", {s['licence']}" if s.get("licence") else "") + ")" for ident, s in table["sources"].items()]
    return t + [""]


t = ["# Relecture : les tables de l'histoire (le temps)", "",
     "> Pages générées depuis les tables (`scripts/histoire_geo/page_relecture_histoire.py`). **À relire, puis à",
     "> valider** (depuis `Arrera-School-IA`), table par table : la commande est sous chaque titre. Le programme est la",
     "> première source (histoire-géographie de 2026, BO n° 22 du 28 mai 2026) ; sinon Wikipédia ou le Wiktionnaire",
     "> (Vikidia refuse les accès automatisés). Ce qu'il faut regarder : **chaque fait**, et **ce qui n'est jamais",
     "> demandé** parce que discuté (dit sous chaque table).", ""]

calendrier = charger("calendrier")
t += titre("calendrier", "Le calendrier", calendrier)
t += ["> Questions : le jour d'après-demain, d'hier, « dans 4 jours » (CE1) ; le mois juste après mars, le cinquième",
      "> mois (CE1) ; la saison juste après l'été, celle qui manque dans une suite. **Jamais** le premier jour de la",
      "> semaine (le lundi pour la norme ISO, le dimanche ailleurs), ni le nombre de saisons (deux sous les tropiques).",
      "", "| Suite | Dans l'ordre | Source |", "|---|---|---|"]
for suite in ("jour", "mois", "saison"):
    lignes = sorted((l for l in calendrier["lignes"] if l["suite"] == suite), key=lambda l: l["rang"])
    t.append(f"| {suite} | {', '.join(l['nom'] for l in lignes)} | {', '.join(sorted({l['source'] for l in lignes}))} |")

durees = charger("durees")
t += [""] + titre("durees", "Les durées", durees)
t += ["> Questions : « Combien de jours y a-t-il dans une semaine ? » (CP) ; « Combien d'années y a-t-il dans 3",
      "> siècles ? », « Combien de décennies dans un siècle ? » (CE1). **Jamais** le nombre de jours d'un mois (28 à 31).",
      "", "| Unité | Contient | Dès le | Source |", "|---|---|---|---|"]
t += [f"| {l['article']} {l['unite']} | {l['nombre']} {l['contient']} | {l['depuis']} | {l['source']} |"
      for l in durees["lignes"]]

periodes = charger("periodes")
t += [""] + titre("periodes", "Les grandes périodes (CE1, CE2)", periodes)
t += ["> Questions : la période juste après le Moyen Âge ; la plus ancienne de quatre ; l'année où commence le Moyen",
      "> Âge (seulement les limites précises : 476, 1492, 1789) ; « En 1200, dans quelle période sommes-nous ? », avec",
      "> une année toujours loin d'une limite (50 ans ; 500 ans quand la limite est « environ »).",
      "", "| Rang | Période | De | À |", "|---|---|---|---|"]
t += [f"| {l['rang']} | {l['nom']} | {l['debut']} | {l['fin']} |" for l in sorted(periodes["lignes"], key=lambda l: l["rang"])]

reperes = charger("reperes")
t += [""] + titre("reperes", "Les repères datés (CE2)", reperes)
t += ["> Questions : « Quel repère correspond à « 987 » ? » ; « Quelle date va avec « la guerre de Cent Ans » ? » ;",
      "> « Lequel de ces repères est le plus ancien ? ». Deux repères ne sont comparés que si leur écart dépasse la",
      "> somme de leurs marges : **jamais Ötzi contre l'écriture** (200 ans d'écart, 450 ans d'incertitude).",
      "", "| Repère | Date (programme) | Pour ranger | Marge | Source | Note |", "|---|---|---|---|---|---|"]
t += [f"| {l['evenement']} | {l['date']} | {l['annee']} | {l['marge']} ans | {l['source']} | {l.get('note', '')} |"
      for l in sorted(reperes["lignes"], key=lambda l: l["annee"])]

pre = charger("prehistoire")
t += [""] + titre("prehistoire", "La Préhistoire (CE2)", pre)
t += ["> Questions : « Au Paléolithique, les êtres humains sont surtout… » (nomades) ; « Au Néolithique, beaucoup",
      "> d'êtres humains deviennent… » (sédentaires) ; « Qu'est-ce qui apparaît au Néolithique ? » (une nouveauté ; les",
      "> mauvaises réponses : des activités du Paléolithique) ; « Qu'est-ce qui existait déjà au Paléolithique ? » ;",
      "> « À quelle période apparaît l'élevage ? » (seulement les lignes « apparaît : oui »). **Écartés**, parce que",
      "> discutés : la poterie (plus ancienne que le Néolithique en Asie de l'Est), les premiers villages (déjà avant le",
      "> Néolithique au Proche-Orient).",
      "", "| Période | Sorte | Fait | « À quelle période apparaît… ? » | Source |", "|---|---|---|---|---|"]
sortes = {"mode_de_vie": "mode de vie", "metier": "les êtres humains sont…", "activite": "existait déjà",
          "nouveaute": "apparaît"}
t += [f"| {l['periode']} | {sortes[l['sorte']]} | {l['texte']} | {l['apparait']} | {l['source']} |" for l in pre["lignes"]]

page.write_text("\n".join(t) + "\n", encoding="utf-8")
print(f"{page} : {sum(len(charger(n)['lignes']) for n in ('calendrier', 'durees', 'periodes', 'reperes', 'prehistoire'))} lignes")
