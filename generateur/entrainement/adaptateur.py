"""L'adaptateur LoRA (plan IA, IA4.2) : l'entraîner sur le Mac avec mlx-lm, puis l'écrire au format de llama.cpp.

    python -m generateur.entrainement entrainer               # le dernier jeu → modeles/adaptateurs/<AAAAMMJJ-HHMM>.gguf
    python -m generateur.entrainement convertir <dossier> [--poids 0000200_adapters.safetensors]

Pour s'en servir : config.yaml, `llamacpp.adaptateur: "modeles/adaptateurs/<nom>.gguf"` ; null : le modèle de base.

L'entraînement : `mlx_lm lora`, QLoRA sur Gemma 4 E4B en 4 bits pour MLX, dans son propre environnement (config.yaml,
section `entrainement` ; il demande transformers 5), sur un jeu figé (IA3) dont les empreintes sont vérifiées d'abord.
Seul l'exercice est appris, pas le prompt (`mask_prompt`). Une itération = un exercice ; à chaque époque, la perte sur
la validation et un point d'étape (`0000200_adapters.safetensors`…) : on peut comparer les époques sans réentraîner.
Rien n'est téléchargé ni envoyé (`HF_HUB_OFFLINE`).

La conversion : mlx-lm range l'adaptateur en safetensors, llama.cpp le lit en GGUF. Plutôt que de passer par le format
PEFT et le script de llama.cpp (torch, transformers 4 et un clone de llama.cpp : essai du 30/10), on l'écrit ici, avec
numpy seulement :
- mlx-lm calcule `W x + échelle · (x @ lora_a) @ lora_b`, lora_a (entrée × r), lora_b (r × sortie) ; llama.cpp
  `W x + (alpha / r) · B (A x)`, A (r × entrée), B (sortie × r) : A = lora_aᵀ, B = lora_bᵀ, alpha = échelle × r ;
- les noms : `language_model.model.layers.26.self_attn.q_proj.lora_a` → `blk.26.attn_q.weight.lora_a`.
"""

import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from generateur.moteur import config

POIDS = "adapters.safetensors"  # le nom que mlx-lm donne à l'adaptateur (les points d'étape : 0000200_adapters…)
ARCHITECTURE = "gemma4"  # vérifiée par llama.cpp au chargement : un adaptateur ne se pose que sur son modèle
# les modules de mlx-lm → les tenseurs de llama.cpp (per_layer_* : propres aux Gemma « E »). Les 18 dernières
# couches de Gemma 4 E4B n'ont ni k_proj ni v_proj : elles reprennent les clés et valeurs de couches précédentes.
MODULES = {"self_attn.q_proj": "attn_q", "self_attn.k_proj": "attn_k", "self_attn.v_proj": "attn_v",
           "self_attn.o_proj": "attn_output", "mlp.gate_proj": "ffn_gate", "mlp.up_proj": "ffn_up",
           "mlp.down_proj": "ffn_down", "per_layer_input_gate": "inp_gate", "per_layer_projection": "proj"}
_CLE = re.compile(r"language_model\.model\.layers\.(\d+)\.(.+)\.lora_([ab])")


# --- lire l'adaptateur de mlx-lm (safetensors) -------------------------------------------------------------

_TYPES = {"F32": np.dtype("<f4"), "F16": np.dtype("<f2"), "BF16": np.dtype("<u2")}


def lire_safetensors(chemin: Path) -> dict[str, np.ndarray]:
    """Les tenseurs d'un fichier safetensors : la taille de l'en-tête (8 octets), l'en-tête (JSON : type, forme et
    position de chaque tenseur), puis les données."""
    donnees = Path(chemin).read_bytes()
    taille = struct.unpack("<Q", donnees[:8])[0]
    entete = json.loads(donnees[8:8 + taille])
    debut = 8 + taille
    tenseurs = {}
    for nom, t in entete.items():
        if nom == "__metadata__":
            continue
        if t["dtype"] not in _TYPES:
            raise ValueError(f"{chemin.name} : {nom} est en {t['dtype']}, type non pris en charge")
        type_, (a, b) = _TYPES[t["dtype"]], t["data_offsets"]
        if b - a != int(np.prod(t["shape"])) * type_.itemsize or debut + b > len(donnees):
            raise ValueError(f"{chemin.name} : {nom} ne correspond pas à sa description (fichier abîmé ?)")
        x = np.frombuffer(donnees, dtype=type_, count=(b - a) // type_.itemsize, offset=debut + a).reshape(t["shape"])
        if t["dtype"] == "BF16":  # bfloat16 : les 16 bits de poids fort d'un float32
            x = (x.astype(np.uint32) << 16).view(np.float32)
        tenseurs[nom] = x
    return tenseurs


def tenseurs_gguf(poids: dict[str, np.ndarray], rang: int) -> dict[str, np.ndarray]:
    """Les tenseurs de llama.cpp, en float16, dans l'ordre de son script de conversion (couche, module, A puis B)."""
    ranges = []
    for cle, x in poids.items():
        m = _CLE.fullmatch(cle)
        if not m or m.group(2) not in MODULES:
            raise ValueError(f"module inattendu dans l'adaptateur : {cle}")
        couche, module, ab = m.groups()
        if x.ndim != 2 or x.shape[1 if ab == "a" else 0] != rang:
            raise ValueError(f"{cle} : forme {list(x.shape)}, rang {rang} attendu")
        ranges.append(((int(couche), module, ab), f"blk.{couche}.{MODULES[module]}.weight.lora_{ab}", x))
    noms = {nom for _, nom, _ in ranges}
    if orphelins := sorted(n for n in noms if n[:-1] + ("b" if n.endswith("a") else "a") not in noms):
        raise ValueError(f"A sans B, ou B sans A : {', '.join(orphelins)}")
    sortie = {}
    for _, nom, x in sorted(ranges, key=lambda r: r[0]):
        y = np.ascontiguousarray(x.T, dtype=np.float16)  # A = lora_aᵀ, B = lora_bᵀ
        if not np.isfinite(y).all():
            raise ValueError(f"{nom} : des valeurs trop grandes pour un float16")
        sortie[nom] = y
    return sortie


# --- écrire le GGUF de llama.cpp ----------------------------------------------------------------------

GGUF_VERSION = 3
ALIGNEMENT = 32
_UINT32, _FLOAT32, _CHAINE = 4, 6, 8  # types des métadonnées
_F16 = 1  # type ggml des tenseurs


def _chaine(texte: str) -> bytes:
    octets = texte.encode("utf-8")
    return struct.pack("<Q", len(octets)) + octets


def _valeur(v: str | float | int) -> bytes:
    if isinstance(v, str):
        return struct.pack("<I", _CHAINE) + _chaine(v)
    if isinstance(v, float):
        return struct.pack("<If", _FLOAT32, v)
    if isinstance(v, int) and not isinstance(v, bool):
        return struct.pack("<II", _UINT32, v)
    raise TypeError(f"métadonnée GGUF non prise en charge : {v!r}")


def _aligne(n: int) -> int:
    return -(-n // ALIGNEMENT) * ALIGNEMENT


def ecrire_gguf(chemin: Path, metadonnees: dict, tenseurs: dict[str, np.ndarray]) -> None:
    """Le format GGUF, version 3 : l'en-tête, les métadonnées (clé, type, valeur), la description de chaque tenseur
    (nom, dimensions de la plus rapide à la plus lente, type, position), puis les données, alignées sur 32 octets."""
    entete = b"GGUF" + struct.pack("<IQQ", GGUF_VERSION, len(tenseurs), len(metadonnees))
    for cle, v in metadonnees.items():
        entete += _chaine(cle) + _valeur(v)
    position = 0
    for nom, x in tenseurs.items():
        assert x.dtype == np.float16 and x.flags.c_contiguous
        entete += (_chaine(nom) + struct.pack("<I", x.ndim) + struct.pack(f"<{x.ndim}Q", *reversed(x.shape))
                   + struct.pack("<IQ", _F16, position))
        position += _aligne(x.nbytes)
    with open(chemin, "wb") as f:
        f.write(entete + bytes(_aligne(len(entete)) - len(entete)))
        for x in tenseurs.values():
            f.write(x.tobytes() + bytes(_aligne(x.nbytes) - x.nbytes))


def convertir(dossier: Path, sortie: Path, poids: str = POIDS) -> dict:
    """L'adaptateur de mlx-lm (`dossier` : adapter_config.json et ses poids) → un fichier GGUF pour llama.cpp."""
    reglages = json.loads((dossier / "adapter_config.json").read_text(encoding="utf-8"))
    if reglages.get("fine_tune_type", "lora") != "lora":
        raise ValueError(f"seul un adaptateur LoRA se convertit (ici : {reglages['fine_tune_type']})")
    rang, echelle = int(reglages["lora_parameters"]["rank"]), float(reglages["lora_parameters"]["scale"])
    tenseurs = tenseurs_gguf(lire_safetensors(dossier / poids), rang)
    ecrire_gguf(sortie, {"general.architecture": ARCHITECTURE, "general.type": "adapter", "adapter.type": "lora",
                         "general.name": sortie.stem, "adapter.lora.alpha": echelle * rang,
                         "general.quantization_version": 2}, tenseurs)
    return {"tenseurs": len(tenseurs), "rang": rang, "alpha": echelle * rang, "octets": sortie.stat().st_size,
            "sha256": hashlib.sha256(sortie.read_bytes()).hexdigest()}


# --- entraîner (mlx-lm) -------------------------------------------------------------------------------

def dernier_jeu(jeux: Path) -> Path:
    figes = sorted(d for d in jeux.iterdir() if (d / "manifeste.json").is_file()) if jeux.is_dir() else []
    if not figes:
        raise ValueError(f"aucun jeu de données dans {jeux} : le préparer d'abord (python -m generateur.entrainement jeu)")
    return figes[-1]


def verifier_jeu(jeu: Path) -> dict:
    """Le manifeste du jeu, une fois vérifié qu'aucun de ses fichiers n'a changé depuis qu'il a été figé."""
    manifeste = json.loads((jeu / "manifeste.json").read_text(encoding="utf-8"))
    for nom, empreinte in manifeste["empreintes"].items():
        if not (jeu / nom).is_file() or hashlib.sha256((jeu / nom).read_bytes()).hexdigest() != empreinte:
            raise ValueError(f"{jeu / nom} a changé depuis que le jeu a été figé : refaire le jeu")
    if not manifeste["jeux"]["train"] or not manifeste["jeux"]["valid"]:
        raise ValueError(f"{jeu} : pas d'exercice d'entraînement ou de validation")
    return manifeste


def reglages(conf: dict, jeu: Path, dossier: Path, exemples: int, epoques: int) -> dict:
    """La configuration de `mlx_lm lora`, gardée à côté de l'adaptateur (reglages.yaml)."""
    return {"model": str(config.RACINE / conf["modele"]), "train": True, "data": str(jeu),
            "adapter_path": str(dossier), "fine_tune_type": "lora", "num_layers": conf["couches"],
            "lora_parameters": {"rank": conf["rang"], "scale": float(conf["echelle"]), "dropout": 0.0},
            "batch_size": 1, "iters": epoques * exemples, "learning_rate": float(conf["taux"]),
            "mask_prompt": True, "grad_checkpoint": True, "max_seq_length": conf["longueur_max"],
            "seed": conf["graine"], "steps_per_report": 10, "steps_per_eval": exemples, "val_batches": -1,
            "save_every": exemples}


def _lancer(commande: list[str], journal: Path) -> int:
    """Lance mlx-lm : sa sortie s'affiche au fil de l'eau et reste dans journal.txt."""
    env = {**os.environ, "HF_HUB_OFFLINE": "1"}  # tout est sur le Mac : rien à télécharger, rien à envoyer
    with open(journal, "w", encoding="utf-8") as f, subprocess.Popen(
            commande, cwd=config.RACINE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as p:
        for ligne in p.stdout:
            sys.stdout.write(ligne)
            sys.stdout.flush()
            f.write(ligne)
        return p.wait()


def _relatif(chemin: Path) -> str:
    return str(chemin.relative_to(config.RACINE)) if chemin.is_relative_to(config.RACINE) else str(chemin)


def entrainer(jeu: Path, adaptateurs: Path, epoques: int | None = None, nom: str | None = None,
              conf: dict | None = None) -> dict:
    """Entraîne un adaptateur sur le jeu figé `jeu`, le convertit pour llama.cpp et décrit ce qui a été fait :
    adaptateurs/<nom>.gguf, et adaptateurs/<nom>/ (l'adaptateur de mlx-lm, reglages.yaml, journal.txt,
    entrainement.json)."""
    conf = conf or config.charger()["entrainement"]
    epoques = epoques or conf["epoques"]
    python = config.RACINE / conf["python"]
    if not python.is_file():
        raise ValueError(f"mlx-lm introuvable ({python}) : l'installer (docs/etapes/etape-IA4-entrainement.md §1)")
    manifeste = verifier_jeu(jeu)
    nom = nom or f"{datetime.now():%Y%m%d-%H%M}"
    dossier, gguf = adaptateurs / nom, adaptateurs / f"{nom}.gguf"
    if dossier.exists() or gguf.exists():
        raise ValueError(f"{dossier} existe déjà : choisir un autre nom (--nom)")
    dossier.mkdir(parents=True)
    r = reglages(conf, jeu, dossier, len(manifeste["jeux"]["train"]), epoques)
    (dossier / "reglages.yaml").write_text(yaml.safe_dump(r, allow_unicode=True, sort_keys=False), encoding="utf-8")
    debut = time.monotonic()
    code = _lancer([str(python), "-m", "mlx_lm", "lora", "-c", str(dossier / "reglages.yaml")], dossier / "journal.txt")
    if code != 0 or not (dossier / POIDS).is_file():
        raise ValueError(f"l'entraînement a échoué (code {code}) : voir {dossier / 'journal.txt'}")
    duree = round(time.monotonic() - debut)
    bilan = {"nom": nom, "date": datetime.now().isoformat(timespec="seconds"), "jeu": _relatif(jeu),
             "manifeste_sha256": hashlib.sha256((jeu / "manifeste.json").read_bytes()).hexdigest(),
             "exemples": {k: len(v) for k, v in manifeste["jeux"].items()}, "epoques": epoques, "duree_s": duree,
             "reglages": r, "adaptateur": _relatif(gguf), **convertir(dossier, gguf)}
    (dossier / "entrainement.json").write_text(json.dumps(bilan, ensure_ascii=False, indent=2), encoding="utf-8")
    return bilan
