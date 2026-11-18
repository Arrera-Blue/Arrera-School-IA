"""La voix des exercices (E5) : fabriquée sur le PC enseignant par Piper, rangée dans la page en MP3.

Le poste de l'élève ne fait que jouer des fichiers son : aucune voix à installer, rien en ligne, la même voix
partout. La page mélange les propositions : on fabrique donc un morceau par texte (énoncé, chaque proposition,
explication) et les quelques phrases fixes (« A : », « Ta réponse : B. »…), que la page enchaîne dans l'ordre
affiché.

Sans Piper ou sans voix (réglage `lecture.voix` vide, fichier absent), la page se rend sans audio et retombe sur
la voix du navigateur (gabarit). La voix ne fait jamais échouer un rendu.

Essai à l'oreille :
    python -m generateur.moteur.lecture "Quelle fraction est égale à 3/4 ?" --sortie essai.mp3
"""

import argparse
import base64
import hashlib
import io
import os
import re
import sys
import threading
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from generateur.moteur import config

LETTRES = "ABCD"
# compression MP3 de libsndfile (0 à 1, 1 refusé) : 0,8 ≈ 4,5 Ko par seconde de voix, sans perte audible
COMPRESSION = 0.8


def phrases_fixes(nb_lettres: int = len(LETTRES)) -> dict[str, str]:
    fixes = {"juste": "Ta réponse est juste.", "explication": "Explication :"}
    for lettre in LETTRES[:nb_lettres]:
        fixes[f"lettre_{lettre}"] = f"{lettre} :"
        fixes[f"choisie_{lettre}"] = f"Ta réponse : {lettre}."
        fixes[f"bonne_{lettre}"] = f"La bonne réponse est {lettre}."
    return fixes


LETTRE = "a-zàâçéèêëîïôûùüœ"
ROMAINS = {"I": 1, "V": 5, "X": 10}
ORDINAUX = ("premier", "deuxième", "troisième", "quatrième", "cinquième", "sixième", "septième", "huitième", "neuvième",
            "dixième", "onzième", "douzième", "treizième", "quatorzième", "quinzième", "seizième", "dix-septième",
            "dix-huitième", "dix-neuvième", "vingtième", "vingt et unième")


def ordinal(romain: str) -> str:
    """« XIV » → « quatorzième » ; « I » → « premier »."""
    valeurs = [ROMAINS[c] for c in romain]
    n = sum(-v if i + 1 < len(valeurs) and v < valeurs[i + 1] else v for i, v in enumerate(valeurs))
    return ORDINAUX[n - 1] if 1 <= n <= len(ORDINAUX) else romain


def prononcable(texte: str) -> str:
    """Les écritures que la synthèse lit mal (le gabarit fait de même pour la voix du navigateur) : les maths ; une
    terminaison s'épelle (« -ent » : « e, n, t » ; lue, elle ferait « an », et Piper n'en tirait aucun son), un préfixe
    se lit sans son tiret (« in- ») ; la flèche d'une règle (« -al → -aux ») se dit « devient » (étape 1.5 du lot 1).
    L'histoire (lot 2) : « av. J.-C. » se dit « avant Jésus-Christ » ; un siècle en chiffres romains, en toutes lettres
    (« XIVe-XVe siècles » : « quatorzième et quinzième siècles ») ; « 10000 / 9000 » (deux années), « 10000 ou 9000 ».
    Les sciences (étape 2.3) : l'espace entre les milliers est retirée (« 3 000 grammes » : « 3000 », trois mille)."""
    texte = re.sub(r"(\d)[ \u00a0\u202f](?=\d{3}\b)", r"\1", texte)
    texte = re.sub(r"\b(?:av\.|avant) J\.-C\.", "avant Jésus-Christ", texte)
    texte = re.sub(r"\b(?:apr\.|après) J\.-C\.", "après Jésus-Christ", texte)
    texte = re.sub(r"\b([IVX]+)(?:er|e)\s*[-–]\s*([IVX]+)e\b", lambda m: f"{ordinal(m[1])} et {ordinal(m[2])}", texte)
    texte = re.sub(r"\b([IVX]+)(?:er|e)\b", lambda m: ordinal(m[1]), texte)
    texte = re.sub(r"\b(\d{4,})\s*/\s*(\d{4,})\b", r"\1 ou \2", texte)
    texte = re.sub(r"(\d)\s*/\s*(\d)", r"\1 sur \2", texte)
    texte = texte.replace("²", " au carré").replace("³", " au cube").replace("×", " fois ").replace("÷", " divisé par ")
    texte = re.sub(rf"(^|[^{LETTRE}-])-([{LETTRE}]+)(?![{LETTRE}])", lambda m: m[1] + ", ".join(m[2]), texte, flags=re.I)
    texte = re.sub(rf"^([{LETTRE}]+)-$", r"\1", texte.strip(), flags=re.I).replace("→", " devient ")
    return re.sub(r"\s+", " ", texte).strip()


@dataclass
class Voix:
    """Une voix chargée. `signature` change avec la voix et ses réglages : elle invalide le cache des morceaux."""
    signature: str
    synthetiser: object  # texte → MP3 (bytes)


def _avertir(message: str) -> None:
    print(f"lecture à voix haute : {message} ; la page utilisera la voix du navigateur", file=sys.stderr)


@cache
def voix() -> Voix | None:
    """La voix du réglage `lecture`, chargée une fois par processus ; None si elle n'est pas utilisable."""
    reglage = config.charger().get("lecture") or {}
    if not reglage.get("voix"):
        return None
    fichier = config.RACINE / reglage["voix"]
    if not fichier.exists():
        _avertir(f"voix introuvable ({reglage['voix']})")
        return None
    try:
        import numpy as np
        import soundfile
        from piper import PiperVoice, SynthesisConfig
    except ImportError as e:
        _avertir(f"Piper n'est pas installé ({e.name})")
        return None

    modele = PiperVoice.load(fichier)
    locuteur = reglage.get("locuteur")
    numero = None
    if locuteur is not None:
        if locuteur not in modele.config.speaker_id_map:
            _avertir(f"locuteur « {locuteur} » absent de la voix ({', '.join(modele.config.speaker_id_map) or 'aucun'})")
            return None
        numero = modele.config.speaker_id_map[locuteur]
    lenteur = reglage.get("lenteur")
    reglages = SynthesisConfig(speaker_id=numero, length_scale=lenteur)
    verrou = threading.Lock()  # une seule synthèse à la fois : l'interface sert plusieurs requêtes en parallèle

    def synthetiser(texte: str) -> bytes:
        with verrou:
            morceaux = list(modele.synthesize(texte, syn_config=reglages))
        audio = np.concatenate([m.audio_int16_array for m in morceaux])
        sortie = io.BytesIO()
        soundfile.write(sortie, audio, morceaux[0].sample_rate, format="MP3", compression_level=COMPRESSION)
        return sortie.getvalue()

    return Voix(f"{fichier.name}|{locuteur}|{lenteur}|{COMPRESSION}", synthetiser)


def _morceau(v: Voix, texte: str) -> tuple[str, bytes]:
    """Le MP3 d'un texte, gardé sur disque : un aperçu refait ne refait pas la voix."""
    cle = hashlib.sha256(f"{v.signature}\n{texte}".encode()).hexdigest()[:24]
    fichier = config.chemin("lecture") / f"{cle}.mp3"
    if fichier.exists():
        return cle, fichier.read_bytes()
    son = v.synthetiser(texte)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    temporaire = fichier.with_name(f".{cle}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporaire.write_bytes(son)
    os.replace(temporaire, fichier)
    return cle, son


def pour_la_page(instance: dict, explications: bool = True) -> dict | None:
    """Les morceaux de voix d'un exercice QCM, à ranger dans la page ; None sans voix utilisable.

    {"questions": [{"titre", "enonce", "propositions": [...], "explication"}], "fixes": {nom: clé},
     "clips": {clé: MP3 en base64}} : les questions et les phrases fixes désignent les morceaux par leur clé, un
    texte répété n'est rangé qu'une fois. Sans `explications` (page du serveur de classe), les explications restent
    au serveur : elles diraient la bonne réponse (`morceau_base64`, après la vérification)."""
    v = voix()
    if v is None:
        return None
    clips: dict[str, str] = {}

    def morceau(texte: str) -> str:
        cle, son = _morceau(v, prononcable(texte))
        clips.setdefault(cle, base64.b64encode(son).decode("ascii"))
        return cle

    try:
        n = len(instance["questions"])
        questions = [{"titre": morceau(f"Question {i} sur {n}."), "enonce": morceau(q["enonce"]),
                      "propositions": [morceau(p) for p in q["propositions"]],
                      **({"explication": morceau(q["explication"])} if explications else {})}
                     for i, q in enumerate(instance["questions"], start=1)]
        nb_lettres = max(len(q["propositions"]) for q in instance["questions"])
        fixes = {nom: morceau(texte) for nom, texte in phrases_fixes(nb_lettres).items()}
    except Exception as e:  # la voix ne fait jamais échouer un rendu
        _avertir(f"synthèse impossible ({type(e).__name__} : {e})")
        return None
    return {"questions": questions, "fixes": fixes, "clips": clips}


def morceau_base64(texte: str) -> str | None:
    """Le MP3 d'un seul texte, en base64 (l'explication envoyée par le serveur de classe après la vérification)."""
    v = voix()
    if v is None:
        return None
    try:
        return base64.b64encode(_morceau(v, prononcable(texte))[1]).decode("ascii")
    except Exception as e:  # la voix ne fait jamais échouer une réponse
        _avertir(f"synthèse impossible ({type(e).__name__} : {e})")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Lire un texte avec la voix du réglage `lecture` (essai à l'oreille).")
    parser.add_argument("texte")
    parser.add_argument("--sortie", type=Path, default=Path("essai-voix.mp3"))
    args = parser.parse_args()
    v = voix()
    if v is None:
        sys.exit("aucune voix utilisable : voir la section `lecture` de config.yaml")
    args.sortie.write_bytes(v.synthetiser(prononcable(args.texte)))
    print(f"voix écrite : {args.sortie}")


if __name__ == "__main__":
    main()
