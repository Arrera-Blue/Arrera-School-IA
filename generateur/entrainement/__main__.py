"""python -m generateur.entrainement nuit | bilan | prerelecture | corriger | jeu (plan IA, IA3) | entrainer | convertir |
aveugle generer | aveugle chemins | aveugle bilan (IA4 ; le critère de fin des lots du cycle 2)."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from generateur import entrainement
from generateur.entrainement import adaptateur, aveugle, bilan, jeu, nuit, prerelecture
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
    p = sous.add_parser("prerelecture", help="enregistrer dans le lot les avis d'un paquet de pré-relecture (Claude), "
                                             "que l'enseignant verra en relisant")
    p.add_argument("paquet", type=Path, help="le fichier JSONL des avis, une ligne par exercice (prerelecture.py)")
    k = sous.add_parser("corriger", help="appliquer les corrections de la pré-relecture (Claude) aux questions jugées "
                                         "fausses ; l'enseignant les vérifie et accepte de nouveau")
    k.add_argument("fichier", type=Path, help="le fichier JSONL des corrections, une ligne par question (prerelecture.py)")
    j = sous.add_parser("jeu", help="mettre en forme le jeu de données, le séparer par notion, le figer et le décrire")
    j.add_argument("--part-procedurale", type=float, default=jeu.PART_PROCEDURALE, metavar="P",
                   help="part du jeu laissée aux exercices du générateur procédural non relus (défaut : un tiers)")
    j.add_argument("--graine", type=int, default=jeu.GRAINE)
    e = sous.add_parser("entrainer", help="entraîner un adaptateur LoRA sur un jeu figé (mlx-lm) et l'écrire pour "
                                          "llama.cpp (plan IA, IA4)")
    e.add_argument("--jeu", type=Path, help="le dossier du jeu (défaut : le dernier fait)")
    e.add_argument("--epoques", type=int, metavar="N", help="défaut : entrainement.epoques de config.yaml")
    e.add_argument("--nom", help="défaut : la date et l'heure (AAAAMMJJ-HHMM)")
    c = sous.add_parser("convertir", help="écrire pour llama.cpp (GGUF) un adaptateur de mlx-lm")
    c.add_argument("dossier", type=Path, help="le dossier de l'adaptateur de mlx-lm (adapter_config.json, ses poids)")
    c.add_argument("--poids", default=adaptateur.POIDS,
                   help=f"un point d'étape à la place de l'adaptateur final (défaut : {adaptateur.POIDS})")
    c.add_argument("--sortie", type=Path, help="défaut : à côté du dossier, <dossier>.gguf (<dossier>-<itération>.gguf "
                                               "pour un point d'étape)")
    v = sous.add_parser("aveugle", help="plan IA, IA4.3 : le modèle de base contre le modèle entraîné, relus à l'aveugle")
    vsous = v.add_subparsers(dest="action", required=True)
    g = vsous.add_parser("generer", help="générer les exercices des deux modèles sur les mêmes demandes, puis les mélanger "
                                         "(reprend la dernière comparaison si elle n'est pas finie)")
    g.add_argument("--adaptateur", type=Path, help="le modèle entraîné : un .gguf (… convertir pour un point d'étape) ; "
                                                   "pour une nouvelle comparaison")
    g.add_argument("--jeu", type=Path, help="le jeu sur lequel il a été entraîné (défaut : celui de sa description)")
    g.add_argument("--nombre", type=int, default=aveugle.NOMBRE, help=f"demandes (défaut : {aveugle.NOMBRE})")
    g.add_argument("--graine", type=int, default=aveugle.GRAINE)
    g.add_argument("--nouvelle", action="store_true", help="une nouvelle comparaison, même si la dernière n'est pas finie")
    ch = vsous.add_parser("chemins", help="le modèle seul contre le générateur procédural, sur des demandes réelles (le "
                                          "critère de fin d'un lot du cycle 2) ; reprend la dernière si elle n'est pas finie")
    ch.add_argument("--demandes", type=Path, help="un fichier JSON : [{\"phrase\", \"formulaire\"?, \"graine\"?}] "
                                                  "(scripts/essais/criteres/)")
    ch.add_argument("--graine", type=int, default=aveugle.GRAINE, help="le mélange")
    ch.add_argument("--nouvelle", action="store_true", help="une nouvelle comparaison, même si la dernière n'est pas finie")
    vb = vsous.add_parser("bilan", help="dévoiler les modèles une fois tout relu : bilan.md (défaut : la dernière comparaison)")
    vb.add_argument("dossier", type=Path, nargs="?")
    vb.add_argument("--meme-si-pas-fini", action="store_true", help="dévoiler avant la fin de la relecture")
    args = parser.parse_args()

    if args.commande == "aveugle":
        try:
            _aveugle(args)
        except ValueError as erreur:
            sys.exit(f"Erreur : {erreur}")
        except KeyboardInterrupt:
            print("\nArrêtée (Ctrl-C) : relancer la même commande reprend là où elle s'est arrêtée.")
    elif args.commande == "nuit":
        _rester_eveille()
        fin = nuit.heure_de_fin(args.jusqua) if args.jusqua else None
        try:
            nuit.nuit(nuit.plan(args.passes), fin, args.nombre, args.fournisseur)
        except KeyboardInterrupt:
            print("\nArrêtée (Ctrl-C) : la demande en cours sera refaite à la prochaine génération.")
    elif args.commande == "prerelecture":
        entrainement.utiliser()  # les avis vont aux exercices du lot, jamais à la vraie banque
        try:
            c = prerelecture.importer(args.paquet)
        except (ValueError, OSError) as erreur:
            sys.exit(f"Erreur : {erreur}")
        print(f"{sum(c[a] for a in prerelecture.AVIS)} avis enregistrés : {c['bon']} bon(s), {c['a_corriger']} à "
              f"corriger, {c['a_rejeter']} à rejeter" + (f" ; dont {c['deja_decides']} sur des exercices déjà décidés "
                                                         "(leur statut ne change pas)" if c["deja_decides"] else "") + ".")
    elif args.commande == "corriger":
        entrainement.utiliser()  # les corrections vont aux exercices du lot, jamais à la vraie banque
        try:
            r = prerelecture.corriger(args.fichier)
        except OSError as erreur:
            sys.exit(f"Erreur : {erreur}")
        exercices = len({ident for ident, _ in r["appliquees"]})
        print(f"{len(r['appliquees'])} question(s) corrigée(s) dans {exercices} exercice(s) : ils sont de nouveau en "
              "cours de relecture, à vérifier et à accepter." + (f"\n{len(r['refusees'])} refusée(s) :\n- "
                                                                   + "\n- ".join(r["refusees"]) if r["refusees"] else ""))
    elif args.commande == "jeu":
        lot = entrainement.chemins()
        dossier = entrainement.dossier() / "jeux" / f"{datetime.now():%Y%m%d-%H%M%S}"
        m = jeu.construire(lot["banque"], config.chemin("banque"), [config.chemin("rejets"), lot["rejets"]],
                           nuit.noms_proteges(), dossier, args.part_procedurale, args.graine)
        tailles = {nom: len(liste) for nom, liste in m["jeux"].items()}
        print(f"Jeu de données : {sum(tailles.values())} exercices (entraînement {tailles['train']}, validation "
              f"{tailles['valid']}, test {tailles['test']}), {m['paires']} paire(s) avant → après, {m['a_eviter']} "
              f"exercice(s) à éviter, {len(m['ecartes'])} écarté(s).\nDossier : {dossier}\nFiche : {dossier / 'fiche.md'}")
    elif args.commande == "entrainer":
        _rester_eveille()
        jeux = entrainement.dossier() / "jeux"
        try:
            jeu_ = args.jeu or adaptateur.dernier_jeu(jeux)
            print(f"Entraînement sur {jeu_} ; jusqu'à ~19 Go de mémoire : fermer les autres applications.", flush=True)
            b = adaptateur.entrainer(jeu_, config.chemin("adaptateurs"), args.epoques, args.nom)
        except ValueError as erreur:
            sys.exit(f"Erreur : {erreur}")
        print(f"\nAdaptateur entraîné en {b['duree_s'] // 60} min ({b['epoques']} époque(s) sur {b['exemples']['train']} "
              f"exercices) : {b['adaptateur']}\nPour s'en servir, dans config.yaml : llamacpp.adaptateur: "
              f"\"{b['adaptateur']}\" (null : le modèle de base).")
    elif args.commande == "convertir":
        iteration = args.poids.split("_", 1)[0] if args.poids != adaptateur.POIDS else None
        sortie = args.sortie or args.dossier.parent / f"{args.dossier.name}{'-' + iteration if iteration else ''}.gguf"
        try:
            r = adaptateur.convertir(args.dossier, sortie, args.poids)
        except (ValueError, FileNotFoundError) as erreur:
            sys.exit(f"Erreur : {erreur}")
        print(f"{sortie} : {r['tenseurs']} tenseurs, rang {r['rang']}, alpha {r['alpha']:g}, "
              f"{r['octets'] / 1e6:.1f} Mo.")
    else:
        texte = bilan.bilan(entrainement.chemins()["banque"], nuit.lire_journal(), config.chemin("banque"))
        print(texte)
        if args.sortie:
            args.sortie.write_text(texte, encoding="utf-8")


def _aveugle(args) -> None:
    """aveugle generer : reprendre la dernière comparaison si elle n'est pas finie, sinon en commencer une (il faut
    l'adaptateur) ; aveugle chemins : de même, le modèle seul contre le générateur procédural (il faut les demandes) ;
    aveugle bilan : dévoiler les modèles, ou les chemins."""
    if args.action == "bilan":
        dossier = args.dossier or aveugle.dernier()
        print(aveugle.bilan(dossier, args.meme_si_pas_fini))
        print(f"Écrit dans {dossier / 'bilan.md'}")
        return
    _rester_eveille()
    try:
        en_cours = aveugle.dernier()
    except ValueError:
        en_cours = None
    if en_cours and not aveugle.melanges(en_cours) and not args.nouvelle:
        plan = aveugle.lire_plan(en_cours)
        if (args.action == "chemins") != aveugle.des_chemins(plan):
            autre = "des deux chemins (aveugle chemins)" if aveugle.des_chemins(plan) else "des deux modèles (aveugle generer)"
            raise ValueError(f"la comparaison {en_cours.name} {autre} n'est pas finie : la reprendre, ou en commencer une "
                             "autre (--nouvelle)")
        if args.action == "generer":
            prevu = plan["adaptateur"]
            if args.adaptateur and args.adaptateur.resolve() != aveugle._absolu(prevu["chemin"]).resolve():
                raise ValueError(f"la comparaison {en_cours.name} n'est pas finie, avec l'adaptateur {prevu['nom']} : la "
                                 "reprendre (sans --adaptateur), ou en commencer une autre (--nouvelle)")
        dossier = en_cours
        print(f"Reprise de la comparaison {dossier.name} : {len(aveugle.reste_a_faire(dossier))} génération(s) à faire.")
    elif args.action == "chemins":
        if not args.demandes:
            raise ValueError("préciser les demandes : --demandes scripts/essais/criteres/<lot>.json")
        dossier = aveugle.racine() / f"{datetime.now():%Y%m%d-%H%M}"
        plan = aveugle.preparer_chemins(json.loads(args.demandes.read_text(encoding="utf-8")), dossier, args.graine)
        print(f"Comparaison {dossier.name} : {len(plan['demandes'])} demandes, chacune par le modèle seul puis par le "
              "générateur procédural. Environ 1 min par exercice du modèle.", flush=True)
    else:
        if not args.adaptateur:
            raise ValueError("préciser le modèle entraîné : --adaptateur modeles/adaptateurs/<nom>.gguf")
        jeu_ = args.jeu or aveugle.jeu_de_l_adaptateur(args.adaptateur)
        if jeu_ is None:
            raise ValueError(f"le jeu de données de {args.adaptateur.name} est introuvable : préciser --jeu")
        dossier = aveugle.racine() / f"{datetime.now():%Y%m%d-%H%M}"
        plan = aveugle.preparer(args.adaptateur, jeu_, dossier, args.nombre, args.graine)
        print(f"Comparaison {dossier.name} : {len(plan['demandes'])} demandes, chacune par le modèle de base puis par "
              f"le modèle entraîné ({plan['adaptateur']['nom']}). Environ 1 min par génération.", flush=True)
    aveugle.generer(dossier, lambda texte: print(texte, flush=True))
    if not aveugle.melanges(dossier):
        print("Pas fini : relancer la même commande reprend là où elle s'est arrêtée.")


if __name__ == "__main__":
    main()
