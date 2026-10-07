from abc import ABC, abstractmethod


class ErreurFournisseur(Exception):
    """Panne du fournisseur (injoignable, modèle absent, délai dépassé…), avec un message lisible."""


class Fournisseur(ABC):
    nom: str
    modele: str
    # compteurs du dernier appel (tokens lus et écrits, durées en secondes), quand le fournisseur les donne
    compteurs: dict | None = None

    @abstractmethod
    def generer(self, messages: list[dict], schema: dict) -> str:
        """Envoie les messages au modèle et renvoie sa réponse brute, contrainte par `schema`."""
