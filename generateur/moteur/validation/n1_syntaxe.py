"""N1 — la réponse du modèle est-elle du JSON analysable ?"""

import json
import re

from generateur.moteur.validation import ErreurValidation

BLOC_CODE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extraire_json(texte: str) -> dict:
    """Extrait l'objet JSON même s'il est entouré de texte ou d'un bloc ```json."""
    bloc = BLOC_CODE.search(texte)
    if bloc:
        texte = bloc.group(1)
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut == -1 or fin < debut:
        raise ErreurValidation("N1", ["la réponse ne contient aucun objet JSON"])
    try:
        instance = json.loads(texte[debut:fin + 1])
    except json.JSONDecodeError as e:
        raise ErreurValidation("N1", [f"JSON invalide ligne {e.lineno}, colonne {e.colno} : {e.msg}"]) from e
    if not isinstance(instance, dict):
        raise ErreurValidation("N1", ["la réponse n'est pas un objet JSON"])
    return instance
