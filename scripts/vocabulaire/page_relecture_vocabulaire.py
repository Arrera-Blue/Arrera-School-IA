"""La page de relecture des tables du vocabulaire (lot 1, étape 1.4) : contraires, préfixes, familles, lettres
muettes, catégories, niveaux de langue, pour que l'enseignant les relise avant de les valider.

Usage : python -I page_relecture_vocabulaire.py <generateur/procedural/donnees> <page.md>"""
import sys
from pathlib import Path

import yaml

donnees, page = Path(sys.argv[1]), Path(sys.argv[2])


def lignes(nom: str) -> list[dict]:
    return yaml.safe_load((donnees / "francais" / f"{nom}.yaml").read_text(encoding="utf-8"))["lignes"]


def titre(nom: str, texte: str, n: int) -> list[str]:
    return [f"## {texte} ({n})", "",
            f"`.venv/bin/python -m generateur.procedural.tables relire francais/{nom} --par \"…\"`", ""]


t = ["# Relecture : les tables du vocabulaire", "",
     "> Pages générées depuis les tables. **À relire, puis à valider** (depuis `Arrera-School-IA`), table par table : la",
     "> commande est sous chaque titre. Tout a été comparé à Lexique 3.83 par le programme (351 vérifications, 0 écart) ;",
     "> **les pièges des préfixes et des lettres muettes ont été choisis pour ne faire aucun vrai mot** (« chas » existe :",
     "> s n'est jamais proposé pour « chat »). Ce qu'il faut regarder : les mots, **le sens** (des contraires vraiment",
     "> contraires, des familles vraiment familles, des pièges vraiment hors de la famille), et ce qui est au CP.", ""]
contraires = lignes("contraires")
t += titre("contraires", "Les contraires", len(contraires))
t += ["> Les mauvaises réponses viennent toujours **d'un autre champ de sens** (jamais « court » contre « grand »).", "",
      "| Mot | Contraire | Classe | Champ de sens |", "|---|---|---|---|"]
t += [f"| {l['mot']} | {l['contraire']} | {l['classe']} | {l['sens']} |" for l in contraires]
prefixes = lignes("prefixes")
t += [""] + titre("prefixes", "Les contraires par un préfixe (CE1, CE2)", len(prefixes))
t += ["| Mot | Préfixe | Contraire | Préfixes pièges (aucun vrai mot) | Classe |", "|---|---|---|---|---|"]
t += [f"| {l['mot']} | {l['prefixe']} | {l['contraire']} | {l['pieges']} | dès le {l['depuis']} |" for l in prefixes]
familles = lignes("familles")
t += [""] + titre("familles", "Les familles de mots", len(familles))
t += ["| Mot | De la même famille | Pièges (ressemblent, sans en être) | Classe |", "|---|---|---|---|"]
t += [f"| {l['mot']} | {l['parent']} | {', '.join(l['pieges'].split())} | dès le {l['depuis']} |" for l in familles]
muettes = lignes("lettres_muettes")
t += [""] + titre("lettres_muettes", "Les lettres muettes (CP, CE1)", len(muettes))
t += ["| Mot | Lettre muette | On l'entend dans | Lettres pièges (aucun vrai mot) | Classe |", "|---|---|---|---|---|"]
t += [f"| {l['mot']} | {l['lettre']} | {l['famille']} | {', '.join(l['pieges'].split())} | dès le {l['depuis']} |"
      for l in muettes]
categories = lignes("categories")
t += [""] + titre("categories", "Les catégories (termes génériques)", len(categories))
par_categorie: dict[str, list[str]] = {}
for l in categories:
    par_categorie.setdefault(l["categorie"], []).append(l["mot"])
t += [f"- **{c}** : {', '.join(m)}" for c, m in par_categorie.items()]
niveaux = lignes("niveaux_de_langue")
t += [""] + titre("niveaux_de_langue", "Les niveaux de langue", len(niveaux))
t += ["> Au CP, seulement familier et courant. **Aussi** : un autre mot de la table qui a aussi ce sens, jamais proposé",
      "> comme piège (« Quel mot soutenu veut dire « travail » ? » : « ouvrage » serait juste aussi).", "",
      "| Familier | Courant | Soutenu | Aussi (jamais piège) |", "|---|---|---|---|"]
t += [f"| {l['familier']} | {l['courant']} | {l['soutenu']} | {'' if l['aussi'] == '-' else l['aussi']} |" for l in niveaux]
page.parent.mkdir(parents=True, exist_ok=True)
page.write_text("\n".join(t) + "\n", encoding="utf-8")
print(f"{page} : 6 tables")
