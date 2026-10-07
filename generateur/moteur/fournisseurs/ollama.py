"""Fournisseur Ollama : le modèle tourne sur l'hôte du VPS, joint à l'URL de config.yaml."""

import httpx

from generateur.moteur.fournisseurs.base import ErreurFournisseur, Fournisseur


class Ollama(Fournisseur):
    nom = "ollama"

    def __init__(self, modele: str, url: str, delai_max: float, num_ctx: int, think: bool, temperature: float = 0.5):
        self.modele = modele
        self.url = url.rstrip("/")
        self.delai_max = delai_max
        self.num_ctx = num_ctx
        self.think = think
        self.temperature = temperature

    def generer(self, messages: list[dict], schema: dict) -> str:
        self.compteurs = None
        corps = {
            "model": self.modele,
            "messages": messages,
            # sortie structurée : Ollama contraint la génération au schéma, champ par champ
            "format": schema,
            "stream": False,
            "think": self.think,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        try:
            reponse = httpx.post(f"{self.url}/api/chat", json=corps, timeout=httpx.Timeout(self.delai_max, connect=5))
        except httpx.ConnectError as e:
            raise ErreurFournisseur(
                f"modèle injoignable à {self.url} : le service Ollama tourne-t-il sur l'hôte ? "
                "(sudo systemctl status ollama) — et le conteneur est-il bien en --network=host ?"
            ) from e
        except httpx.TimeoutException as e:
            raise ErreurFournisseur(
                f"délai dépassé ({self.delai_max} s) : le modèle n'a pas fini de répondre ; "
                "augmenter delai_max dans config.yaml ou demander moins de questions"
            ) from e

        if reponse.status_code == 404 and "not found" in reponse.text:
            raise ErreurFournisseur(f"modèle « {self.modele} » absent de l'hôte : ollama pull {self.modele}")
        if reponse.status_code != 200:
            raise ErreurFournisseur(f"Ollama a répondu {reponse.status_code} : {reponse.text[:300]}")
        donnees = reponse.json()
        self.compteurs = compteurs(donnees)
        return donnees["message"]["content"]


DUREES = (("load_duration", "chargement_s"), ("prompt_eval_duration", "lecture_s"),
          ("eval_duration", "ecriture_s"), ("total_duration", "total_s"))


def compteurs(donnees: dict) -> dict:
    """Ce qu'Ollama dit de l'appel : tokens lus (le prompt) et écrits (la réponse), et où le temps est passé
    (chargement du modèle, lecture du prompt, écriture). Les durées d'Ollama sont en nanosecondes."""
    resultat = {"tokens_lus": donnees.get("prompt_eval_count"), "tokens_ecrits": donnees.get("eval_count")}
    for cle, nom in DUREES:
        if donnees.get(cle) is not None:
            resultat[nom] = round(donnees[cle] / 1e9, 1)
    return {k: v for k, v in resultat.items() if v is not None}
