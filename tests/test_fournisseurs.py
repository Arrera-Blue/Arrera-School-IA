"""Fournisseur Ollama, sans réseau : ce qu'on garde de sa réponse (étape 1.5)."""

import httpx

from generateur.moteur.fournisseurs import ollama
from generateur.moteur.fournisseurs.ollama import Ollama, compteurs

# réponse d'Ollama (/api/chat, stream: false), durées en nanosecondes
REPONSE = {"model": "gemma4:e4b-it-qat", "message": {"role": "assistant", "content": "{\"questions\": []}"},
           "done": True, "total_duration": 82_612_000_000, "load_duration": 98_000_000,
           "prompt_eval_count": 2310, "prompt_eval_duration": 4_215_000_000,
           "eval_count": 412, "eval_duration": 78_190_000_000}


def test_compteurs():
    assert compteurs(REPONSE) == {"tokens_lus": 2310, "tokens_ecrits": 412, "chargement_s": 0.1,
                                  "lecture_s": 4.2, "ecriture_s": 78.2, "total_s": 82.6}


def test_compteurs_absents():
    # prompt déjà en cache : Ollama peut omettre prompt_eval_count ; rien n'est inventé
    assert compteurs({"eval_count": 12, "message": {}}) == {"tokens_ecrits": 12}


def test_generer_garde_les_compteurs_du_dernier_appel(monkeypatch):
    monkeypatch.setattr(ollama.httpx, "post", lambda *a, **k: httpx.Response(200, json=REPONSE))
    fournisseur = Ollama("gemma4:e4b-it-qat", "http://127.0.0.1:11434", 600, 8192, False)
    assert fournisseur.compteurs is None
    assert fournisseur.generer([], {}) == "{\"questions\": []}"
    assert fournisseur.compteurs["tokens_ecrits"] == 412
