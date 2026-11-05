"""La pré-relecture du lot d'entraînement (plan IA, IA3, 05/11) : Claude (Opus 5.5, un autre modèle que celui qui a
écrit les exercices) relit l'échantillon avant l'enseignant et donne son avis, exercice par exercice : bon, à corriger
(les questions en cause, la correction proposée) ou à rejeter (les motifs). **L'enseignant décide** : l'avis ne change
ni le statut ni les questions. Un exercice pré-relu et pas encore décidé est « en cours de relecture ».

Les avis arrivent par paquets : un fichier JSONL écrit par Claude, une ligne par exercice, gardé dans
donnees/entrainement/prerelecture/ (la trace de ce qu'il a dit) :

    python -m generateur.entrainement prerelecture donnees/entrainement/prerelecture/paquet-01.jsonl

    {"id": "qcm-…", "avis": "a_corriger", "resume": "Les questions 2 et 4 ont chacune deux propositions justes…",
     "questions": [{"numero": 1, "juste": true}, {"numero": 2, "juste": false, "remarque": "…", "proposition": "…"}, …],
     "motifs": ["plusieurs_justes"], "precisions": "…"}

Chaque question est relue (une ligne par question, `juste` ou non) ; `motifs` et `precisions` remplissent d'avance la
boîte « Rejeter : pourquoi ? ». Un paquet où une ligne ne va pas n'est pas enregistré du tout. Chaque remarque garde
l'empreinte de la question relue : si l'enseignant la modifie ou la régénère, l'interface le dit au lieu de montrer une
remarque qui ne vaut plus. Chaque décision note l'avis du moment (`banque.decider`) : la fiche du jeu dit combien de
fois l'enseignant l'a suivi.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from generateur.moteur import banque

PAR = "Claude (Opus 5.5)"
AVIS = {"bon": "bon", "a_corriger": "à corriger", "a_rejeter": "à rejeter"}
RESUME_MAX, REMARQUE_MAX, PROPOSITION_MAX = 1000, 600, 400
PRECISIONS_MAX = 500  # comme le motif d'une décision (banque.decider)


def empreinte(question: dict) -> str:
    """La question telle qu'elle a été relue : si elle change (modifiée, régénérée), la remarque ne vaut plus."""
    cle = json.dumps([question.get("enonce"), question.get("propositions"), question.get("index_correct"),
                      question.get("explication")], ensure_ascii=False)
    return hashlib.sha256(cle.encode("utf-8")).hexdigest()[:16]


def _texte(valeur, nom: str, maximum: int, obligatoire: bool = False) -> str | None:
    if valeur is None and not obligatoire:
        return None
    if not isinstance(valeur, str) or not valeur.strip():
        raise ValueError(f"« {nom} » : un texte{'' if obligatoire else ' ou rien'}")
    if len(valeur.strip()) > maximum:
        raise ValueError(f"« {nom} » : {len(valeur.strip())} caractères, {maximum} au plus")
    return valeur.strip()


def preparer(ligne: dict, instance: dict, date: str) -> dict:
    """L'avis d'une ligne du paquet, vérifié, tel qu'il est gardé dans meta.prerelecture. ValueError s'il ne va pas."""
    if ligne.get("avis") not in AVIS:
        raise ValueError(f"avis inconnu : {ligne.get('avis')!r} ({', '.join(AVIS)})")
    questions = instance.get("questions") or []
    relues: dict[int, dict] = {}
    for q in ligne.get("questions") or []:
        n = q.get("numero") if isinstance(q, dict) else None
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(questions):
            raise ValueError(f"question {n!r} inexistante : l'exercice en compte {len(questions)}")
        if n in relues:
            raise ValueError(f"question {n} relue deux fois")
        if not isinstance(q.get("juste"), bool):
            raise ValueError(f"question {n} : « juste » vaut true ou false")
        relue = {"numero": n, "juste": q["juste"],
                 "remarque": _texte(q.get("remarque"), f"question {n}, remarque", REMARQUE_MAX, not q["juste"]),
                 "proposition": _texte(q.get("proposition"), f"question {n}, proposition", PROPOSITION_MAX),
                 "empreinte": empreinte(questions[n - 1])}
        relues[n] = {k: v for k, v in relue.items() if v is not None}
    if manquantes := [n for n in range(1, len(questions) + 1) if n not in relues]:
        raise ValueError(f"question(s) {', '.join(map(str, manquantes))} sans avis : chaque question est relue")
    fausses = [n for n, q in relues.items() if not q["juste"]]
    if ligne["avis"] == "bon" and fausses:
        raise ValueError(f"avis « bon », mais la question {fausses[0]} n'est pas juste")
    if ligne["avis"] == "a_corriger" and not fausses:
        raise ValueError("avis « à corriger », mais toutes les questions sont justes")
    motifs = ligne.get("motifs") or []
    if not isinstance(motifs, list) or (inconnus := [m for m in motifs if m not in banque.MOTIFS_DE_REJET]):
        raise ValueError(f"motif de rejet inconnu : {inconnus[0] if isinstance(motifs, list) else motifs!r}")
    if ligne["avis"] == "bon" and (motifs or ligne.get("precisions")):
        raise ValueError("avis « bon » : ni motif de rejet, ni précisions")
    return {"par": PAR, "date": date, "avis": ligne["avis"], "resume": _texte(ligne.get("resume"), "resume", RESUME_MAX, True),
            "questions": [relues[n] for n in sorted(relues)],
            "motifs": [m for m in banque.MOTIFS_DE_REJET if m in motifs],
            "precisions": _texte(ligne.get("precisions"), "precisions", PRECISIONS_MAX)}


def importer(fichier: Path) -> dict:
    """Enregistre les avis d'un paquet dans les exercices du lot (les dossiers de la banque doivent être ceux du lot :
    `entrainement.utiliser()`). Tout ou rien : ValueError, avec chaque ligne qui ne va pas, et rien n'est écrit.
    Renvoie les comptes : par avis, et les exercices déjà décidés (leur avis est gardé, leur statut ne change pas)."""
    date = datetime.now().isoformat(timespec="seconds")
    avis, problemes, vus = [], [], set()
    for numero, texte in enumerate(fichier.read_text(encoding="utf-8").splitlines(), start=1):
        if not texte.strip():
            continue
        try:
            ligne = json.loads(texte)
            if not isinstance(ligne, dict):
                raise ValueError("un objet JSON par ligne")
            ident = ligne.get("id")
            if ident in vus:
                raise ValueError(f"« {ident} » a déjà un avis plus haut dans le paquet")
            vus.add(ident)
            avis.append((ident, preparer(ligne, banque.charger(ident), date)))
        except (json.JSONDecodeError, ValueError, banque.ExerciceInconnu) as e:
            problemes.append(f"ligne {numero} : {e}")
    if problemes:
        raise ValueError("paquet refusé, rien n'est enregistré :\n" + "\n".join(problemes))
    comptes = {cle: 0 for cle in (*AVIS, "deja_decides")}
    for ident, valeur in avis:
        instance = banque.noter(ident, "prerelecture", valeur)
        comptes[valeur["avis"]] += 1
        comptes["deja_decides"] += banque.statut(instance) != banque.GENERE
    return comptes


def en_cours(instance: dict) -> bool:
    """Pré-relu, pas encore décidé : « en cours de relecture »."""
    return banque.statut(instance) == banque.GENERE and bool((instance.get("meta") or {}).get("prerelecture"))


def vue(instance: dict) -> dict | None:
    """L'avis pour la relecture, question par question ; `modifiee` : la question a changé depuis (la remarque portait
    sur l'ancienne version). None : pas de pré-relecture."""
    p = (instance.get("meta") or {}).get("prerelecture")
    if not p:
        return None
    questions = instance.get("questions") or []
    return {"par": p.get("par"), "date": p.get("date"), "avis": p.get("avis"), "libelle": AVIS.get(p.get("avis")),
            "resume": p.get("resume"), "motifs": p.get("motifs") or [], "precisions": p.get("precisions"),
            "questions": [{**{k: v for k, v in q.items() if k != "empreinte"},
                           "modifiee": q["numero"] > len(questions) or q.get("empreinte") != empreinte(questions[q["numero"] - 1])}
                          for q in p.get("questions") or []]}


def _derniere_decision(instance: dict) -> dict:
    return ((instance.get("meta") or {}).get("decisions") or [{}])[-1]


def suivi(instance: dict) -> bool | None:
    """L'enseignant a-t-il suivi l'avis ? None : décidé sans pré-relecture (ou pas décidé). Bon : accepté ; à rejeter :
    rejeté ; à corriger : accepté après avoir corrigé (modifié ou régénéré) au moins une question depuis l'avis."""
    decision = _derniere_decision(instance)
    avis = decision.get("avis_prerelecture")
    if not avis or banque.statut(instance) == banque.GENERE:
        return None
    if decision.get("statut") == banque.REJETE:
        return avis == "a_rejeter"
    if avis != "a_corriger":
        return avis == "bon"
    depuis = ((instance.get("meta") or {}).get("prerelecture") or {}).get("date") or ""
    return any((e.get("date") or "") >= depuis for e in banque.historique(instance))


def compter(du_lot: list[dict]) -> dict:
    """En cours de relecture ; décidés après une pré-relecture, et combien de fois l'avis a été suivi ; acceptés avant
    la pré-relecture (sans l'avoir vue), et combien d'entre eux Claude trouve à corriger ou à rejeter."""
    suivis = [s for s in map(suivi, du_lot) if s is not None]
    avant = [i for i in du_lot if banque.statut(i) == banque.ACCEPTE and (i.get("meta") or {}).get("prerelecture")
             and not _derniere_decision(i).get("avis_prerelecture")]
    return {"en_cours": sum(map(en_cours, du_lot)), "decides": len(suivis), "suivis": sum(suivis),
            "acceptes_avant": len(avant),
            **{f"acceptes_{avis}": sum(i["meta"]["prerelecture"].get("avis") == avis for i in avant)
               for avis in ("a_corriger", "a_rejeter")}}
