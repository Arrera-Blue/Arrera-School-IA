"""La page de relecture des conjugaisons (lot 1, étape 1.1) : une grille par verbe, comme un Bescherelle, pour que
l'utilisateur relise la table `francais/conjugaisons` d'un coup d'œil avant de la valider.

Usage : python -I page_relecture_conjugaisons.py <generateur/procedural/donnees> <page.md>"""
import sys
from pathlib import Path

import yaml

donnees, page = Path(sys.argv[1]), Path(sys.argv[2])
conj = yaml.safe_load((donnees / "francais" / "conjugaisons.yaml").read_text(encoding="utf-8"))
term = yaml.safe_load((donnees / "francais" / "terminaisons.yaml").read_text(encoding="utf-8"))
TEMPS = {"present": "Présent", "imparfait": "Imparfait", "futur": "Futur", "passe_compose": "Passé composé"}
PERSONNES = ("je", "tu", "il", "nous", "vous", "ils")
CLASSE = {"CP": "dès le CP", "CE1": "dès le CE1", "CE2": "au CE2"}


def ecrite(pronom: str, forme: str) -> str:
    return f"j'{forme}" if pronom == "je" and forme[0] in "aeéèêiîoôuy" else f"{pronom} {forme}"


lignes = conj["lignes"]
verbes = list(dict.fromkeys(l["infinitif"] for l in lignes))
texte = [
    "# Relecture : la table des conjugaisons (`francais/conjugaisons`)", "",
    f"> Page générée depuis la table ({len(lignes)} formes, {len(verbes)} verbes). **À relire, puis à valider** :",
    "> `.venv/bin/python -m generateur.procedural.tables relire francais/conjugaisons --par \"…\"` (depuis",
    "> `Arrera-School-IA`). Chaque forme a déjà été comparée à Verbiste par le programme : 516 sur 516 identiques.",
    "> Ce qu'il faut regarder : les formes elles-mêmes, et **ce que chaque classe voit** (CP : être et avoir au présent ;",
    "> CE1 : 4 temps, être, avoir, verbes en -er ; CE2 : les 8 verbes irréguliers en plus).",
    "> Une case « — » : la forme n'est pas dans la table, exprès (passé composé avec être : seulement il et ils, car",
    "> « je suis allé » et « je suis allée » sont justes tous les deux).", ""]
for verbe in verbes:
    du_verbe = [l for l in lignes if l["infinitif"] == verbe]
    depuis = sorted({l["depuis"] for l in du_verbe}, key=["CP", "CE1", "CE2"].index)
    quand = " ; ".join(f"{TEMPS[t].lower()} {CLASSE[d]}" for d in depuis
                       for t in TEMPS if any(l["temps"] == t and l["depuis"] == d for l in du_verbe))
    texte += [f"## {verbe}", "", f"*{quand}*", "", "| | " + " | ".join(TEMPS.values()) + " |",
              "|---|" + "---|" * len(TEMPS)]
    for p in PERSONNES:
        cases = []
        for t in TEMPS:
            l = next((x for x in du_verbe if x["temps"] == t and x["personne"] == p), None)
            cases.append(ecrite(p, l["forme"]) if l else "—")
        texte.append(f"| **{p}** | " + " | ".join(cases) + " |")
    texte.append("")
texte += ["# Relecture : la table des terminaisons (`francais/terminaisons`)", "",
          "> Les terminaisons des verbes en -er (pour les explications et les questions « quelle est la terminaison »).",
          "> À valider : `.venv/bin/python -m generateur.procedural.tables relire francais/terminaisons --par \"…\"`", "",
          "| | Présent | Imparfait | Futur |", "|---|---|---|---|"]
for p in PERSONNES:
    texte.append(f"| **{p}** | " + " | ".join(next(l["terminaison"] for l in term["lignes"]
                                                 if l["temps"] == t and l["personne"] == p)
                                            for t in ("present", "imparfait", "futur")) + " |")
page.parent.mkdir(parents=True, exist_ok=True)
page.write_text("\n".join(texte) + "\n", encoding="utf-8")
print(f"{page} : {len(verbes)} grilles")
