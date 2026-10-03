"""Demande → modèle → JSON validé (N1, N2, N3, N4) → bloc meta → exercice HTML.

Exemples (dans le conteneur, depuis /app) :
    python -m generateur.moteur.generation --demande "un QCM de 5 questions sur les fractions pour des 6e"
    python -m generateur.moteur.generation --matiere maths --niveau 4e --notion "théorème de Pythagore" --questions 5
    python -m generateur.moteur.generation --fournisseur maquette --notion test      # sans modèle
"""

import argparse
import copy
import json
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from generateur.moteur import config, registre, rendu
from generateur.moteur.fournisseurs import ErreurFournisseur, creer
from generateur.moteur.validation import ErreurValidation, n3_pedagogie, n4_calcul
from generateur.moteur.validation.n1_syntaxe import extraire_json
from generateur.moteur.validation.n2_schema import valider


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


def identifiant(type_: str, instance: dict, horodatage: str = "%Y%m%d-%H%M%S") -> str:
    texte = unicodedata.normalize("NFKD", instance.get("notion") or instance.get("titre") or "exercice")
    slug = re.sub(r"[^a-z0-9]+", "-", texte.encode("ascii", "ignore").decode().lower()).strip("-")[:40]
    return f"{type_}-{slug}-{instance.get('niveau', '')}-{datetime.now():{horodatage}}"


def generer(demande: dict, type_: str = "qcm", nom_fournisseur: str | None = None) -> dict:
    cfg = config.charger()
    nom_fournisseur = nom_fournisseur or cfg["fournisseurs"]["ordre"][0]
    reglages = dict(cfg["fournisseurs"].get(nom_fournisseur, {}))
    if nom_fournisseur == "ollama":
        reglages["temperature"] = cfg["generation"]["temperature"]
    fournisseur = creer(nom_fournisseur, reglages)

    type_exo = registre.charger(type_)
    schema = schema_de_sortie(type_exo.schema, demande)
    messages = construire_messages(type_exo, schema, demande)

    print(f"→ génération par {fournisseur.nom} ({fournisseur.modele})… cela peut prendre plusieurs minutes", flush=True)
    debut = time.monotonic()
    brut = fournisseur.generer(messages, schema)
    duree = round(time.monotonic() - debut, 1)
    print(f"→ réponse reçue en {duree} s", flush=True)

    instance = None
    try:
        instance = extraire_json(brut)
        valider(instance, schema)
        avertissements = n3_pedagogie.valider(instance)
        bilan_n4 = n4_calcul.valider(instance)
    except ErreurValidation as e:
        # on garde la réponse fautive : c'est elle qu'il faut regarder pour corriger le prompt, et elle
        # compte dans les mesures (taux d'erreur du modèle, point de décision de N4)
        ecrire_brut(brut)
        try:
            e.rejet = enregistrer_rejet(e, brut, instance, demande, type_, fournisseur, duree)
        except OSError as erreur_disque:  # ne jamais masquer le rejet lui-même
            print(f"⚠ rejet non enregistré : {erreur_disque}", file=sys.stderr)
        raise

    instance["meta"] = {
        "id": identifiant(type_, instance),
        "fournisseur": fournisseur.nom,
        "modele": fournisseur.modele,
        "date": datetime.now().isoformat(timespec="seconds"),
        "duree_s": duree,
        "tentatives": 1,
        "validation": {"n1": True, "n2": True, "n3": True, **bilan_n4},
        "avertissements": avertissements,
        "statut": "genere",
        "prompt_origine": demande.get("demande_enseignant") or demande,
    }
    return instance


def enregistrer_rejet(erreur: ErreurValidation, brut: str, instance: dict | None, demande: dict, type_: str,
                      fournisseur, duree: float) -> Path:
    """Conserve chaque génération rejetée dans banque/rejets/.

    Sans cela, les exercices faux disparaîtraient et le taux d'erreur du modèle serait invisible : c'est
    pourtant la donnée du point de décision de N4 (docs/etapes/etape-1.3.md §8). Quand N1 et N2 sont
    passés, l'instance est gardée telle quelle : N4 pourra être recalculée dessus à chaque amélioration.
    """
    rejet = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "fournisseur": fournisseur.nom,
        "modele": fournisseur.modele,
        "duree_s": duree,
        "demande": demande,
        "niveau": erreur.niveau,
        "erreurs": erreur.erreurs,
        "questions": list(erreur.questions),
        "instance": instance if erreur.niveau not in ("N1", "N2") else None,
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
        instance = generer(demande, args.type, args.fournisseur)
    except ErreurFournisseur as e:
        sys.exit(f"✗ fournisseur : {e}")
    except ErreurValidation as e:
        print(f"✗ réponse du modèle rejetée ({e.niveau}) :", file=sys.stderr)
        for erreur in e.erreurs:
            print(f"   - {erreur}", file=sys.stderr)
        print(f"   réponse brute conservée dans {config.chemin('sortie') / 'derniere_reponse_brute.txt'}", file=sys.stderr)
        sys.exit(f"   rejet enregistré (il compte dans les mesures) : {e.rejet}")

    ident = instance["meta"]["id"]
    json_chemin = config.chemin("banque") / f"{ident}.json"
    json_chemin.parent.mkdir(parents=True, exist_ok=True)
    json_chemin.write_text(json.dumps(instance, ensure_ascii=False, indent=2), encoding="utf-8")

    html_chemin = rendu.ecrire(rendu.rendre(instance, args.type), args.sortie or config.chemin("sortie") / f"{ident}.html")
    print(f"✓ {len(instance['questions'])} questions — « {instance['titre']} »")
    for avertissement in instance["meta"]["avertissements"]:
        print(f"   ⚠ à relire : {avertissement}")
    print(f"   {resume_n4(instance)}")
    print(f"   JSON : {json_chemin}")
    print(f"   HTML : {html_chemin}")


if __name__ == "__main__":
    main()
