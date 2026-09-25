from abc import ABC, abstractmethod


class ErreurFournisseur(Exception):
    """Panne du fournisseur (injoignable, modèle absent, délai dépassé…), avec un message lisible."""


class Fournisseur(ABC):
    nom: str
    modele: str

    @abstractmethod
    def generer(self, messages: list[dict], schema: dict) -> str:
        """Envoie les messages au modèle et renvoie sa réponse brute, contrainte par `schema`."""
