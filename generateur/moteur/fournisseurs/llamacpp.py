"""Fournisseur llama-cpp-python : le modèle tourne dans le processus Python, sans service à côté.

Pourquoi quitter Ollama (08/10/2026) : sur le VPS, une génération à froid passait ~200 s à relire un prompt
de 3 300 tokens. Ici, l'état du modèle après lecture du prompt est **gardé sur disque** (LlamaDiskCache) :
une génération qui commence comme une précédente (mêmes consignes, même exemple) reprend cet état au lieu de
tout relire, même après un redémarrage. Dans un processus qui dure (l'API de la phase 3), le modèle reste en
mémoire et le début commun des conversations n'est relu qu'une fois.

Le modèle est un fichier GGUF (config.yaml : `llamacpp.modele`), le même Gemma 4 E4B QAT qu'avec Ollama.
`llama_cpp` n'est importé qu'à la première génération : les tests et le reste du code s'en passent.
"""

import time
from pathlib import Path

from generateur.moteur import config
from generateur.moteur.fournisseurs.base import ErreurFournisseur, Fournisseur

# un modèle chargé par fichier et par processus : le charger coûte plusieurs secondes et ~5 Go de mémoire
_CHARGES: dict[tuple, object] = {}
GIGA = 1024 ** 3


class LlamaCpp(Fournisseur):
    nom = "llamacpp"

    def __init__(self, modele: str, n_ctx: int = 8192, n_threads: int | None = None, temperature: float = 0.5,
                 cache: str | None = "cache/llamacpp", cache_max_go: float = 2.0, options: dict | None = None):
        self.chemin = Path(modele) if Path(modele).is_absolute() else config.RACINE / modele
        self.modele = self.chemin.name
        self.n_ctx, self.n_threads, self.temperature = n_ctx, n_threads, temperature
        self.cache = (Path(cache) if Path(cache).is_absolute() else config.RACINE / cache) if cache else None
        self.cache_max_go = cache_max_go
        # autres réglages de llama_cpp.Llama, tels quels (swa_full, n_batch…) : sans toucher au code
        self.options = dict(options or {})
        self.chargement_s = 0.0  # compté au premier appel seulement, comme le « chargement » d'Ollama

    def _llama(self):
        cle = (str(self.chemin), self.n_ctx, self.n_threads, tuple(sorted(self.options.items())))
        if cle in _CHARGES:
            return _CHARGES[cle]
        if not self.chemin.is_file():
            raise ErreurFournisseur(
                f"modèle introuvable : {self.chemin} ; le télécharger (docs/etapes/migration-llamacpp.md, étape 2) "
                "ou corriger llamacpp.modele dans config.yaml")
        try:
            import llama_cpp
        except ImportError as e:
            raise ErreurFournisseur("llama-cpp-python n'est pas installé dans l'image : reconstruire le conteneur "
                                    "(docs/etapes/migration-llamacpp.md, étape 3)") from e
        debut = time.monotonic()
        try:
            llm = llama_cpp.Llama(model_path=str(self.chemin), n_ctx=self.n_ctx, n_threads=self.n_threads,
                                  verbose=False, **self.options)
        except TypeError as e:
            raise ErreurFournisseur(f"option de llamacpp.options inconnue de cette version de llama-cpp-python : {e}") from e
        except (ValueError, RuntimeError) as e:
            raise ErreurFournisseur(f"llama.cpp ne sait pas charger {self.chemin.name} : {e}") from e
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
            llm.set_cache(llama_cpp.LlamaDiskCache(cache_dir=str(self.cache),
                                                   capacity_bytes=int(self.cache_max_go * GIGA)))
        self.chargement_s = round(time.monotonic() - debut, 1)
        _CHARGES[cle] = llm
        return llm

    def generer(self, messages: list[dict], schema: dict) -> str:
        self.compteurs, self.chargement_s = None, 0.0
        llm = self._llama()
        debut = time.monotonic()
        try:
            # sortie structurée : llama.cpp traduit le schéma en grammaire, la génération ne peut pas en sortir
            reponse = llm.create_chat_completion(messages=messages, temperature=self.temperature,
                                                 response_format={"type": "json_object", "schema": schema})
        except ValueError as e:  # prompt plus long que le contexte, notamment
            raise ErreurFournisseur(f"llama.cpp a refusé la demande : {e} (n_ctx = {self.n_ctx})") from e
        usage = reponse.get("usage") or {}
        self.compteurs = {k: v for k, v in (("tokens_lus", usage.get("prompt_tokens")),
                                             ("tokens_ecrits", usage.get("completion_tokens")),
                                             ("chargement_s", self.chargement_s),
                                             ("total_s", round(time.monotonic() - debut + self.chargement_s, 1)))
                          if v is not None}
        return reponse["choices"][0]["message"]["content"]
