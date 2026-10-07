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
from datetime import datetime
from pathlib import Path

from generateur import procedural
from generateur.moteur import config, registre, rendu
from generateur.moteur.fournisseurs import ErreurFournisseur, creer
from generateur.moteur.validation import ErreurValidation, n3_pedagogie, n4_calcul
from generateur.moteur.validation.n1_syntaxe import extraire_json
from generateur.moteur.validation.n2_schema import valider
from generateur.procedural import habillage

MODES = ("auto", "ia", "procedural")


class AucunGenerateur(Exception):
    """--mode procedural pour une demande qu'aucun générateur procédural ne couvre."""


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


def construire_messages(type_exo: registre.TypeExercice, schema: dict, demande: dict) -> list[dict]:
    utilisateur = (
        "Schéma JSON à respecter :\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
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


def message_de_reprise(defauts: list[str], a_remplacer: list[int] | None, format_refuse: list[str]) -> str:
    """Ce qu'on dit au modèle pour qu'il corrige : les messages de N1 → N4, tels quels, puis la consigne."""
    lignes = ["Ta réponse a été refusée par la vérification automatique :"]
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


def _numero(message: str) -> int:
    m = re.match(r"question (\d+)", message)
    return int(m[1]) if m else 0


def valider_le_fond(instance: dict) -> tuple[list[str], dict]:
    """N3 puis N4, en signalant TOUS les défauts d'un coup.

    S'arrêter au premier niveau en faute cacherait les erreurs de calcul quand N3 a déjà rejeté : la
    reprise sur erreur (1.4) corrigerait une partie des questions, puis échouerait sur le reste à l'essai
    suivant. Cas réel du 03/10 : N3 rejetait les questions 1, 2 et 4, et l'erreur de calcul de la
    question 3 n'apparaissait pas.
    """
    rejets: list[ErreurValidation] = []
    avertissements, bilan_n4 = [], {}
    try:
        avertissements = n3_pedagogie.valider(instance)
    except ErreurValidation as e:
        rejets.append(e)
    try:
        bilan_n4 = n4_calcul.valider(instance)
    except ErreurValidation as e:
        # « plusieurs propositions conviennent » sur une question déjà rejetée par N3 : même défaut, pas deux fois
        deja = set(rejets[0].questions) if rejets else set()
        messages = [m for m in e.erreurs if not (_numero(m) in deja and "plusieurs propositions conviennent" in m)]
        rejets.append(ErreurValidation("N4", messages, tuple(_numero(m) for m in messages)))
    rejets = [r for r in rejets if r.erreurs]
    if rejets:
        raise ErreurValidation(", ".join(r.niveau for r in rejets),
                               sorted((m for r in rejets for m in r.erreurs), key=_numero),
                               tuple(sorted({q for r in rejets for q in r.questions})))
    return avertissements, bilan_n4


def generer(demande: dict, type_: str = "qcm", nom_fournisseur: str | None = None, mode: str = "auto",
            graine: int | None = None) -> dict:
    """Génère l'exercice, puis reprend les questions refusées par N3 ou N4 sans regénérer les autres.

    La reprise prolonge la conversation : le modèle revoit sa réponse, lit les messages de la validation et
    ne renvoie que les questions à remplacer. Le reste de l'exercice est conservé, puis tout est revalidé
    (une nouvelle question peut dupliquer une ancienne). Au plus `tentatives_max` appels au modèle.

    `mode` : « auto » confie au générateur procédural les demandes qu'il couvre, « ia » ne passe jamais par lui,
    « procedural » l'exige. `graine` rend un exercice procédural reproductible.
    """
    notion = procedural.aiguiller(demande) if mode != "ia" and type_ == "qcm" else None
    if mode == "procedural" and notion is None:
        raise AucunGenerateur(f"aucun générateur procédural ne couvre cette demande (disponibles : "
                              f"{', '.join(procedural.notions())}) ; une seule notion par exercice")
    cfg = config.charger()
    nom_fournisseur = nom_fournisseur or cfg["fournisseurs"]["ordre"][0]
    reglages = dict(cfg["fournisseurs"].get(nom_fournisseur, {}))
    if nom_fournisseur == "ollama":
        reglages["temperature"] = cfg["generation"]["temperature"]
    fournisseur = creer(nom_fournisseur, reglages)
    if notion is not None:
        return generer_procedural(demande, notion, fournisseur, graine)
    tentatives_max = max(1, int(cfg["generation"].get("tentatives_max", 1)))

    type_exo = registre.charger(type_)
    schema = schema_de_sortie(type_exo.schema, demande)
    messages = construire_messages(type_exo, schema, demande)

    print(f"→ génération par {fournisseur.nom} ({fournisseur.modele})… cela peut prendre plusieurs minutes", flush=True)
    instance: dict | None = None       # dernier exercice complet et bien formé (N1, N2)
    precedent = ""                     # ce que le modèle a « dit » en dernier, pour prolonger la conversation
    defauts: ErreurValidation | None = None
    format_refuse: list[str] = []      # N1/N2 d'une reprise ratée : redit au modèle à la tentative suivante
    par_question: list[int] = []
    reprises: list[dict] = []
    appels: list[dict] = []            # un par appel au modèle : durée, tokens (étape 1.5)
    duree_totale = 0.0
    brut = ""

    for tentative in range(1, tentatives_max + 1):
        a_remplacer = None
        if tentative == 1:
            appel, schema_appel = messages, schema
        else:
            a_remplacer = questions_a_remplacer(defauts) if instance is not None else None
            quoi = _enumerer(a_remplacer) if a_remplacer else "l'exercice entier"
            print(f"→ reprise {tentative - 1}/{tentatives_max - 1} : {quoi}…", flush=True)
            appel = messages + [{"role": "assistant", "content": precedent},
                                {"role": "user", "content": message_de_reprise(defauts.erreurs, a_remplacer, format_refuse)}]
            schema_appel = schema_partiel(schema, len(a_remplacer)) if a_remplacer else schema

        debut = time.monotonic()
        brut = fournisseur.generer(appel, schema_appel)
        duree = round(time.monotonic() - debut, 1)
        duree_totale += duree
        appels.append({"tentative": tentative, "duree_s": duree, **(fournisseur.compteurs or {})})
        print(f"→ réponse reçue en {duree} s{detail_appel(fournisseur.compteurs)}", flush=True)

        trace = {"tentative": tentative, "questions": a_remplacer or "toutes",
                 "erreurs": list(defauts.erreurs) if defauts else [], "duree_s": duree}
        # 1. la réponse est-elle bien formée (N1, N2) ?
        try:
            if a_remplacer:
                partiel = extraire_json(brut)
                valider(partiel, schema_appel)
                remplacees = [instance["questions"][n - 1] for n in a_remplacer]
                instance = copy.deepcopy(instance)
                for n, q in zip(a_remplacer, partiel["questions"]):
                    instance["questions"][n - 1] = q
                    par_question[n - 1] += 1
                trace |= {"resultat": "questions remplacées", "questions_remplacees": remplacees}
                precedent = json.dumps(instance, ensure_ascii=False, indent=2)
            else:
                nouvelle = extraire_json(brut)
                valider(nouvelle, schema)
                if tentative > 1:
                    trace |= {"resultat": "exercice regénéré",
                              "questions_remplacees": instance["questions"] if instance else None}
                par_question = [p + 1 for p in par_question] if instance and len(par_question) == len(
                    nouvelle["questions"]) else [1] * len(nouvelle["questions"])
                instance, precedent = nouvelle, brut
            format_refuse = []
        except ErreurValidation as e:
            if tentative > 1:
                reprises.append(trace | {"resultat": f"réponse inutilisable ({e.niveau})", "erreurs_reponse": e.erreurs})
            print(f"✗ tentative {tentative} : réponse inutilisable ({e.niveau}) — {e.erreurs[0]}", flush=True)
            if instance is None:
                defauts, precedent = e, brut
            else:
                format_refuse = e.erreurs
            continue
        if tentative > 1:
            reprises.append(trace)

        # 2. le fond est-il juste (N3, N4) ?
        try:
            avertissements, bilan_n4 = valider_le_fond(instance)
        except ErreurValidation as e:
            defauts = e
            if tentative < tentatives_max:  # le dernier refus est détaillé par l'appelant
                quoi = _enumerer(list(e.questions)) if e.questions else "l'exercice"
                print(f"✗ tentative {tentative} refusée ({e.niveau}) : {quoi}", flush=True)
                for message in e.erreurs:
                    print(f"   - {message}", flush=True)
            continue
        defauts = None
        break

    if defauts is not None:
        # on garde la réponse fautive : c'est elle qu'il faut regarder pour corriger le prompt, et elle
        # compte dans les mesures (taux d'erreur du modèle, point de décision de N4)
        ecrire_brut(brut)
        try:
            defauts.rejet = enregistrer_rejet(defauts, brut, instance, demande, type_, fournisseur,
                                              round(duree_totale, 1), tentative, reprises, appels)
        except OSError as erreur_disque:  # ne jamais masquer le rejet lui-même
            print(f"⚠ rejet non enregistré : {erreur_disque}", file=sys.stderr)
        raise defauts

    instance["meta"] = {
        "id": identifiant(type_, instance),
        "fournisseur": fournisseur.nom,
        "modele": fournisseur.modele,
        "date": datetime.now().isoformat(timespec="seconds"),
        "duree_s": round(duree_totale, 1),
        "tentatives": tentative,
        "tentatives_par_question": par_question,
        "reprises": reprises,
        "appels": appels,
        "validation": {"n1": True, "n2": True, "n3": True, **bilan_n4},
        "avertissements": avertissements,
        "statut": "genere",
        "prompt_origine": demande.get("demande_enseignant") or demande,
    }
    return instance


def detail_appel(compteurs: dict | None) -> str:
    """« (1 830 tokens lus, 412 écrits ; chargement 0.1 s) », ou rien si le fournisseur ne compte pas."""
    if not compteurs or "tokens_ecrits" not in compteurs:
        return ""
    lus = f"{compteurs['tokens_lus']} tokens lus, " if "tokens_lus" in compteurs else ""
    chargement = f" ; chargement {compteurs['chargement_s']} s" if "chargement_s" in compteurs else ""
    return f" ({lus}{compteurs['tokens_ecrits']} écrits{chargement})"


def generer_procedural(demande: dict, notion: str, fournisseur, graine: int | None = None) -> dict:
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
    habille = habillage.habiller(squelettes, niveau, None if fournisseur.nom == "maquette" else fournisseur)
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
    }
    return instance


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

    ident = instance["meta"]["id"]
    json_chemin = config.chemin("banque") / f"{ident}.json"
    json_chemin.parent.mkdir(parents=True, exist_ok=True)
    json_chemin.write_text(json.dumps(instance, ensure_ascii=False, indent=2), encoding="utf-8")

    html_chemin = rendu.ecrire(rendu.rendre(instance, args.type), args.sortie or config.chemin("sortie") / f"{ident}.html")
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
