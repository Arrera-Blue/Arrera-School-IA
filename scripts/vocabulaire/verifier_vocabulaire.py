"""Le second contrôle des tables du vocabulaire (lot 1, étape 1.4), avec Lexique 3.83 (http://www.lexique.org,
CC BY-SA 4.0 : téléchargé à part) :

- contraires : les deux mots existent dans leur classe ; aucun mot dans deux paires (« vieux » contraire de « jeune »
  et de « neuf » donnerait deux bonnes réponses) ;
- préfixes : le contraire existe et s'écrit préfixe + mot ; aucun préfixe piège ne fait un vrai mot ;
- familles : tous les mots existent ; les pièges ne sont ni le mot ni son parent ;
- lettres muettes : le mot finit par sa lettre, le mot de la famille commence par lui (on y entend la lettre) ; aucune
  lettre piège ne fait un vrai mot ;
- catégories : chaque mot existe (nom) et n'est rangé qu'une fois ;
- niveaux de langue : chaque mot existe (une expression de plusieurs mots n'est pas cherchée).

Usage : python -I verifier_vocabulaire.py <Lexique383.tsv> <generateur/procedural/donnees>"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

lexique, donnees = Path(sys.argv[1]), Path(sys.argv[2])
categories = defaultdict(set)
with open(lexique, encoding="utf-8") as f:
    for ligne in csv.DictReader(f, delimiter="\t"):
        categories[ligne["ortho"]].add(ligne["cgram"].split(":")[0])
CLASSE = {"adjectif": {"ADJ"}, "verbe": {"VER"}, "nom": {"NOM"}, "adverbe": {"ADV", "PRE"}}


def table(nom: str) -> list[dict]:
    return yaml.safe_load((donnees / "francais" / f"{nom}.yaml").read_text(encoding="utf-8"))["lignes"]


ecarts, n = [], 0


def existe(mot: str, quoi: str, permises: set[str] | None = None) -> None:
    global n
    n += 1
    trouvees = categories.get(mot) or categories.get(mot.replace("œ", "oe"))
    if not trouvees:
        ecarts.append(f"{quoi} : « {mot} » absent de Lexique")
    elif permises and not trouvees & permises:
        ecarts.append(f"{quoi} : « {mot} » attendu {'/'.join(sorted(permises))}, Lexique : {', '.join(sorted(trouvees))}")


contraires = table("contraires")
for l in contraires:
    existe(l["mot"], f"contraire {l['mot']}", CLASSE[l["classe"]])
    existe(l["contraire"], f"contraire de {l['mot']}", CLASSE[l["classe"]])
for mot, fois in Counter(m for l in contraires for m in (l["mot"], l["contraire"])).items():
    if fois > 1:
        ecarts.append(f"contraires : « {mot} » dans {fois} paires (deux bonnes réponses possibles)")
for l in table("prefixes"):
    existe(l["contraire"], f"préfixe {l['mot']}")
    if l["prefixe"][:-1] + l["mot"] != l["contraire"]:
        ecarts.append(f"préfixe {l['mot']} : {l['prefixe']} + {l['mot']} ≠ {l['contraire']}")
    pieges = l["pieges"].split()
    if len(pieges) < 3:
        ecarts.append(f"préfixe {l['mot']} : {len(pieges)} pièges seulement")
    for p in pieges:
        if (p[:-1] + l["mot"]) in categories:
            ecarts.append(f"préfixe {l['mot']} : le piège {p} fait un vrai mot ({p[:-1] + l['mot']})")
for l in table("familles"):
    for mot in (l["mot"], l["parent"], *l["pieges"].split()):
        existe(mot, f"famille de {l['mot']}")
    if {l["mot"], l["parent"]} & set(l["pieges"].split()):
        ecarts.append(f"famille de {l['mot']} : un piège est le mot ou son parent")
for l in table("lettres_muettes"):
    existe(l["mot"], f"lettre muette {l['mot']}")
    existe(l["famille"], f"lettre muette {l['mot']} (famille)")
    if not l["mot"].endswith(l["lettre"]) or not l["famille"].startswith(l["mot"]):
        ecarts.append(f"lettre muette {l['mot']} : « {l['lettre']} » / « {l['famille']} » incohérents")
    pieges = l["pieges"].split()
    if len(pieges) < 3:
        ecarts.append(f"lettre muette {l['mot']} : {len(pieges)} pièges seulement")
    for p in pieges:
        if (l["mot"][:-1] + p) in categories:
            ecarts.append(f"lettre muette {l['mot']} : le piège « {p} » fait un vrai mot ({l['mot'][:-1] + p})")
cats = table("categories")
for l in cats:
    existe(l["mot"], f"catégorie {l['categorie']}", {"NOM"})
for mot, fois in Counter(l["mot"] for l in cats).items():
    if fois > 1:
        ecarts.append(f"catégories : « {mot} » rangé {fois} fois")
for l in table("niveaux_de_langue"):
    for registre in ("familier", "courant", "soutenu"):
        if " " not in l[registre]:
            existe(l[registre], f"niveau de langue ({registre})")
print(f"{n} vérifications ; {len(ecarts)} écart(s)")
for e in ecarts:
    print("  ✗", e)
sys.exit(1 if ecarts else 0)
