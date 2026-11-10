"""La contre-vérification (plan IA, IA1.4) : le modèle répond à chaque question qu'il a écrite, SANS voir la
réponse cochée ; s'il ne la retrouve pas, la question est signalée « à relire », avec ce qu'il a répondu.

Pourquoi : hors des maths, rien ne recalcule la réponse (N4). Au banc d'IA0, le modèle trouve 78 réponses sur 80
quand on lui pose la question seule, mais coche une mauvaise réponse dans 6 questions sur 35 qu'il écrit lui-même
(l'explication juste, une autre proposition cochée…). Essai du 29/10 sur ces 35 questions : 5 défauts sur 11
signalés, aucune fausse alerte sur les 24 questions justes, ~2,3 s par question, à température 0 ; ajouter les
réponses « aucune » et « plusieurs » n'attrapait pas plus (4 sur 11, deux fois) : le choix simple est gardé.

Jamais un rejet : un signalement, que l'enseignant tranche à la relecture (régénérer, modifier, accepter). Les
questions dont N4 a vérifié le calcul ne sont pas reposées. Un échec du modèle n'arrête jamais la génération.
"""

import hashlib
import json
import time
from contextlib import contextmanager

from generateur.moteur.fournisseurs import ErreurFournisseur, Fournisseur

CONSIGNE = (
    "Tu réponds à une question de QCM d'école élémentaire ou de collège français. Écris d'abord une explication courte (la règle, le fait, "
    "la date, le calcul), puis le numéro de la seule bonne proposition. Réponds uniquement par l'objet JSON demandé.")


def empreinte(question: dict) -> str:
    """La question telle qu'elle a été contre-vérifiée : si elle change (modifiée, régénérée), le verdict ne vaut plus."""
    cle = json.dumps([question.get("enonce"), question.get("propositions"), question.get("index_correct")],
                     ensure_ascii=False)
    return hashlib.sha256(cle.encode("utf-8")).hexdigest()[:16]


@contextmanager
def _sans_hasard(fournisseur: Fournisseur):
    """Température 0 le temps de la vérification : un verdict reproductible (même résultat à l'essai du 29/10)."""
    avant = getattr(fournisseur, "temperature", None)
    if avant is not None:
        fournisseur.temperature = 0.0
    try:
        yield
    finally:
        if avant is not None:
            fournisseur.temperature = avant


def repondre(fournisseur: Fournisseur, instance: dict, question: dict) -> dict:
    """{"retrouvee": numéro choisi par le modèle, "explication": …} ; lève ErreurFournisseur ou ValueError."""
    propositions = question["propositions"]
    schema = {"type": "object", "additionalProperties": False, "required": ["explication", "reponse"],
              "properties": {"explication": {"type": "string", "maxLength": 400},
                             "reponse": {"type": "integer", "minimum": 0, "maximum": len(propositions) - 1}}}
    texte = (f"Classe : {instance.get('niveau')}. Matière : {instance.get('matiere')}.\n"
             f"Question : {question['enonce']}\nPropositions :\n"
             + "\n".join(f"{i}. {p}" for i, p in enumerate(propositions)))
    reponse = json.loads(fournisseur.generer([{"role": "system", "content": CONSIGNE},
                                              {"role": "user", "content": texte}], schema))
    if not isinstance(reponse.get("reponse"), int) or not 0 <= reponse["reponse"] < len(propositions):
        raise ValueError(f"réponse hors des propositions : {reponse.get('reponse')!r}")
    return {"retrouvee": reponse["reponse"], "explication": str(reponse.get("explication") or "")[:400]}


def verifier(fournisseur: Fournisseur, instance: dict, statuts_n4: list[str] | None = None,
             numeros: list[int] | None = None, suivi=None) -> list[dict]:
    """Un verdict par question reposée (toutes, ou `numeros`), sauf celles dont N4 a vérifié le calcul :
    {"numero", "empreinte", "cochee", "retrouvee", "accord", "explication", "duree_s"} ; ou {"numero", "erreur"}."""
    questions = instance.get("questions") or []
    a_verifier = [n for n in (numeros or range(1, len(questions) + 1))
                  if not (statuts_n4 and n <= len(statuts_n4) and statuts_n4[n - 1] == "verifie")]
    verdicts = []
    with _sans_hasard(fournisseur):
        for rang, n in enumerate(a_verifier, start=1):
            q = questions[n - 1]
            if suivi is not None:
                suivi({"etape": "contre_verification", "question": n,
                       "message": f"Contre-vérification : le modèle répond à la question {n} sans voir la réponse "
                                  f"({rang} sur {len(a_verifier)})…"})
            debut = time.monotonic()
            try:
                r = repondre(fournisseur, instance, q)
            except (ErreurFournisseur, ValueError) as e:  # json.JSONDecodeError est une ValueError
                verdicts.append({"numero": n, "empreinte": empreinte(q), "erreur": str(e)[:200]})
                continue
            verdicts.append({"numero": n, "empreinte": empreinte(q), "cochee": q["index_correct"], **r,
                             "accord": r["retrouvee"] == q["index_correct"],
                             "duree_s": round(time.monotonic() - debut, 1)})
    return verdicts


def fusionner(anciens: list[dict] | None, nouveaux: list[dict]) -> list[dict]:
    """Les verdicts d'un exercice après la contre-vérification de quelques questions (régénération)."""
    par_numero = {v["numero"]: v for v in anciens or []}
    par_numero.update({v["numero"]: v for v in nouveaux})
    return [par_numero[n] for n in sorted(par_numero)]


def alertes(instance: dict) -> dict[int, str]:
    """{numéro : message} pour les questions où le modèle n'a pas retrouvé la réponse cochée, si la question n'a pas
    changé depuis (sinon, le verdict ne vaut plus)."""
    questions = instance.get("questions") or []
    resultat = {}
    for v in ((instance.get("meta") or {}).get("contre_verification") or []):
        n = v.get("numero")
        if v.get("accord") is not False or not isinstance(n, int) or not 1 <= n <= len(questions):
            continue
        q = questions[n - 1]
        if v.get("empreinte") != empreinte(q) or not 0 <= v.get("retrouvee", -1) < len(q["propositions"]):
            continue
        explication = (v.get("explication") or "").strip()
        if len(explication) > 160:
            explication = explication[:157] + "…"
        resultat[n] = (f"question {n} : la contre-vérification ne retrouve pas la réponse cochée : sans la voir, le "
                       f"modèle choisit « {q['propositions'][v['retrouvee']]} »"
                       + (f" ({explication})" if explication else "")
                       + ". Vérifiez la question, ou régénérez-la.")
    return resultat
