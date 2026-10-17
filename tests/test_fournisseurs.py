"""Fournisseurs Ollama et llama-cpp-python, sans réseau ni modèle : ce qu'on envoie, ce qu'on garde."""

import contextlib
import json
import sys
import types

import httpx
import pytest

from generateur.moteur.fournisseurs import ErreurFournisseur, creer, llamacpp, ollama
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


def flux(*lignes: dict, statut: int = 200, texte: str | None = None):
    """Remplace httpx.stream : la réponse d'Ollama en stream, une ligne JSON par morceau (3.3, C4)."""
    corps = texte if texte is not None else "\n".join(json.dumps(l) for l in lignes) + "\n"
    recu = {}

    @contextlib.contextmanager
    def stream(methode, url, json=None, timeout=None):
        recu.update(methode=methode, url=url, json=json)
        yield httpx.Response(statut, content=corps.encode())
    stream.recu = recu
    return stream


def morceaux_de(reponse: dict) -> list[dict]:
    """La réponse non diffusée de REPONSE, découpée comme Ollama la diffuse : du texte, puis « done »."""
    texte = reponse["message"]["content"]
    lignes = [{"message": {"role": "assistant", "content": texte[i:i + 5]}, "done": False}
              for i in range(0, len(texte), 5)]
    return lignes + [{**reponse, "message": {"role": "assistant", "content": ""}}]


def test_generer_garde_les_compteurs_du_dernier_appel(monkeypatch):
    stream = flux(*morceaux_de(REPONSE))
    monkeypatch.setattr(ollama.httpx, "stream", stream)
    fournisseur = Ollama("gemma4:e4b-it-qat", "http://127.0.0.1:11434", 600, 8192, False)
    assert fournisseur.compteurs is None
    recus = []
    fournisseur.au_fil = recus.append
    assert fournisseur.generer([], {}) == "{\"questions\": []}"
    assert fournisseur.compteurs["tokens_ecrits"] == 412 and fournisseur.compteurs["lecture_s"] == 4.2
    assert "".join(recus) == "{\"questions\": []}" and len(recus) > 1  # au fil de l'écriture
    assert stream.recu["json"]["stream"] is True and stream.recu["url"].endswith("/api/chat")


def test_ollama_erreurs_lisibles(monkeypatch):
    fournisseur = Ollama("gemma4:e4b-it-qat", "http://127.0.0.1:11434", 600, 8192, False)
    monkeypatch.setattr(ollama.httpx, "stream", flux(statut=404, texte='{"error":"model \'x\' not found"}'))
    with pytest.raises(ErreurFournisseur, match="ollama pull gemma4:e4b-it-qat"):
        fournisseur.generer([], {})
    monkeypatch.setattr(ollama.httpx, "stream", flux({"error": "mémoire insuffisante"}))
    with pytest.raises(ErreurFournisseur, match="mémoire insuffisante"):
        fournisseur.generer([], {})
    monkeypatch.setattr(ollama.httpx, "stream", flux(texte="pas du JSON\n"))
    with pytest.raises(ErreurFournisseur, match="illisible"):
        fournisseur.generer([], {})


# --- llama-cpp-python, sans le vrai modèle (étape : migration-llamacpp.md) -----------------------


class FauxLlama:
    charges = 0

    def __init__(self, model_path, n_ctx, n_threads, verbose, swa_full=False):
        self.verbose = verbose
        FauxLlama.charges += 1
        self.model_path, self.n_ctx, self.cache, self.recu = model_path, n_ctx, None, None
        self.swa_full = swa_full

    def set_cache(self, cache):
        self.cache = cache

    def create_chat_completion(self, messages, temperature, response_format, stream):
        self.recu = (messages, temperature, response_format, stream)
        self.n_tokens = 3300  # le prompt lu, puis un token par morceau écrit
        for texte in ("", "{\"questions\"", ": []", "}"):
            self.n_tokens += bool(texte)
            yield {"choices": [{"delta": {"content": texte} if texte else {"role": "assistant"}}]}


@pytest.fixture
def faux_llama_cpp(monkeypatch, tmp_path):
    module = types.SimpleNamespace(Llama=FauxLlama, LlamaDiskCache=lambda cache_dir, capacity_bytes:
                                   ("disque", cache_dir, capacity_bytes))
    monkeypatch.setitem(sys.modules, "llama_cpp", module)
    monkeypatch.setattr(llamacpp, "_CHARGES", {})
    FauxLlama.charges = 0
    modele = tmp_path / "gemma-4-E4B_q4_0-it.gguf"
    modele.write_bytes(b"GGUF")
    return modele


def test_llamacpp_genere_avec_le_schema_et_garde_les_compteurs(faux_llama_cpp, tmp_path):
    f = creer("llamacpp", {"modele": str(faux_llama_cpp), "n_ctx": 8192, "temperature": 0.5,
                           "cache": str(tmp_path / "cache"), "cache_max_go": 1})
    assert f.nom == "llamacpp" and f.modele == "gemma-4-E4B_q4_0-it.gguf"
    schema = {"type": "object", "properties": {"questions": {"type": "array"}}}
    assert f.generer([{"role": "user", "content": "…"}], schema) == "{\"questions\": []}"
    llm = llamacpp._CHARGES[(str(faux_llama_cpp), 8192, None, False, ())]
    assert llm.recu[1] == 0.5 and llm.recu[2] == {"type": "json_object", "schema": schema} and llm.recu[3]
    assert llm.cache == ("disque", str(tmp_path / "cache"), 1024 ** 3)            # cache du prompt sur disque
    assert f.compteurs["tokens_lus"] == 3300 and f.compteurs["tokens_ecrits"] == 3
    assert {"chargement_s", "lecture_s", "ecriture_s", "total_s"} <= set(f.compteurs)
    assert f.compteurs["gpu"] is False                                           # n_gpu_layers absent


def test_llamacpp_gpu_seulement_si_compile_pour(faux_llama_cpp, monkeypatch):
    # n_gpu_layers sans llama.cpp compilé pour un GPU : llama.cpp reste sur le processeur, le meta doit le dire
    f = creer("llamacpp", {"modele": str(faux_llama_cpp), "cache": None, "options": {"n_gpu_layers": -1}})
    assert f.sur_gpu() is False
    monkeypatch.setattr(sys.modules["llama_cpp"], "llama_supports_gpu_offload", lambda: True, raising=False)
    assert f.sur_gpu() is True
    f.options["n_gpu_layers"] = 0
    assert f.sur_gpu() is False


def test_llamacpp_charge_le_modele_une_seule_fois(faux_llama_cpp):
    reglages = {"modele": str(faux_llama_cpp), "cache": None}
    creer("llamacpp", reglages).generer([], {})
    second = creer("llamacpp", reglages)
    second.generer([], {})
    assert FauxLlama.charges == 1 and second.compteurs["chargement_s"] == 0.0


def test_llamacpp_modele_absent(faux_llama_cpp, tmp_path):
    with pytest.raises(ErreurFournisseur, match="modèle introuvable"):
        creer("llamacpp", {"modele": str(tmp_path / "absent.gguf")}).generer([], {})


def test_llamacpp_non_installe(monkeypatch, faux_llama_cpp):
    monkeypatch.setitem(sys.modules, "llama_cpp", None)  # import llama_cpp → ImportError
    with pytest.raises(ErreurFournisseur, match="pas installé"):
        creer("llamacpp", {"modele": str(faux_llama_cpp)}).generer([], {})


def test_llamacpp_options_transmises(faux_llama_cpp):
    f = creer("llamacpp", {"modele": str(faux_llama_cpp), "cache": None, "options": {"swa_full": True}})
    f.generer([], {})
    assert next(iter(llamacpp._CHARGES.values())).swa_full is True
    with pytest.raises(ErreurFournisseur, match="option de llamacpp.options inconnue"):
        creer("llamacpp", {"modele": str(faux_llama_cpp), "cache": None, "options": {"inconnue": 1}}).generer([], {})
