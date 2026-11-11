"""Le second contrôle des tables des accords (lot 1, étape 1.2) : chaque nom, pluriel, adjectif et féminin comparé à
Lexique 3.83 (http://www.lexique.org, CC BY-SA 4.0 : téléchargé à part, jamais dans le projet).

Signale : un mot absent ; un genre ou un nombre qui ne correspond pas ; un nom que Lexique donne aussi à l'autre
genre (ambigu pour « quel nom est féminin ? ») ; une « erreur typique » qui serait un vrai mot. En remarque (pas une
faute) : un lemme différent (Lexique range les noms féminins sous le masculin : « voisines », lemme voisin ; et
quelques pluriels sous eux-mêmes : « bijoux ») ; un mot rare (fréquence du lemme dans les livres sous 2 par million).
Lexique écrit « oe » pour « œ » (soeur) ; un nom invariable (souris, ours) n'y est souvent qu'au singulier.

Usage : python -I verifier_accords.py <Lexique383.tsv> <generateur/procedural/donnees>"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

import yaml

lexique, donnees = Path(sys.argv[1]), Path(sys.argv[2])
par_forme = defaultdict(list)
with open(lexique, encoding="utf-8") as f:
    for ligne in csv.DictReader(f, delimiter="\t"):
        par_forme[ligne["ortho"]].append(ligne)


def table(nom: str) -> list[dict]:
    return yaml.safe_load((donnees / "francais" / f"{nom}.yaml").read_text(encoding="utf-8"))["lignes"]


def entrees(forme: str, cgram: str) -> list[dict]:
    return [e for e in par_forme.get(forme, []) + par_forme.get(forme.replace("œ", "oe"), []) if e["cgram"] == cgram]


def convient(e: dict, genre: str | None, nombre: str | None, lemme: str | None) -> bool:
    return ((genre is None or e["genre"] in (genre, "")) and (nombre is None or e["nombre"] in (nombre, ""))
            and (lemme is None or e["lemme"] == lemme))


ecarts, rares, remarques, n = [], [], [], 0


def verifier(quoi: str, forme: str, cgram: str, genre=None, nombre=None, lemme=None) -> None:
    """Le genre et le nombre doivent correspondre (une faute sinon) ; le lemme, seulement en remarque."""
    global n
    n += 1
    trouvees = entrees(forme, cgram)
    vu = ", ".join(f"{e['genre'] or '?'}{e['nombre'] or '?'} lemme {e['lemme']}" for e in trouvees)
    if not trouvees:
        ecarts.append(f"{quoi} : « {forme} » absent de Lexique ({cgram})")
    elif not any(convient(e, genre, nombre, None) for e in trouvees):
        ecarts.append(f"{quoi} : « {forme} » attendu {genre or ''}{nombre or ''}, Lexique : {vu}")
    elif lemme and not any(convient(e, genre, nombre, lemme) for e in trouvees):
        remarques.append(f"{quoi} : « {forme} » rangé par Lexique sous un autre lemme ({vu})")


for l in table("noms"):
    verifier(f"nom {l['nom']}", l["nom"], "NOM", l["genre"], "s")
    if l["pluriel"] != l["nom"]:  # un nom invariable (souris, ours) : rien de plus à vérifier
        verifier(f"pluriel de {l['nom']}", l["pluriel"], "NOM", l["genre"], "p", l["nom"])
    autre = "f" if l["genre"] == "m" else "m"
    if any(e["genre"] == autre for e in entrees(l["nom"], "NOM")):
        ecarts.append(f"nom {l['nom']} : Lexique le donne aussi au {'féminin' if autre == 'f' else 'masculin'} (ambigu)")
    freq = max((float(e["freqlemlivres"] or 0) for e in entrees(l["nom"], "NOM")), default=0)
    if freq < 2:
        rares.append(f"{l['nom']} ({freq:g} par million)")
for l in table("adjectifs"):
    for cle, (genre, nombre) in {"ms": ("m", "s"), "fs": ("f", "s"), "mp": ("m", "p"), "fp": ("f", "p")}.items():
        verifier(f"adjectif {l['ms']} ({cle})", l[cle], "ADJ", genre, nombre, l["ms"])
for l in table("pluriels_irreguliers"):
    verifier(f"pluriel de {l['singulier']}", l["pluriel"], "NOM", None, "p", l["singulier"])
    if par_forme.get(l["erreur"]):
        ecarts.append(f"erreur « {l['erreur']} » (pluriel de {l['singulier']}) : c'est un vrai mot "
                      f"({', '.join(sorted({e['cgram'] + ' ' + e['lemme'] for e in par_forme[l['erreur']]}))})")
for l in table("feminins"):
    cgram = "NOM" if l["nature"] == "nom" else "ADJ"
    n += 1
    if not any(convient(e, "f", "s", None) and e["lemme"] in (l["masculin"], l["feminin"])
               for e in entrees(l["feminin"], cgram)):
        ecarts.append(f"féminin de {l['masculin']} : « {l['feminin']} » pas trouvé au féminin singulier ({cgram})")
    if par_forme.get(l["erreur"]):
        ecarts.append(f"erreur « {l['erreur']} » (féminin de {l['masculin']}) : c'est un vrai mot "
                      f"({', '.join(sorted({e['cgram'] + ' ' + e['lemme'] for e in par_forme[l['erreur']]}))})")

print(f"{n} vérifications ; {len(ecarts)} écart(s)")
for e in ecarts:
    print("  ✗", e)
for r in remarques:
    print("  ~", r)
if rares:
    print(f"  mots rares (à regarder) : {', '.join(rares)}")
sys.exit(1 if ecarts else 0)
