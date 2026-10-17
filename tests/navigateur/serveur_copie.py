"""Lance l'interface enseignant sur une COPIE de la banque, pour l'essai dans le navigateur (essai.mjs).

    .venv/bin/python tests/navigateur/serveur_copie.py <dossier> [port]

Copie banque/ dans <dossier>, puis sert l'interface sur 127.0.0.1:<port> (8012 par défaut) en écrivant
uniquement dans cette copie : les essais (accepter, modifier, supprimer…) ne touchent jamais la vraie banque.
"""

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
COPIES = {"banque": "banque/instances", "rejets": "banque/rejets", "supprimes": "banque/supprimes", "sortie": "sortie"}
config.chemin = lambda nom: copie / COPIES[nom] if nom in COPIES else vrai_chemin(nom)

import uvicorn  # noqa: E402

from generateur.interface import api  # noqa: E402

print(f"Interface d'essai : http://127.0.0.1:{port}/ (banque copiée dans {copie})", flush=True)
uvicorn.run(api.creer_application(), host="127.0.0.1", port=port, log_level="warning")
