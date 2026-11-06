"""La relecture à l'aveugle (plan IA, IA4.3) : le modèle de base et le modèle entraîné écrivent chacun un exercice pour
les mêmes demandes ; les exercices sont mélangés, sans rien qui dise lequel les a écrits, et l'enseignant les relit
comme le lot (accepter, rejeter en cochant pourquoi, modifier une question) ; le bilan dévoile ensuite les modèles.

    python -m generateur.entrainement aveugle generer --adaptateur modeles/adaptateurs/<nom>.gguf [--nombre 15]
    python -m generateur.interface.api --aveugle          # http://127.0.0.1:8003 : relire, sans savoir lequel
    python -m generateur.entrainement aveugle bilan

Les demandes : des attendus des programmes (maths et français, 6e et 5e) que l'entraînement n'a jamais vus (ni en
entraînement, ni en validation, qui a servi à choisir le point d'étape), ceux du jeu de test d'abord ; aucun que le
générateur procédural couvre (le modèle y écrit tout, comme en vrai) ; les matières et les classes en alternance ;
5 questions, la difficulté mélangée. Chaque demande passe par le chemin habituel (`generation.generer` : N1 → N4, les
reprises, la contre-vérification), une fois avec chaque modèle. Rien n'entre dans la vraie banque ni dans le lot.

    donnees/entrainement/aveugle/<AAAAMMJJ-HHMM>/
        plan.json            les demandes, l'adaptateur (nom, empreinte), le jeu de l'entraînement, la graine
        avancement.jsonl     une ligne par génération (modèle, demande) : de quoi reprendre après une coupure
        originaux/           les exercices tels que la génération les a produits, avec toute leur meta
        rejets/, brut/       les générations refusées par N1 → N4 (elles comptent dans le bilan)
        banque/instances/    les exercices mélangés, sans rien qui dise quel modèle : ce que relit l'enseignant
        sortie/              leurs pages HTML
        cle.json             quel modèle a écrit quel exercice : lu par le bilan seulement
        bilan.md, bilan.json
"""

import copy
import hashlib
import json
import random
import statistics
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from generateur import entrainement, procedural, programmes
from generateur.entrainement import nuit, relecture
from generateur.moteur import banque, config, generation, securite
from generateur.moteur.validation import ErreurValidation

MODELES = ("base", "entraine")
LIBELLES = {"base": "Modèle de base", "entraine": "Modèle entraîné"}
NOMBRE = 15
QUESTIONS = 5
GRAINE = 2026
FAITS = ("genere", "rejete", "refuse")  # une « erreur » (le modèle en panne…) sera refaite à la reprise
# ce qui, dans la meta, dirait quel modèle a écrit l'exercice, ou le laisserait deviner (durée, tentatives)
CACHES = ("adaptateur", "machine", "duree_s", "tentatives", "tentatives_par_question", "reprises", "appels",
          "contre_verification_s", "entrainement")
# les motifs de rejet qui disent qu'une réponse cochée est fausse : la 1re condition de la décision (IA4.4)
REPONSES_FAUSSES = ("reponse_fausse", "plusieurs_justes")


def racine() -> Path:
    return entrainement.dossier() / "aveugle"


def dernier(dans: Path | None = None) -> Path:
    """Le dossier de la dernière comparaison ; ValueError s'il n'y en a pas."""
    dans = dans or racine()
    dossiers = sorted(d for d in dans.iterdir() if (d / "plan.json").is_file()) if dans.is_dir() else []
    if not dossiers:
        raise ValueError(f"aucune comparaison dans {dans} : python -m generateur.entrainement aveugle generer "
                         "--adaptateur <fichier.gguf>")
    return dossiers[-1]


def chemins(dossier: Path) -> dict[str, Path]:
    """Les dossiers de la relecture à l'aveugle, sous les noms de ceux de la banque (l'interface, --aveugle)."""
    return {"banque": dossier / "banque" / "instances", "rejets": dossier / "banque" / "rejets",
            "supprimes": dossier / "banque" / "supprimes", "sortie": dossier / "sortie"}


def empreinte(fichier: Path) -> str:
    return hashlib.sha256(fichier.read_bytes()).hexdigest()


def _relatif(chemin: Path) -> str:
    chemin = chemin.resolve()
    return str(chemin.relative_to(config.RACINE)) if chemin.is_relative_to(config.RACINE) else str(chemin)


def _absolu(chemin: str) -> Path:
    return Path(chemin) if Path(chemin).is_absolute() else config.RACINE / chemin


# --- les demandes -------------------------------------------------------------------------------------------

def jeu_de_l_adaptateur(adaptateur: Path) -> Path | None:
    """Le jeu de données sur lequel l'adaptateur a été entraîné, d'après sa description (<nom>/entrainement.json ; pour
    un point d'étape « <nom>-0000053.gguf », celle de <nom>). None si elle est introuvable."""
    for nom in (adaptateur.stem, adaptateur.stem.rsplit("-", 1)[0]):
        description = adaptateur.parent / nom / "entrainement.json"
        if description.is_file():
            jeu = json.loads(description.read_text(encoding="utf-8")).get("jeu")
            return _absolu(jeu) if jeu else None
    return None


def notions_du_jeu(manifeste: dict) -> tuple[set[str], set[str]]:
    """Les notions vues par l'entraînement (entraînement et validation), et celles du jeu de test."""
    jeux = manifeste["jeux"]
    vues = {x["notion"] for nom in ("train", "valid") for x in jeux.get(nom) or []}
    return vues, {x["notion"] for x in jeux.get("test") or []} - vues


def _demande(a) -> dict:
    return {"type": "qcm", "matiere": a.matiere, "niveau": a.niveau, "notion": programmes.notion_de(a.id),
            "attendu": a.id, "nb_questions": QUESTIONS}


def choisir(vues: set[str], test: set[str], nombre: int = NOMBRE, graine: int = GRAINE) -> list[dict]:
    """Les demandes de la comparaison : des attendus jamais vus par l'entraînement, que le modèle écrit seul (aucun
    générateur procédural) ; ceux du jeu de test d'abord, puis d'autres tirés au sort ; les matières et les classes
    en alternance."""
    rng = random.Random(graine)
    candidats = [a for a in sorted(programmes.lister(qcm=True), key=lambda a: a.id)
                 if a.matiere in nuit.MATIERES and a.niveau in nuit.NIVEAUX and a.id not in vues
                 and procedural.aiguiller(_demande(a)) is None]
    autres = [a for a in candidats if a.id not in test]
    rng.shuffle(autres)
    groupes: dict[tuple, list] = defaultdict(list)
    for a in [a for a in candidats if a.id in test] + autres:
        groupes[(a.matiere, a.niveau)].append(a)
    choisis = []
    while len(choisis) < nombre and any(groupes.values()):
        for cle in sorted(groupes):
            if groupes[cle] and len(choisis) < nombre:
                choisis.append(groupes[cle].pop(0))
    return [{"n": n, "test": a.id in test, "demande": _demande(a)} for n, a in enumerate(choisis, start=1)]


def preparer(adaptateur: Path, jeu: Path, dossier: Path, nombre: int = NOMBRE, graine: int = GRAINE) -> dict:
    """Une nouvelle comparaison : son dossier et son plan (les demandes, l'adaptateur et son empreinte, le jeu)."""
    if not adaptateur.is_file():
        raise ValueError(f"adaptateur introuvable : {adaptateur}")
    if not (jeu / "manifeste.json").is_file():
        raise ValueError(f"jeu de données introuvable : {jeu} (préciser --jeu)")
    vues, test = notions_du_jeu(json.loads((jeu / "manifeste.json").read_text(encoding="utf-8")))
    demandes = choisir(vues, test, nombre, graine)
    if not demandes:
        raise ValueError("aucun attendu que l'entraînement n'ait pas vu")
    plan = {"date": datetime.now().isoformat(timespec="seconds"), "graine": graine, "jeu": _relatif(jeu),
            "adaptateur": {"chemin": _relatif(adaptateur), "nom": adaptateur.name, "sha256": empreinte(adaptateur)},
            "demandes": demandes}
    dossier.mkdir(parents=True)
    (dossier / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan


def lire_plan(dossier: Path) -> dict:
    return json.loads((dossier / "plan.json").read_text(encoding="utf-8"))


# --- générer --------------------------------------------------------------------------------------------------

def journal(dossier: Path) -> Path:
    return dossier / "avancement.jsonl"


def dernieres_entrees(dossier: Path) -> dict[tuple[str, int], dict]:
    """La dernière ligne du journal de chaque génération (modèle, demande)."""
    return {(e["modele"], e["n"]): e for e in nuit.lire_journal(journal(dossier)) if "modele" in e and "n" in e}


def reste_a_faire(dossier: Path, plan: dict | None = None) -> list[tuple[str, dict]]:
    plan = plan or lire_plan(dossier)
    entrees = dernieres_entrees(dossier)
    return [(m, d) for m in MODELES for d in plan["demandes"]
            if (entrees.get((m, d["n"])) or {}).get("resultat") not in FAITS]


def melanges(dossier: Path) -> bool:
    return (dossier / "cle.json").is_file()


def faire(dossier: Path, modele: str, d: dict, noms) -> dict:
    """Une génération : l'exercice gardé dans originaux/ (ou le rejet), et la ligne du journal qui le dit."""
    demande = d["demande"]
    entree = {"modele": modele, "n": d["n"], "attendu": demande["attendu"], "date": datetime.now().isoformat(timespec="seconds")}
    debut = time.monotonic()
    try:
        instance = generation.generer(dict(demande), mode="ia", noms_proteges=noms)
        fichier = dossier / "originaux" / f"{modele}-{d['n']:02d}.json"
        fichier.parent.mkdir(exist_ok=True)
        fichier.write_text(json.dumps(instance, ensure_ascii=False, indent=2), encoding="utf-8")
        meta = instance["meta"]
        entree |= {"resultat": "genere", "fichier": fichier.name, "tentatives": meta.get("tentatives", 1),
                   "duree_s": meta.get("duree_s"), "signalements": len(banque.signalements(instance))}
    except ErreurValidation as e:
        entree |= {"resultat": "rejete", "niveau": e.niveau, "erreurs": e.erreurs[:3]}
    except securite.DemandeRefusee as e:
        entree |= {"resultat": "refuse", "categorie": e.categorie}
    except Exception as e:  # le modèle en panne, un défaut du code : la suite continue, la génération sera refaite
        entree |= {"resultat": "erreur", "erreur": f"{type(e).__name__} : {e}"[:300]}
    entree["duree_totale_s"] = round(time.monotonic() - debut, 1)
    return entree


def _liberer() -> None:
    """Un modèle à la fois en mémoire (~5 Go chacun) : l'autre est libéré avant de changer d'adaptateur."""
    from generateur.moteur.fournisseurs import llamacpp
    llamacpp.decharger()


def _ligne(rang: int, total: int, entree: dict) -> str:
    resultat = {"genere": f"✓ {entree.get('tentatives', 1)} tentative(s), {entree.get('signalements', 0)} signalement(s)",
                "rejete": f"✗ rejeté ({entree.get('niveau')})", "refuse": f"✗ demande refusée ({entree.get('categorie')})",
                "erreur": f"⚠ erreur, à refaire : {entree.get('erreur')}"}[entree["resultat"]]
    return f"[{rang}/{total}] {entree['attendu']} — {resultat}, {entree['duree_totale_s']} s"


def generer(dossier: Path, afficher: Callable[[str], None] = print) -> Counter:
    """Les générations du plan qui ne sont pas encore faites : toutes celles du modèle de base, puis toutes celles du
    modèle entraîné (un seul chargement de chacun). S'arrête après 3 erreurs de suite. Quand tout est fait, mélange les
    exercices pour la relecture à l'aveugle."""
    plan = lire_plan(dossier)
    chemin = _absolu(plan["adaptateur"]["chemin"])
    if not chemin.is_file() or empreinte(chemin) != plan["adaptateur"]["sha256"]:
        raise ValueError(f"l'adaptateur {chemin} a changé ou disparu depuis le début de la comparaison : en commencer "
                         "une nouvelle (--nouvelle)")
    config.rediriger({"rejets": dossier / "rejets", "sortie": dossier / "brut"})  # ni la vraie banque, ni le lot
    a_faire = reste_a_faire(dossier, plan)
    noms = nuit.noms_proteges()
    resultats: Counter = Counter()
    rang = de_suite = 0
    for modele in MODELES:
        siennes = [d for m, d in a_faire if m == modele]
        if not siennes:
            continue
        generation.utiliser_adaptateur(None if modele == "base" else chemin)
        _liberer()
        afficher(f"{LIBELLES[modele]}" + (f" ({plan['adaptateur']['nom']})" if modele == "entraine" else "")
                 + f" : {len(siennes)} demande(s).")
        for d in siennes:
            rang += 1
            entree = faire(dossier, modele, d, noms)
            with journal(dossier).open("a", encoding="utf-8") as f:
                f.write(json.dumps(entree, ensure_ascii=False) + "\n")
            resultats[entree["resultat"]] += 1
            afficher(_ligne(rang, len(a_faire), entree))
            de_suite = de_suite + 1 if entree["resultat"] == "erreur" else 0
            if de_suite >= nuit.ERREURS_DE_SUITE_MAX:
                afficher(f"Arrêt : {nuit.ERREURS_DE_SUITE_MAX} erreurs de suite (dernière : {entree['erreur']}). "
                         "Relancer la même commande reprend là où elle s'est arrêtée.")
                return resultats
    if not reste_a_faire(dossier, plan) and not melanges(dossier):
        cle = melanger(dossier)
        afficher(f"{len(cle)} exercices mélangés pour la relecture à l'aveugle : python -m generateur.interface.api "
                 "--aveugle")
    return resultats


# --- mélanger -------------------------------------------------------------------------------------------------

def anonymiser(instance: dict, ident: str, date: datetime) -> dict:
    """L'exercice tel que le voit l'enseignant à l'aveugle : rien dans la meta ne dit quel modèle l'a écrit (ni
    l'adaptateur, ni la durée, ni les tentatives) ; un identifiant et une date qui suivent l'ordre tiré au sort."""
    x = copy.deepcopy(instance)
    meta = {k: v for k, v in (x.get("meta") or {}).items() if k not in CACHES}
    x["meta"] = meta | {"id": ident, "date": date.isoformat(timespec="seconds"), "statut": banque.GENERE, "aveugle": True}
    return x


def melanger(dossier: Path) -> dict[str, dict]:
    """Range les exercices produits, mélangés, dans la banque de la relecture à l'aveugle ; écrit la clé."""
    if melanges(dossier):
        raise ValueError(f"déjà mélangés : {dossier / 'cle.json'}")
    plan = lire_plan(dossier)
    produits = [(m, n, json.loads((dossier / "originaux" / e["fichier"]).read_text(encoding="utf-8")))
                for (m, n), e in sorted(dernieres_entrees(dossier).items()) if e.get("resultat") == "genere"]
    random.Random(plan["graine"]).shuffle(produits)
    debut = datetime.fromisoformat(plan["date"]).replace(second=0)
    config.rediriger(chemins(dossier))
    cle = {}
    for rang, (modele, n, instance) in enumerate(produits, start=1):
        ident = f"aveugle-{rang:02d}"
        banque.enregistrer(anonymiser(instance, ident, debut + timedelta(minutes=rang)))
        cle[ident] = {"modele": modele, "n": n, "original": f"originaux/{modele}-{n:02d}.json"}
    (dossier / "cle.json").write_text(json.dumps(cle, ensure_ascii=False, indent=2), encoding="utf-8")
    return cle


# --- le bilan -------------------------------------------------------------------------------------------------

def _decision(instance: dict | None) -> dict:
    return (((instance or {}).get("meta") or {}).get("decisions") or [{}])[-1]


def _mediane(valeurs: list[float]) -> float | None:
    return round(statistics.median(valeurs), 1) if valeurs else None


def compter(dossier: Path) -> dict:
    """Les chiffres de la comparaison, modèle par modèle, et demande par demande (la clé est lue : les modèles sont
    dévoilés)."""
    plan = lire_plan(dossier)
    cle = json.loads((dossier / "cle.json").read_text(encoding="utf-8"))
    lot = {i["meta"]["id"]: i for i in relecture.instances(chemins(dossier)["banque"])}
    entrees = dernieres_entrees(dossier)
    par_cle = {(c["modele"], c["n"]): ident for ident, c in cle.items()}
    modeles = {}
    for m in MODELES:
        gens = [entrees.get((m, d["n"])) or {} for d in plan["demandes"]]
        produits = [e for e in gens if e.get("resultat") == "genere"]
        relus = [lot.get(ident) for ident, c in cle.items() if c["modele"] == m]
        statuts = Counter(banque.statut(i) if i else "absent" for i in relus)
        motifs = Counter(motif for i in relus if i and banque.statut(i) == banque.REJETE
                         for motif in _decision(i).get("motifs") or [])
        modeles[m] = {
            "demandes": len(plan["demandes"]), "produits": len(produits),
            "du_premier_coup": sum(e.get("tentatives", 1) == 1 for e in produits),
            "rejetes_par_les_controles": sum(e.get("resultat") == "rejete" for e in gens),
            "refuses": sum(e.get("resultat") == "refuse" for e in gens),
            "pas_faits": sum(e.get("resultat") not in FAITS for e in gens),
            "duree_mediane_s": _mediane([e["duree_s"] for e in produits if e.get("duree_s") is not None]),
            "duree_totale_mediane_s": _mediane([e["duree_totale_s"] for e in produits if e.get("duree_totale_s")]),
            "signalements": sum(e.get("signalements", 0) for e in produits),
            "acceptes": statuts[banque.ACCEPTE], "rejetes": statuts[banque.REJETE], "pas_decides": statuts[banque.GENERE],
            "motifs": dict(motifs), "rejets_sans_motif": sum(1 for i in relus if i and banque.statut(i) == banque.REJETE
                                                             and not _decision(i).get("motifs")),
            "reponses_fausses": sum(motifs[x] for x in REPONSES_FAUSSES),
            "questions_modifiees": sum(len((i or {}).get("meta", {}).get("modifications") or []) for i in relus),
        }
    demandes = []
    for d in plan["demandes"]:
        ligne = {"n": d["n"], "attendu": d["demande"]["attendu"], "test": d.get("test", False)}
        for m in MODELES:
            e = entrees.get((m, d["n"])) or {}
            ident = par_cle.get((m, d["n"]))
            instance = lot.get(ident) if ident else None
            ligne[m] = {"id": ident, "resultat": e.get("resultat"), "niveau": e.get("niveau"),
                        "statut": banque.statut(instance) if instance else None,
                        "motifs": _decision(instance).get("motifs") or [] if instance else [],
                        "modifiees": len((instance or {}).get("meta", {}).get("modifications") or [])}
        demandes.append(ligne)
    b, e = modeles["base"], modeles["entraine"]
    regle = {"pas_plus_de_reponses_fausses": e["reponses_fausses"] <= b["reponses_fausses"],
             "mieux_accepte": e["acceptes"] > b["acceptes"]}
    return {"plan": {k: plan[k] for k in ("date", "graine", "jeu", "adaptateur")}, "nombre": len(plan["demandes"]),
            "modeles": modeles, "demandes": demandes, "regle": regle | {"remplie": all(regle.values())}}


def _case(x: dict) -> str:
    if x["resultat"] == "rejete":
        return f"rejeté par {x['niveau']}"
    if x["resultat"] != "genere":
        return x["resultat"] or "pas fait"
    if x["statut"] == banque.ACCEPTE:
        return "✓ accepté" + (f" ({x['modifiees']} question(s) modifiée(s))" if x["modifiees"] else "")
    if x["statut"] == banque.REJETE:
        motifs = ", ".join(banque.MOTIFS_DE_REJET.get(m, m).lower() for m in x["motifs"])
        return "✗ rejeté" + (f" : {motifs}" if motifs else "")
    return "pas décidé"


def ecrire_bilan(dossier: Path, c: dict) -> str:
    b, e = c["modeles"]["base"], c["modeles"]["entraine"]
    n = c["nombre"]
    adaptateur = c["plan"]["adaptateur"]

    def ligne(libelle: str, cle: str, fmt=str) -> str:
        return f"| {libelle} | {fmt(b[cle])} | {fmt(e[cle])} |"

    secondes = lambda v: "—" if v is None else f"{v:g} s".replace(".", ",")
    sur_n = lambda v: f"{v} sur {n}"
    motifs = sorted(set(b["motifs"]) | set(e["motifs"]), key=lambda m: list(banque.MOTIFS_DE_REJET).index(m)
                    if m in banque.MOTIFS_DE_REJET else 99)
    r = c["regle"]
    oui = lambda v: "oui" if v else "non"
    texte = [
        "# Relecture à l'aveugle : le modèle de base contre le modèle entraîné", "",
        f"Comparaison du {c['plan']['date'][:10]} ({dossier.name}) : **{n} demandes**, chacune générée par les deux "
        f"modèles. Modèle entraîné : l'adaptateur `{adaptateur['nom']}` (empreinte {adaptateur['sha256'][:12]}), "
        f"entraîné sur le jeu `{c['plan']['jeu']}`. Des attendus que l'entraînement n'a jamais vus ; aucun que le "
        "générateur procédural couvre.", "",
        "| | Modèle de base | Modèle entraîné |", "|---|---|---|",
        ligne("Exercices produits (N1 → N4 passés)", "produits", sur_n),
        ligne("Du premier coup (aucune question reprise)", "du_premier_coup"),
        ligne("Rejetés par N1 → N4 après les reprises", "rejetes_par_les_controles"),
        ligne("Durée de génération (médiane)", "duree_mediane_s", secondes),
        ligne("Avec la contre-vérification (médiane)", "duree_totale_mediane_s", secondes),
        ligne("Signalements des contrôles à la relecture", "signalements"),
        f"| **Acceptés à la relecture** | **{b['acceptes']} sur {n}** | **{e['acceptes']} sur {n}** |",
        ligne("Rejetés à la relecture", "rejetes"),
        *[f"| … {banque.MOTIFS_DE_REJET.get(m, m).lower()} | {b['motifs'].get(m, 0)} | {e['motifs'].get(m, 0)} |"
          for m in motifs],
        ligne("Questions modifiées à la main", "questions_modifiees"),
        ligne("Pas encore décidés", "pas_decides"), "",
        "## La règle de décision (IA4.4)", "",
        "Le modèle entraîné n'est adopté que s'il n'a **pas plus de réponses fausses** (exercices rejetés pour une "
        f"réponse fausse ou plusieurs réponses justes : {e['reponses_fausses']} contre {b['reponses_fausses']} : "
        f"**{oui(r['pas_plus_de_reponses_fausses'])}**) **et** s'il est **mieux accepté** ({e['acceptes']} contre "
        f"{b['acceptes']} sur {n} : **{oui(r['mieux_accepte'])}**). "
        + ("Les deux conditions sont remplies." if r["remplie"] else "Les deux conditions ne sont pas remplies : on "
           "garde le modèle de base.")
        + " Restent à regarder le banc d'attaque (l'entraînement ne doit pas affaiblir la sécurité) et le banc des "
          "connaissances, lancés avec `--adaptateur`.", "",
        "## Demande par demande", "",
        "| | Attendu | Modèle de base | Modèle entraîné |", "|---|---|---|---|",
        *[f"| {d['n']} | {d['attendu']}{' (test)' if d['test'] else ''} | {_case(d['base'])} | {_case(d['entraine'])} |"
          for d in c["demandes"]], "",
        "## Les limites", "",
        f"- {n} demandes : un écart d'un ou deux exercices tient au hasard autant qu'au modèle.",
        "- Une seule personne relit, et elle a construit le projet ; elle ne sait pas quel modèle a écrit l'exercice, "
        "mais les deux versions d'une même demande se reconnaissent.",
        "- Le modèle entraîné a appris sur un petit jeu ; le modèle de base reste le même Gemma 4 E4B, 4 bits.", ""]
    md = "\n".join(texte)
    (dossier / "bilan.md").write_text(md, encoding="utf-8")
    (dossier / "bilan.json").write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return md


def bilan(dossier: Path, meme_si_pas_fini: bool = False) -> str:
    """Le bilan de la comparaison (bilan.md, bilan.json). Tant que la relecture n'est pas finie, il est refusé : il
    dévoilerait les modèles (sauf `meme_si_pas_fini`)."""
    if not melanges(dossier):
        raise ValueError("les exercices ne sont pas encore mélangés : la génération n'est pas finie (relancer "
                         "python -m generateur.entrainement aveugle generer pour la reprendre)")
    c = compter(dossier)
    pas_decides = sum(m["pas_decides"] for m in c["modeles"].values())
    if pas_decides and not meme_si_pas_fini:
        raise ValueError(f"{pas_decides} exercice(s) pas encore décidé(s) : le bilan dévoilerait les modèles. Finir la "
                         "relecture (python -m generateur.interface.api --aveugle), ou --meme-si-pas-fini")
    return ecrire_bilan(dossier, c)
