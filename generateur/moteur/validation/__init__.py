class ErreurValidation(Exception):
    """Réponse du modèle rejetée ; le message est lisible par un humain (et réinjectable dans le prompt).

    `questions` liste les numéros (à partir de 1) des questions en faute, quand le défaut est localisé :
    c'est ce qui permettra de ne regénérer que ces questions-là.
    """

    def __init__(self, niveau: str, erreurs: list[str], questions: tuple[int, ...] = ()):
        self.niveau = niveau
        self.erreurs = erreurs
        self.questions = questions
        super().__init__(f"{niveau} : " + " ; ".join(erreurs))
