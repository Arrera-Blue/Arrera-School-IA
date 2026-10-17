"""Fournisseur Ollama : le modèle tourne sur l'hôte du VPS, joint à l'URL de config.yaml."""

import json
import time

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
        """La réponse arrive au fil de l'écriture (`stream`), une ligne JSON par morceau, comme avec llama.cpp :
        l'interface en tire la question en cours d'écriture (3.3, C4 : sur un PC sans GPU, une génération dure
        plusieurs minutes). La dernière ligne (« done ») porte les compteurs. `delai_max` borne l'attente de
        chaque morceau et la durée totale."""
        self.compteurs = None
        corps = {
            "model": self.modele,
            "messages": messages,
            # sortie structurée : Ollama contraint la génération au schéma, champ par champ
            "format": schema,
            "stream": True,
            "think": self.think,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        debut = time.monotonic()
        morceaux: list[str] = []
        fin: dict = {}
        try:
            with httpx.stream("POST", f"{self.url}/api/chat", json=corps,
                              timeout=httpx.Timeout(self.delai_max, connect=5)) as reponse:
                if reponse.status_code != 200:
                    texte = reponse.read().decode("utf-8", "replace")
                    if reponse.status_code == 404 and "not found" in texte:
                        raise ErreurFournisseur(f"modèle « {self.modele} » absent de l'hôte : ollama pull {self.modele}")
                    raise ErreurFournisseur(f"Ollama a répondu {reponse.status_code} : {texte[:300]}")
                for ligne in reponse.iter_lines():
                    if not ligne.strip():
                        continue
                    donnees = json.loads(ligne)
                    if donnees.get("error"):
                        raise ErreurFournisseur(f"Ollama a signalé une erreur : {donnees['error']}")
                    texte = (donnees.get("message") or {}).get("content")
                    if texte:
                        morceaux.append(texte)
                        if self.au_fil is not None:
                            self.au_fil(texte)
                    if donnees.get("done"):
                        fin = donnees
                    if time.monotonic() - debut > self.delai_max:
                        raise httpx.ReadTimeout("durée totale dépassée")
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
        except json.JSONDecodeError as e:
            raise ErreurFournisseur(f"réponse d'Ollama illisible : {e}") from e
        self.compteurs = compteurs(fin)
        return "".join(morceaux)


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
