from abc import ABC, abstractmethod
from collections.abc import Callable


class ErreurFournisseur(Exception):
    """Panne du fournisseur (injoignable, modèle absent, délai dépassé…), avec un message lisible."""


class Fournisseur(ABC):
    nom: str
    modele: str
    # compteurs du dernier appel (tokens lus et écrits, durées en secondes), quand le fournisseur les donne
    compteurs: dict | None = None
    # reçoit la réponse au fil de son écriture, morceau par morceau, quand le fournisseur la diffuse
    # (llama.cpp) : l'interface en tire la question en cours d'écriture
    au_fil: Callable[[str], None] | None = None

    @property
    def adaptateur(self) -> dict | None:
        """L'adaptateur LoRA posé sur le modèle (plan IA, IA4), noté dans chaque exercice : {"nom", "sha256"} ; None :
        le modèle de base."""
        return None

    @abstractmethod
    def generer(self, messages: list[dict], schema: dict) -> str:
        """Envoie les messages au modèle et renvoie sa réponse brute, contrainte par `schema`."""
