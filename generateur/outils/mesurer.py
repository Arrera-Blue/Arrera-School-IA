"""Phase 2 : mesurer les modèles et les machines, à partir des meta déjà enregistrés.

Lit les exercices acceptés (banque/instances/) **et rejetés** (banque/rejets/) : sans les rejets, les échecs
seraient invisibles et les taux de réussite surestimés. Une ligne par chemin (modèle seul, ou générateur
procédural), par modèle et par machine, avec :
- les générations : acceptées au premier essai, acceptées après reprise, rejetées ;
- le nombre moyen d'appels au modèle (tentatives) ;
- la durée médiane d'une génération, et par question ;
- les vitesses médianes de lecture du prompt et d'écriture, en tokens par seconde (compteurs de l'étape 1.5,
  enregistrés depuis le 07/10 : les générations plus anciennes ne comptent que dans les durées) ;
- le chargement du modèle à froid.

La mémoire occupée ne figure pas dans les meta : elle se relève à part, pendant une génération.
Le fournisseur « maquette » est écarté : il ne mesure rien.

    python -m generateur.outils.mesurer
    python -m generateur.outils.mesurer --depuis 2026-10-08                 # seulement le prompt actuel
    python -m generateur.outils.mesurer --modele gemma-4-E4B_q4_0-it.gguf   # seulement ce modèle
"""

import argparse
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

from generateur.moteur import config, machine
from generateur.outils.bilan_n4 import _lire

MODELE, PROCEDURAL = "modèle", "procédural"


@dataclass
class Groupe:
    chemin: str
    fournisseur: str
    modele: str
    machine: str
    premier_essai: int = 0
    apres_reprise: int = 0
    rejetees: int = 0
    tentatives: list[int] = field(default_factory=list)
    durees: list[float] = field(default_factory=list)
    par_question: list[float] = field(default_factory=list)
    lecture: list[float] = field(default_factory=list)      # tokens/s, premier appel de chaque génération
    ecriture: list[float] = field(default_factory=list)     # tokens/s, chaque appel
    chargements: list[float] = field(default_factory=list)  # chargements à froid seulement (> 0 s)
    gpu: set = field(default_factory=set)
    # les taux ne se comparent qu'à matières égales : hors maths, N4 ne rejette rien
    matieres: Counter = field(default_factory=Counter)

    @property
    def generations(self) -> int:
        return self.premier_essai + self.apres_reprise + self.rejetees

    def compter(self, meta: dict, acceptee: bool, questions: int, matiere: str | None) -> None:
        self.matieres[matiere or "?"] += 1
        tentatives = meta.get("tentatives") or 1
        if not acceptee:
            self.rejetees += 1
        elif tentatives == 1:
            self.premier_essai += 1
        else:
            self.apres_reprise += 1
        self.tentatives.append(tentatives)
        if meta.get("duree_s") is not None:
            self.durees.append(meta["duree_s"])
            if questions:
                self.par_question.append(meta["duree_s"] / questions)
        for i, appel in enumerate(meta.get("appels") or []):
            if i == 0 and appel.get("lecture_s") and appel.get("tokens_lus"):
                self.lecture.append(appel["tokens_lus"] / appel["lecture_s"])
            if appel.get("ecriture_s") and appel.get("tokens_ecrits"):
                self.ecriture.append(appel["tokens_ecrits"] / appel["ecriture_s"])
            if appel.get("chargement_s"):
                self.chargements.append(appel["chargement_s"])
            if "gpu" in appel:
                self.gpu.add(appel["gpu"])


def _groupe(groupes: dict, meta: dict) -> Groupe:
    chemin = PROCEDURAL if meta.get("origine") == "procedural" else MODELE
    fournisseur = meta.get("fournisseur") or "?"
    modele = meta.get("modele") or ("aucun (programme seul)" if fournisseur == "procedural" else "?")
    cle = (chemin, fournisseur, modele, machine.libelle(meta.get("machine")))
    if cle not in groupes:
        groupes[cle] = Groupe(*cle)
    return groupes[cle]


def mesurer(dossier_instances: Path, dossier_rejets: Path, depuis: str | None = None,
            modele: str | None = None) -> list[Groupe]:
    """`depuis` (« 2026-10-08 ») et `modele` filtrent comme dans bilan_n4."""
    def retenue(meta: dict) -> bool:
        return (meta.get("fournisseur") != "maquette" and (depuis is None or (meta.get("date") or "") >= depuis)
                and (modele is None or meta.get("modele") == modele))

    groupes: dict[tuple, Groupe] = {}
    for chemin in sorted(dossier_instances.glob("*.json")) if dossier_instances.is_dir() else []:
        instance = _lire(chemin) or {}
        meta = instance.get("meta") or {}
        if meta and retenue(meta):
            _groupe(groupes, meta).compter(meta, True, len(instance.get("questions") or []), instance.get("matiere"))
    for chemin in sorted(dossier_rejets.glob("*.json")) if dossier_rejets.is_dir() else []:
        rejet = _lire(chemin) or {}
        if rejet and retenue(rejet):
            demandees = (rejet.get("demande") or {}).get("nb_questions")
            instance = rejet.get("instance") or {}
            questions = demandees or len(instance.get("questions") or [])
            matiere = instance.get("matiere") or (rejet.get("demande") or {}).get("matiere")
            _groupe(groupes, rejet).compter(rejet, False, questions, matiere)
    return sorted(groupes.values(), key=lambda g: (g.chemin, g.machine, g.modele))


def _median(valeurs: list[float], unite: str = "", chiffres: int = 0) -> str:
    return f"{median(valeurs):.{chiffres}f}{unite}" if valeurs else "—"


def _gpu(groupe: Groupe) -> str:
    if groupe.gpu == {True}:
        return "oui"
    if groupe.gpu == {False}:
        return "non"
    return "mixte" if groupe.gpu else "?"


def rapport(groupes: list[Groupe]) -> str:
    if not groupes:
        return "Aucune génération à mesurer : lancer des générations d'abord."
    lignes = [
        "| Chemin | Fournisseur | Modèle | Machine | GPU | Générations | Matières | 1er essai | Après reprise | Rejetées "
        "| Tentatives (moy.) | Durée médiane | Par question | Lecture (tokens/s) | Écriture (tokens/s) | Chargement |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for g in groupes:
        n = g.generations
        matieres = ", ".join(f"{m} {k}" for m, k in g.matieres.most_common())
        lignes.append(
            f"| {g.chemin} | {g.fournisseur} | {g.modele} | {g.machine} | {_gpu(g)} | {n} | {matieres} "
            f"| {g.premier_essai} ({g.premier_essai / n:.0%}) | {g.apres_reprise} | {g.rejetees} "
            f"| {sum(g.tentatives) / n:.1f} | {_median(g.durees, ' s')} | {_median(g.par_question, ' s')} "
            f"| {_median(g.lecture)} | {_median(g.ecriture, chiffres=1)} | {_median(g.chargements, ' s', 1)} |")
    lignes += [
        "",
        "Lecture : premier appel de chaque génération ; un prompt déjà en cache (Ollama, llama.cpp) la rend très "
        "rapide, d'où la médiane. Taux de réussite : à comparer à matières égales (hors maths, N4 ne "
        "rejette rien). Tokens et vitesses : générations du 07/10 et après. « machine non relevée » : "
        "meta antérieurs à l'enregistrement de la machine. Mémoire : à relever à part.",
    ]
    return "\n".join(lignes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mesurer durées, vitesses et taux de réussite par modèle et par machine.")
    parser.add_argument("--instances", type=Path, default=config.chemin("banque"))
    parser.add_argument("--rejets", type=Path, default=config.chemin("rejets"))
    parser.add_argument("--depuis", metavar="AAAA-MM-JJ", help="ne compter que les générations de cette date ou après")
    parser.add_argument("--modele", metavar="NOM", help="ne compter que les générations de ce modèle, tel que le meta le nomme")
    args = parser.parse_args()
    print(rapport(mesurer(args.instances, args.rejets, args.depuis, args.modele)))


if __name__ == "__main__":
    main()
