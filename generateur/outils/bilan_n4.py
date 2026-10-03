"""Point de décision de l'étape 1.3 : N4 suffit-elle, ou faut-il un générateur procédural pour les maths ?

Recalcule N4, avec le code actuel, sur toutes les générations de maths conservées :
- les exercices acceptés (banque/instances/) ;
- les exercices rejetés après N2 (banque/rejets/), qui gardent leur instance.
Recalculer plutôt que relire le meta permet de remesurer le même corpus après chaque amélioration de N4.
Les seuils sont ceux de docs/etapes/etape-1.3.md §8.

    python -m generateur.outils.bilan_n4
    python -m generateur.outils.bilan_n4 --depuis 2026-10-03     # seulement le prompt actuel
"""

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from generateur.moteur import config
from generateur.moteur.validation.n4_calcul import A_RELIRE, FAUX, VERIFIE, verifier

GENERATIONS_MIN = 10
FAUX_FAIBLE, FAUX_ELEVE = 0.10, 0.20
VERIFIE_ELEVE, VERIFIE_FAIBLE = 0.60, 0.50


@dataclass
class Bilan:
    acceptees: int = 0
    rejetees: int = 0
    rejets_non_mesurables: int = 0  # rejetés en N1 ou N2 : pas d'instance exploitable
    statuts: Counter = field(default_factory=Counter)

    @property
    def generations(self) -> int:
        return self.acceptees + self.rejetees

    @property
    def questions(self) -> int:
        return sum(self.statuts.values())

    def part(self, statut: str) -> float:
        return self.statuts[statut] / self.questions if self.questions else 0.0


def _lire(chemin: Path) -> dict | None:
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def mesurer(dossier_instances: Path, dossier_rejets: Path, depuis: str | None = None) -> Bilan:
    """`depuis` (« 2026-10-03 ») ne garde que les générations de cette date ou après : utile pour juger
    un nouveau prompt sans le mélanger aux générations de l'ancien."""
    def retenue(date: str | None) -> bool:
        return depuis is None or (date or "") >= depuis

    bilan = Bilan()
    for chemin in sorted(dossier_instances.glob("*.json")) if dossier_instances.is_dir() else []:
        instance = _lire(chemin)
        if instance and instance.get("matiere") == "maths" and retenue((instance.get("meta") or {}).get("date")):
            bilan.acceptees += 1
            bilan.statuts.update(v.statut for v in verifier(instance))
    for chemin in sorted(dossier_rejets.glob("*.json")) if dossier_rejets.is_dir() else []:
        rejet = _lire(chemin) or {}
        if not retenue(rejet.get("date")):
            continue
        instance = rejet.get("instance")
        if instance is None:
            if (rejet.get("demande") or {}).get("matiere") in (None, "maths"):
                bilan.rejets_non_mesurables += 1
            continue
        if instance.get("matiere") == "maths":
            bilan.rejetees += 1
            bilan.statuts.update(v.statut for v in verifier(instance))
    return bilan


def decision(bilan: Bilan) -> str:
    if bilan.questions == 0:
        return "aucune question de maths à analyser : lancer des générations d'abord"
    faux, verifie = bilan.part(FAUX), bilan.part(VERIFIE)
    if faux > FAUX_ELEVE:
        conseil = "le modèle se trompe trop souvent en calcul : passer au GÉNÉRATEUR PROCÉDURAL pour les maths"
    elif verifie < VERIFIE_FAIBLE:
        conseil = ("N4 ne vérifie pas assez de questions : étendre les reconnaisseurs, "
                   "ou passer au GÉNÉRATEUR PROCÉDURAL")
    elif faux < FAUX_FAIBLE and verifie > VERIFIE_ELEVE:
        conseil = "garder la chaîne actuelle : le modèle génère, N4 contrôle, la reprise sur erreur (1.4) corrige"
    else:
        conseil = "zone intermédiaire : à discuter au vu des exercices concernés"
    if bilan.generations < GENERATIONS_MIN:
        conseil += f" (indicatif : {bilan.generations} génération(s), il en faut au moins {GENERATIONS_MIN})"
    return conseil


def rapport(bilan: Bilan) -> str:
    lignes = [
        f"Générations de maths analysées : {bilan.generations} "
        f"({bilan.acceptees} acceptée(s), {bilan.rejetees} rejetée(s))",
    ]
    if bilan.rejets_non_mesurables:
        lignes.append(f"Rejets en N1/N2, sans instance exploitable : {bilan.rejets_non_mesurables}")
    lignes.append(f"Questions : {bilan.questions}")
    for statut, libelle in ((VERIFIE, "vérifiées "), (FAUX, "fausses   "), (A_RELIRE, "à relire  ")):
        lignes.append(f"  {libelle}: {bilan.statuts[statut]:3d}  ({bilan.part(statut):.0%})")
    lignes.append(f"Décision suggérée : {decision(bilan)}")
    lignes.append("Seuils : docs/etapes/etape-1.3.md §8 — ce sont des ordres de grandeur, pas une règle.")
    return "\n".join(lignes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mesurer N4 sur les générations de maths conservées.")
    parser.add_argument("--instances", type=Path, default=config.chemin("banque"))
    parser.add_argument("--rejets", type=Path, default=config.chemin("rejets"))
    parser.add_argument("--depuis", metavar="AAAA-MM-JJ",
                        help="ne compter que les générations de cette date ou après (par exemple depuis un changement de prompt)")
    args = parser.parse_args()
    if args.depuis:
        print(f"Générations retenues : depuis le {args.depuis}")
    print(rapport(mesurer(args.instances, args.rejets, args.depuis)))


if __name__ == "__main__":
    main()
