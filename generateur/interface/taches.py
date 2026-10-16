"""File d'attente des générations (phase 3) : une seule à la fois, dans un fil à part.

Une génération dure de quelques secondes à plusieurs minutes, bien plus qu'une requête HTTP ordinaire ; et
le modèle ne sait servir qu'une demande à la fois (llama.cpp tourne dans ce processus ; Ollama est réglé
avec NUM_PARALLEL=1). L'interface dépose donc une tâche, reçoit son identifiant tout de suite, puis lit son
avancement : l'étape en cours, la question en cours d'écriture, le journal des étapes passées.
"""

import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

EN_ATTENTE, EN_COURS, TERMINE, ECHEC = "en_attente", "en_cours", "termine", "echec"
GARDEES = 50  # tâches finies gardées en mémoire, pour l'affichage ; les exercices, eux, sont dans la banque


class FilePleine(Exception):
    pass


@dataclass
class Tache:
    id: str
    nature: str                                         # « generation » | « regeneration »
    description: str
    executer: Callable[[Callable[[dict], None]], dict]  # reçoit `suivi`, renvoie le résultat
    exercice: str | None = None                         # l'exercice concerné, ou produit
    etat: str = EN_ATTENTE
    cree: float = field(default_factory=time.time)
    debut: float | None = None
    fin: float | None = None
    progression: dict = field(default_factory=dict)     # le dernier événement reçu
    journal: list[dict] = field(default_factory=list)   # {"t": secondes depuis le début, "message": …}
    resultat: dict | None = None
    erreur: dict | None = None
    fini: threading.Event = field(default_factory=threading.Event)


class File:
    def __init__(self, taille_max: int = 5, decrire_erreur: Callable[[Exception], dict] | None = None):
        self.taille_max = taille_max
        # pris pendant chaque tâche ; l'analyse d'une phrase le prend aussi, si elle le trouve libre
        self.modele = threading.Lock()
        self._decrire_erreur = decrire_erreur or (lambda e: {"message": str(e)})
        self._verrou = threading.Lock()
        self._taches: dict[str, Tache] = {}
        self._attente: queue.Queue[Tache] = queue.Queue()
        self._fil: threading.Thread | None = None

    # --- dépôt et lecture ------------------------------------------------------------------------

    def soumettre(self, nature: str, description: str, executer: Callable, exercice: str | None = None) -> Tache:
        with self._verrou:
            if sum(t.etat == EN_ATTENTE for t in self._taches.values()) >= self.taille_max:
                raise FilePleine(f"{self.taille_max} générations attendent déjà : réessayer quand l'une d'elles "
                                 "sera terminée")
            tache = Tache(uuid.uuid4().hex[:12], nature, description, executer, exercice)
            self._taches[tache.id] = tache
            self._purger()
            if self._fil is None or not self._fil.is_alive():
                self._fil = threading.Thread(target=self._travailler, name="generations", daemon=True)
                self._fil.start()
        self._attente.put(tache)
        return tache

    def lire(self, ident: str) -> dict | None:
        with self._verrou:
            tache = self._taches.get(ident)
            return self._publique(tache) if tache else None

    def lister(self) -> list[dict]:
        """Les tâches, des plus récentes aux plus anciennes."""
        with self._verrou:
            return [self._publique(t) for t in sorted(self._taches.values(), key=lambda t: t.cree, reverse=True)]

    def occupee_pour(self, exercice: str) -> bool:
        """Une tâche attend ou travaille sur cet exercice : on ne le modifie pas en même temps."""
        with self._verrou:
            return any(t.exercice == exercice and t.etat in (EN_ATTENTE, EN_COURS) for t in self._taches.values())

    def attendre(self, ident: str, delai: float) -> dict | None:
        """Pour les tests et les scripts : attend la fin de la tâche (au plus `delai` secondes)."""
        with self._verrou:
            tache = self._taches.get(ident)
        if tache is None:
            return None
        tache.fini.wait(delai)
        return self.lire(ident)

    # --- le fil de travail -----------------------------------------------------------------------

    def _travailler(self) -> None:
        while True:
            tache = self._attente.get()
            with self._verrou:
                tache.etat, tache.debut = EN_COURS, time.time()
            try:
                with self.modele:
                    resultat = tache.executer(lambda evenement: self._noter(tache, evenement))
            except Exception as e:  # une tâche qui échoue ne doit jamais arrêter le fil : elle est notée en échec
                erreur = self._decrire_erreur(e)
                with self._verrou:
                    tache.etat, tache.erreur = ECHEC, erreur
                    tache.journal.append({"t": self._ecoule(tache), "message": erreur["message"]})
            else:
                with self._verrou:
                    tache.etat, tache.resultat = TERMINE, resultat
                    tache.exercice = tache.exercice or (resultat or {}).get("exercice")
            finally:
                tache.fin = time.time()
                tache.fini.set()

    def _noter(self, tache: Tache, evenement: dict) -> None:
        with self._verrou:
            ecoule = self._ecoule(tache)
            tache.progression = {**evenement, "ecoule_s": ecoule}
            # l'écriture, token après token, met à jour la progression ; le journal ne garde que les étapes
            if evenement.get("etape") != "ecriture" and evenement.get("message"):
                tache.journal.append({"t": ecoule, "message": evenement["message"]})

    @staticmethod
    def _ecoule(tache: Tache) -> float:
        return round(time.time() - (tache.debut or tache.cree), 1)

    def _purger(self) -> None:
        finies = sorted((t for t in self._taches.values() if t.etat in (TERMINE, ECHEC)), key=lambda t: t.cree)
        for tache in finies[:max(0, len(finies) - GARDEES)]:
            del self._taches[tache.id]

    def _publique(self, tache: Tache) -> dict:
        """Ce que l'interface reçoit (appelé sous le verrou)."""
        vue = {"id": tache.id, "nature": tache.nature, "description": tache.description, "exercice": tache.exercice,
               "etat": tache.etat, "progression": tache.progression, "journal": list(tache.journal),
               "resultat": tache.resultat, "erreur": tache.erreur}
        if tache.etat == EN_ATTENTE:
            devant = [t for t in self._taches.values()
                      if t.etat == EN_COURS or (t.etat == EN_ATTENTE and t.cree < tache.cree)]
            vue["devant"] = len(devant)
        if tache.debut:
            vue["ecoule_s"] = round((tache.fin or time.time()) - tache.debut, 1)
        return vue
