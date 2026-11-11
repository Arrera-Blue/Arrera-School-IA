"""Banc d'essai du prompt principal : les mêmes demandes, un prompt donné, le vrai modèle ; rien dans la vraie banque.

    .venv/bin/python scripts/essais/banc_prompt.py <dossier> [--prompt fichier.txt]   (depuis Arrera-School-IA)
                                      [--fois 2] [--demandes demandes.json] [--seulement cle1,cle2]

Chaque exercice produit (ou rejeté) est écrit dans <dossier>/<clé>-<n>.json, avec sa durée, ses tentatives et les
avertissements de N3 ; <dossier>/releve.md les montre tous, question par question, pour la relecture
(grille de la recette 1.6 : fond, ambiguïté, niveau, forme).
"""

import argparse
import contextlib
import dataclasses
import io
import json
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]  # Arrera-School-IA (scripts/essais/banc_prompt.py)
sys.path.insert(0, str(RACINE))

from generateur.moteur import config, generation, registre  # noqa: E402
from generateur.moteur.validation import ErreurValidation  # noqa: E402

LETTRES = "ABCD"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("dossier", type=Path)
    p.add_argument("--prompt", type=Path, help="le prompt à essayer (défaut : celui du dépôt)")
    p.add_argument("--fois", type=int, default=2)
    p.add_argument("--demandes", type=Path, default=Path(__file__).with_name("demandes.json"))
    p.add_argument("--seulement", help="clés des demandes à lancer, séparées par des virgules")
    args = p.parse_args()
    dossier = args.dossier.resolve()
    dossier.mkdir(parents=True, exist_ok=True)

    vrai = config.chemin  # banque, rejets, sortie : dans le dossier du banc, jamais dans la vraie banque
    config.chemin = lambda nom: dossier / nom if nom in ("banque", "rejets", "sortie", "supprimes") else vrai(nom)
    if args.prompt:
        texte = args.prompt.read_text(encoding="utf-8")
        charger = registre.charger
        registre.charger = lambda nom: dataclasses.replace(charger(nom), prompt=texte) if nom == "qcm" else charger(nom)
    prompt = registre.charger("qcm").prompt
    demandes = json.loads(args.demandes.read_text(encoding="utf-8"))
    if args.seulement:
        demandes = [d for d in demandes if d["cle"] in args.seulement.split(",")]

    releve = [f"# Banc du prompt — {time.strftime('%d/%m/%Y %H:%M')}\n",
              f"Prompt : `{args.prompt or 'dépôt'}` ({len(prompt)} caractères, {len(prompt.split())} mots)\n"]
    for d in demandes:
        for n in range(1, args.fois + 1):
            demande = {k: v for k, v in d.items() if k != "cle"}
            debut = time.monotonic()
            sortie = io.StringIO()
            try:
                with contextlib.redirect_stdout(sortie):
                    instance = generation.generer(demande, "qcm", mode="ia")
                rejet = None
            except ErreurValidation as e:
                instance, rejet = None, [str(x) for x in e.erreurs]
            duree = round(time.monotonic() - debut, 1)
            (dossier / f"{d['cle']}-{n}.json").write_text(json.dumps(
                {"demande": d, "duree_s": duree, "rejet": rejet, "instance": instance}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            releve.append(f"\n## {d['cle']} — essai {n} ({duree} s)\n")
            if rejet:
                releve.append(f"**Rejeté** : {rejet}\n")
                print(f"{d['cle']}-{n} : rejeté ({duree} s)", flush=True)
                continue
            meta = instance["meta"]
            appels = meta.get("appels") or []
            releve.append(f"Tentatives : {meta['tentatives']} ; tokens lus : "
                          f"{[a.get('tokens_lus') for a in appels]} ; "
                          f"avertissements N3 : {meta['avertissements'] or 'aucun'}\n")
            for i, q in enumerate(instance["questions"], start=1):
                props = " · ".join(("→ " if j == q["index_correct"] else "") + f"{LETTRES[j]}) {x}"
                                   for j, x in enumerate(q["propositions"]))
                releve.append(f"{i}. {q['enonce']}  \n   {props}  \n   *{q['explication']}*"
                              f"{' (' + q['difficulte'] + ')' if q.get('difficulte') else ''}\n")
            print(f"{d['cle']}-{n} : {len(instance['questions'])} questions, {meta['tentatives']} tentative(s), "
                  f"{duree} s, {len(meta['avertissements'])} avertissement(s)", flush=True)
    (dossier / "releve.md").write_text("\n".join(releve), encoding="utf-8")
    print(dossier / "releve.md")


if __name__ == "__main__":
    main()
