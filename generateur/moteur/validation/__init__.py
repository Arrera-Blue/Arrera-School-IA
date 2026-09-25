class ErreurValidation(Exception):
    """Réponse du modèle rejetée ; le message est lisible par un humain (et réinjectable dans le prompt)."""

    def __init__(self, niveau: str, erreurs: list[str]):
        self.niveau = niveau
        self.erreurs = erreurs
        super().__init__(f"{niveau} : " + " ; ".join(erreurs))
