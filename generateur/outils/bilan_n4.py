"""Point de décision de l'étape 1.3 : N4 suffit-elle, ou faut-il un générateur procédural pour les maths ?

Recalcule N4, avec le code actuel, sur toutes les générations de maths conservées :
- les exercices acceptés (banque/instances/) ;
- les exercices rejetés après N2 (banque/rejets/), qui gardent leur instance.
Recalculer plutôt que relire le meta permet de remesurer le même corpus après chaque amélioration de N4.
Les seuils sont ceux de docs/etapes/etape-1.3.md §8.

    python -m generateur.outils.bilan_n4
    python -m generateur.outils.bilan_n4 --depuis 2026-10-03     # seulement le prompt actuel
    python -m generateur.outils.bilan_n4 --modele gemma4:e4b-it-qat   # seulement ce modèle
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
REPONSE_FAUSSE, PLUSIEURS_JUSTES = "réponse annoncée fausse", "plusieurs bonnes réponses"


@dataclass
class Bilan:
    acceptees: int = 0
    rejetees: int = 0
    rejets_non_mesurables: int = 0  # rejetés en N1 ou N2 : pas d'instance exploitable
    statuts: Counter = field(default_factory=Counter)
    # nature des « faux » : une réponse annoncée fausse (erreur de calcul) n'appelle pas le même remède que
    # plusieurs bonnes réponses (défaut de conception du QCM, que la reprise ou le prompt peuvent corriger)
    faux_par_nature: Counter = field(default_factory=Counter)

    def compter(self, instance: dict) -> None:
        for v in verifier(instance):
            self.statuts[v.statut] += 1
            if v.statut == FAUX:
                nature = PLUSIEURS_JUSTES if "plusieurs propositions conviennent" in v.message else REPONSE_FAUSSE
                self.faux_par_nature[nature] += 1

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


def mesurer(dossier_instances: Path, dossier_rejets: Path, depuis: str | None = None,
            modele: str | None = None) -> Bilan:
    """`depuis` (« 2026-10-03 ») ne garde que les générations de cette date ou après : utile pour juger
    un nouveau prompt sans le mélanger aux générations de l'ancien. `modele` (« gemma4:e4b-it-qat ») ne
    garde que les générations de ce modèle : utile pour comparer deux modèles essayés le même jour."""
    def retenue(date: str | None, modele_utilise: str | None = None) -> bool:
        return (depuis is None or (date or "") >= depuis) and (modele is None or modele_utilise == modele)

    bilan = Bilan()
    for chemin in sorted(dossier_instances.glob("*.json")) if dossier_instances.is_dir() else []:
        instance = _lire(chemin)
        meta = (instance or {}).get("meta") or {}
        if instance and instance.get("matiere") == "maths" and retenue(meta.get("date"), meta.get("modele")):
            bilan.acceptees += 1
            bilan.compter(instance)
    for chemin in sorted(dossier_rejets.glob("*.json")) if dossier_rejets.is_dir() else []:
        rejet = _lire(chemin) or {}
        if not retenue(rejet.get("date"), rejet.get("modele")):
            continue
        instance = rejet.get("instance")
        if instance is None:
            if (rejet.get("demande") or {}).get("matiere") in (None, "maths"):
                bilan.rejets_non_mesurables += 1
            continue
        if instance.get("matiere") == "maths":
            bilan.rejetees += 1
            bilan.compter(instance)
    return bilan


def decision(bilan: Bilan) -> str:
    if bilan.questions == 0:
        return "aucune question de maths à analyser : lancer des générations d'abord"
    faux, verifie = bilan.part(FAUX), bilan.part(VERIFIE)
    if faux > FAUX_ELEVE and bilan.faux_par_nature[PLUSIEURS_JUSTES] > bilan.faux_par_nature[REPONSE_FAUSSE]:
        conseil = ("trop de questions fausses, surtout à plusieurs bonnes réponses : remesurer après la reprise "
                   "sur erreur (1.4), qui renvoie ces défauts au modèle ; si le taux reste élevé, passer au "
                   "GÉNÉRATEUR PROCÉDURAL pour les maths")
    elif faux > FAUX_ELEVE:
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
        if statut == FAUX and bilan.statuts[FAUX]:
            for nature in (REPONSE_FAUSSE, PLUSIEURS_JUSTES):
                lignes.append(f"      dont {nature} : {bilan.faux_par_nature[nature]}")
    lignes.append(f"Décision suggérée : {decision(bilan)}")
    lignes.append("Seuils : docs/etapes/etape-1.3.md §8 — ce sont des ordres de grandeur, pas une règle.")
    return "\n".join(lignes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mesurer N4 sur les générations de maths conservées.")
    parser.add_argument("--instances", type=Path, default=config.chemin("banque"))
    parser.add_argument("--rejets", type=Path, default=config.chemin("rejets"))
    parser.add_argument("--depuis", metavar="AAAA-MM-JJ",
                        help="ne compter que les générations de cette date ou après (par exemple depuis un changement de prompt)")
    parser.add_argument("--modele", metavar="NOM",
                        help="ne compter que les générations de ce modèle, tel que le nomme config.yaml (par exemple gemma4:e4b-it-qat)")
    args = parser.parse_args()
    if args.depuis:
        print(f"Générations retenues : depuis le {args.depuis}")
    if args.modele:
        print(f"Générations retenues : modèle {args.modele}")
    print(rapport(mesurer(args.instances, args.rejets, args.depuis, args.modele)))


if __name__ == "__main__":
    main()
