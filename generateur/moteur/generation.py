"""Demande → modèle → JSON validé (N1, N2, N3, N4), avec reprise des questions fautives → meta → HTML.

Pour le calcul mental, les pourcentages et Pythagore, la demande passe par le générateur procédural (étape
1.7) : le programme tire les nombres et calcule les réponses, le modèle ne fait que réécrire les énoncés.

Exemples (dans le conteneur, depuis /app) :
    python -m generateur.moteur.generation --demande "un QCM de 5 questions sur les fractions pour des 6e"
    python -m generateur.moteur.generation --matiere maths --niveau 4e --notion "théorème de Pythagore" --questions 5
    python -m generateur.moteur.generation --fournisseur maquette --notion test      # sans modèle
    python -m generateur.moteur.generation --notion pourcentages --fournisseur maquette --graine 42   # procédural, sans modèle
"""

import argparse
import copy
import json
import random
import re
import sys
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from generateur import procedural
from generateur.moteur import banque, config, machine, registre
from generateur.moteur.analyse import QUESTIONS_MAX, QUESTIONS_MIN, lire_classe, lire_nombre_de_questions
from generateur.moteur.fournisseurs import ErreurFournisseur, Fournisseur, creer
from generateur.moteur.validation import ErreurValidation, n3_pedagogie, n4_calcul, numero_de_question
from generateur.moteur.validation.fond import tolerant, valider_le_fond
from generateur.moteur.validation.n1_syntaxe import extraire_json
from generateur.moteur.validation.n2_schema import valider
from generateur.procedural import habillage

MODES = ("auto", "ia", "procedural")
ESSAIS_DE_TIRAGE = 20  # régénération d'une question procédurale : tirages au plus
ENSEIGNANT = "enseignant"  # « niveau » d'un défaut signalé par l'enseignant, et non par N1 → N4
# reçoit les étapes d'une génération : {"etape": "modele" | "ecriture" | "validation" | "refus" | "valide" | …,
# "message": « texte lisible », …} ; c'est ainsi que l'interface affiche la progression
Suivi = Callable[[dict], None]


class AucunGenerateur(Exception):
    """--mode procedural pour une demande qu'aucun générateur procédural ne couvre."""


def completer_demande(demande: dict) -> dict:
    """Le nombre de questions et la classe, lus dans la phrase de l'enseignant s'ils ne sont pas donnés
    (mêmes règles que l'extraction d'intention, moteur/analyse.py).

    Sans cela, le générateur procédural produisait 5 questions pour « un QCM de 15 questions » (recette 1.6,
    08/10) ; et le schéma donné au modèle n'imposait pas le nombre demandé."""
    texte = demande.get("demande_enseignant") or ""
    complete = dict(demande)
    nombre = lire_nombre_de_questions(texte)
    if not complete.get("nb_questions") and nombre is not None and QUESTIONS_MIN <= nombre <= QUESTIONS_MAX:
        complete["nb_questions"] = nombre
    if not complete.get("niveau") and (classe := lire_classe(texte)):
        complete["niveau"] = classe
    return complete


def schema_de_sortie(schema: dict, demande: dict) -> dict:
    """Schéma passé au modèle : sans « meta », et resserré sur ce que la demande impose déjà."""
    s = copy.deepcopy(schema)
    s["properties"].pop("meta", None)
    if demande.get("nb_questions"):
        s["properties"]["questions"]["minItems"] = s["properties"]["questions"]["maxItems"] = demande["nb_questions"]
    for champ in ("matiere", "niveau"):
        if demande.get(champ):
            s["properties"][champ] = {"enum": [demande[champ]]}
    return s


def construire_messages(type_exo: registre.TypeExercice, demande: dict) -> list[dict]:
    """Ce qui ne change jamais d'abord (consignes, schéma générique, exemple), la demande à la fin : le début
    du message est le même pour toutes les demandes, et son traitement est réutilisé d'une génération à
    l'autre (cache d'Ollama tant que le modèle est chargé, cache sur disque de llama.cpp). Le schéma resserré
    sur la demande (nombre de questions, classe) n'est pas écrit ici : il est imposé à la génération."""
    utilisateur = (
        "Schéma JSON à respecter :\n"
        f"{json.dumps(schema_de_sortie(type_exo.schema, {}), ensure_ascii=False, indent=2)}\n\n"
        "Exemple d'une sortie valide :\n"
        f"{json.dumps(type_exo.exemple, ensure_ascii=False, indent=2)}\n\n"
        "Demande :\n"
        f"{json.dumps(demande, ensure_ascii=False, indent=2)}"
    )
    return [{"role": "system", "content": type_exo.prompt}, {"role": "user", "content": utilisateur}]


def schema_partiel(schema: dict, nombre: int) -> dict:
    """Schéma d'une reprise : seulement les questions à remplacer, ni plus ni moins."""
    questions = copy.deepcopy(schema["properties"]["questions"])
    questions["minItems"] = questions["maxItems"] = nombre
    return {"type": "object", "required": ["questions"], "additionalProperties": False,
            "properties": {"questions": questions}}


def _enumerer(numeros: list[int]) -> str:
    """[2] → « la question 2 » ; [2, 4] → « les questions 2 et 4 »."""
    if len(numeros) == 1:
        return f"la question {numeros[0]}"
    return f"les questions {', '.join(map(str, numeros[:-1]))} et {numeros[-1]}"


def message_de_reprise(defauts: list[str], a_remplacer: list[int] | None, format_refuse: list[str],
                       enseignant: bool = False) -> str:
    """Ce qu'on dit au modèle pour qu'il corrige : les messages de N1 → N4, tels quels, puis la consigne.
    `enseignant` : ce n'est pas la vérification qui refuse, c'est l'enseignant qui demande une autre question."""
    lignes = ["L'enseignant a relu l'exercice et demande une autre question :" if enseignant
              else "Ta réponse a été refusée par la vérification automatique :"]
    lignes += [f"- {d}" for d in defauts]
    if format_refuse:
        lignes += ["", "Ta dernière correction n'était pas utilisable :"] + [f"- {d}" for d in format_refuse]
    lignes.append("")
    if a_remplacer is None:
        lignes.append("Corrige ces défauts et renvoie l'exercice complet, au format JSON demandé.")
    else:
        k = len(a_remplacer)
        ordre = "" if k == 1 else ", dans cet ordre"
        lignes.append(
            f"Écris {k} nouvelle{'s' if k > 1 else ''} question{'s' if k > 1 else ''} pour remplacer "
            f"{_enumerer(a_remplacer)}{ordre}. Même notion et même niveau ; ne reprends aucune des autres "
            "questions de l'exercice ; respecte toutes les règles du message système. Réponds uniquement par un "
            f"objet JSON de la forme {{\"questions\": [...]}}, avec exactement {k} question{'s' if k > 1 else ''}.")
    return "\n".join(lignes)


def questions_a_remplacer(erreur: ErreurValidation) -> list[int] | None:
    """Les numéros des questions en faute, ou None si un défaut ne concerne pas une question précise
    (titre, JSON illisible…) : il faut alors reprendre l'exercice entier."""
    if erreur.niveau in ("N1", "N2") or not erreur.questions or any(_numero(m) == 0 for m in erreur.erreurs):
        return None
    return sorted(erreur.questions)


def identifiant(type_: str, instance: dict, horodatage: str = "%Y%m%d-%H%M%S") -> str:
    texte = unicodedata.normalize("NFKD", instance.get("notion") or instance.get("titre") or "exercice")
    slug = re.sub(r"[^a-z0-9]+", "-", texte.encode("ascii", "ignore").decode().lower()).strip("-")[:40]
    return f"{type_}-{slug}-{instance.get('niveau', '')}-{datetime.now():{horodatage}}"


_numero = numero_de_question


def creer_fournisseur(nom: str | None = None) -> Fournisseur:
    """Le fournisseur `nom` (défaut : le premier de `fournisseurs.ordre`), réglé d'après config.yaml."""
    cfg = config.charger()
    nom = nom or cfg["fournisseurs"]["ordre"][0]
    reglages = dict(cfg["fournisseurs"].get(nom, {}))
    if nom in ("ollama", "llamacpp"):
        reglages["temperature"] = cfg["generation"]["temperature"]
    return creer(nom, reglages)


def _signaler(suivi: Suivi | None, **evenement) -> None:
    """Prévient l'interface (phase 3) : `evenement` porte au moins `etape` et un `message` lisible."""
    if suivi is not None:
        suivi(evenement)


def _au_fil(suivi: Suivi, sur: int | None, entete: str) -> Callable[[str], None]:
    """Reçoit la réponse du modèle morceau par morceau (llama.cpp) et en déduit la question en cours
    d'écriture : chaque question commence par la clé « enonce »."""
    etat = {"texte": "", "vu": 0, "questions": 0, "morceaux": 0}

    def recevoir(morceau: str) -> None:
        etat["texte"] += morceau
        etat["morceaux"] += 1
        avant = etat["questions"]
        while (i := etat["texte"].find('"enonce"', etat["vu"])) != -1:
            etat["questions"] += 1
            etat["vu"] = i + 1
        etat["vu"] = max(etat["vu"], len(etat["texte"]) - len('"enonce"'))
        if etat["questions"] != avant or etat["morceaux"] % 20 == 0:
            n = etat["questions"]
            quoi = f"question {n} sur {sur}" if n and sur else (f"question {n}" if n else "début de la réponse")
            suivi({"etape": "ecriture", "message": f"{entete} : écriture, {quoi}…", "question": n, "sur": sur,
                   "tokens": etat["morceaux"]})
    return recevoir


@dataclass
class _Etat:
    """Ce que la boucle génération + reprises fait évoluer, d'un appel au modèle à l'autre."""
    instance: dict | None = None       # dernier exercice complet et bien formé (N1, N2)
    precedent: str = ""                # ce que le modèle a « dit » en dernier, pour prolonger la conversation
    defauts: ErreurValidation | None = None
    format_refuse: list[str] = field(default_factory=list)  # N1/N2 d'une reprise ratée : redit au modèle ensuite
    par_question: list[int] = field(default_factory=list)
    reprises: list[dict] = field(default_factory=list)
    appels: list[dict] = field(default_factory=list)        # un par appel au modèle : durée, tokens (étape 1.5)
    duree_totale: float = 0.0
    brut: str = ""
    tentative: int = 0
    avertissements: list[str] = field(default_factory=list)
    bilan_n4: dict = field(default_factory=dict)
    # régénération : la seule question que le modèle a le droit de réécrire. Sinon, un doublon entre la nouvelle
    # question 2 et la question 4 ferait réécrire la 4 (N3 signale la seconde d'un doublon), que l'enseignant
    # n'a pas demandé de changer
    seules: list[int] | None = None


def _generer_et_reprendre(fournisseur: Fournisseur, messages: list[dict], schema: dict, tentatives_max: int,
                          etat: _Etat, suivi: Suivi | None = None,
                          controle: Callable[[dict], None] | None = None,
                          valider_fond: Callable[[dict], tuple[list[str], dict]] | None = None) -> _Etat:
    """La boucle commune à la génération et à la régénération d'une question : un appel au modèle, N1/N2, puis
    N3/N4 ; les questions refusées sont renvoyées au modèle, au plus `tentatives_max` appels.

    `etat.instance` vide : le premier appel écrit l'exercice entier. Rempli, avec `etat.defauts` : chaque appel
    est une reprise (l'enseignant a demandé de remplacer une question). `valider_fond` remplace N3/N4 (la
    régénération tolère les défauts déjà présents ailleurs) ; `controle` ajoute une vérification après (lève
    ErreurValidation). En sortie, `etat.defauts` vaut None si l'exercice est accepté ;
    sinon, il porte les derniers défauts."""
    depart = etat.instance is not None
    for tentative in range(1, tentatives_max + 1):
        etat.tentative = tentative
        reprise = depart or tentative > 1
        a_remplacer = None
        if not reprise:
            appel, schema_appel = messages, schema
            entete = "Génération"
            _signaler(suivi, etape="modele", tentative=tentative, tentatives_max=tentatives_max,
                      message=f"Le modèle lit la demande ({fournisseur.nom}, {fournisseur.modele})…")
        else:
            a_remplacer = etat.seules or (questions_a_remplacer(etat.defauts) if etat.instance is not None else None)
            quoi = _enumerer(a_remplacer) if a_remplacer else "l'exercice entier"
            numero = tentative if depart else tentative - 1
            sur_reprises = tentatives_max if depart else tentatives_max - 1
            # une régénération demandée par l'enseignant n'est pas une reprise après erreur : « essai »
            entete = f"{'Essai' if depart else 'Reprise'} {numero}/{sur_reprises}"
            print(f"→ {entete.lower()} : {quoi}…", flush=True)
            _signaler(suivi, etape="modele", tentative=tentative, tentatives_max=tentatives_max,
                      questions=a_remplacer, message=f"{entete} : le modèle réécrit {quoi}…")
            appel = messages + [{"role": "assistant", "content": etat.precedent},
                                {"role": "user", "content": message_de_reprise(
                                    etat.defauts.erreurs, a_remplacer, etat.format_refuse,
                                    enseignant=etat.defauts.niveau == ENSEIGNANT)}]
            schema_appel = schema_partiel(schema, len(a_remplacer)) if a_remplacer else schema

        bornes = schema_appel["properties"]["questions"]
        sur = bornes.get("maxItems") if bornes.get("minItems") == bornes.get("maxItems") else None
        fournisseur.au_fil = _au_fil(suivi, sur, entete) if suivi is not None else None
        debut = time.monotonic()
        try:
            etat.brut = fournisseur.generer(appel, schema_appel)
        finally:
            fournisseur.au_fil = None
        duree = round(time.monotonic() - debut, 1)
        etat.duree_totale += duree
        etat.appels.append({"tentative": tentative, "duree_s": duree, **(fournisseur.compteurs or {})})
        print(f"→ réponse reçue en {duree} s{detail_appel(fournisseur.compteurs)}", flush=True)
        _signaler(suivi, etape="validation", message=f"Réponse reçue en {duree} s : vérification N1 → N4…")

        trace = {"tentative": tentative, "questions": a_remplacer or "toutes",
                 "erreurs": list(etat.defauts.erreurs) if etat.defauts else [], "duree_s": duree}
        # 1. la réponse est-elle bien formée (N1, N2) ?
        try:
            if a_remplacer:
                partiel = extraire_json(etat.brut)
                valider(partiel, schema_appel)
                remplacees = [etat.instance["questions"][n - 1] for n in a_remplacer]
                instance = copy.deepcopy(etat.instance)
                for n, q in zip(a_remplacer, partiel["questions"]):
                    instance["questions"][n - 1] = q
                    etat.par_question[n - 1] += 1
                etat.instance = instance
                trace |= {"resultat": "questions remplacées", "questions_remplacees": remplacees}
                etat.precedent = json.dumps(etat.instance, ensure_ascii=False, indent=2)
            else:
                nouvelle = extraire_json(etat.brut)
                valider(nouvelle, schema)
                if reprise:
                    trace |= {"resultat": "exercice regénéré",
                              "questions_remplacees": etat.instance["questions"] if etat.instance else None}
                etat.par_question = [p + 1 for p in etat.par_question] if etat.instance and len(
                    etat.par_question) == len(nouvelle["questions"]) else [1] * len(nouvelle["questions"])
                etat.instance, etat.precedent = nouvelle, etat.brut
            etat.format_refuse = []
        except ErreurValidation as e:
            if reprise:
                etat.reprises.append(trace | {"resultat": f"réponse inutilisable ({e.niveau})",
                                              "erreurs_reponse": e.erreurs})
            print(f"✗ tentative {tentative} : réponse inutilisable ({e.niveau}) — {e.erreurs[0]}", flush=True)
            _signaler(suivi, etape="refus", erreurs=e.erreurs,
                      message=f"Tentative {tentative} : réponse inutilisable ({e.niveau}) — {e.erreurs[0]}")
            if etat.instance is None:
                etat.defauts, etat.precedent = e, etat.brut
            else:
                etat.format_refuse = e.erreurs
            continue
        if reprise:
            etat.reprises.append(trace)

        # 2. le fond est-il juste (N3, N4) ?
        try:
            etat.avertissements, etat.bilan_n4 = (valider_fond or valider_le_fond)(etat.instance)
            if controle is not None:
                controle(etat.instance)
        except ErreurValidation as e:
            etat.defauts = e
            quoi = _enumerer(list(e.questions)) if e.questions else "l'exercice"
            _signaler(suivi, etape="refus", erreurs=e.erreurs,
                      message=f"Tentative {tentative} refusée ({e.niveau}) : {quoi}")
            if tentative < tentatives_max:  # le dernier refus est détaillé par l'appelant
                print(f"✗ tentative {tentative} refusée ({e.niveau}) : {quoi}", flush=True)
                for message in e.erreurs:
                    print(f"   - {message}", flush=True)
            continue
        etat.defauts = None
        _signaler(suivi, etape="valide", message="Exercice validé : N1 → N4 passés")
        break
    return etat


def generer(demande: dict, type_: str = "qcm", nom_fournisseur: str | None = None, mode: str = "auto",
            graine: int | None = None, suivi: Suivi | None = None) -> dict:
    """Génère l'exercice, puis reprend les questions refusées par N3 ou N4 sans regénérer les autres.

    La reprise prolonge la conversation : le modèle revoit sa réponse, lit les messages de la validation et
    ne renvoie que les questions à remplacer. Le reste de l'exercice est conservé, puis tout est revalidé
    (une nouvelle question peut dupliquer une ancienne). Au plus `tentatives_max` appels au modèle.

    `mode` : « auto » confie au générateur procédural les demandes qu'il couvre, « ia » ne passe jamais par lui,
    « procedural » l'exige. `graine` rend un exercice procédural reproductible. `suivi` reçoit les étapes de la
    génération (interface enseignant).
    """
    demande = completer_demande(demande)
    notion = procedural.aiguiller(demande) if mode != "ia" and type_ == "qcm" else None
    if mode == "procedural" and notion is None:
        raise AucunGenerateur(f"aucun générateur procédural ne couvre cette demande (disponibles : "
                              f"{', '.join(procedural.notions())}) ; une seule notion par exercice")
    cfg = config.charger()
    fournisseur = creer_fournisseur(nom_fournisseur)
    if notion is not None:
        return generer_procedural(demande, notion, fournisseur, graine, suivi)
    tentatives_max = max(1, int(cfg["generation"].get("tentatives_max", 1)))

    type_exo = registre.charger(type_)
    schema = schema_de_sortie(type_exo.schema, demande)
    messages = construire_messages(type_exo, demande)

    print(f"→ génération par {fournisseur.nom} ({fournisseur.modele})… cela peut prendre plusieurs minutes", flush=True)
    etat = _generer_et_reprendre(fournisseur, messages, schema, tentatives_max, _Etat(), suivi)

    if etat.defauts is not None:
        # on garde la réponse fautive : c'est elle qu'il faut regarder pour corriger le prompt, et elle
        # compte dans les mesures (taux d'erreur du modèle, point de décision de N4)
        ecrire_brut(etat.brut)
        try:
            etat.defauts.rejet = enregistrer_rejet(etat.defauts, etat.brut, etat.instance, demande, type_, fournisseur,
                                                   round(etat.duree_totale, 1), etat.tentative, etat.reprises,
                                                   etat.appels)
        except OSError as erreur_disque:  # ne jamais masquer le rejet lui-même
            print(f"⚠ rejet non enregistré : {erreur_disque}", file=sys.stderr)
        raise etat.defauts

    instance = etat.instance
    instance["meta"] = {
        "id": identifiant(type_, instance),
        "fournisseur": fournisseur.nom,
        "modele": fournisseur.modele,
        "machine": machine.decrire(),
        "date": datetime.now().isoformat(timespec="seconds"),
        "duree_s": round(etat.duree_totale, 1),
        "tentatives": etat.tentative,
        "tentatives_par_question": etat.par_question,
        "reprises": etat.reprises,
        "appels": etat.appels,
        "validation": {"n1": True, "n2": True, "n3": True, **etat.bilan_n4},
        "avertissements": etat.avertissements,
        "statut": "genere",
        "prompt_origine": demande.get("demande_enseignant") or demande,
        "demande": demande,
    }
    return instance


def detail_appel(compteurs: dict | None) -> str:
    """« (1 830 tokens lus, 412 écrits ; chargement 0.1 s) », ou rien si le fournisseur ne compte pas."""
    if not compteurs or "tokens_ecrits" not in compteurs:
        return ""
    lus = f"{compteurs['tokens_lus']} tokens lus, " if "tokens_lus" in compteurs else ""
    chargement = f" ; chargement {compteurs['chargement_s']} s" if "chargement_s" in compteurs else ""
    durees = (f", lecture {compteurs['lecture_s']} s, écriture {compteurs['ecriture_s']} s"
              if "lecture_s" in compteurs and "ecriture_s" in compteurs else "")
    return f" ({lus}{compteurs['tokens_ecrits']} écrits{chargement}{durees})"


def generer_procedural(demande: dict, notion: str, fournisseur, graine: int | None = None,
                       suivi: Suivi | None = None) -> dict:
    """Étape 1.7 : le programme tire les questions, le modèle réécrit les énoncés, puis N2, N3 et N4 contrôlent.

    Une question que N3 ou N4 refuse après habillage reprend son énoncé-gabarit ; refusée avec son
    énoncé-gabarit, elle est tirée à nouveau. Le modèle n'est appelé qu'une fois : aucune reprise ne passe par
    lui. `fournisseur` « maquette » : pas d'habillage, l'exercice garde ses énoncés-gabarits."""
    module = procedural.notions()[notion]
    graine = graine if graine is not None else random.SystemRandom().randrange(1_000_000)
    rng = random.Random(graine)
    niveau = demande.get("niveau") or module.NIVEAU
    nombre = demande.get("nb_questions") or 5
    debut = time.monotonic()

    squelettes = procedural.tirer(notion, nombre, rng)
    print(f"→ génération procédurale ({module.NOTION}) : {nombre} questions tirées (graine {graine})", flush=True)
    _signaler(suivi, etape="tirage", message=f"Générateur procédural ({module.NOTION}) : {nombre} questions "
                                              "tirées, calculs faits par le programme")
    habillage_min = int(config.charger()["generation"].get("habillage_min", 1))
    if fournisseur.nom != "maquette" and sum(s.habillable for s in squelettes) >= habillage_min:
        _signaler(suivi, etape="habillage", message="Le modèle réécrit les énoncés en situation concrète "
                                                     "(les nombres ne changent pas)…")
    habille = habillage.habiller(squelettes, niveau, None if fournisseur.nom == "maquette" else fournisseur,
                                 habillage_min)
    if habille.appel:
        print(f"→ réponse reçue en {habille.appel['duree_s']} s{detail_appel(habille.appel)}", flush=True)
    enonces, par_question = habille.enonces, habille.par_question
    instance = procedural.assembler(notion, niveau, squelettes, enonces, rng)
    # N2 : le générateur doit produire un QCM conforme au schéma, comme le modèle
    valider(instance, schema_de_sortie(registre.charger("qcm").schema, demande))

    for _ in range(3):
        try:
            avertissements, bilan_n4 = valider_le_fond(instance)
            break
        except ErreurValidation as e:
            fautives = sorted(e.questions) or [i + 1 for i, h in enumerate(par_question) if h["habillage"] == "modele"]
            deja = {s.cle for s in squelettes}
            for n in fautives:
                i, message = n - 1, next((m for m in e.erreurs if _numero(m) == n), e.erreurs[0])
                if par_question[i]["habillage"] == "modele":
                    enonces[i] = squelettes[i].enonce
                    par_question[i] = {"habillage": "gabarit", "refus": f"{e.niveau} : {message}"}
                    print(f"   ⚠ question {n} : refusée après habillage ({e.niveau}) → énoncé-gabarit", flush=True)
                else:
                    genre = next(g for g in module.GENRES if squelettes[i].genre.endswith(f".{g.__name__}"))
                    squelettes[i] = procedural.tirer_une(genre, rng, deja)
                    enonces[i] = squelettes[i].enonce
                    par_question[i] = {"habillage": "gabarit", "retiree": message}
                    print(f"   ⚠ question {n} : refusée ({e.niveau}) → tirée à nouveau", flush=True)
                instance["questions"][i] = procedural.question(squelettes[i], enonces[i], rng)
    else:
        raise ErreurValidation(e.niveau, e.erreurs, e.questions)  # un bug du générateur : à corriger, pas à cacher

    appels = [habille.appel] if habille.appel else []
    instance["meta"] = {
        "id": identifiant("qcm", instance),
        "fournisseur": fournisseur.nom if appels else "procedural",
        "modele": fournisseur.modele if appels else None,
        "machine": machine.decrire(),
        "date": datetime.now().isoformat(timespec="seconds"),
        "duree_s": round(time.monotonic() - debut, 1),
        "tentatives": 1,
        "origine": "procedural",
        "generateur": notion,
        "graine": graine,
        "questions": [{"genre": s.genre, **h} for s, h in zip(squelettes, par_question)],
        "appels": appels,
        "validation": {"n1": True, "n2": True, "n3": True, **bilan_n4},
        "avertissements": avertissements,
        "statut": "genere",
        "prompt_origine": demande.get("demande_enseignant") or demande,
        "demande": demande,
    }
    _signaler(suivi, etape="valide", message="Exercice validé : N2 → N4 passés")
    return instance


def _demande_d_origine(instance: dict) -> dict:
    """La demande qui a produit l'exercice : enregistrée dans le meta depuis le 13/10, reconstituée avant."""
    meta = instance.get("meta") or {}
    if meta.get("demande"):
        return dict(meta["demande"])
    demande = {"type": instance.get("type", "qcm"), "matiere": instance.get("matiere"),
               "niveau": instance.get("niveau"), "notion": instance.get("notion"),
               "nb_questions": len(instance.get("questions") or [])}
    if isinstance(meta.get("prompt_origine"), str):
        demande["demande_enseignant"] = meta["prompt_origine"]
    return {k: v for k, v in demande.items() if v}


def regenerer_question(instance: dict, numero: int, motif: str | None = None, nom_fournisseur: str | None = None,
                       suivi: Suivi | None = None) -> dict:
    """Remplace la question `numero` (à partir de 1) à la demande de l'enseignant, sans toucher aux autres.

    Exercice écrit par le modèle : la conversation de la génération est reconstituée (même demande, l'exercice
    actuel comme réponse du modèle), le modèle écrit une seule question, revalidée avec tout l'exercice
    (N2 → N4), et reprise si elle est refusée. Exercice procédural : une nouvelle question du même genre est
    tirée par le programme, juste par construction ; son énoncé reste l'énoncé-gabarit.

    Renvoie une nouvelle instance, à faire accepter de nouveau (statut « genere ») ; l'ancienne question est
    gardée dans meta.regenerations. Lève ErreurValidation si aucune question acceptable n'a été obtenue :
    l'exercice reste alors tel qu'il était."""
    questions = instance.get("questions") or []
    if not 1 <= numero <= len(questions):
        raise ValueError(f"question {numero} inexistante : l'exercice en compte {len(questions)}")
    motif = (motif or "").strip()[:200] or None
    meta = copy.deepcopy(instance.get("meta") or {})
    ancienne = questions[numero - 1]
    debut = time.monotonic()
    valider_fond = tolerant(instance, numero)
    if meta.get("origine") == "procedural":
        nouvelle, trace = _retirer_question(instance, numero, meta, valider_fond, suivi)
    else:
        nouvelle, trace = _reecrire_question(instance, numero, motif, nom_fournisseur, valider_fond, suivi)
    meta.setdefault("regenerations", []).append({
        "question": numero, "date": datetime.now().isoformat(timespec="seconds"), "motif": motif,
        "duree_s": round(time.monotonic() - debut, 1), "ancienne": ancienne, **trace})
    avertissements, bilan_n4 = valider_fond(nouvelle)
    meta["validation"] = {"n1": True, "n2": True, "n3": True, **bilan_n4}
    meta["avertissements"] = avertissements
    meta["statut"] = banque.GENERE  # l'exercice a changé : l'enseignant doit l'accepter de nouveau
    nouvelle["meta"] = meta
    _signaler(suivi, etape="valide", message=f"Question {numero} remplacée : N1 → N4 passés")
    return nouvelle


def _reecrire_question(instance: dict, numero: int, motif: str | None, nom_fournisseur: str | None,
                       valider_fond: Callable, suivi: Suivi | None) -> tuple[dict, dict]:
    demande = _demande_d_origine(instance)
    type_exo = registre.charger(instance.get("type", "qcm"))
    schema = schema_de_sortie(type_exo.schema, demande)
    messages = construire_messages(type_exo, demande)
    exercice = {k: v for k, v in instance.items() if k != "meta"}
    defaut = f"question {numero} : l'enseignant demande de la remplacer par une autre question"
    etat = _Etat(instance=exercice, precedent=json.dumps(exercice, ensure_ascii=False, indent=2),
                 defauts=ErreurValidation(ENSEIGNANT, [defaut + (f" ({motif})" if motif else "")], (numero,)),
                 par_question=[1] * len(exercice["questions"]), seules=[numero])
    fournisseur = creer_fournisseur(nom_fournisseur)
    tentatives_max = max(1, int(config.charger()["generation"].get("tentatives_max", 1)))
    ancienne = n3_pedagogie.normaliser(instance["questions"][numero - 1]["enonce"])

    def differente(candidate: dict) -> None:
        # le modèle peut récrire à l'identique la question que l'enseignant veut voir partir
        if n3_pedagogie.normaliser(candidate["questions"][numero - 1]["enonce"]) == ancienne:
            raise ErreurValidation("N3", [f"question {numero} : c'est la question que l'enseignant a demandé de "
                                          "remplacer ; écris une question différente"], (numero,))

    print(f"→ régénération de la question {numero} par {fournisseur.nom} ({fournisseur.modele})…", flush=True)
    etat = _generer_et_reprendre(fournisseur, messages, schema, tentatives_max, etat, suivi, differente, valider_fond)
    if etat.defauts is not None:
        # jamais remplacée : le dernier défaut est celui de la réponse illisible, ou celui de N3/N4
        erreurs = etat.format_refuse or etat.defauts.erreurs
        niveau = etat.defauts.niveau if etat.defauts.niveau != ENSEIGNANT else "N1/N2"
        raise ErreurValidation(niveau, [f"la question {numero} n'a pas pu être remplacée après {etat.tentative} "
                                        f"tentative(s)"] + erreurs, (numero,))
    trace = {"origine": "modele", "fournisseur": fournisseur.nom, "modele": fournisseur.modele,
             "machine": machine.decrire(), "tentatives": etat.tentative, "appels": etat.appels,
             "reprises": etat.reprises}
    return etat.instance, trace


def _retirer_question(instance: dict, numero: int, meta: dict, valider_fond: Callable,
                      suivi: Suivi | None) -> tuple[dict, dict]:
    module = procedural.notions()[meta["generateur"]]
    origines = meta.get("questions") or []
    nom_du_genre = origines[numero - 1]["genre"] if numero <= len(origines) else ""
    genre = next((g for g in module.GENRES if nom_du_genre.endswith(f".{g.__name__}")), None)
    graine = random.SystemRandom().randrange(1_000_000)
    rng = random.Random(graine)
    ancienne = instance["questions"][numero - 1]
    schema = schema_de_sortie(registre.charger("qcm").schema, _demande_d_origine(instance))
    _signaler(suivi, etape="tirage", message=f"Générateur procédural ({module.NOTION}) : nouveau tirage de la "
                                              f"question {numero}")
    derniere = None
    for _ in range(ESSAIS_DE_TIRAGE):
        squelette = procedural.tirer_une(genre or rng.choice(module.GENRES), rng, set())
        question = procedural.question(squelette, squelette.enonce, rng)
        if question["enonce"] == ancienne["enonce"]:
            continue
        nouvelle = {k: v for k, v in instance.items() if k != "meta"}
        nouvelle["questions"] = list(nouvelle["questions"])
        nouvelle["questions"][numero - 1] = question
        try:
            valider(nouvelle, schema)
            valider_fond(nouvelle)
        except ErreurValidation as e:  # une question en double avec une autre, par exemple : on tire à nouveau
            derniere = e
            continue
        meta["questions"] = list(origines)
        if numero <= len(origines):
            meta["questions"][numero - 1] = {"genre": squelette.genre, "habillage": "gabarit", "regeneree": True}
        return nouvelle, {"origine": "procedural", "graine": graine}
    raise ErreurValidation(derniere.niveau if derniere else "N3",
                           [f"la question {numero} n'a pas pu être tirée à nouveau"] + (derniere.erreurs if derniere
                                                                                       else []), (numero,))


def enregistrer_rejet(erreur: ErreurValidation, brut: str, instance: dict | None, demande: dict, type_: str,
                      fournisseur, duree: float, tentatives: int = 1, reprises: list[dict] | None = None,
                      appels: list[dict] | None = None) -> Path:
    """Conserve chaque génération rejetée dans banque/rejets/.

    Sans cela, les exercices faux disparaîtraient et le taux d'erreur du modèle serait invisible : c'est
    pourtant la donnée du point de décision de N4 (docs/etapes/etape-1.3.md §8). Quand N1 et N2 sont
    passés, l'instance est gardée telle quelle : N4 pourra être recalculée dessus à chaque amélioration.
    Les reprises tentées, avec les versions fautives des questions remplacées, sont gardées aussi.
    """
    rejet = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "fournisseur": fournisseur.nom,
        "modele": fournisseur.modele,
        "machine": machine.decrire(),
        "duree_s": duree,
        "tentatives": tentatives,
        "reprises": reprises or [],
        "appels": appels or [],
        "demande": demande,
        "niveau": erreur.niveau,
        "erreurs": erreur.erreurs,
        "questions": list(erreur.questions),
        "instance": instance,
        "brut": brut,
    }
    chemin = config.chemin("rejets") / f"{identifiant(type_, instance or {}, '%Y%m%d-%H%M%S-%f')}.json"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(rejet, ensure_ascii=False, indent=2), encoding="utf-8")
    return chemin


def resume_n4(instance: dict) -> str:
    """« N4 : 4 question(s) recalculée(s) et juste(s), 1 à relire (question 3) »."""
    statuts = instance["meta"]["validation"]["n4_questions"]
    if instance.get("matiere") != "maths":
        return "N4 : hors maths, aucun calcul recalculé : le fond est à relire par l'enseignant"
    verifiees = statuts.count(n4_calcul.VERIFIE)
    a_relire = [str(n) for n, s in enumerate(statuts, start=1) if s == n4_calcul.A_RELIRE]
    texte = f"N4 : {verifiees} question(s) recalculée(s) et juste(s)"
    if a_relire:
        texte += f", {len(a_relire)} à relire (question {', '.join(a_relire)})"
    return texte


def ecrire_brut(brut: str) -> Path:
    chemin = config.chemin("sortie") / "derniere_reponse_brute.txt"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(brut, encoding="utf-8")
    return chemin


def main() -> None:
    parser = argparse.ArgumentParser(description="Générer un exercice avec le modèle d'IA.")
    parser.add_argument("--type", default="qcm", help=f"type d'exercice ({', '.join(registre.lister())})")
    parser.add_argument("--demande", help="la demande en langage naturel, telle que l'écrirait l'enseignant")
    parser.add_argument("--matiere")
    parser.add_argument("--niveau")
    parser.add_argument("--notion")
    parser.add_argument("--questions", type=int, help="nombre de questions")
    parser.add_argument("--difficulte", choices=["facile", "moyen", "difficile"])
    parser.add_argument("--fournisseur", help="ollama (défaut) ou maquette")
    parser.add_argument("--sortie", type=Path, help="fichier HTML produit (défaut : sortie/<id>.html)")
    parser.add_argument("--mode", choices=MODES, default="auto",
                        help="auto (défaut) : générateur procédural pour les notions qu'il couvre ; ia : toujours le "
                             "modèle ; procedural : toujours le générateur")
    parser.add_argument("--graine", type=int, help="graine du générateur procédural (exercice reproductible)")
    args = parser.parse_args()

    if not (args.demande or args.notion):
        parser.error("indiquer au moins --demande ou --notion")

    demande = {
        "type": args.type,
        "demande_enseignant": args.demande,
        "matiere": args.matiere,
        "niveau": args.niveau,
        "notion": args.notion,
        "nb_questions": args.questions,
        "difficulte": args.difficulte,
    }
    demande = {k: v for k, v in demande.items() if v is not None}

    try:
        instance = generer(demande, args.type, args.fournisseur, args.mode, args.graine)
    except ErreurFournisseur as e:
        sys.exit(f"✗ fournisseur : {e}")
    except AucunGenerateur as e:
        sys.exit(f"✗ {e}")
    except ErreurValidation as e:
        print(f"✗ réponse du modèle rejetée ({e.niveau}), après toutes les tentatives :", file=sys.stderr)
        for erreur in e.erreurs:
            print(f"   - {erreur}", file=sys.stderr)
        print(f"   réponse brute conservée dans {config.chemin('sortie') / 'derniere_reponse_brute.txt'}", file=sys.stderr)
        sys.exit(f"   rejet enregistré (il compte dans les mesures) : {e.rejet}")

    json_chemin, html_chemin = banque.enregistrer(instance, args.sortie)
    meta = instance["meta"]
    if meta.get("origine") == "procedural":
        habilles = sum(q["habillage"] == "modele" for q in meta["questions"])
        print(f"✓ {len(instance['questions'])} questions — « {instance['titre']} » — calculs justes par construction "
              f"({habilles} énoncé(s) réécrit(s) par le modèle, {meta['duree_s']} s)")
    elif meta["tentatives"] > 1:
        print(f"✓ {len(instance['questions'])} questions — « {instance['titre']} » — en {meta['tentatives']} "
              f"tentatives, {meta['duree_s']} s au total")
    else:
        print(f"✓ {len(instance['questions'])} questions — « {instance['titre']} »")
    for avertissement in instance["meta"]["avertissements"]:
        print(f"   ⚠ à relire : {avertissement}")
    print(f"   {resume_n4(instance)}")
    print(f"   JSON : {json_chemin}")
    print(f"   HTML : {html_chemin}")


if __name__ == "__main__":
    main()
