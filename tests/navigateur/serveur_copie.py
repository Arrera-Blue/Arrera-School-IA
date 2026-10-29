"""Lance l'interface enseignant sur une COPIE de la banque, pour l'essai dans le navigateur (essai.mjs).

    .venv/bin/python tests/navigateur/serveur_copie.py <dossier> [port] [--entrainement]

Copie banque/ dans <dossier>, puis sert l'interface sur 127.0.0.1:<port> (8012 par défaut) en écrivant
uniquement dans cette copie : les essais (accepter, modifier, supprimer…) ne touchent jamais la vraie banque.
La base (comptes, journal) est neuve, dans la copie, avec un seul compte administrateur : ESSAI (E1), sa classe
de démonstration (24 élèves fictifs) et leurs réponses simulées, pour le suivi (E4).
Le serveur de classe (E8) tourne aussi, sur la même copie, au port suivant (<port> + 1) : c'est son adresse que
l'interface affiche, et l'essai y bloque un élève par 5 codes faux.

Avec --entrainement (plan IA, IA3) : l'interface du lot d'entraînement, sur la même copie (même base), avec un lot
d'essai de 5 exercices dans <dossier>/entrainement/ et un échantillon de 2 exercices à relire (pour en voir la fin) ;
sans serveur de classe (celui de la première interface tourne déjà).
"""

import contextlib
import io
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE))

from generateur.moteur import config  # noqa: E402

arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
ENTRAINEMENT = "--entrainement" in sys.argv
copie = Path(arguments[0]).resolve()
port = int(arguments[1]) if len(arguments) > 1 else 8012
if (RACINE / "banque").is_dir() and not ENTRAINEMENT:  # le lot : la copie est déjà faite, par la première interface
    shutil.copytree(RACINE / "banque", copie / "banque", dirs_exist_ok=True)
vrai_chemin = config.chemin
COPIES = {"banque": "banque/instances", "rejets": "banque/rejets", "supprimes": "banque/supprimes", "sortie": "sortie",
          "base": "donnees/arrera.sqlite3", "sauvegardes": "donnees/sauvegardes", "cle_codes": "donnees/cle-codes"}
if ENTRAINEMENT:  # les dossiers de la banque sont ceux du lot, comme `entrainement.utiliser()` le fait
    COPIES |= {"banque": "entrainement/banque/instances", "rejets": "entrainement/banque/rejets",
               "supprimes": "entrainement/banque/supprimes", "sortie": "entrainement/sortie"}
config.chemin = lambda nom: copie / COPIES[nom] if nom in COPIES else vrai_chemin(nom)


def semer_le_lot(dossier: Path) -> None:
    """5 exercices : 2 de français (6e) et 2 de maths (4e), écrits par « le modèle », dans cet ordre de génération ; un
    du générateur procédural, plus ancien. L'ordre de relecture attendu : français 1, maths 1, français 2, maths 2,
    puis le procédural."""
    import json

    from generateur.moteur import registre
    exemple = registre.charger("qcm").exemple
    grammaire = [("Quel mot est un nom commun ?", ["maison", "rapide", "courir", "très"], "« maison » désigne une chose."),
                 ("Quel mot est un verbe ?", ["chanter", "table", "joli", "sous"], "« chanter » exprime une action."),
                 ("Quel mot est un adjectif ?", ["grand", "pomme", "partir", "avec"], "« grand » qualifie un nom.")]
    dossier.mkdir(parents=True, exist_ok=True)
    for ident, matiere, heure, origine in [("qcm-lot-francais-1", "francais", "22:00", "modele"),
                                           ("qcm-lot-francais-2", "francais", "22:01", "modele"),
                                           ("qcm-lot-maths-1", "maths", "22:02", "modele"),
                                           ("qcm-lot-maths-2", "maths", "22:03", "modele"),
                                           ("qcm-lot-procedural", "maths", "21:00", "procedural")]:
        x = json.loads(json.dumps(exemple))
        if matiere == "francais":
            x |= {"titre": f"Les classes de mots ({ident[-1]})", "matiere": "francais", "niveau": "6e",
                  "notion": "les classes de mots", "questions": [
                      {"enonce": e, "propositions": p[1:i + 1] + [p[0]] + p[i + 1:], "index_correct": i, "explication": d,
                       "difficulte": "facile"} for i, (e, p, d) in enumerate(grammaire)]}
        else:
            x["titre"] = f"Le théorème de Pythagore ({ident.rsplit('-', 1)[-1]})"
        x["meta"] = {"id": ident, "statut": "genere", "date": f"2026-10-29T{heure}:00", "fournisseur": "llamacpp",
                     "modele": "gemma-4-E4B_q4_0-it.gguf", "entrainement": {"lot": "nuit-20261029", "passe": 1},
                     **({"origine": "procedural", "generateur": "pythagore"} if origine == "procedural" else {})}
        (dossier / f"{ident}.json").write_text(json.dumps(x, ensure_ascii=False), encoding="utf-8")


if ENTRAINEMENT and not config.chemin("banque").is_dir():
    semer_le_lot(config.chemin("banque"))

from generateur.donnees import comptes, demo, simulation  # noqa: E402
from generateur.donnees.base import Base  # noqa: E402

# le compte de l'essai (le même dans essai.mjs) ; il n'existe que dans cette copie temporaire
ESSAI = {"identifiant": "essai", "nom": "Essai navigateur", "mot_de_passe": "essai du navigateur 2026"}
base = Base(config.chemin("base"))
if not comptes.lire(base, ESSAI["identifiant"]):
    comptes.creer(base, ESSAI["identifiant"], ESSAI["nom"], ESSAI["mot_de_passe"], "admin")
    with contextlib.redirect_stdout(io.StringIO()):  # « 6e Démo », remplie de réponses aux profils connus
        assert demo.main([ESSAI["identifiant"]]) == 0 and simulation.main([ESSAI["identifiant"]]) == 0

import threading  # noqa: E402

import uvicorn  # noqa: E402

from generateur.classe import serveur as serveur_classe  # noqa: E402
from generateur.interface import api  # noqa: E402

if ENTRAINEMENT:
    from generateur.entrainement import relecture
    relecture.OBJECTIF_RELUS = 2  # un échantillon de 2 : l'essai en voit la fin
    print(f"Lot d'entraînement d'essai : http://127.0.0.1:{port}/ (lot dans {copie / 'entrainement'})", flush=True)
    uvicorn.run(api.creer_application(entrainement=True, banque_enseignant=copie / "banque" / "instances"),
                host="127.0.0.1", port=port, log_level="warning")
    sys.exit(0)

REGLAGES_CLASSE = {"adresse": "127.0.0.1", "port": port + 1, "hotes": [], "certificat": None, "cle_privee": None}
serveur_classe.reglages = lambda: REGLAGES_CLASSE  # l'interface montre l'adresse de CE serveur de classe
threading.Thread(target=uvicorn.run, args=(serveur_classe.creer_application(r=REGLAGES_CLASSE),),
                 kwargs={"host": "127.0.0.1", "port": port + 1, "log_level": "warning"}, daemon=True).start()
print(f"Interface d'essai : http://127.0.0.1:{port}/ (banque copiée dans {copie}) ; "
      f"serveur de classe : http://127.0.0.1:{port + 1}/", flush=True)
uvicorn.run(api.creer_application(), host="127.0.0.1", port=port, log_level="warning")
