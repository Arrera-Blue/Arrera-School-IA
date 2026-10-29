"""La génération de nuit (plan IA, IA3.2) : des exercices sur les attendus des programmes, rangés dans le lot
d'entraînement, que l'enseignant relira (accepter, rejeter, corriger) avant qu'ils servent à entraîner le modèle.

Chaque demande suit le chemin habituel (`generation.generer`) : le générateur procédural pour les attendus qu'il
couvre, le modèle sinon, puis N1 → N4, la contre-vérification, les noms des élèves interdits. Rien n'est publié.

Le plan est fixé par sa graine : chaque passe demande un exercice pour chacun des attendus qui se prêtent à un QCM
(maths et français, 6e et 5e), dans un ordre tiré au sort. Une nuit interrompue (Ctrl-C, heure de fin, panne) reprend
le lendemain là où elle s'est arrêtée : avancement.jsonl garde le résultat de chaque demande.
"""

import json
import random
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from generateur import entrainement, programmes
from generateur.donnees import classes
from generateur.donnees.base import Base
from generateur.moteur import banque, config, generation, securite
from generateur.moteur.validation import ErreurValidation

MATIERES = ("maths", "francais")
NIVEAUX = ("6e", "5e")
QUESTIONS = (4, 5, 6)
DIFFICULTES = (None, "facile", "moyen", "difficile")  # None : le mélange, comme dans le formulaire
PASSES = 3
GRAINE = 2026
FAITS = ("genere", "rejete", "refuse")  # une « erreur » (le modèle en panne…) sera refaite à la nuit suivante
ERREURS_DE_SUITE_MAX = 3


@dataclass(frozen=True)
class Commande:
    passe: int
    demande: dict

    @property
    def cle(self) -> str:
        return f"{self.passe}:{self.demande['attendu']}"


def plan(passes: int = PASSES, graine: int = GRAINE) -> list[Commande]:
    """Les demandes de la génération de nuit, dans l'ordre. L'ordre est tiré au sort à chaque passe : une nuit
    interrompue couvre quand même les deux matières et les deux classes. Le nombre de questions et la difficulté
    varient d'une demande à l'autre."""
    rng = random.Random(graine)
    attendus = sorted((a for a in programmes.lister(qcm=True) if a.matiere in MATIERES and a.niveau in NIVEAUX),
                      key=lambda a: a.id)
    commandes = []
    for passe in range(1, passes + 1):
        ordre = list(attendus)
        rng.shuffle(ordre)
        for a in ordre:
            demande = {"type": "qcm", "matiere": a.matiere, "niveau": a.niveau, "notion": programmes.notion_de(a.id),
                       "attendu": a.id, "nb_questions": rng.choice(QUESTIONS)}
            if difficulte := rng.choice(DIFFICULTES):
                demande["difficulte"] = difficulte
            commandes.append(Commande(passe, demande))
    return commandes


def journal() -> Path:
    return entrainement.dossier() / "avancement.jsonl"


def lire_journal(chemin: Path | None = None) -> list[dict]:
    chemin = chemin or journal()
    entrees = []
    for ligne in chemin.read_text(encoding="utf-8").splitlines() if chemin.is_file() else []:
        try:
            entrees.append(json.loads(ligne))
        except json.JSONDecodeError:  # une ligne coupée par une panne : on l'ignore, la demande sera refaite
            continue
    return entrees


def heure_de_fin(heure: str, maintenant: datetime | None = None) -> datetime:
    """« 07:30 » → le prochain 7 h 30 (demain matin si l'heure est passée)."""
    maintenant = maintenant or datetime.now()
    h, _, m = heure.partition(":")
    fin = maintenant.replace(hour=int(h), minute=int(m or 0), second=0, microsecond=0)
    return fin if fin > maintenant else fin + timedelta(days=1)


def noms_proteges() -> list[tuple[str, str]]:
    """Les noms de tous les élèves de la base : aucun ne doit entrer dans un exercice d'entraînement."""
    chemin = config.chemin("base")
    return classes.noms_de_tous_les_eleves(Base(chemin)) if chemin.is_file() else []


def faire(commande: Commande, lot: str, fournisseur: str | None, noms) -> dict:
    """Une demande : l'exercice rangé dans le lot (ou le rejet), et la ligne du journal qui le dit."""
    demande = commande.demande
    entree = {"cle": commande.cle, "passe": commande.passe, "attendu": demande["attendu"], "lot": lot,
              "date": datetime.now().isoformat(timespec="seconds"), "demande": demande}
    debut = time.monotonic()
    try:
        instance = generation.generer(dict(demande), nom_fournisseur=fournisseur, noms_proteges=noms)
        instance["meta"]["entrainement"] = {"lot": lot, "passe": commande.passe}
        banque.enregistrer(instance)
        entree |= {"resultat": "genere", "id": instance["meta"]["id"],
                   "origine": "procedural" if instance["meta"].get("origine") == "procedural" else "modele",
                   "tentatives": instance["meta"].get("tentatives", 1), "signalements": len(banque.signalements(instance))}
    except ErreurValidation as e:
        rejet = getattr(e, "rejet", None)
        entree |= {"resultat": "rejete", "niveau": e.niveau, "erreurs": e.erreurs[:3],
                   "rejet": rejet.name if isinstance(rejet, Path) else None}
    except securite.DemandeRefusee as e:
        entree |= {"resultat": "refuse", "categorie": e.categorie}
    except Exception as e:  # le modèle en panne, un défaut du code : la nuit continue, la demande sera refaite
        entree |= {"resultat": "erreur", "erreur": f"{type(e).__name__} : {e}"[:300]}
    entree["duree_s"] = round(time.monotonic() - debut, 1)
    return entree


def _ligne(rang: int, total: int, entree: dict) -> str:
    d = entree["demande"]
    quoi = f"{d['matiere']} {d['niveau']}, {d['attendu'].split('.', 2)[2]}, {d['nb_questions']} q, " \
           f"{d.get('difficulte') or 'mélange'}"
    resultat = {"genere": f"✓ gardé ({entree.get('origine')}, {entree.get('signalements', 0)} signalement(s))",
                "rejete": f"✗ rejeté ({entree.get('niveau')})", "refuse": f"✗ demande refusée ({entree.get('categorie')})",
                "erreur": f"⚠ erreur, à refaire : {entree.get('erreur')}"}[entree["resultat"]]
    return f"[{rang}/{total}] {quoi} — {resultat}, {entree['duree_s']} s"


def nuit(commandes: list[Commande] | None = None, fin: datetime | None = None, nombre: int | None = None,
         fournisseur: str | None = None, afficher: Callable[[str], None] = print) -> Counter:
    """Fait les demandes du plan qui ne sont pas encore faites, jusqu'à l'heure de `fin` ou `nombre` demandes. S'arrête
    après 3 erreurs de suite (le modèle ne se charge pas, par exemple). Renvoie le compte des résultats."""
    entrainement.utiliser()
    commandes = plan() if commandes is None else commandes
    faits = {e["cle"] for e in lire_journal() if e.get("resultat") in FAITS}
    a_faire = [c for c in commandes if c.cle not in faits]
    noms = noms_proteges()
    lot = f"nuit-{datetime.now():%Y%m%d}"
    afficher(f"Génération de nuit ({lot}) : {len(a_faire)} demande(s) à faire sur {len(commandes)}"
             + (f", jusqu'à {fin:%H:%M}" if fin else "") + (f", {nombre} au plus" if nombre else "")
             + f". Lot : {entrainement.dossier()}")
    resultats: Counter = Counter()
    de_suite = 0
    journal().parent.mkdir(parents=True, exist_ok=True)
    for rang, commande in enumerate(a_faire, start=1):
        if nombre is not None and sum(resultats.values()) >= nombre:
            break
        if fin is not None and datetime.now() >= fin:
            afficher(f"Heure de fin atteinte ({fin:%H:%M}).")
            break
        entree = faire(commande, lot, fournisseur, noms)
        with journal().open("a", encoding="utf-8") as f:
            f.write(json.dumps(entree, ensure_ascii=False) + "\n")
        resultats[entree["resultat"]] += 1
        afficher(_ligne(rang, len(a_faire), entree))
        de_suite = de_suite + 1 if entree["resultat"] == "erreur" else 0
        if de_suite >= ERREURS_DE_SUITE_MAX:
            afficher(f"Arrêt : {ERREURS_DE_SUITE_MAX} erreurs de suite (dernière : {entree['erreur']}).")
            break
    afficher("Fin : " + (", ".join(f"{n} {r}" for r, n in resultats.most_common()) or "rien à faire") + ".")
    return resultats
