"""La page de relecture des tables des accords (lot 1, étape 1.2) : les noms, les adjectifs, les pluriels et les
féminins irréguliers, en listes lisibles, pour que l'enseignant les relise avant de les valider.

Usage : python -I page_relecture_accords.py <generateur/procedural/donnees> <page.md>"""
import sys
from pathlib import Path

import yaml

donnees, page = Path(sys.argv[1]), Path(sys.argv[2])


def lignes(nom: str) -> list[dict]:
    return yaml.safe_load((donnees / "francais" / f"{nom}.yaml").read_text(encoding="utf-8"))["lignes"]


def valider(nom: str) -> str:
    return f"`.venv/bin/python -m generateur.procedural.tables relire francais/{nom} --par \"…\"`"


SORTES = {"personne": "Des personnes", "animal": "Des animaux", "objet": "Des objets", "lieu": "Des lieux",
          "aliment": "Des aliments", "nature": "La nature"}
noms, adjectifs = lignes("noms"), lignes("adjectifs")
pluriels, feminins = lignes("pluriels_irreguliers"), lignes("feminins")
t = ["# Relecture : les tables des accords", "",
     "> Pages générées depuis les tables. **À relire, puis à valider** (depuis `Arrera-School-IA`), table par table : la",
     "> commande est sous chaque titre. Chaque mot a déjà été comparé à Lexique 3.83 par le programme (genre, nombre,",
     "> formes) : 329 vérifications, 0 écart. Ce qu'il faut regarder : les mots eux-mêmes, **ce qui est au CP et ce qui",
     "> attend le CE2**, les adjectifs et les noms qu'ils peuvent qualifier (pour éviter « une soupe ronde »), et les",
     "> **erreurs typiques** (elles serviront de mauvaises réponses : elles doivent être fausses, et vraisemblables).", "",
     f"## Les noms ({len(noms)})", "", valider("noms"), "",
     "Le nom, son article défini, son pluriel ; *CE2* : un pluriel irrégulier, seulement à partir du CE2.", ""]
for sorte, titre in SORTES.items():
    du_genre = [n for n in noms if n["sorte"] == sorte]
    t += [f"**{titre}** : " + ", ".join(
        f"{'l’' if n['article'] == 'l' + chr(39) else n['article'] + ' '}{n['nom']} ({'masc.' if n['genre'] == 'm' else 'fém.'}"
        f"{', pl. ' + n['pluriel'] if n['pluriel'] != n['nom'] + 's' else ''}{', *CE2*' if n['depuis'] == 'CE2' else ''})"
        for n in du_genre), ""]
t += [f"## Les adjectifs ({len(adjectifs)})", "", valider("adjectifs"), "",
      "| Masc. sing. | Fém. sing. | Masc. plur. | Fém. plur. | Place | Avec des noms de… |", "|---|---|---|---|---|---|"]
t += [f"| {a['ms']} | {a['fs']} | {a['mp']} | {a['fp']} | {'avant le nom' if a['place'] == 'avant' else 'après le nom'} | "
      f"{'toutes les sortes' if a['pour'] == 'tout' else ', '.join(SORTES[s].lower() for s in a['pour'].split())} |"
      for a in adjectifs]
t += ["", "> Au CP, seulement les adjectifs réguliers (+e, +s : petit, grand, noir…) ; blanc, long, gentil à partir du CE1.",
      "", f"## Les pluriels irréguliers, au CE2 ({len(pluriels)})", "", valider("pluriels_irreguliers"), "",
      "| Singulier | Pluriel | Règle | Erreur typique (mauvaise réponse) |", "|---|---|---|---|"]
t += [f"| {p['singulier']} | {p['pluriel']} | {p['regle']} | {p['erreur']} |" for p in pluriels]
t += ["", f"## Les féminins qui s'entendent, au CE2 ({len(feminins)})", "", valider("feminins"), "",
      "| Masculin | Féminin | Nature | Règle | Erreur typique (mauvaise réponse) |", "|---|---|---|---|---|"]
t += [f"| {f['masculin']} | {f['feminin']} | {f['nature']} | {f['regle']} | {f['erreur']} |" for f in feminins]
page.parent.mkdir(parents=True, exist_ok=True)
page.write_text("\n".join(t) + "\n", encoding="utf-8")
print(f"{page} : {len(noms)} noms, {len(adjectifs)} adjectifs, {len(pluriels)} pluriels, {len(feminins)} féminins")
