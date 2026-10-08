"""Relire un exercice généré, accepté ou rejeté : la recette (étape 1.6) se fait question par question.

Affiche, pour chaque question : le verdict de N4, l'origine (programme ou modèle), l'énoncé, les propositions
avec la bonne réponse marquée, l'explication ; puis les avertissements, et les versions refusées par N3 ou N4
avant reprise. Rien n'est recalculé : c'est ce que l'enseignant recevrait, tel qu'enregistré.

    python -m generateur.outils.relire                       # le dernier exercice produit
    python -m generateur.outils.relire --depuis 2026-10-08   # tous ceux produits depuis cette date
    python -m generateur.outils.relire banque/instances/qcm-fractions-6e-20261007-141737.json
"""

import argparse
import json
from pathlib import Path

from generateur.moteur import config

MARQUES = {"verifie": "✔ vérifiée", "faux": "✘ FAUSSE", "a_relire": "? à relire"}


def _question(n: int, q: dict, statut: str | None, origine: dict | None) -> list[str]:
    entete = f"{n}. [{MARQUES.get(statut, statut or '—')}]"
    if origine:
        source = "modèle" if origine.get("habillage") == "modele" else "gabarit"
        entete += f" {origine['genre']}, énoncé : {source}"
        if "refus" in origine:
            entete += f" (réécriture refusée : {origine['refus']})"
    lignes = [entete, f"   {q['enonce']}"]
    for i, p in enumerate(q["propositions"]):
        lignes.append(f"   {'→' if i == q['index_correct'] else ' '} {p}")
    lignes.append(f"   Explication : {q['explication']}")
    return lignes


def presenter(document: dict, chemin: Path | None = None) -> str:
    """Un exercice accepté (banque/instances) ou un rejet (banque/rejets), mis en forme pour la relecture."""
    rejet = "instance" in document and "niveau" in document and "erreurs" in document
    instance = document.get("instance") if rejet else document
    meta = (document if rejet else document.get("meta")) or {}
    lignes = [f"=== {chemin.name if chemin else 'exercice'}"]
    if rejet:
        lignes.append(f"REJETÉ ({document['niveau']}) après {document.get('tentatives', 1)} tentative(s) :")
        lignes += [f"   - {e}" for e in document["erreurs"]]
        if instance is None:
            lignes.append("   (réponse illisible : aucune instance à relire)")
            return "\n".join(lignes)
    origine = "générateur procédural" if meta.get("origine") == "procedural" else "modèle"
    lignes.append(f"« {instance.get('titre')} » — {instance.get('matiere')}, {instance.get('niveau')} — {origine}, "
                  f"{meta.get('duree_s', '?')} s, {meta.get('tentatives', 1)} tentative(s)")
    if meta.get("graine") is not None:
        lignes.append(f"graine {meta['graine']} (rejouer : --graine {meta['graine']})")
    statuts = (meta.get("validation") or {}).get("n4_questions") or []
    origines = meta.get("questions") if meta.get("origine") == "procedural" else None
    for n, q in enumerate(instance["questions"], start=1):
        lignes.append("")
        lignes += _question(n, q, statuts[n - 1] if n <= len(statuts) else None,
                            origines[n - 1] if origines else None)
    if meta.get("avertissements"):
        lignes += ["", "Avertissements de N3 :"] + [f"   ⚠ {a}" for a in meta["avertissements"]]
    refusees = [(r, v) for r in meta.get("reprises") or [] for v in r.get("questions_remplacees") or []]
    if refusees:
        lignes += ["", "Versions refusées avant reprise :"]
        for reprise, v in refusees:
            lignes.append(f"   (tentative {reprise['tentative'] - 1}) {v['enonce']} → "
                          f"{v['propositions'][v['index_correct']]}  |  {' · '.join(v['propositions'])}")
    return "\n".join(lignes)


def a_relire(fichier: Path | None, depuis: str | None) -> list[Path]:
    dossiers = [config.chemin("banque"), config.chemin("rejets")]
    tous = [f for d in dossiers if d.is_dir() for f in d.glob("*.json")]
    if fichier:
        return [fichier]
    if depuis:
        def date(f: Path) -> str:
            d = json.loads(f.read_text(encoding="utf-8"))
            return (d.get("meta") or {}).get("date") or d.get("date") or ""
        return sorted((f for f in tous if date(f) >= depuis), key=lambda f: f.stat().st_mtime)
    return sorted(tous, key=lambda f: f.stat().st_mtime)[-1:]


def main() -> None:
    parser = argparse.ArgumentParser(description="Relire un exercice généré, question par question.")
    parser.add_argument("fichier", nargs="?", type=Path, help="un exercice (défaut : le dernier produit)")
    parser.add_argument("--depuis", metavar="AAAA-MM-JJ", help="tous les exercices produits depuis cette date")
    args = parser.parse_args()
    fichiers = a_relire(args.fichier, args.depuis)
    if not fichiers:
        print("aucun exercice à relire")
    for f in fichiers:
        print(presenter(json.loads(f.read_text(encoding="utf-8")), f), end="\n\n")


if __name__ == "__main__":
    main()
