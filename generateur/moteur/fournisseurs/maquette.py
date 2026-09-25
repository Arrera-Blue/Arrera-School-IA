"""Fournisseur factice : renvoie exemple.json sans appel réseau. Sert à tester toute la chaîne sans modèle."""

import json

from generateur.moteur import registre
from generateur.moteur.fournisseurs.base import Fournisseur


class Maquette(Fournisseur):
    nom = "maquette"
    modele = "exemple.json"

    def generer(self, messages: list[dict], schema: dict) -> str:
        type_ = schema["properties"]["type"]["const"]
        return json.dumps(registre.charger(type_).exemple, ensure_ascii=False)
