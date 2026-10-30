"""L'adaptateur LoRA (plan IA, IA4.2), sans mlx-lm ni modèle : la conversion pour llama.cpp, la commande d'entraînement.

La conversion a été comparée une fois au vrai script de llama.cpp (convert_lora_to_gguf.py, 30/10) : sur l'adaptateur
d'essai, le même fichier à l'octet près. Ici, un petit adaptateur fabriqué : les noms, les formes, l'alignement, et
surtout le calcul (llama.cpp doit ajouter au modèle exactement ce qu'ajoutait mlx-lm).
"""

import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

from generateur.entrainement import __main__ as commande
from generateur.entrainement import adaptateur

RANG, ECHELLE = 4, 20.0
# (module de mlx-lm, entrée, sortie) : de quoi couvrir l'attention, le MLP et les deux modules propres à Gemma 4
MODULES = [("self_attn.q_proj", 16, 8), ("mlp.down_proj", 24, 16), ("per_layer_input_gate", 16, 4),
           ("per_layer_projection", 4, 16)]


def ecrire_safetensors(chemin, tenseurs: dict[str, np.ndarray], types: dict[str, str] | None = None) -> None:
    entete, donnees = {}, b""
    for nom, x in tenseurs.items():
        octets = x.tobytes()
        entete[nom] = {"dtype": (types or {}).get(nom, "F32"), "shape": list(x.shape),
                       "data_offsets": [len(donnees), len(donnees) + len(octets)]}
        donnees += octets
    brut = json.dumps(entete).encode()
    chemin.write_bytes(struct.pack("<Q", len(brut)) + brut + donnees)


def faux_adaptateur(dossier, couches=(26, 27), modules=MODULES, reglages=None) -> dict[str, np.ndarray]:
    """Un adaptateur comme les range mlx-lm : lora_a (entrée × r), lora_b (r × sortie), en float32."""
    rng = np.random.default_rng(1)
    poids = {}
    for c in couches:
        for module, entree, sortie in modules:
            cle = f"language_model.model.layers.{c}.{module}"
            poids[f"{cle}.lora_a"] = rng.normal(0, 0.1, (entree, RANG)).astype(np.float32)
            poids[f"{cle}.lora_b"] = rng.normal(0, 0.1, (RANG, sortie)).astype(np.float32)
    dossier.mkdir(parents=True, exist_ok=True)
    ecrire_safetensors(dossier / adaptateur.POIDS, poids)
    (dossier / "adapter_config.json").write_text(json.dumps(reglages or {
        "fine_tune_type": "lora", "num_layers": len(couches),
        "lora_parameters": {"rank": RANG, "scale": ECHELLE, "dropout": 0.0}}))
    return poids


def lire_gguf(chemin):
    """Un lecteur GGUF minimal, pour relire ce que la conversion écrit."""
    b = chemin.read_bytes()
    pos = 0

    def lire(fmt):
        nonlocal pos
        v = struct.unpack_from(fmt, b, pos)
        pos += struct.calcsize(fmt)
        return v if len(v) > 1 else v[0]

    def chaine():
        nonlocal pos
        n = lire("<Q")
        pos += n
        return b[pos - n:pos].decode()

    assert b[:4] == b"GGUF"
    pos = 4
    version, n_tenseurs, n_meta = lire("<IQQ")
    meta = {}
    for _ in range(n_meta):
        cle, type_ = chaine(), lire("<I")
        meta[cle] = {8: chaine, 6: lambda: lire("<f"), 4: lambda: lire("<I")}[type_]()
    infos = []
    for _ in range(n_tenseurs):
        nom, n = chaine(), lire("<I")
        dims = [lire("<Q") for _ in range(n)]
        infos.append((nom, dims, *lire("<IQ")))
    debut = -(-pos // 32) * 32
    tenseurs = {nom: (dims, type_, position,
                      np.frombuffer(b, np.float16, int(np.prod(dims)), debut + position).reshape(dims[::-1]))
                for nom, dims, type_, position in infos}
    return version, meta, tenseurs


def test_convertir_calcule_comme_mlx(tmp_path):
    poids = faux_adaptateur(tmp_path / "mlx")
    r = adaptateur.convertir(tmp_path / "mlx", tmp_path / "essai.gguf")
    assert r["tenseurs"] == 16 and r["rang"] == RANG and r["alpha"] == ECHELLE * RANG
    assert r["sha256"] == hashlib.sha256((tmp_path / "essai.gguf").read_bytes()).hexdigest()
    version, meta, tenseurs = lire_gguf(tmp_path / "essai.gguf")
    assert version == 3
    assert meta == {"general.architecture": "gemma4", "general.type": "adapter", "adapter.type": "lora",
                    "general.name": "essai", "adapter.lora.alpha": ECHELLE * RANG, "general.quantization_version": 2}
    # l'ordre du script de llama.cpp : couche, module, A puis B ; chaque tenseur aligné sur 32 octets
    assert list(tenseurs)[:4] == ["blk.26.ffn_down.weight.lora_a", "blk.26.ffn_down.weight.lora_b",
                                  "blk.26.inp_gate.weight.lora_a", "blk.26.inp_gate.weight.lora_b"]
    assert {n.split(".")[2] for n in tenseurs} == {"attn_q", "ffn_down", "inp_gate", "proj"}
    assert all(position % 32 == 0 and type_ == 1 for _, type_, position, _ in tenseurs.values())
    # le calcul : mlx-lm ajoute échelle · (x @ lora_a) @ lora_b ; llama.cpp ajoute (alpha / r) · B (A x)
    x = np.random.default_rng(2).normal(size=24).astype(np.float32)
    a, b = poids["language_model.model.layers.27.mlp.down_proj.lora_a"], poids["language_model.model.layers.27.mlp.down_proj.lora_b"]
    dims_a, _, _, A = tenseurs["blk.27.ffn_down.weight.lora_a"]
    _, _, _, B = tenseurs["blk.27.ffn_down.weight.lora_b"]
    assert dims_a == [24, RANG]  # dans GGUF, la dimension la plus rapide d'abord : (entrée, r), comme dans mlx-lm
    attendu = ECHELLE * (x @ a) @ b
    obtenu = meta["adapter.lora.alpha"] / RANG * (B.astype(np.float32) @ (A.astype(np.float32) @ x))
    assert np.allclose(obtenu, attendu, rtol=1e-2, atol=1e-3)


def test_convertir_refuse_ce_qu_il_ne_sait_pas_traduire(tmp_path):
    faux_adaptateur(tmp_path / "inconnu", modules=[("self_attn.rotary", 8, 8)])
    with pytest.raises(ValueError, match="module inattendu"):
        adaptateur.convertir(tmp_path / "inconnu", tmp_path / "x.gguf")
    poids = faux_adaptateur(tmp_path / "orphelin")
    del poids["language_model.model.layers.26.self_attn.q_proj.lora_b"]
    ecrire_safetensors(tmp_path / "orphelin" / adaptateur.POIDS, poids)
    with pytest.raises(ValueError, match="A sans B"):
        adaptateur.convertir(tmp_path / "orphelin", tmp_path / "x.gguf")
    faux_adaptateur(tmp_path / "dora", reglages={"fine_tune_type": "dora", "lora_parameters": {"rank": RANG, "scale": 1}})
    with pytest.raises(ValueError, match="seul un adaptateur LoRA"):
        adaptateur.convertir(tmp_path / "dora", tmp_path / "x.gguf")
    faux_adaptateur(tmp_path / "rang", reglages={"lora_parameters": {"rank": 8, "scale": 1}})
    with pytest.raises(ValueError, match="rang 8 attendu"):
        adaptateur.convertir(tmp_path / "rang", tmp_path / "x.gguf")
    assert not (tmp_path / "x.gguf").exists()


def test_lire_safetensors_bfloat16_et_fichier_abime(tmp_path):
    valeurs = np.array([[1.5, -2.0], [0.25, 3.0]], dtype=np.float32)
    bf16 = (valeurs.view(np.uint32) >> 16).astype(np.uint16)  # valeurs exactes en bfloat16
    ecrire_safetensors(tmp_path / "bf16.safetensors", {"t": bf16}, {"t": "BF16"})
    assert np.array_equal(adaptateur.lire_safetensors(tmp_path / "bf16.safetensors")["t"], valeurs)
    ecrire_safetensors(tmp_path / "abime.safetensors", {"t": valeurs})
    (tmp_path / "abime.safetensors").write_bytes((tmp_path / "abime.safetensors").read_bytes()[:-4])
    with pytest.raises(ValueError, match="abîmé"):
        adaptateur.lire_safetensors(tmp_path / "abime.safetensors")


# --- l'entraînement, mlx-lm remplacé par un faux qui range un adaptateur ------------------------------------

def faux_jeu(dossier, train=6, valid=1, test=1):
    dossier.mkdir(parents=True)
    jeux = {"train": train, "valid": valid, "test": test}
    for nom, n in jeux.items():
        (dossier / f"{nom}.jsonl").write_text("".join(json.dumps({"messages": [i]}) + "\n" for i in range(n)))
    for nom in ("paires.jsonl", "a_eviter.jsonl"):
        (dossier / nom).write_text("")
    manifeste = {"jeux": {nom: [{"id": f"{nom}-{i}"} for i in range(n)] for nom, n in jeux.items()},
                 "empreintes": {f: hashlib.sha256((dossier / f).read_bytes()).hexdigest()
                                for f in ("train.jsonl", "valid.jsonl", "test.jsonl", "paires.jsonl", "a_eviter.jsonl")}}
    (dossier / "manifeste.json").write_text(json.dumps(manifeste))
    return dossier


@pytest.fixture
def conf(tmp_path):
    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("")
    return {"python": str(python), "modele": str(tmp_path / "gemma-mlx"), "epoques": 2, "rang": RANG,
            "echelle": ECHELLE, "couches": 2, "taux": 1e-5, "longueur_max": 6144, "graine": 2026}


@pytest.fixture
def faux_mlx(monkeypatch):
    lancees = []

    def lancer(commande, journal):
        lancees.append(commande)
        r = yaml.safe_load(open(commande[-1], encoding="utf-8"))
        faux_adaptateur(Path(r["adapter_path"]))
        journal.write_text("Iter 6: Val loss 0.250\n")
        return 0

    monkeypatch.setattr(adaptateur, "_lancer", lancer)
    return lancees


def test_dernier_jeu_et_jeu_modifie(tmp_path):
    with pytest.raises(ValueError, match="aucun jeu"):
        adaptateur.dernier_jeu(tmp_path / "jeux")
    faux_jeu(tmp_path / "jeux" / "20261101-090000")
    recent = faux_jeu(tmp_path / "jeux" / "20261102-090000")
    (tmp_path / "jeux" / "20261103-090000").mkdir()  # pas de manifeste : pas un jeu figé
    assert adaptateur.dernier_jeu(tmp_path / "jeux") == recent
    assert len(adaptateur.verifier_jeu(recent)["jeux"]["train"]) == 6
    (recent / "train.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="a changé depuis que le jeu a été figé"):
        adaptateur.verifier_jeu(recent)


def test_entrainer_lance_mlx_et_ecrit_l_adaptateur_pour_llama_cpp(tmp_path, conf, faux_mlx):
    jeu = faux_jeu(tmp_path / "jeux" / "20261101-090000")
    b = adaptateur.entrainer(jeu, tmp_path / "adaptateurs", nom="essai", conf=conf)
    [lancee] = faux_mlx
    assert lancee == [conf["python"], "-m", "mlx_lm", "lora", "-c", str(tmp_path / "adaptateurs" / "essai" / "reglages.yaml")]
    r = yaml.safe_load((tmp_path / "adaptateurs" / "essai" / "reglages.yaml").read_text(encoding="utf-8"))
    # une itération = un exercice : 2 époques sur 6 exercices ; validation et point d'étape à chaque époque
    assert r["iters"] == 12 and r["steps_per_eval"] == 6 and r["save_every"] == 6 and r["batch_size"] == 1
    assert r["mask_prompt"] is True and r["data"] == str(jeu) and r["fine_tune_type"] == "lora"
    assert r["lora_parameters"] == {"rank": RANG, "scale": ECHELLE, "dropout": 0.0}
    assert (tmp_path / "adaptateurs" / "essai.gguf").is_file()
    assert b["exemples"] == {"train": 6, "valid": 1, "test": 1} and b["epoques"] == 2 and b["tenseurs"] == 16
    assert b["manifeste_sha256"] == hashlib.sha256((jeu / "manifeste.json").read_bytes()).hexdigest()
    assert json.loads((tmp_path / "adaptateurs" / "essai" / "entrainement.json").read_text(encoding="utf-8")) == b
    with pytest.raises(ValueError, match="existe déjà"):
        adaptateur.entrainer(jeu, tmp_path / "adaptateurs", nom="essai", conf=conf)


def test_entrainer_echec_et_mlx_absent(tmp_path, conf, monkeypatch):
    jeu = faux_jeu(tmp_path / "jeu")
    monkeypatch.setattr(adaptateur, "_lancer", lambda commande, journal: 1)
    with pytest.raises(ValueError, match="l'entraînement a échoué"):
        adaptateur.entrainer(jeu, tmp_path / "adaptateurs", nom="raté", conf=conf)
    assert not (tmp_path / "adaptateurs" / "raté.gguf").exists()
    with pytest.raises(ValueError, match="mlx-lm introuvable"):
        adaptateur.entrainer(jeu, tmp_path / "adaptateurs", conf={**conf, "python": str(tmp_path / "absent")})


def test_commande_convertir_un_point_d_etape(tmp_path, monkeypatch, capsys):
    poids = faux_adaptateur(tmp_path / "20261101-0900")
    ecrire_safetensors(tmp_path / "20261101-0900" / "0000006_adapters.safetensors", poids)
    monkeypatch.setattr(sys, "argv", ["entrainement", "convertir", str(tmp_path / "20261101-0900"),
                                      "--poids", "0000006_adapters.safetensors"])
    commande.main()
    assert (tmp_path / "20261101-0900-0000006.gguf").is_file()
    assert "16 tenseurs, rang 4, alpha 80" in capsys.readouterr().out
