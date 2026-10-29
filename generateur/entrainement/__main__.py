"""python -m generateur.entrainement nuit | bilan (plan IA, IA3)."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from generateur import entrainement
from generateur.entrainement import bilan, nuit
from generateur.moteur import config


def _rester_eveille() -> None:
    """Sur le Mac : pas de mise en veille tant que la génération tourne (caffeinate s'arrête avec elle). Un portable
    dont on ferme l'écran s'endort quand même."""
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m generateur.entrainement",
                                     description="Les données d'entraînement du modèle (plan IA, IA3).")
    sous = parser.add_subparsers(dest="commande", required=True)
    n = sous.add_parser("nuit", help="générer des exercices dans le lot d'entraînement (reprend là où la dernière "
                                     "génération s'est arrêtée)")
    n.add_argument("--jusqua", metavar="HH:MM", help="s'arrêter à cette heure (la prochaine : demain matin si elle "
                                                     "est passée)")
    n.add_argument("--nombre", type=int, metavar="N", help="faire au plus N demandes")
    n.add_argument("--fournisseur", help="défaut : le premier de config.yaml (llamacpp)")
    n.add_argument("--passes", type=int, default=nuit.PASSES,
                   help=f"passes sur les attendus des programmes (défaut : {nuit.PASSES})")
    b = sous.add_parser("bilan", help="ce qui est généré, relu, et ce qui pourra entrer dans le jeu de données")
    b.add_argument("--sortie", type=Path, help="écrire aussi le bilan dans ce fichier (Markdown)")
    args = parser.parse_args()

    if args.commande == "nuit":
        _rester_eveille()
        fin = nuit.heure_de_fin(args.jusqua) if args.jusqua else None
        try:
            nuit.nuit(nuit.plan(args.passes), fin, args.nombre, args.fournisseur)
        except KeyboardInterrupt:
            print("\nArrêtée (Ctrl-C) : la demande en cours sera refaite à la prochaine génération.")
    else:
        texte = bilan.bilan(entrainement.chemins()["banque"], nuit.lire_journal(), config.chemin("banque"))
        print(texte)
        if args.sortie:
            args.sortie.write_text(texte, encoding="utf-8")


if __name__ == "__main__":
    main()
