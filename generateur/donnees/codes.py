"""Les codes de connexion des élèves (évolution E3, choix ⚖3 du modèle de menace) : 4 images parmi 12 en 6e ; de la 5e
à la 3e, un mot de passe tiré au sort, imprimé sur la carte (E8, 27/10 : « tigre-bleu-27 », 2 mots et 2 chiffres,
~185 000 possibilités contre 20 736 pour les images ; majuscules, espaces et tirets oubliés pardonnés).

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
import unicodedata
from pathlib import Path

from generateur.donnees import images
from generateur.donnees.base import _fichier_prive

LONGUEUR = 4
# des mots courts, sans accent, faciles à taper et à lire à voix haute ; masculins, pour que l'adjectif s'accorde
NOMS = ("tigre", "lion", "ours", "loup", "renard", "castor", "dauphin", "requin", "phoque", "cheval", "lapin", "hibou",
        "aigle", "faucon", "corbeau", "moineau", "canard", "cygne", "pingouin", "koala", "panda", "chameau", "lama",
        "bison", "cerf", "lynx", "jaguar", "puma", "gorille", "crabe", "homard", "saumon", "crayon", "cahier", "ballon",
        "bateau", "avion", "train", "camion", "robot", "nuage", "volcan", "glacier", "sapin", "rocher", "caillou",
        "tambour", "violon", "piano", "sifflet", "chapeau", "manteau", "soleil", "orage", "comete", "phare", "moulin",
        "pont", "jardin", "chateau", "tresor", "dragon", "lutin", "griffon")
ADJECTIFS = ("bleu", "vert", "rouge", "jaune", "orange", "violet", "rose", "blanc", "noir", "gris", "brun", "rapide",
             "calme", "joyeux", "malin", "brave", "fort", "doux", "grand", "petit", "sage", "vif", "fier", "curieux",
             "agile", "discret", "gentil", "solide", "ancien", "moderne", "geant", "timide")
SCRYPT_CODE_RECOMMANDE = {"n": 2 ** 14, "r": 8, "p": 1}
SCRYPT_CODE = dict(SCRYPT_CODE_RECOMMANDE)  # les tests l'allègent (tests/conftest.py)
TAILLE_CLE = 32


def tirer() -> tuple[int, ...]:
    """4 rangs d'images, tirés par `secrets` ; jamais 4 fois la même image."""
    while True:
        code = tuple(secrets.randbelow(images.NOMBRE) for _ in range(LONGUEUR))
        if len(set(code)) > 1:
            return code


def tirer_mot_de_passe() -> str:
    """« tigre-bleu-27 » : un nom, un adjectif, deux chiffres (10 à 99), tirés par `secrets`."""
    return f"{secrets.choice(NOMS)}-{secrets.choice(ADJECTIFS)}-{10 + secrets.randbelow(90)}"


def normaliser(texte: str) -> str:
    """Ce qui compte dans un mot de passe tapé : les lettres et les chiffres, sans accent ni majuscule.
    « Tigre Bleu 27 », « tigre-bleu27 » et « TIGRE-BLEU-27 » valent « tigrebleu27 »."""
    sans_accent = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode("ascii")
    return "".join(c for c in sans_accent.lower() if c.isalnum())[:64]


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


def _octets(code: tuple[int, ...] | str) -> bytes:
    """Un code d'images (rangs) ou un mot de passe (normalisé) ; préfixes distincts : l'un ne vaut jamais l'autre."""
    if isinstance(code, str):
        return b"mdp:" + normaliser(code).encode("ascii")
    return "-".join(str(i) for i in code).encode("ascii")


def _calcul(code: tuple[int, ...] | str, sel: bytes, n: int, r: int, p: int, cle: bytes) -> bytes:
    derive = hashlib.scrypt(_octets(code), salt=sel, n=n, r=r, p=p, maxmem=2 ** 26, dklen=32)
    return hmac.new(cle, derive, "sha256").digest()


def empreinte(code: tuple[int, ...] | str, cle: bytes) -> str:
    """« scrypt-hmac$n$r$p$sel$mac » (sel et mac en base64)."""
    n, r, p = SCRYPT_CODE["n"], SCRYPT_CODE["r"], SCRYPT_CODE["p"]
    sel = secrets.token_bytes(16)
    mac = _calcul(code, sel, n, r, p, cle)
    return "$".join(["scrypt-hmac", str(n), str(r), str(p), base64.b64encode(sel).decode(), base64.b64encode(mac).decode()])


def verifier(code: tuple[int, ...] | str | None, enregistree: str, cle: bytes) -> bool:
    """Comparaison en temps constant ; False pour un code ou une empreinte mal formés, ou un mot de passe vide."""
    if code is None or (isinstance(code, str) and not normaliser(code)):
        return False
    try:
        nom, n, r, p, sel, mac = enregistree.split("$")
        if nom != "scrypt-hmac":
            return False
        calcule = _calcul(code, base64.b64decode(sel), int(n), int(r), int(p), cle)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calcule, base64.b64decode(mac))
