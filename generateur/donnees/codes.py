"""Les codes de connexion des élèves (évolution E3, choix ⚖3 du modèle de menace) : 4 images parmi 12.

Le code n'est jamais gardé : la base n'a que son empreinte, un scrypt léger (n = 2¹⁴, ~40 ms : sur 20 736 codes
possibles, un calcul plus lent ne protégerait guère mieux une base volée), puis un HMAC-SHA256 avec une **clé
secrète de l'installation**. Cette clé est dans un fichier à part (`chemins.cle_codes`, droits 600), hors de la
base et de ses sauvegardes : une base ou une sauvegarde copiée seule ne permet pas de retrouver les codes en les
essayant tous. Clé perdue : tous les codes sont à refaire (« Nouveaux codes » de chaque classe).
"""

import base64
import hashlib
import hmac
import os
import secrets
from pathlib import Path

from generateur.donnees import images
from generateur.donnees.base import _fichier_prive

LONGUEUR = 4
SCRYPT_CODE_RECOMMANDE = {"n": 2 ** 14, "r": 8, "p": 1}
SCRYPT_CODE = dict(SCRYPT_CODE_RECOMMANDE)  # les tests l'allègent (tests/conftest.py)
TAILLE_CLE = 32


def tirer() -> tuple[int, ...]:
    """4 rangs d'images, tirés par `secrets` ; jamais 4 fois la même image."""
    while True:
        code = tuple(secrets.randbelow(images.NOMBRE) for _ in range(LONGUEUR))
        if len(set(code)) > 1:
            return code


def depuis_images(noms: list[str]) -> tuple[int, ...] | None:
    """[« soleil », « lune »…] → (0, 1…) ; None si ce n'est pas un code valable."""
    rangs = {ident: rang for rang, (ident, _) in enumerate(images.IMAGES)}
    if len(noms) != LONGUEUR or any(n not in rangs for n in noms):
        return None
    return tuple(rangs[n] for n in noms)


def cle_secrete(chemin: Path) -> bytes:
    """La clé de l'installation : lue, ou créée au premier usage (32 octets de `secrets`, droits 600)."""
    if not chemin.exists():
        _fichier_prive(chemin)
        descripteur = os.open(chemin, os.O_WRONLY | os.O_TRUNC)
        with os.fdopen(descripteur, "wb") as f:
            f.write(secrets.token_bytes(TAILLE_CLE))
    cle = chemin.read_bytes()
    if len(cle) != TAILLE_CLE:
        raise ValueError(f"clé des codes illisible ({chemin}) : la supprimer refait une clé, et tous les codes "
                         "seront à refaire")
    return cle


def _octets(code: tuple[int, ...]) -> bytes:
    return "-".join(str(i) for i in code).encode("ascii")


def _calcul(code: tuple[int, ...], sel: bytes, n: int, r: int, p: int, cle: bytes) -> bytes:
    derive = hashlib.scrypt(_octets(code), salt=sel, n=n, r=r, p=p, maxmem=2 ** 26, dklen=32)
    return hmac.new(cle, derive, "sha256").digest()


def empreinte(code: tuple[int, ...], cle: bytes) -> str:
    """« scrypt-hmac$n$r$p$sel$mac » (sel et mac en base64)."""
    n, r, p = SCRYPT_CODE["n"], SCRYPT_CODE["r"], SCRYPT_CODE["p"]
    sel = secrets.token_bytes(16)
    mac = _calcul(code, sel, n, r, p, cle)
    return "$".join(["scrypt-hmac", str(n), str(r), str(p), base64.b64encode(sel).decode(), base64.b64encode(mac).decode()])


def verifier(code: tuple[int, ...] | None, enregistree: str, cle: bytes) -> bool:
    """Comparaison en temps constant ; False pour un code ou une empreinte mal formés."""
    if code is None:
        return False
    try:
        nom, n, r, p, sel, mac = enregistree.split("$")
        if nom != "scrypt-hmac":
            return False
        calcule = _calcul(code, base64.b64decode(sel), int(n), int(r), int(p), cle)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calcule, base64.b64decode(mac))
