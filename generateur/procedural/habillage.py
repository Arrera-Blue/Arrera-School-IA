"""Habillage : le modèle réécrit les énoncés-gabarits dans une situation concrète, sous contrôle.

Le modèle ne touche ni aux nombres, ni à la réponse, ni aux propositions. Chaque énoncé réécrit est contrôlé
(mêmes nombres, même sens, bonne forme) ; un énoncé refusé est remplacé par son énoncé-gabarit, juste par
construction. Sans modèle, ou si sa réponse est inutilisable, tout l'exercice garde ses énoncés-gabarits :
l'habillage n'est jamais une cause d'échec.
"""

import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from generateur.moteur.fournisseurs import ErreurFournisseur, Fournisseur
from generateur.moteur.validation import ErreurValidation
from generateur.moteur.validation.n1_syntaxe import extraire_json
from generateur.moteur.validation.n2_schema import valider
from generateur.moteur.validation.n3_pedagogie import (ADRESSE_WEB, COURRIEL, FIGURE_ABSENTE, TELEPHONE, normaliser,
                                                       valeur)
from generateur.moteur.validation.n4_calcul import VALEUR_ENONCE, preparer
from generateur.procedural import Squelette

PROMPT = Path(__file__).with_name("prompt_habillage.txt")
LONGUEUR_MAX = 300  # celle du schéma QCM
# un nombre écrit en lettres échappe au contrôle des nombres : « deux articles à 50 € » change le calcul
NOMBRE_EN_LETTRES = re.compile(r"\b(?:deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|treize|quatorze|"
                               r"quinze|seize|vingt|trente|quarante|cinquante|soixante|cent|mille|double|triple|"
                               r"moitiés?|tiers|quarts?|dizaines?|douzaines?|centaines?)\b", re.IGNORECASE)


@dataclass
class Habillage:
    enonces: list[str]
    par_question: list[dict]   # {"habillage": "modele" | "gabarit", "refus": "…"} pour chaque question
    appel: dict | None = None  # durée et compteurs de l'appel au modèle, s'il a eu lieu


def nombres(texte: str) -> Counter:
    """Les valeurs citées, comptées : « 50 € … 30 % » → {50: 1, 3/10: 1}, lues comme N4 les lit."""
    return Counter(valeur(m.group(0))[1] for m in VALEUR_ENONCE.finditer(preparer(texte)))


def question_finale(texte: str) -> str:
    return re.split(r"(?<=[.!?;:])\s+", texte.strip())[-1]


def controler(squelette: Squelette, texte: str) -> str | None:
    """La raison du refus de l'énoncé réécrit, ou None s'il est accepté."""
    texte = re.sub(r"\s+", " ", texte).strip()
    if not texte.endswith("?") or texte.count("?") != 1:
        return "une seule question, terminée par un point d'interrogation"
    if len(texte) > LONGUEUR_MAX:
        return "trop long"
    attendus, trouves = nombres(squelette.enonce), nombres(texte)
    if trouves != attendus:
        ajoutes, manquants = trouves - attendus, attendus - trouves
        return "nombres modifiés" + (f" (en plus : {len(ajoutes)})" if ajoutes else "") + \
            (f" (manquants : {len(manquants)})" if manquants else "")
    if m := NOMBRE_EN_LETTRES.search(texte):
        return f"nombre écrit en lettres : « {m.group(0)} »"
    if m := FIGURE_ABSENTE.search(texte):
        return f"renvoi à une figure : « {m.group(0)} »"
    if COURRIEL.search(texte) or TELEPHONE.search(texte) or ADRESSE_WEB.search(texte):
        return "donnée personnelle"
    minuscule, question = normaliser(texte), normaliser(question_finale(texte))
    for motif in squelette.obligatoires:
        if not re.search(motif, minuscule, re.IGNORECASE):
            return f"sens modifié : il manque « {motif} »"
    for motif in squelette.interdits:
        if m := re.search(motif, minuscule, re.IGNORECASE):
            return f"sens modifié : « {m.group(0)} »"
    for motif in squelette.demande:
        if not re.search(motif, question, re.IGNORECASE):
            return f"question modifiée : il manque « {motif} »"
    for motif in squelette.demande_interdits:
        if m := re.search(motif, question, re.IGNORECASE):
            return f"question modifiée : « {m.group(0)} »"
    return None


def schema(nombre: int) -> dict:
    return {"type": "object", "required": ["questions"], "additionalProperties": False,
            "properties": {"questions": {
                "type": "array", "minItems": nombre, "maxItems": nombre,
                "items": {"type": "object", "required": ["enonce"], "additionalProperties": False,
                          "properties": {"enonce": {"type": "string", "minLength": 5, "maxLength": LONGUEUR_MAX}}}}}}


def messages(squelettes: list[Squelette], niveau: str) -> list[dict]:
    donnees = {"niveau": niveau, "enonces": [s.enonce for s in squelettes]}
    return [{"role": "system", "content": PROMPT.read_text(encoding="utf-8")},
            {"role": "user", "content": json.dumps(donnees, ensure_ascii=False, indent=2)}]


def habiller(squelettes: list[Squelette], niveau: str, fournisseur: Fournisseur | None) -> Habillage:
    enonces = [s.enonce for s in squelettes]
    par_question = [{"habillage": "gabarit"} for _ in squelettes]
    a_habiller = [i for i, s in enumerate(squelettes) if s.habillable]
    if fournisseur is None or not a_habiller:
        return Habillage(enonces, par_question)

    print(f"→ habillage par {fournisseur.nom} ({fournisseur.modele})…", flush=True)
    schema_appel = schema(len(a_habiller))
    debut = time.monotonic()
    try:
        brut = fournisseur.generer(messages([squelettes[i] for i in a_habiller], niveau), schema_appel)
        reponse = extraire_json(brut)
        valider(reponse, schema_appel)
    except (ErreurFournisseur, ErreurValidation) as e:
        # le modèle est absent ou sa réponse illisible : l'exercice garde ses énoncés-gabarits
        raison = f"modèle indisponible ({e})" if isinstance(e, ErreurFournisseur) else "réponse du modèle illisible"
        print(f"   ⚠ habillage impossible : {raison} → énoncés-gabarits", flush=True)
        for i in a_habiller:
            par_question[i]["refus"] = raison
        return Habillage(enonces, par_question)
    duree = round(time.monotonic() - debut, 1)
    appel = {"duree_s": duree, **(fournisseur.compteurs or {})}

    for i, proposition in zip(a_habiller, reponse["questions"]):
        texte = re.sub(r"\s+", " ", proposition["enonce"]).strip()
        refus = controler(squelettes[i], texte)
        if refus is None:
            enonces[i], par_question[i] = texte, {"habillage": "modele"}
        else:
            # le texte refusé est gardé : c'est lui qui sert à régler le prompt et les contrôles
            par_question[i] |= {"refus": refus, "texte_refuse": texte}
            print(f"   ⚠ question {i + 1} : habillage refusé ({refus}) → énoncé-gabarit", flush=True)
    return Habillage(enonces, par_question, appel)
