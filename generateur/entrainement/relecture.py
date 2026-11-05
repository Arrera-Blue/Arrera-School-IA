"""La relecture du lot d'entraînement (plan IA, IA3, étape 2) : l'ordre de relecture, où en est la relecture, et ce qui
pourra entrer dans le jeu de données, source par source.

Deux sources : le lot d'entraînement, et la banque de l'enseignant (lue seulement : ses exercices acceptés, ses
corrections, ses motifs de rejet). Le fournisseur « maquette » ne compte pas : il ne produit que l'exemple.
"""

import json
from collections import defaultdict
from pathlib import Path

from generateur.entrainement import prerelecture
from generateur.moteur import banque

OBJECTIF_RELUS = 150     # plan IA, ⚖10 : l'échantillon que relit l'enseignant
OBJECTIF_ACCEPTES = 300  # plan IA, ⚖10 : avant d'entraîner


def instances(dossier: Path | None) -> list[dict]:
    """Les exercices d'un dossier rangé comme la banque, sans ceux de la maquette."""
    lues = []
    for fichier in sorted(dossier.glob("*.json")) if dossier and dossier.is_dir() else []:
        try:
            instance = json.loads(fichier.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(instance, dict) and (instance.get("meta") or {}).get("fournisseur") != "maquette":
            instance.setdefault("meta", {}).setdefault("id", fichier.stem)
            lues.append(instance)
    return lues


def corrections(instance: dict) -> int:
    """Les paires « avant → après » : questions corrigées à la main ou régénérées à la demande de l'enseignant."""
    meta = instance.get("meta") or {}
    return len(meta.get("modifications") or []) + len(meta.get("regenerations") or [])


def motifs_ecrits(instance: dict) -> int:
    """Les rejets dont l'enseignant a dit pourquoi (motifs cochés ou précisions)."""
    return sum(1 for d in (instance.get("meta") or {}).get("decisions") or []
               if d.get("statut") == banque.REJETE and (d.get("motif") or d.get("motifs")))


def ligne(instance: dict) -> dict:
    """Ce que l'ordre de relecture lit d'un exercice (les mêmes clés qu'une ligne de `banque.lister`), sans contrôle."""
    meta = instance.get("meta") or {}
    return {"id": meta.get("id"), "statut": banque.statut(instance), "matiere": instance.get("matiere"),
            "niveau": instance.get("niveau"), "date": meta.get("date"),
            "origine": "procedural" if meta.get("origine") == "procedural" else "modele",
            "prerelecture": banque.avis_en_bref(meta)}


def ordonner(lignes: list[dict]) -> list[dict]:
    """L'ordre de relecture. D'abord les exercices écrits par le modèle et pas encore relus, les matières et les classes
    en alternance (dans chacune, dans l'ordre de la génération) : l'échantillon relu couvre le français autant que les
    maths, alors que le lot compte trois fois plus de maths. Puis ceux du générateur procédural, justes par construction.
    Ceux que Claude a pré-relus (« en cours de relecture ») passent devant, dans ce même ordre. Enfin ceux déjà relus, du
    plus récent au plus ancien."""
    def date(l: dict) -> str:
        return l.get("date") or ""

    a_relire = [l for l in lignes if l.get("statut") == banque.GENERE]
    groupes: dict[tuple, list[dict]] = defaultdict(list)
    for l in sorted((l for l in a_relire if l.get("origine") != "procedural"), key=date):
        groupes[(l.get("matiere") or "", l.get("niveau") or "")].append(l)
    files = [groupes[cle] for cle in sorted(groupes)]
    alternes = [f[rang] for rang in range(max(map(len, files), default=0)) for f in files if rang < len(f)]
    proceduraux = sorted((l for l in a_relire if l.get("origine") == "procedural"), key=date)
    relus = sorted((l for l in lignes if l.get("statut") != banque.GENERE), key=date, reverse=True)
    a_relire = alternes + proceduraux
    return [l for l in a_relire if l.get("prerelecture")] + [l for l in a_relire if not l.get("prerelecture")] + relus


def compter(du_lot: list[dict], enseignant: list[dict]) -> dict:
    """Où en est la relecture du lot, et ce qui pourra entrer dans le jeu de données, source par source."""
    a_relire = [i for i in du_lot if banque.statut(i) == banque.GENERE]
    proceduraux = [i for i in a_relire if (i.get("meta") or {}).get("origine") == "procedural"
                   and banque.relecture(i)["valide"] and not corrections(i)]
    acceptes = sum(banque.statut(i) == banque.ACCEPTE for i in du_lot)
    acceptes_banque = sum(banque.statut(i) == banque.ACCEPTE for i in enseignant)
    return {
        "lot": len(du_lot), "relus": sum(bool((i.get("meta") or {}).get("decisions")) for i in du_lot),
        "objectif_relus": OBJECTIF_RELUS, "acceptes": acceptes,
        "rejetes": sum(banque.statut(i) == banque.REJETE for i in du_lot),
        "motifs": sum(motifs_ecrits(i) for i in du_lot), "corrections": sum(corrections(i) for i in du_lot),
        "corrections_claude": sum(bool(m.get("par")) for i in du_lot for m in (i.get("meta") or {}).get("modifications") or []),
        "a_relire": len(a_relire), "prerelecture": prerelecture.compter(du_lot),
        "jeu": {"acceptes_lot": acceptes, "proceduraux": len(proceduraux), "acceptes_banque": acceptes_banque,
                "total": acceptes + len(proceduraux) + acceptes_banque, "objectif": OBJECTIF_ACCEPTES,
                "paires": sum(corrections(i) for i in du_lot + enseignant),
                "motifs": sum(motifs_ecrits(i) for i in du_lot + enseignant)},
    }


def etat(lot: Path, banque_enseignant: Path | None) -> dict:
    """Pour l'interface du lot : `compter`, l'ordre de relecture des exercices à relire (leurs identifiants), et les
    motifs de rejet à cocher."""
    du_lot = instances(lot)
    resultat = compter(du_lot, instances(banque_enseignant))
    resultat["ordre"] = [l["id"] for l in ordonner([ligne(i) for i in du_lot]) if l["statut"] == banque.GENERE]
    resultat["motifs_de_rejet"] = [{"code": code, "libelle": libelle} for code, libelle in banque.MOTIFS_DE_REJET.items()]
    return resultat
