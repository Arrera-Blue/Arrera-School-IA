"""Une classe fictive pour essayer le suivi sans aucune donnée réelle (évolution E3.4).

    python -m generateur.donnees.demo <identifiant>        # la classe « 6e Démo » de cet enseignant, 24 élèves

Les noms sont inventés. Les codes s'affichent une seule fois, ici ; ensuite, l'interface (« Classes » → la classe →
« Nouveaux codes pour toute la classe ») en refait et imprime les cartes.
"""

import argparse
import sys

from generateur.donnees import classes, codes, comptes
from generateur.donnees.base import Base

# 24 noms inventés (prénoms courants, noms fréquents) : aucun élève réel
ELEVES = [("ARNAUD", "Léa"), ("BERNARD", "Hugo"), ("BLANC", "Inès"), ("BONNET", "Lucas"), ("CHEVALIER", "Chloé"),
          ("DAVID", "Nathan"), ("DUBOIS", "Manon"), ("DURAND", "Théo"), ("FAURE", "Jade"), ("FONTAINE", "Louis"),
          ("GARNIER", "Camille"), ("GIRARD", "Tom"), ("LAMBERT", "Zoé"), ("LEROY", "Noah"), ("MARTIN", "Alice"),
          ("MERCIER", "Gabriel"), ("MOREL", "Lina"), ("MOREAU", "Arthur"), ("PETIT", "Emma"), ("RICHARD", "Jules"),
          ("ROUSSEL", "Louise"), ("SIMON", "Adam"), ("THOMAS", "Rose"), ("VINCENT", "Raphaël")]
NOM_CLASSE = "6e Démo"


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m generateur.donnees.demo",
                                     description="Créer une classe fictive de 24 élèves aux noms inventés.")
    parser.add_argument("identifiant", help="le compte enseignant à qui la confier")
    parser.add_argument("--niveau", default="6e", choices=classes.NIVEAUX)
    args = parser.parse_args(arguments)
    from generateur.moteur import config

    base = Base(config.chemin("base"))
    compte = comptes.lire(base, args.identifiant)
    if compte is None:
        print(f"Refusé : compte inconnu : {args.identifiant}", file=sys.stderr)
        return 1
    nom = NOM_CLASSE if args.niveau == "6e" else f"{args.niveau} Démo"
    try:
        classe, cartes = classes.creer(base, compte, nom, args.niveau, None,
                                       [{"nom": n, "prenom": p} for n, p in ELEVES], codes.cle_secrete(config.chemin("cle_codes")))
    except classes.ClasseInvalide as e:
        print(f"Refusé : {e}", file=sys.stderr)
        return 1
    print(f"Classe « {classe['nom']} » ({classe['annee']}) créée pour {compte['identifiant']} : {classe['eleves']} élèves "
          "fictifs.\nCodes (affichés une seule fois) :")
    for carte in cartes:
        print(f"  n° {carte['numero']:>2}  {carte['prenom']} {carte['nom']:<12} "
              + " · ".join(image["nom"] for image in carte["code"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
