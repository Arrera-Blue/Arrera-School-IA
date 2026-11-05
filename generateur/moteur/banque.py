"""La banque d'exercices : un fichier JSON par exercice dans banque/instances/, son rendu HTML dans sortie/.

Statuts (architecture §11.2, règle n° 5) : « genere » à la création, puis « accepte » ou « rejete » par
l'enseignant. Seuls les exercices acceptés pourront être publiés (phase 4). Chaque décision est gardée dans
meta.decisions : c'est la donnée du taux d'acceptation enseignant (phase 7).

La relecture contrôle le fond avec les règles du jour (validation/fond.py), pas avec le verdict enregistré à la
génération : un exercice accepté avant une amélioration de N3 ou N4 peut contenir une erreur que son meta
ignore. Un exercice où le contrôle trouve une erreur ne peut pas être accepté.

L'enseignant peut aussi corriger une question à la main (`modifier_question`) : la modification est revalidée
(N2 → N4) avant d'être enregistrée, et l'ancienne version est gardée dans meta.modifications.

Le lot d'entraînement (plan IA, IA3) se range comme la banque ; ses exercices peuvent porter l'avis d'une pré-relecture
(meta.prerelecture, `noter` : entrainement/prerelecture.py), que chaque décision garde.

Supprimer un exercice ne l'efface pas : il est déplacé dans banque/supprimes/, d'où on peut le remettre à la main.

Les générations refusées par N1 → N4 ne sont pas dans la banque : elles sont dans banque/rejets/.
"""

import json
import os
import re
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

from generateur import programmes
from generateur.moteur import ancrage, config, contre_verification, registre, rendu
from generateur.moteur.validation import ErreurValidation, numero_de_question
from generateur.moteur.validation.fond import controler, tolerant
from generateur.moteur.validation.n2_schema import valider as valider_le_format

GENERE, ACCEPTE, REJETE = "genere", "accepte", "rejete"
STATUTS = (GENERE, ACCEPTE, REJETE)
DECISIONS = {"accepter": ACCEPTE, "rejeter": REJETE}
# ce qui ne va pas dans un exercice rejeté, coché par l'enseignant (plan IA, IA3) : ce que le modèle doit apprendre à éviter
MOTIFS_DE_REJET = {
    "reponse_fausse": "Une bonne réponse est fausse",
    "plusieurs_justes": "Plusieurs propositions sont justes",
    "explication_fausse": "Une explication est fausse",
    "distracteurs_faciles": "Les mauvaises réponses sont trop faciles à écarter",
    "enonce_ambigu": "Énoncé mal formulé ou ambigu",
    "hors_programme": "Hors programme, ou pas du niveau de la classe",
}
# ce que produit generation.identifiant : « qcm-fractions-6e-20261007-141737 » ; rien d'autre n'est un exercice
# (un identifiant sert à construire un chemin de fichier : « ../ » ne doit jamais y entrer)
IDENTIFIANT = re.compile(r"[a-z0-9][a-z0-9_-]{0,160}")  # « _ » : les types vrai_faux, texte_a_trous
# lecture-modification-écriture d'un exercice : l'interface sert plusieurs requêtes à la fois
_VERROU = threading.RLock()


class ExerciceInconnu(Exception):
    pass


class ExerciceFaux(Exception):
    """Accepter un exercice où le contrôle du fond trouve une erreur : refusé, il faut d'abord la corriger."""


class SuppressionRefusee(Exception):
    """Supprimer un exercice accepté : refusé, il faut d'abord le rejeter (il pourrait déjà être publié)."""


def chemin(ident: str) -> Path:
    if not IDENTIFIANT.fullmatch(ident or ""):
        raise ExerciceInconnu(f"identifiant d'exercice invalide : {ident!r}")
    return config.chemin("banque") / f"{ident}.json"


def charger(ident: str) -> dict:
    fichier = chemin(ident)
    try:
        return json.loads(fichier.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ExerciceInconnu(f"exercice « {ident} » introuvable") from None
    except (OSError, json.JSONDecodeError) as e:
        raise ExerciceInconnu(f"exercice « {ident} » illisible : {e}") from None


def rendre(instance: dict) -> str:
    """Le fichier HTML autonome de l'exercice, tel que l'élève le recevra."""
    return rendu.rendre(instance, instance.get("type", "qcm"))


def _ecrire_atomique(fichier: Path, texte: str) -> None:
    """Jamais de fichier à moitié écrit : on écrit à côté, puis on remplace d'un coup."""
    fichier.parent.mkdir(parents=True, exist_ok=True)
    temporaire = fichier.with_name(f".{fichier.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporaire.write_text(texte, encoding="utf-8")
    os.replace(temporaire, fichier)


def ecrire(instance: dict, sortie: Path | None = None) -> tuple[Path, Path]:
    """Enregistre l'exercice (JSON) et son rendu (HTML, par défaut sortie/<id>.html). Renvoie les deux chemins."""
    ident = instance["meta"]["id"]
    html = rendre(instance)  # avant d'écrire quoi que ce soit : un exercice qui ne se rend pas n'entre pas
    with _VERROU:
        fichier = chemin(ident)
        _ecrire_atomique(fichier, json.dumps(instance, ensure_ascii=False, indent=2))
        page = sortie or config.chemin("sortie") / f"{ident}.html"
        _ecrire_atomique(page, html)
    return fichier, page


def enregistrer(instance: dict, sortie: Path | None = None) -> tuple[Path, Path]:
    """Un exercice neuf. L'identifiant est horodaté à la seconde : deux exercices de même notion produits dans
    la même seconde (le générateur procédural répond en 0 s) auraient le même ; le second reçoit alors « -2 »,
    au lieu d'écraser le premier."""
    with _VERROU:
        base = ident = instance["meta"]["id"]
        suivant = 2
        while chemin(ident).exists():
            ident, suivant = f"{base}-{suivant}", suivant + 1
        instance["meta"]["id"] = ident
        return ecrire(instance, sortie)


def decider(ident: str, decision: str, motif: str | None = None, motifs: list[str] | None = None) -> dict:
    """« accepter » ou « rejeter » : le statut change, la décision est ajoutée à l'historique. `motifs` : ce qui ne va
    pas dans un exercice rejeté, parmi MOTIFS_DE_REJET (relecture du lot d'entraînement, plan IA, IA3)."""
    if decision not in DECISIONS:
        raise ValueError(f"décision inconnue : {decision!r} (accepter ou rejeter)")
    if inconnus := [m for m in motifs or [] if m not in MOTIFS_DE_REJET]:
        raise ValueError(f"motif de rejet inconnu : {inconnus[0]!r}")
    if motifs and decision != "rejeter":
        raise ValueError("un motif de rejet accompagne un rejet")
    with _VERROU:
        instance = charger(ident)
        if decision == "accepter" and (erreurs := controler(instance)["erreurs"]):
            raise ExerciceFaux("l'exercice contient une erreur, à corriger (régénérer la question) avant de "
                               "l'accepter : " + " ; ".join(erreurs))
        meta = instance.setdefault("meta", {"id": ident})
        meta["statut"] = DECISIONS[decision]
        avis = (meta.get("prerelecture") or {}).get("avis")  # l'avis que l'enseignant avait sous les yeux
        meta.setdefault("decisions", []).append({"statut": meta["statut"], "date": _maintenant(),
                                                 "motif": (motif or "").strip()[:500] or None}
                                                | ({"motifs": [m for m in MOTIFS_DE_REJET if m in motifs]}
                                                   if motifs else {})
                                                | ({"avis_prerelecture": avis} if avis else {}))
        _ecrire_atomique(chemin(ident), json.dumps(instance, ensure_ascii=False, indent=2))
    return instance


def noter(ident: str, cle: str, valeur) -> dict:
    """Range `valeur` dans meta[cle] (l'avis d'une pré-relecture, plan IA, IA3), sans rien changer d'autre : ni le statut,
    ni les questions, ni le rendu."""
    with _VERROU:
        instance = charger(ident)
        instance.setdefault("meta", {"id": ident})[cle] = valeur
        _ecrire_atomique(chemin(ident), json.dumps(instance, ensure_ascii=False, indent=2))
    return instance


def modifier_question(ident: str, numero: int, question: dict) -> dict:
    """Remplace la question `numero` (à partir de 1) par la version écrite par l'enseignant.

    La modification est revalidée comme une régénération : format (N2) sur tout l'exercice, puis fond (N3, N4) ;
    seuls les défauts NOUVEAUX bloquent (ceux d'autres questions, déjà là avant, restent affichés à la relecture).
    Lève ErreurValidation si elle est refusée : l'exercice reste alors tel qu'il était.
    L'ancienne question est gardée dans meta.modifications ; l'exercice repasse « à relire »."""
    with _VERROU:
        instance = charger(ident)
        questions = list(instance.get("questions") or [])
        if not 1 <= numero <= len(questions):
            raise ValueError(f"question {numero} inexistante : l'exercice en compte {len(questions)}")
        ancienne = questions[numero - 1]
        nouvelle = {cle: valeur for cle, valeur in question.items() if valeur is not None}
        if "difficulte" in ancienne and "difficulte" not in nouvelle:
            nouvelle["difficulte"] = ancienne["difficulte"]
        if nouvelle == ancienne:
            raise ValueError("la question n'a pas changé")
        questions[numero - 1] = nouvelle
        modifiee = instance | {"questions": questions}
        valider_le_format(modifiee, registre.charger(instance.get("type", "qcm")).schema, meta_autorise=True)
        avertissements, bilan_n4 = tolerant(instance, numero)({k: v for k, v in modifiee.items() if k != "meta"})
        meta = json.loads(json.dumps(instance.get("meta") or {"id": ident}))
        meta.setdefault("modifications", []).append({"question": numero, "date": _maintenant(), "ancienne": ancienne})
        meta["validation"] = {"n1": True, "n2": True, "n3": True, **bilan_n4}
        meta["avertissements"] = avertissements
        meta["statut"] = GENERE  # l'exercice a changé : l'enseignant doit l'accepter de nouveau
        modifiee["meta"] = meta
        ecrire(modifiee)
    return modifiee


def supprimer(ident: str) -> Path:
    """Retire l'exercice de la banque : son JSON part dans banque/supprimes/ (récupérable à la main), son rendu
    HTML est effacé. Un exercice accepté doit d'abord être rejeté. Renvoie le chemin du fichier déplacé."""
    with _VERROU:
        instance = charger(ident)
        if statut(instance) == ACCEPTE:
            raise SuppressionRefusee("un exercice accepté ne peut pas être supprimé : le rejeter d'abord")
        corbeille = config.chemin("supprimes")
        corbeille.mkdir(parents=True, exist_ok=True)
        destination = corbeille / f"{ident}.json"
        os.replace(chemin(ident), destination)
        (config.chemin("sortie") / f"{ident}.html").unlink(missing_ok=True)
    return destination


def historique(instance: dict) -> list[dict]:
    """Les régénérations et les modifications à la main, de la plus ancienne à la plus récente, chacune avec sa
    « nature ». Défaire l'historique à l'envers redonne l'exercice tel que la chaîne l'a produit (bilan_n4)."""
    meta = instance.get("meta") or {}
    evenements = [{**r, "nature": "regeneration"} for r in meta.get("regenerations") or []] + \
                 [{**m, "nature": "modification"} for m in meta.get("modifications") or []]
    return sorted(evenements, key=lambda e: e.get("date") or "")


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte.casefold()) if not unicodedata.combining(c))


def correspond(instance: dict, recherche: str) -> bool:
    """Recherche plein texte : chaque mot doit apparaître dans le titre, la notion, la consigne ou une question
    (énoncé, propositions, explication), sans tenir compte des majuscules ni des accents."""
    morceaux = [instance.get("titre"), instance.get("notion"), instance.get("consigne")]
    for q in instance.get("questions") or []:
        morceaux += [q.get("enonce"), q.get("explication"), *(q.get("propositions") or [])]
    texte = _sans_accents(" ".join(m for m in morceaux if isinstance(m, str)))
    return all(mot in texte for mot in _sans_accents(recherche).split())


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def statut(instance: dict) -> str:
    return (instance.get("meta") or {}).get("statut") or GENERE


def signalements(instance: dict, releve: dict | None = None) -> list[int]:
    """Ce qu'un contrôle signale à la relecture : les numéros des questions en cause (erreur ou avertissement de N3, de
    la contre-vérification ou de l'ancrage ; calcul de maths que N4 n'a pas su refaire), et 0 pour un avertissement sur
    l'exercice entier. Hors maths, aucun calcul n'est refait : ce n'est pas un signalement. `releve` : la relecture,
    si elle est déjà faite."""
    releve = releve or relecture(instance)
    maths = instance.get("matiere") == "maths"
    return [0] * bool(releve["avertissements"] or releve["erreurs"]) + \
        [q["numero"] for q in releve["questions"] if q["avertissements"] or q["erreurs"]
         or (maths and q["n4"] == "a_relire" and q["calcul"] == "modele")]


def resume(instance: dict, fond: dict | None = None) -> dict:
    """Une ligne de la liste de la banque. `fond` : le contrôle du fond, s'il a déjà été fait."""
    meta = instance.get("meta") or {}
    fond = fond or controler(instance)
    releve = relecture(instance, fond)
    return {
        "id": meta.get("id"), "titre": instance.get("titre"), "matiere": instance.get("matiere"),
        "niveau": instance.get("niveau"), "notion": instance.get("notion"),
        "questions": len(instance.get("questions") or []), "statut": statut(instance), "date": meta.get("date"),
        "origine": "procedural" if meta.get("origine") == "procedural" else "modele",
        "fournisseur": meta.get("fournisseur"), "modele": meta.get("modele"), "duree_s": meta.get("duree_s"),
        "a_relire": releve["a_relire"], "signalements": len(signalements(instance, releve)),
        "a_corriger": len(fond["questions"]) or (1 if fond["erreurs"] else 0),
        "avertissements": len(fond["avertissements"]),
        "attendus": list((meta.get("programme") or {}).get("attendus") or []),  # programme officiel (E2.5)
        "difficulte": (meta.get("demande") or {}).get("difficulte"),  # demandée à la génération ; None : mélange
        "prerelecture": avis_en_bref(meta),
    }


def avis_en_bref(meta: dict) -> dict | None:
    """L'avis de la pré-relecture en bref (le lot d'entraînement, plan IA, IA3) : l'avis, les questions qui ne sont pas
    justes. None : pas de pré-relecture."""
    p = meta.get("prerelecture")
    if not isinstance(p, dict) or not p.get("avis"):
        return None
    return {"avis": p["avis"], "questions": [q.get("numero") for q in p.get("questions") or [] if q.get("juste") is False]}


def lister(matiere: str | None = None, niveau: str | None = None, statut_voulu: str | None = None,
           recherche: str | None = None, attendu: str | None = None) -> list[dict]:
    """Les exercices de la banque, du plus récent au plus ancien, éventuellement filtrés (`recherche` : voir
    `correspond` ; `attendu` : un attendu ou un thème du programme, qui trouve aussi les exercices rattachés au
    thème ou à l'un de ses attendus)."""
    dossier = config.chemin("banque")
    lignes = []
    for fichier in dossier.glob("*.json") if dossier.is_dir() else []:
        try:
            instance = json.loads(fichier.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if recherche and recherche.strip() and not correspond(instance, recherche):
            continue
        try:
            ligne = resume(instance)
        except (KeyError, TypeError, IndexError):  # un fichier au format inattendu : on le saute
            continue
        ligne["id"] = ligne["id"] or fichier.stem
        if (matiere and ligne["matiere"] != matiere) or (niveau and ligne["niveau"] != niveau) or \
                (statut_voulu and ligne["statut"] != statut_voulu):
            continue
        if attendu and not any(programmes.couvre(attendu, a) for a in ligne["attendus"]):
            continue
        lignes.append(ligne)
    return sorted(lignes, key=lambda l: l["date"] or "", reverse=True)


def relecture(instance: dict, fond: dict | None = None) -> dict:
    """Ce que l'enseignant doit savoir pour relire, question par question : N4, qui a écrit l'énoncé et fait
    le calcul (programme, modèle ou enseignant), les erreurs et avertissements de N3/N4 (règles du jour), les
    questions déjà régénérées ou modifiées à la main (la plus récente des deux l'emporte).

    « a_relire » ne compte que les calculs du modèle que N4 n'a pas su refaire : un calcul du programme est
    juste par construction, même quand N4 ne reconnaît pas l'énoncé réécrit par le modèle (essai du 16/10 :
    3 questions de pourcentages annoncées « à relire » à tort). Une question modifiée à la main n'est pas non
    plus « à relire » : l'enseignant l'a écrite.

    La contre-vérification (plan IA, IA1.4), faite une fois à la génération, s'ajoute aux avertissements : une question
    dont le modèle n'a pas retrouvé la réponse cochée est « à relire », tant qu'elle n'a pas changé. Un exercice écrit à
    partir des cours de l'enseignant (IA2) : chaque question montre sa source (cours, page, extrait), et une source qui
    ne justifie pas la réponse cochée s'ajoute aux avertissements."""
    meta = instance.get("meta") or {}
    fond = fond or controler(instance)
    procedural = meta.get("origine") == "procedural"
    statuts = fond["n4_questions"]
    origines = meta.get("questions") if procedural else None
    derniers = {e.get("question"): e["nature"] for e in historique(instance)}  # le plus récent l'emporte

    def ranger(messages: list[str]) -> tuple[dict[int, list[str]], list[str]]:
        par_question: dict[int, list[str]] = {}
        generaux = []
        for message in messages:
            n = numero_de_question(message)
            (par_question.setdefault(n, []) if n else generaux).append(message)
        return par_question, generaux

    erreurs, erreurs_generales = ranger(fond["erreurs"])
    par_question, generaux = ranger(fond["avertissements"])
    desaccords = contre_verification.alertes(instance)
    for n, message in desaccords.items():
        par_question.setdefault(n, []).append(message)
    non_ancrees = ancrage.alertes(instance)
    for n, message in non_ancrees.items():
        par_question.setdefault(n, []).append(message)
    sources = ancrage.sources(instance)
    questions = []
    for n, _ in enumerate(instance.get("questions") or [], start=1):
        origine = origines[n - 1] if origines and n <= len(origines) else {}
        modifiee = derniers.get(n) == "modification"
        if modifiee:
            calcul = enonce = "enseignant"
        else:
            calcul = "programme" if procedural else "modele"
            enonce = ("modele" if origine.get("habillage") == "modele" else "programme") if procedural else "modele"
        questions.append({
            "numero": n,
            "n4": statuts[n - 1] if n <= len(statuts) else None,
            "calcul": calcul,
            "enonce": enonce,
            "erreurs": erreurs.get(n, []),
            "avertissements": par_question.get(n, []),
            "regeneree": derniers.get(n) == "regeneration",
            "modifiee": modifiee,
            "source": sources.get(n),
        })
    return {"questions": questions, "avertissements": generaux, "erreurs": erreurs_generales,
            "procedural": procedural, "valide": not fond["erreurs"],
            "a_corriger": sorted(erreurs), "niveau": fond["niveau"],
            "a_relire": sum(q["n4"] == "a_relire" and q["calcul"] == "modele" for q in questions),
            "contre_verification": sorted(desaccords), "ancrage": sorted(non_ancrees)}
