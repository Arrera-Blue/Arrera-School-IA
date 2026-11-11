"""Le second contrôle des conjugaisons (décision 7 du lot 1) : chaque ligne de `francais/conjugaisons.yaml` comparée à
Verbiste, par verbecc (installé à part, jamais dans le projet). Une forme différente, ou un verbe que verbecc ne connaît
que par prédiction : signalés.

Usage : <python où verbecc est installé> -I verifier_conjugaisons.py <conjugaisons.yaml>"""
import logging
import sys

import yaml
from verbecc import CompleteConjugator

logging.disable(logging.CRITICAL)
TEMPS = {"present": "présent", "imparfait": "imparfait", "futur": "futur-simple", "passe_compose": "passé-composé"}
PRONOMS = {"je": "1s", "tu": "2s", "il": "3s", "nous": "1p", "vous": "2p", "ils": "3p"}

def champ(entree, nom):
    """Un champ d'une entrée de verbecc (objet : `_person`, `_conjugations`…), valeur simple (« 1 », « s », « je »)."""
    valeur = getattr(entree, nom, None)
    valeur = getattr(entree, "_" + nom) if valeur is None or callable(valeur) else valeur
    return getattr(valeur, "value", valeur)


table = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
cg = CompleteConjugator(lang="fr")
connus = set(cg.get_infinitives())
attendu, ecarts, verbes = {}, [], sorted({l["infinitif"] for l in table["lignes"]})
for infinitif in verbes:
    if infinitif not in connus:
        ecarts.append(f"{infinitif} : absent du dictionnaire de Verbiste (forme seulement prédite)")
    for temps, nom in TEMPS.items():
        for entree in cg.conjugate_mood_tense(infinitif, "indicatif", nom, conjugate_pronouns=False):
            personne, nombre, genre, pronom = (champ(entree, c) for c in ("person", "number", "gender", "pronoun"))
            if pronom in ("on", "elle", "elles") or genre == "f":
                continue  # il, ils : le masculin, comme dans la table
            attendu[(infinitif, temps, personne + nombre)] = list(champ(entree, "conjugations"))
n = 0
for l in table["lignes"]:
    n += 1
    formes = attendu.get((l["infinitif"], l["temps"], PRONOMS[l["personne"]]))
    if formes is None:
        ecarts.append(f"{l['infinitif']}, {l['temps']}, {l['personne']} : Verbiste ne donne rien")
    elif l["forme"] not in formes:
        ecarts.append(f"{l['infinitif']}, {l['temps']}, {l['personne']} : table « {l['forme']} », Verbiste {formes}")
print(f"{n - len([e for e in ecarts if ' : table ' in e or 'ne donne rien' in e])} formes sur {n} identiques à Verbiste")
for e in ecarts:
    print("  ✗", e)
sys.exit(1 if ecarts else 0)
