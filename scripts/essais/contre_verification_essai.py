"""Essai (hors dépôt) : la contre-vérification d'IA1.4 sur les 35 questions relues du banc de génération."""
import json, glob, os, sys, time
sys.path.insert(0, ".")
from generateur.moteur import generation
from generateur.outils.banc_ia import CONSIGNE_CONNAISSANCES
R = sys.argv[1]
verdicts = json.load(open(f"{R}/verdicts.json"))
f = generation.creer_fournisseur()
lignes, tableau = [], {"defaut_signale": 0, "defaut_rate": 0, "juste_signale": 0, "juste_ok": 0}
for p in sorted(glob.glob(f"{R}/*-[0-9].json")):
    cle = os.path.basename(p)[:-5]
    i = json.load(open(p))["instance"]
    if not i: continue
    v = verdicts.get(cle, {})
    defauts = set(v.get("fausses", [])) | set(v.get("ambigues", []))
    for n, q in enumerate(i["questions"], 1):
        schema = {"type": "object", "additionalProperties": False, "required": ["explication", "reponse"],
                  "properties": {"explication": {"type": "string", "maxLength": 400},
                                 "reponse": {"type": "integer", "minimum": 0, "maximum": len(q["propositions"]) - 1}}}
        texte = (f"Classe : {i['niveau']}. Matière : {i['matiere']}.\nQuestion : {q['enonce']}\nPropositions :\n"
                 + "\n".join(f"{k}. {x}" for k, x in enumerate(q["propositions"])))
        t = time.monotonic()
        r = json.loads(f.generer([{"role": "system", "content": CONSIGNE_CONNAISSANCES}, {"role": "user", "content": texte}], schema))
        signale = r["reponse"] != q["index_correct"]
        cle_t = ("defaut_" if n in defauts else "juste_") + ("signale" if signale else ("rate" if n in defauts else "ok"))
        tableau[cle_t] += 1
        lignes.append(f"{cle} Q{n} {'DÉFAUT' if n in defauts else 'juste'} : cochée {q['index_correct']}, retrouvée {r['reponse']} ({time.monotonic()-t:.1f} s)")
print("\n".join(lignes)); print(tableau)
json.dump({"tableau": tableau, "lignes": lignes}, open(f"{R}/contre-verification-essai.json", "w"), ensure_ascii=False, indent=1)
