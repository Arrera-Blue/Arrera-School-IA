"""Le bilan des données d'entraînement (plan IA, IA3.1) : ce que la génération de nuit a produit, ce que l'enseignant a
relu, et ce qui pourra entrer dans le jeu de données, source par source (les comptes : relecture.py).
"""

from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median

from generateur.entrainement import relecture
from generateur.moteur import banque


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

    du_lot, enseignant = relecture.instances(lot), relecture.instances(banque_enseignant)
    c = relecture.compter(du_lot, enseignant)
    a_relire = [i for i in du_lot if banque.statut(i) == banque.GENERE]
    lignes += ["", "## La relecture", "",
               f"- Exercices dans le lot : {c['lot']}.",
               f"- Relus : {c['relus']} sur {c['objectif_relus']} visés ; acceptés {c['acceptes']}, rejetés "
               f"{c['rejetes']} (dont {c['motifs']} motif(s) de rejet écrit(s)).",
               f"- Corrections (questions corrigées à la main ou régénérées) : {c['corrections']}.",
               f"- Pré-relecture (Claude) : {c['prerelecture']['en_cours']} en cours de relecture, à décider ; "
               f"{c['prerelecture']['decides']} décidé(s) après son avis, suivi {c['prerelecture']['suivis']} fois.",
               f"- À relire : {c['a_relire']}, dont {sum(bool(banque.signalements(i)) for i in a_relire)} avec un "
               "signalement (contre-vérification, ancrage, calcul à relire, avertissement)."]
    jeu = c["jeu"]
    lignes += ["", "## Ce qui pourra entrer dans le jeu de données", "",
               "| Source | Nombre |", "|---|---|",
               f"| Lot : relus et acceptés | {jeu['acceptes_lot']} |",
               f"| Lot : procéduraux sans erreur, non relus (calculs justes par construction) | {jeu['proceduraux']} |",
               f"| Banque de l'enseignant : exercices acceptés | {jeu['acceptes_banque']} |",
               f"| Paires avant → après (lot et banque) | {jeu['paires']} |",
               f"| Motifs de rejet écrits (lot et banque) | {jeu['motifs']} |",
               "", f"Exercices acceptés (relus, procéduraux, banque) : **{jeu['total']}** ; objectif avant d'entraîner : "
                   f"{jeu['objectif']}. La part de chaque source sera fixée à la mise en forme du jeu (IA3.3)."]
    return "\n".join(lignes) + "\n"
