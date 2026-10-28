"""Lance l'interface enseignant sur une COPIE de la banque, pour l'essai dans le navigateur (essai.mjs).

    .venv/bin/python tests/navigateur/serveur_copie.py <dossier> [port]

Copie banque/ dans <dossier>, puis sert l'interface sur 127.0.0.1:<port> (8012 par défaut) en écrivant
uniquement dans cette copie : les essais (accepter, modifier, supprimer…) ne touchent jamais la vraie banque.
La base (comptes, journal) est neuve, dans la copie, avec un seul compte administrateur : ESSAI (E1), sa classe
de démonstration (24 élèves fictifs) et leurs réponses simulées, pour le suivi (E4).
Le serveur de classe (E8) tourne aussi, sur la même copie, au port suivant (<port> + 1) : c'est son adresse que
l'interface affiche, et l'essai y bloque un élève par 5 codes faux.
"""

import contextlib
import io
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE))

from generateur.moteur import config  # noqa: E402

copie = Path(sys.argv[1]).resolve()
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8012
if (RACINE / "banque").is_dir():
    shutil.copytree(RACINE / "banque", copie / "banque", dirs_exist_ok=True)
vrai_chemin = config.chemin
COPIES = {"banque": "banque/instances", "rejets": "banque/rejets", "supprimes": "banque/supprimes", "sortie": "sortie",
          "base": "donnees/arrera.sqlite3", "sauvegardes": "donnees/sauvegardes", "cle_codes": "donnees/cle-codes"}
config.chemin = lambda nom: copie / COPIES[nom] if nom in COPIES else vrai_chemin(nom)

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

REGLAGES_CLASSE = {"adresse": "127.0.0.1", "port": port + 1, "hotes": [], "certificat": None, "cle_privee": None}
serveur_classe.reglages = lambda: REGLAGES_CLASSE  # l'interface montre l'adresse de CE serveur de classe
threading.Thread(target=uvicorn.run, args=(serveur_classe.creer_application(r=REGLAGES_CLASSE),),
                 kwargs={"host": "127.0.0.1", "port": port + 1, "log_level": "warning"}, daemon=True).start()
print(f"Interface d'essai : http://127.0.0.1:{port}/ (banque copiée dans {copie}) ; "
      f"serveur de classe : http://127.0.0.1:{port + 1}/", flush=True)
uvicorn.run(api.creer_application(), host="127.0.0.1", port=port, log_level="warning")
