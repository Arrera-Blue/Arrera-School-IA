"""Gabarit + instance JSON → fichier HTML autonome.

Usage direct, sans IA, pour tester un gabarit sur un JSON écrit à la main :
    python -m generateur.moteur.rendu generateur/types/qcm/exemple.json --sortie sortie/exemple.html
"""

import argparse
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from generateur.moteur import config, registre


def rendre(instance: dict, type_: str, variante: str = "gabarit") -> str:
    type_exo = registre.charger(type_)
    if variante not in type_exo.gabarits:
        raise ValueError(f"gabarit « {variante} » absent du type « {type_} » ; disponibles : {', '.join(type_exo.gabarits)}")
    env = Environment(
        loader=FileSystemLoader(type_exo.dossier),
        # autoescape : un texte produit par le modèle ne peut jamais devenir du HTML ou du JavaScript
        autoescape=True,
        undefined=StrictUndefined,
    )
    # les champs optionnels absents valent None plutôt que de faire échouer StrictUndefined
    champs = {cle: None for cle in type_exo.schema.get("properties", {})}
    champs.update(instance)
    return env.get_template(f"{variante}.html").render(**champs)


def ecrire(html: str, sortie: Path) -> Path:
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(html, encoding="utf-8")
    return sortie


def main() -> None:
    parser = argparse.ArgumentParser(description="Rendre une instance JSON en exercice HTML.")
    parser.add_argument("instance", type=Path, help="fichier JSON de l'exercice")
    parser.add_argument("--variante", default="gabarit")
    parser.add_argument("--sortie", type=Path, default=config.chemin("sortie") / "exercice.html")
    args = parser.parse_args()

    instance = json.loads(args.instance.read_text(encoding="utf-8"))
    chemin = ecrire(rendre(instance, instance["type"], args.variante), args.sortie)
    print(f"exercice écrit : {chemin}")


if __name__ == "__main__":
    main()
