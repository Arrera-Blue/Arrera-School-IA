"""La banque d'exercices : un fichier JSON par exercice dans banque/instances/, son rendu HTML dans sortie/.

Statuts (architecture §11.2, règle n° 5) : « genere » à la création, puis « accepte » ou « rejete » par
l'enseignant. Seuls les exercices acceptés pourront être publiés (phase 4). Chaque décision est gardée dans
meta.decisions : c'est la donnée du taux d'acceptation enseignant (phase 7).

Les générations refusées par N1 → N4 ne sont pas dans la banque : elles sont dans banque/rejets/.
"""

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

from generateur.moteur import config, rendu
from generateur.moteur.validation import numero_de_question

GENERE, ACCEPTE, REJETE = "genere", "accepte", "rejete"
STATUTS = (GENERE, ACCEPTE, REJETE)
DECISIONS = {"accepter": ACCEPTE, "rejeter": REJETE}
# ce que produit generation.identifiant : « qcm-fractions-6e-20261007-141737 » ; rien d'autre n'est un exercice
# (un identifiant sert à construire un chemin de fichier : « ../ » ne doit jamais y entrer)
IDENTIFIANT = re.compile(r"[a-z0-9][a-z0-9_-]{0,160}")  # « _ » : les types vrai_faux, texte_a_trous
# lecture-modification-écriture d'un exercice : l'interface sert plusieurs requêtes à la fois
_VERROU = threading.RLock()


class ExerciceInconnu(Exception):
    pass


def chemin(ident: str) -> Path:
    if not IDENTIFIANT.fullmatch(ident or ""):
        raise ExerciceInconnu(f"identifiant d'exercice invalide : {ident!r}")
    return config.chemin("banque") / f"{ident}.json"


def charger(ident: str) -> dict:
    fichier = chemin(ident)
    try:
        return json.loads(fichier.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ExerciceInconnu(f"exercice « {ident} » introuvable") from None
    except (OSError, json.JSONDecodeError) as e:
        raise ExerciceInconnu(f"exercice « {ident} » illisible : {e}") from None


def rendre(instance: dict) -> str:
    """Le fichier HTML autonome de l'exercice, tel que l'élève le recevra."""
    return rendu.rendre(instance, instance.get("type", "qcm"))


def _ecrire_atomique(fichier: Path, texte: str) -> None:
    """Jamais de fichier à moitié écrit : on écrit à côté, puis on remplace d'un coup."""
    fichier.parent.mkdir(parents=True, exist_ok=True)
    temporaire = fichier.with_name(f".{fichier.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporaire.write_text(texte, encoding="utf-8")
    os.replace(temporaire, fichier)


def ecrire(instance: dict, sortie: Path | None = None) -> tuple[Path, Path]:
    """Enregistre l'exercice (JSON) et son rendu (HTML, par défaut sortie/<id>.html). Renvoie les deux chemins."""
    ident = instance["meta"]["id"]
    html = rendre(instance)  # avant d'écrire quoi que ce soit : un exercice qui ne se rend pas n'entre pas
    with _VERROU:
        fichier = chemin(ident)
        _ecrire_atomique(fichier, json.dumps(instance, ensure_ascii=False, indent=2))
        page = sortie or config.chemin("sortie") / f"{ident}.html"
        _ecrire_atomique(page, html)
    return fichier, page


def enregistrer(instance: dict, sortie: Path | None = None) -> tuple[Path, Path]:
    """Un exercice neuf. L'identifiant est horodaté à la seconde : deux exercices de même notion produits dans
    la même seconde (le générateur procédural répond en 0 s) auraient le même ; le second reçoit alors « -2 »,
    au lieu d'écraser le premier."""
    with _VERROU:
        base = ident = instance["meta"]["id"]
        suivant = 2
        while chemin(ident).exists():
            ident, suivant = f"{base}-{suivant}", suivant + 1
        instance["meta"]["id"] = ident
        return ecrire(instance, sortie)


def decider(ident: str, decision: str, motif: str | None = None) -> dict:
    """« accepter » ou « rejeter » : le statut change, la décision est ajoutée à l'historique."""
    if decision not in DECISIONS:
        raise ValueError(f"décision inconnue : {decision!r} (accepter ou rejeter)")
    with _VERROU:
        instance = charger(ident)
        meta = instance.setdefault("meta", {"id": ident})
        meta["statut"] = DECISIONS[decision]
        meta.setdefault("decisions", []).append({"statut": meta["statut"], "date": _maintenant(),
                                                 "motif": (motif or "").strip()[:500] or None})
        _ecrire_atomique(chemin(ident), json.dumps(instance, ensure_ascii=False, indent=2))
    return instance


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def statut(instance: dict) -> str:
    return (instance.get("meta") or {}).get("statut") or GENERE


def resume(instance: dict) -> dict:
    """Une ligne de la liste de la banque."""
    meta = instance.get("meta") or {}
    n4 = (meta.get("validation") or {}).get("n4_questions") or []
    return {
        "id": meta.get("id"), "titre": instance.get("titre"), "matiere": instance.get("matiere"),
        "niveau": instance.get("niveau"), "notion": instance.get("notion"),
        "questions": len(instance.get("questions") or []), "statut": statut(instance), "date": meta.get("date"),
        "origine": "procedural" if meta.get("origine") == "procedural" else "modele",
        "fournisseur": meta.get("fournisseur"), "modele": meta.get("modele"), "duree_s": meta.get("duree_s"),
        "a_relire": 0 if meta.get("origine") == "procedural" else sum(s == "a_relire" for s in n4),
        "avertissements": len(meta.get("avertissements") or []),
    }


def lister(matiere: str | None = None, niveau: str | None = None, statut_voulu: str | None = None) -> list[dict]:
    """Les exercices de la banque, du plus récent au plus ancien, éventuellement filtrés."""
    dossier = config.chemin("banque")
    lignes = []
    for fichier in dossier.glob("*.json") if dossier.is_dir() else []:
        try:
            instance = json.loads(fichier.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ligne = resume(instance)
        ligne["id"] = ligne["id"] or fichier.stem
        if (matiere and ligne["matiere"] != matiere) or (niveau and ligne["niveau"] != niveau) or \
                (statut_voulu and ligne["statut"] != statut_voulu):
            continue
        lignes.append(ligne)
    return sorted(lignes, key=lambda l: l["date"] or "", reverse=True)


def relecture(instance: dict) -> dict:
    """Ce que l'enseignant doit savoir pour relire, question par question : N4, qui a écrit l'énoncé et fait
    le calcul (programme ou modèle), les avertissements de N3, les questions déjà régénérées.

    « a_relire » ne compte que les calculs du modèle que N4 n'a pas su refaire : un calcul du programme est
    juste par construction, même quand N4 ne reconnaît pas l'énoncé réécrit par le modèle (essai du 16/10 :
    3 questions de pourcentages annoncées « à relire » à tort)."""
    meta = instance.get("meta") or {}
    procedural = meta.get("origine") == "procedural"
    statuts = (meta.get("validation") or {}).get("n4_questions") or []
    origines = meta.get("questions") if procedural else None
    regenerees = {r.get("question") for r in meta.get("regenerations") or []}
    par_question: dict[int, list[str]] = {}
    generaux = []
    for avertissement in meta.get("avertissements") or []:
        n = numero_de_question(avertissement)
        if n:
            par_question.setdefault(n, []).append(avertissement)
        else:
            generaux.append(avertissement)
    questions = []
    for n, _ in enumerate(instance.get("questions") or [], start=1):
        origine = origines[n - 1] if origines and n <= len(origines) else {}
        questions.append({
            "numero": n,
            "n4": statuts[n - 1] if n <= len(statuts) else None,
            "calcul": "programme" if procedural else "modele",
            "enonce": ("modele" if origine.get("habillage") == "modele" else "programme") if procedural else "modele",
            "avertissements": par_question.get(n, []),
            "regeneree": n in regenerees,
        })
    return {"questions": questions, "avertissements": generaux, "procedural": procedural,
            "a_relire": sum(q["n4"] == "a_relire" and q["calcul"] == "modele" for q in questions)}
