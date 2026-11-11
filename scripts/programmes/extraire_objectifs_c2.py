"""Brouillon du référentiel du cycle 2 (lot 0, étape 0.4) : les « Objectifs d'apprentissage » de chaque classe, mot
pour mot, avec leur domaine, leur thème et, au CP, leur période. Le format diffère du cycle 3 (extraire_objectifs.py) :

- un tableau à deux colonnes « Objectifs d'apprentissage | Exemples de réussite », chaque case faite de puces « - » ;
- selon les pages, pypdf rend les deux colonnes l'une après l'autre, ou ligne de tableau par ligne de tableau (un
  objectif, son exemple, l'objectif suivant…) : on ne peut pas se fier à l'ordre ;
- donc chaque puce est classée par son contenu : un **objectif** s'écrit à l'infinitif (« Encoder des syllabes… ») ;
  un **exemple de réussite** a l'élève pour sujet (« L'élève… », « Il… », « En lecture et en dictée, il… ») ;
- au CP, au CE1 et au CE2, des repères de période (« Dès le début de l'année », « En fin d'année »…), dans chaque
  colonne : un repère qui précède directement un objectif vaut pour lui et les objectifs suivants ; celui qui précède
  un exemple ne compte pas (sans cela, une colonne coupée par un changement de page prend la période d'un exemple) ;
- les titres des thèmes, des classes et des domaines ne sont jamais collés à une puce ;
- mise en page : un mot coupé en fin de ligne après un trait d'union est recollé sans espace (« grapho-phonémiques ») ;
  la puce « \uf0b7 » de la police Symbol, à l'intérieur d'un objectif, est retirée.

Usage : python -I extraire_objectifs_c2.py <annexe3.txt> -> JSON sur la sortie standard, et sur la sortie d'erreur les
puces dont le classement est douteux (à relire à la main).
(annexe3.txt : le texte de l'annexe 3 du BO n° 41 du 31 octobre 2024, page par page, « ===== page N »)."""
import json
import re
import sys

CLASSES = {"Cours préparatoire": "CP", "Cours élémentaire première année": "CE1",
           "Cours élémentaire deuxième année": "CE2"}
DOMAINES = ("Lecture", "Écriture", "Oral", "Vocabulaire", "Grammaire et orthographe")
ENTETE = re.compile(r"^Objectifs( d’apprentissage)? Exemples de réussite$")
PERIODE = re.compile(r"^(Dès|En fin|En milieu|En cours|À la fin|À partir|Au cours|Tout au long|À l’issue)\b[^.]{0,40}$")
# l'élève pour sujet : un exemple de réussite
EXEMPLE = re.compile(r"^(L’élève|L'élève|Il|Elle|Ils|Elles)\b|\bl’élève\b|\bl'élève\b|, (il|elle) ")
NOUVEL_EXEMPLE = re.compile(r"^(L’élève|L'élève|Il|Elle) ")  # un exemple qui commence sans puce
INFINITIF = re.compile(r"^(Être|Avoir|S’|Se |S'|Ne |N’|N')|^\w+(er|ir|re|oir)\b")

lignes = []
for brute in open(sys.argv[1], encoding="utf-8"):
    ligne = re.sub(r"\s+", " ", brute.strip())
    if ligne and not ligne.startswith("===== page"):
        lignes.append(ligne)

sommaire_fin = [i for i, l in enumerate(lignes) if l == "Principes"][1]  # le sommaire répète les titres
TITRES = {l for l in lignes[:sommaire_fin]} - {"Principes"}
blocs, domaine, classe, courant, precedent, periode = [], None, None, None, None, None
for ligne in lignes[sommaire_fin:]:
    if ligne in DOMAINES:
        domaine, courant = ligne, None
    elif ligne in CLASSES:
        classe, courant = CLASSES[ligne], None
    elif ENTETE.match(ligne):
        courant, periode = {"domaine": domaine, "classe": classe, "theme": precedent, "items": []}, None
        blocs.append(courant)
    elif courant is not None and ligne not in TITRES:
        if PERIODE.match(ligne):
            periode = ligne  # en attente : il vaudra pour la puce qui suit, si c'est un objectif
        elif ligne.startswith("- ") or NOUVEL_EXEMPLE.match(ligne):
            courant["items"].append({"texte": ligne[2:] if ligne.startswith("- ") else ligne, "repere": periode})
            periode = None
        elif courant["items"]:
            item = courant["items"][-1]
            if re.search(r"\w-$", item["texte"]):  # un mot coupé après un trait d'union
                print(f"~ recollé : …{item['texte'][-25:]}|{ligne[:25]}…", file=sys.stderr)
                item["texte"] += ligne
            else:
                item["texte"] += " " + ligne
    precedent = ligne

sortie = []
for b in blocs:
    objectifs, periode_objectifs = [], None
    for item in b["items"]:
        item["texte"] = re.sub(r"\s*\uf0b7\s*", " ", item["texte"]).strip()
        exemple = bool(EXEMPLE.search(item["texte"]))
        infinitif = bool(INFINITIF.match(item["texte"]))
        if exemple == infinitif:  # les deux signes, ou aucun : à regarder à la main
            print(f"? {b['classe']} | {b['theme']} | {'exemple' if exemple else 'objectif'} : {item['texte'][:110]}",
                  file=sys.stderr)
        if not exemple:
            periode_objectifs = item["repere"] or periode_objectifs
            objectifs.append({"libelle": item["texte"], "periode": periode_objectifs})
    sortie.append({"domaine": b["domaine"], "classe": b["classe"], "theme": b["theme"], "objectifs": objectifs})
json.dump(sortie, sys.stdout, ensure_ascii=False, indent=1)
