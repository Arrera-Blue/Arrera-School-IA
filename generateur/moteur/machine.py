"""La machine qui génère, notée dans le meta de chaque exercice (phase 2 : mesurer le matériel).

Le même modèle met 395 s sur le VPS (4 vCPU, sans GPU) et 32 s sur un Mac M4 Pro (Metal) : sans la machine,
les durées enregistrées ne se comparent pas. Rien d'identifiant (ni nom d'hôte ni utilisateur) : le
processeur, les cœurs et la mémoire suffisent à dimensionner le PC enseignant.
"""

import os
import platform
import subprocess
from functools import cache
from pathlib import Path

GIGA = 1024 ** 3


def _processeur() -> str | None:
    if platform.system() == "Darwin":
        try:
            sortie = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True,
                                    timeout=5, check=True).stdout.strip()
            return sortie or None
        except (OSError, subprocess.SubprocessError):
            return None
    try:
        for ligne in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if ligne.startswith("model name"):
                return ligne.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


def _ram_go() -> float | None:
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / GIGA, 1)
    except (ValueError, OSError, AttributeError):
        return None


@cache
def decrire() -> dict:
    """{"systeme": "Darwin arm64", "processeur": "Apple M4 Pro", "coeurs": 12, "ram_go": 24.0}"""
    return {"systeme": f"{platform.system()} {platform.machine()}", "processeur": _processeur(),
            "coeurs": os.cpu_count(), "ram_go": _ram_go()}


def libelle(machine: dict | None) -> str:
    """« Apple M4 Pro, 12 cœurs, 24 Go », pour les tableaux de mesure."""
    if not machine:
        return "machine non relevée"
    morceaux = [machine.get("processeur") or machine.get("systeme") or "?"]
    if machine.get("coeurs"):
        morceaux.append(f"{machine['coeurs']} cœurs")
    if machine.get("ram_go"):
        morceaux.append(f"{machine['ram_go']:g} Go")
    return ", ".join(morceaux)
