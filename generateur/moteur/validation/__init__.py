class ErreurValidation(Exception):
    """Réponse du modèle rejetée ; le message est lisible par un humain (et réinjectable dans le prompt)."""

    def __init__(self, niveau: str, erreurs: list[str]):
        self.niveau = niveau
        self.erreurs = erreurs
        super().__init__(f"{niveau} : " + " ; ".join(erreurs))
import re


class ErreurValidation(Exception):
    """Réponse du modèle rejetée ; le message est lisible par un humain (et réinjectable dans le prompt).

    `questions` liste les numéros (à partir de 1) des questions en faute, quand le défaut est localisé :
    c'est ce qui permettra de ne regénérer que ces questions-là.
    `rejet` est renseigné par la génération : le fichier où le rejet a été conservé (banque/rejets/).
    """

    def __init__(self, niveau: str, erreurs: list[str], questions: tuple[int, ...] = ()):
        self.niveau = niveau
        self.erreurs = erreurs
        self.questions = questions
        self.rejet = None
        super().__init__(f"{niveau} : " + " ; ".join(erreurs))


def numero_de_question(message: str) -> int:
    """« question 3 : … » → 3 ; 0 si le message ne concerne pas une question précise (titre, JSON…)."""
    m = re.match(r"question (\d+)", message)
    return int(m[1]) if m else 0
