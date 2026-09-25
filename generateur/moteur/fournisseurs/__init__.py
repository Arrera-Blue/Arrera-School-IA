from generateur.moteur.fournisseurs.base import ErreurFournisseur, Fournisseur


def creer(nom: str, reglages: dict) -> Fournisseur:
    # imports locaux : un fournisseur n'est chargé que s'il est demandé
    if nom == "ollama":
        from generateur.moteur.fournisseurs.ollama import Ollama
        return Ollama(**reglages)
    if nom == "maquette":
        from generateur.moteur.fournisseurs.maquette import Maquette
        return Maquette()
    raise ErreurFournisseur(f"fournisseur « {nom} » inconnu (disponibles : ollama, maquette)")
