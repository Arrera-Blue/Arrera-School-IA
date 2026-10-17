"""File d'attente des générations (phase 3) : une seule à la fois, dans un fil à part.

Une génération dure de quelques secondes à plusieurs minutes, bien plus qu'une requête HTTP ordinaire ; et
le modèle ne sait servir qu'une demande à la fois (llama.cpp tourne dans ce processus ; Ollama est réglé
avec NUM_PARALLEL=1). L'interface dépose donc une tâche, reçoit son identifiant tout de suite, puis lit son
avancement : l'étape en cours, la question en cours d'écriture, le journal des étapes passées.

Une tâche peut être annulée (3.3, C5) : en attente, elle est retirée tout de suite ; en cours, elle s'arrête au
prochain signe de vie de la génération (une étape, ou un morceau de la réponse du modèle : environ toutes les
secondes pendant l'écriture). La lecture du prompt par le modèle, elle, ne peut pas être interrompue.
"""

import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

EN_ATTENTE, EN_COURS, TERMINE, ECHEC, ANNULE = "en_attente", "en_cours", "termine", "echec", "annule"
FINIES = (TERMINE, ECHEC, ANNULE)
GARDEES = 50  # tâches finies gardées en mémoire, pour l'affichage ; les exercices, eux, sont dans la banque


class FilePleine(Exception):
    pass


class Annulee(BaseException):
    """Levée dans le fil de travail quand l'enseignant annule la tâche en cours. BaseException, comme
    KeyboardInterrupt : aucun « except Exception » de la génération (repli, reprise…) ne doit l'arrêter."""


class DejaFinie(Exception):
    """Annuler une tâche déjà terminée : il n'y a plus rien à arrêter."""


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
    annulation: bool = False                            # demandée par l'enseignant, pendant le travail
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
        self.derniere_activite = time.monotonic()  # fin de la dernière tâche ou analyse : pour décharger le modèle

    def noter_activite(self) -> None:
        self.derniere_activite = time.monotonic()

    def inactive(self) -> bool:
        """Aucune tâche n'attend ni ne travaille."""
        with self._verrou:
            return not any(t.etat in (EN_ATTENTE, EN_COURS) for t in self._taches.values())

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

    def annuler(self, ident: str) -> dict | None:
        """Annule la tâche : tout de suite si elle attend, au prochain signe de vie si elle travaille.
        None si elle est inconnue ; DejaFinie si elle est terminée."""
        with self._verrou:
            tache = self._taches.get(ident)
            if tache is None:
                return None
            if tache.etat in FINIES:
                raise DejaFinie("la tâche est déjà terminée")
            if tache.etat == EN_ATTENTE:
                tache.etat, tache.fin = ANNULE, time.time()
                tache.journal.append({"t": 0, "message": "Annulée avant de commencer"})
                tache.fini.set()
            elif not tache.annulation:
                tache.annulation = True
                tache.journal.append({"t": self._ecoule(tache), "message": "Annulation demandée…"})
            return self._publique(tache)

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
                if tache.etat == ANNULE:  # annulée pendant son attente
                    continue
                tache.etat, tache.debut = EN_COURS, time.time()
            try:
                with self.modele:
                    self._verifier_annulation(tache)
                    resultat = tache.executer(lambda evenement: self._noter(tache, evenement))
                    self._verifier_annulation(tache)  # rien n'est rendu d'une tâche annulée à la dernière étape
            except Annulee:
                with self._verrou:
                    tache.etat = ANNULE
                    tache.journal.append({"t": self._ecoule(tache), "message": "Annulée"})
            except Exception as e:  # une tâche qui échoue ne doit jamais arrêter le fil : elle est notée en échec
                try:
                    erreur = self._decrire_erreur(e)
                except Exception:  # même la description de l'erreur ne doit pas l'arrêter
                    erreur = {"message": f"Erreur inattendue ({type(e).__name__})"}
                with self._verrou:
                    tache.etat, tache.erreur = ECHEC, erreur
                    tache.journal.append({"t": self._ecoule(tache), "message": erreur["message"]})
            else:
                with self._verrou:
                    tache.etat, tache.resultat = TERMINE, resultat
                    tache.exercice = tache.exercice or (resultat or {}).get("exercice")
            finally:
                tache.fin = time.time()
                self.noter_activite()
                tache.fini.set()

    def _verifier_annulation(self, tache: Tache) -> None:
        with self._verrou:
            annulee = tache.annulation
        if annulee:
            raise Annulee()

    def _noter(self, tache: Tache, evenement: dict) -> None:
        self._verifier_annulation(tache)  # chaque signe de vie de la génération est l'occasion de s'arrêter
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
        finies = sorted((t for t in self._taches.values() if t.etat in FINIES), key=lambda t: t.cree)
        for tache in finies[:max(0, len(finies) - GARDEES)]:
            del self._taches[tache.id]

    def _publique(self, tache: Tache) -> dict:
        """Ce que l'interface reçoit (appelé sous le verrou)."""
        vue = {"id": tache.id, "nature": tache.nature, "description": tache.description, "exercice": tache.exercice,
               "etat": tache.etat, "progression": tache.progression, "journal": list(tache.journal),
               "resultat": tache.resultat, "erreur": tache.erreur, "annulation": tache.annulation}
        if tache.etat == EN_ATTENTE:
            devant = [t for t in self._taches.values()
                      if t.etat == EN_COURS or (t.etat == EN_ATTENTE and t.cree < tache.cree)]
            vue["devant"] = len(devant)
        if tache.debut:
            vue["ecoule_s"] = round((tache.fin or time.time()) - tache.debut, 1)
        return vue
