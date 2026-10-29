"""Le bilan des données d'entraînement (plan IA, IA3.1) : ce que la génération de nuit a produit, ce que l'enseignant a
relu, et ce qui pourra entrer dans le jeu de données, source par source.

Deux sources : le lot d'entraînement, et la banque de l'enseignant (lue seulement : ses exercices acceptés, ses
corrections, ses motifs de rejet). Le fournisseur « maquette » ne compte pas : il ne produit que l'exemple.
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median

from generateur.entrainement.nuit import signalements
from generateur.moteur import banque

OBJECTIF_ACCEPTES = 300  # plan IA, ⚖10 : avant d'entraîner
OBJECTIF_RELUS = 150


def _instances(dossier: Path) -> list[dict]:
    instances = []
    for fichier in sorted(dossier.glob("*.json")) if dossier.is_dir() else []:
        try:
            instance = json.loads(fichier.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(instance, dict) and (instance.get("meta") or {}).get("fournisseur") != "maquette":
            instances.append(instance)
    return instances


def _corrections(instance: dict) -> int:
    """Les paires « avant → après » : questions corrigées à la main ou régénérées à la demande de l'enseignant."""
    meta = instance.get("meta") or {}
    return len(meta.get("modifications") or []) + len(meta.get("regenerations") or [])


def _motifs(instance: dict) -> int:
    return sum(1 for d in (instance.get("meta") or {}).get("decisions") or [] if d.get("statut") == banque.REJETE
               and d.get("motif"))


def _duree(secondes: float) -> str:
    h, m = divmod(round(secondes / 60), 60)
    return f"{h} h {m:02d}" if h else f"{m} min"


def bilan(lot: Path, journal: list[dict], banque_enseignant: Path) -> str:
    """Le bilan en Markdown. `lot` : le dossier des exercices du lot ; `journal` : avancement.jsonl, lu."""
    derniers = {e["cle"]: e for e in journal if "cle" in e}  # une demande refaite : son dernier résultat
    resultats = Counter(e.get("resultat") for e in derniers.values())
    passes = Counter(e["passe"] for e in derniers.values() if e.get("resultat") != "erreur")
    durees = [e["duree_s"] for e in journal if e.get("duree_s") is not None]
    lignes = [f"# Données d'entraînement : bilan du {datetime.now():%d/%m/%Y %H:%M}", "", "## La génération de nuit", ""]
    if derniers:
        par_classe: dict[tuple, Counter] = {}
        for e in derniers.values():
            d = e.get("demande") or {}
            par_classe.setdefault((d.get("matiere"), d.get("niveau")), Counter())[e.get("resultat")] += 1
        lignes += [
            f"- Demandes faites : {sum(passes.values())} ("
            + ", ".join(f"passe {p} : {n}" for p, n in sorted(passes.items())) + ").",
            f"- Exercices gardés : {resultats['genere']} ; rejetés par N1 → N4 : {resultats['rejete']} ; demandes "
            f"refusées : {resultats['refuse']} ; erreurs, à refaire : {resultats['erreur']}.",
            f"- Durée : {median(durees):.0f} s par demande (médiane), {_duree(sum(durees))} en tout.", "",
            "| Matière | Classe | Gardés | Rejetés | Erreurs |", "|---|---|---|---|---|"]
        for (matiere, niveau), c in sorted(par_classe.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
            lignes.append(f"| {matiere} | {niveau} | {c['genere']} | {c['rejete'] + c['refuse']} | {c['erreur']} |")
    else:
        lignes.append("Aucune demande faite : `python -m generateur.entrainement nuit`.")

    du_lot = _instances(lot)
    statuts = Counter(banque.statut(i) for i in du_lot)
    relus = [i for i in du_lot if (i.get("meta") or {}).get("decisions")]
    a_relire = [i for i in du_lot if banque.statut(i) == banque.GENERE]
    procedurals = [i for i in a_relire if (i.get("meta") or {}).get("origine") == "procedural"
                   and banque.relecture(i)["valide"] and not _corrections(i)]
    lignes += ["", "## La relecture", "",
               f"- Exercices dans le lot : {len(du_lot)}.",
               f"- Relus : {len(relus)} sur {OBJECTIF_RELUS} visés ; acceptés {statuts[banque.ACCEPTE]}, rejetés "
               f"{statuts[banque.REJETE]} (dont {sum(_motifs(i) for i in du_lot)} motif(s) de rejet écrit(s)).",
               f"- Corrections (questions corrigées à la main ou régénérées) : {sum(_corrections(i) for i in du_lot)}.",
               f"- À relire : {len(a_relire)}, dont {sum(bool(signalements(i)) for i in a_relire)} avec un "
               "signalement (contre-vérification, ancrage, calcul à relire, avertissement)."]

    enseignant = _instances(banque_enseignant)
    acceptes_lot = statuts[banque.ACCEPTE]
    acceptes_enseignant = sum(banque.statut(i) == banque.ACCEPTE for i in enseignant)
    lignes += ["", "## Ce qui pourra entrer dans le jeu de données", "",
               "| Source | Nombre |", "|---|---|",
               f"| Lot : relus et acceptés | {acceptes_lot} |",
               f"| Lot : procéduraux sans erreur, non relus (calculs justes par construction) | {len(procedurals)} |",
               f"| Banque de l'enseignant : exercices acceptés | {acceptes_enseignant} |",
               f"| Paires avant → après (lot et banque) | {sum(_corrections(i) for i in du_lot + enseignant)} |",
               f"| Motifs de rejet écrits (lot et banque) | {sum(_motifs(i) for i in du_lot + enseignant)} |",
               "", f"Exercices acceptés (relus, procéduraux, banque) : "
                   f"**{acceptes_lot + len(procedurals) + acceptes_enseignant}** ; objectif avant d'entraîner : "
                   f"{OBJECTIF_ACCEPTES}. La part de chaque source sera fixée à la mise en forme du jeu (IA3.3)."]
    return "\n".join(lignes) + "\n"
