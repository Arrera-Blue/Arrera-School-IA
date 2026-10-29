"""Interface enseignant (phase 3) : générer, relire et accepter un exercice, sans terminal.

    python -m generateur.interface.api                       # http://127.0.0.1:8000, ouvre le navigateur
    python -m generateur.interface.api --port 8001 --sans-navigateur

L'application n'écoute que sur 127.0.0.1, et toute l'API exige une session (évolution E1 :
docs/etapes/etape-E1-securite.md) : connexion par identifiant et mot de passe, cookie HttpOnly et
SameSite=Strict. Elle refuse aussi les requêtes qu'un autre site, ouvert dans le navigateur de l'enseignant,
pourrait lui adresser (voir `proteger`). L'aperçu d'un exercice tourne dans un bac à sable : ses scripts ne
peuvent ni appeler l'API, ni lire la page qui l'affiche.

Points d'entrée (plan-suite 3.2) :
    POST /api/analyser                               phrase → requête structurée, à confirmer
    POST /api/generations                            requête → tâche (file d'attente, une génération à la fois)
    GET  /api/generations[/{id}]                     avancement : en attente | en cours (étape, question) | …
    POST /api/generations/{id}/annuler               arrêter une génération ou une régénération
    GET  /api/exercices                              la banque, filtrée par matière, classe, statut, recherche,
                                                     attendu du programme
    GET  /api/programmes?matiere=&niveau=            les attendus du programme officiel (E2), pour le formulaire
    GET  /api/exercices/{id}[/apercu|/telecharger]   l'exercice, sa relecture, son rendu HTML
    POST /api/exercices/{id}/decision                accepter | rejeter
    POST /api/exercices/{id}/questions/{n}/regenerer remplacer la question n (tâche)
    PUT  /api/exercices/{id}/questions/{n}           la question n corrigée à la main (revalidée N2 → N4)
    DELETE /api/exercices/{id}                       retirer l'exercice de la banque (déplacé dans banque/supprimes/)

Connexion et comptes (E1) :
    POST /api/session                                se connecter (seule route ouverte sans session)
    GET  /api/session · DELETE /api/session          le compte connecté · se déconnecter
    POST /api/session/mot-de-passe                   changer son mot de passe (l'ancien est exigé)
    GET  /api/comptes · POST /api/comptes            administrateurs : lister, créer (mot de passe provisoire)
    POST /api/comptes/{identifiant}/reinitialiser    administrateurs : nouveau mot de passe provisoire
    POST /api/comptes/{identifiant}/debloquer        administrateurs : lever le verrou de 5 échecs
    DELETE /api/comptes/{identifiant}                administrateurs : supprimer un compte
    GET  /api/journal                                administrateurs : le journal des accès
Créer, réinitialiser et supprimer un compte redemandent le mot de passe de l'administrateur (⚖1).

Classes et élèves (E3) : chacun ne voit que SES classes (celle d'un autre est « introuvable ») ; aucun nom d'élève
dans une URL, seulement des identifiants internes (SEC-14) :
    GET  /api/classes · POST /api/classes            ses classes · en créer une (renvoie les cartes, codes en clair)
    POST /api/classes/liste                          lire une liste collée (« NOM;Prénom »), sans rien enregistrer
    GET  /api/classes/purge · POST /api/classes/purge   les années passées : aperçu · purge
    GET  /api/classes/{id}                           la classe et ses élèves (noté au journal)
    POST /api/classes/{id}/eleves · /codes · /archiver  ajouter des élèves · nouveaux codes · archiver
    PUT  /api/eleves/{id} · POST /api/eleves/{id}/code · /actif   corriger · nouveau code · désactiver
    POST /api/eleves/{id}/export · DELETE /api/eleves/{id}        export CSV · suppression
Exporter, supprimer un élève, refaire les codes d'une classe et purger redemandent le mot de passe (⚖1).

Suivi des élèves (E4) : des indicateurs, jamais une décision ; groupes et exercices proposés n'existent qu'une fois
enregistrés par l'enseignant :
    GET  /api/classes/{id}/suivi                     la grille élèves × attendus, et qui a besoin de quoi
    GET  /api/eleves/{id}/suivi                      la fiche d'un élève : ses attendus, ses tentatives
    POST /api/tentatives/{id}/annuler                une tentative faite par erreur ne compte plus (ou de nouveau)
    GET  /api/classes/{id}/groupes · POST            les groupes enregistrés et ceux proposés · en enregistrer un
    PUT  /api/groupes/{id} · DELETE /api/groupes/{id}   l'ajuster · le supprimer
    GET  /api/classes/{id}/propositions · POST       les exercices validés et ceux proposés · valider
    DELETE /api/propositions/{id}                    retirer un exercice validé

Serveur de classe (E8) : l'enseignant publie ses exercices acceptés ; les élèves les font sur le serveur de classe,
application séparée (generateur/classe/) :
    GET  /api/classes/{id}/publications              les exercices publiés de la classe (pour qui, dates, faits)
    GET  /api/exercices/{id}/publications · POST     où l'exercice est publié · le publier (accepté seulement)
    DELETE /api/publications/{id}                    le retirer (les réponses restent dans le suivi)
    POST /api/eleves/{id}/debloquer                  après 5 codes faux
    GET  /api/eleves/bloques                         les élèves bloqués, pour « À faire »
    GET  /api/serveur-classe                         le serveur de classe répond-il ? son adresse

Les cours des enseignants (plan IA, IA2) : le modèle les lit pour générer ; seul leur texte est gardé ; chacun ne
voit que les siens :
    GET  /api/cours · POST /api/cours                ses cours · en déposer un (PDF avec du texte, DOCX, ODT, TXT ; le
                                                     fichier en base64 dans le JSON, comme toute requête)
    GET  /api/cours/{id} · DELETE /api/cours/{id}    le texte extrait, passage par passage · le retirer
    POST /api/generations avec « cours » : true      générer à partir de ses cours (les passages les plus proches)
"""

import argparse
import base64
import binascii
import sqlite3
import threading
import time
import traceback
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from generateur import procedural, programmes
from generateur.classe import serveur as serveur_classe
from generateur.donnees import classes, codes, comptes, journal, publications, sessions, suivi
from generateur.donnees import cours as cours_enseignant
from generateur.donnees.base import Base
from generateur.interface.taches import DejaFinie, File, FilePleine
from generateur.moteur import analyse, banque, config, generation, registre, securite
from generateur.moteur.fournisseurs import ErreurFournisseur, llamacpp
from generateur.moteur.validation import ErreurValidation
from generateur.moteur.validation.fond import controler

STATIQUE = Path(__file__).with_name("statique")
HOTES = {"127.0.0.1", "localhost", "[::1]"}
METHODES_SURES = {"GET", "HEAD", "OPTIONS"}
# la page : ses propres scripts, styles et polices seulement, aucune ressource extérieure (le PC enseignant peut être
# hors ligne), et l'aperçu ne peut venir que d'ici
CSP_PAGE = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "frame-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'")
# l'aperçu : la politique du gabarit, plus un bac à sable (origine opaque) même ouvert hors de l'iframe
CSP_APERCU = ("sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
              "img-src data:; media-src data:; font-src data:; frame-ancestors 'self'")
COOKIE = "session"
# sans session : se connecter, et rien d'autre
PUBLIQUES = {("POST", "/api/session")}
# avec un mot de passe provisoire : le changer, et rien d'autre
AVANT_CHANGEMENT = {("GET", "/api/session"), ("DELETE", "/api/session"), ("POST", "/api/session/mot-de-passe")}
ENTRETIEN_S = 3600


# --- les corps de requête ------------------------------------------------------------------------

class Phrase(BaseModel):
    phrase: str = Field(max_length=1000)


class Demande(BaseModel):
    type: str = "qcm"
    matiere: str | None = None
    niveau: str | None = None
    notion: str | None = Field(None, max_length=120)
    nb_questions: int | None = Field(None, ge=1, le=50)
    difficulte: Literal["facile", "moyen", "difficile"] | None = None
    demande_enseignant: str | None = Field(None, max_length=1000)
    # un attendu (« maths.6e.fractions.09 ») ou un thème (« maths.6e.fractions ») du programme officiel (E2)
    attendu: str | None = Field(None, max_length=80, pattern=r"^[a-z0-9.-]+$")
    mode: Literal["auto", "ia", "procedural"] = "auto"
    fournisseur: Literal["llamacpp", "ollama", "maquette"] | None = None
    # plan IA, IA2.5 : « M'appuyer sur mes cours » ; tous ses cours, ou ceux-ci seulement
    cours: bool = False
    cours_ids: list[int] | None = Field(None, max_length=50)


class Decision(BaseModel):
    decision: Literal["accepter", "rejeter"]
    motif: str | None = Field(None, max_length=500)


class NouveauCours(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    contenu: str = Field(max_length=28_000_000)  # le fichier en base64 (20 Mo au plus une fois décodé)
    matiere: str | None = Field(None, max_length=40)
    niveau: str | None = Field(None, max_length=10)


class Regeneration(BaseModel):
    motif: str | None = Field(None, max_length=500)  # le moteur n'en transmet que 200 au modèle


class Identifiants(BaseModel):
    identifiant: str = Field(max_length=200)
    mot_de_passe: str = Field(max_length=200)


class Confirmation(BaseModel):
    """Le mot de passe de la personne connectée, redemandé avant une action sensible (⚖1)."""
    mot_de_passe: str = Field(max_length=200)


class ChangementMotDePasse(BaseModel):
    ancien: str = Field(max_length=200)
    nouveau: str = Field(max_length=200)


class NouveauCompte(Confirmation):
    identifiant: str = Field(max_length=100)
    nom: str = Field(max_length=100)
    role: Literal["admin", "enseignant"] = "enseignant"


class EleveSaisi(BaseModel):
    nom: str = Field(max_length=80)
    prenom: str = Field(max_length=80)


class NouvelleClasse(BaseModel):
    nom: str = Field(max_length=40)
    niveau: Literal["6e", "5e", "4e", "3e"]
    annee: str | None = Field(None, pattern=r"^\d{4}-\d{4}$")
    eleves: list[EleveSaisi] = Field(default_factory=list, max_length=classes.ELEVES_MAX)


class NouveauxEleves(BaseModel):
    eleves: list[EleveSaisi] = Field(min_length=1, max_length=classes.ELEVES_MAX)


class ListeCollee(BaseModel):
    texte: str = Field(max_length=10_000)


class Archivage(BaseModel):
    archivee: bool


class EtatEleve(BaseModel):
    actif: bool


IDENT_ATTENDU = r"^[a-z0-9.-]+$"


class NouveauGroupe(BaseModel):
    nom: str = Field(max_length=120)
    attendu: str | None = Field(None, max_length=80, pattern=IDENT_ATTENDU)
    nature: Literal["consolider", "approfondir"]
    eleves: list[int] = Field(default_factory=list, max_length=classes.ELEVES_MAX)


class GroupeModifie(BaseModel):
    nom: str = Field(max_length=120)
    eleves: list[int] = Field(default_factory=list, max_length=classes.ELEVES_MAX)


class Publication(BaseModel):
    classe_id: int = Field(ge=1)
    groupe_id: int | None = Field(None, ge=1)
    eleve_id: int | None = Field(None, ge=1)
    debut: str | None = Field(None, max_length=10)
    fin: str | None = Field(None, max_length=10)


class PropositionValidee(BaseModel):
    eleve_id: int
    nature: Literal["retravailler", "plus_loin"]
    attendu: str = Field(max_length=80, pattern=IDENT_ATTENDU)
    exercice: str | None = Field(None, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")


class Propositions(BaseModel):
    propositions: list[PropositionValidee] = Field(max_length=classes.ELEVES_MAX * 50)


class Annulation(BaseModel):
    annulee: bool = True


class Question(BaseModel):
    """Une question corrigée par l'enseignant ; les limites fines (longueurs, 3 ou 4 propositions) sont celles
    du schéma du type, contrôlées par N2 avec des messages en français."""
    enonce: str = Field(max_length=2000)
    propositions: list[str] = Field(max_length=10)
    index_correct: int = Field(ge=0)
    explication: str = Field(max_length=2000)
    difficulte: Literal["facile", "moyen", "difficile"] | None = None


# --- outils --------------------------------------------------------------------------------------

def decrire_erreur(e: Exception) -> dict:
    """Ce que l'enseignant lit quand une tâche échoue."""
    if isinstance(e, ErreurValidation):
        return {"message": f"Réponse du modèle refusée ({e.niveau}), même après les reprises",
                "erreurs": list(e.erreurs), "rejet": e.rejet.name if e.rejet else None}
    if isinstance(e, ErreurFournisseur):
        return {"message": f"Le modèle n'a pas pu répondre : {e}"}
    if isinstance(e, (generation.AucunGenerateur, banque.ExerciceInconnu, registre.TypeInconnu, ValueError)):
        return {"message": str(e)}
    traceback.print_exception(e)
    return {"message": f"Erreur inattendue ({type(e).__name__} : {e}) ; le détail est dans le terminal du serveur"}


def _hote(entete: str) -> str:
    """« 127.0.0.1:8000 » → « 127.0.0.1 » ; « [::1]:8000 » → « [::1] »."""
    if entete.startswith("["):
        return entete.split("]")[0] + "]"
    return entete.rsplit(":", 1)[0] if ":" in entete else entete


def _charger(ident: str) -> dict:
    try:
        return banque.charger(ident)
    except banque.ExerciceInconnu as e:
        raise HTTPException(404, str(e)) from None


def _verifier(corps: Demande) -> dict:
    """La demande, contrôlée contre le schéma du type : ce qui arrive au moteur est toujours valable."""
    if corps.type not in registre.lister():
        raise HTTPException(422, f"type « {corps.type} » inconnu (disponibles : {', '.join(registre.lister())})")
    proprietes = registre.charger(corps.type).schema.get("properties", {})
    for champ in ("matiere", "niveau"):
        valeur, permises = getattr(corps, champ), proprietes.get(champ, {}).get("enum")
        if valeur and permises and valeur not in permises:
            raise HTTPException(422, f"{champ} « {valeur} » inconnue (permises : {', '.join(permises)})")
    bornes = proprietes.get("questions", {})
    minimum, maximum = bornes.get("minItems", 1), bornes.get("maxItems", 50)
    if corps.nb_questions is not None and not minimum <= corps.nb_questions <= maximum:
        raise HTTPException(422, f"nombre de questions : de {minimum} à {maximum}")
    notion = (corps.notion or "").strip() or None
    phrase = (corps.demande_enseignant or "").strip() or None
    matiere, niveau = corps.matiere or None, corps.niveau or None
    if corps.attendu:
        if not programmes.existe(corps.attendu):
            raise HTTPException(422, f"attendu du programme inconnu : {corps.attendu}")
        de_l_attendu, _, reste = corps.attendu.partition(".")
        classe = reste.split(".")[0]
        if (matiere and matiere != de_l_attendu) or (niveau and niveau != classe):
            raise HTTPException(422, f"l'attendu choisi est du programme de {de_l_attendu}, {classe} : il ne "
                                     f"correspond pas à la matière et à la classe demandées")
        matiere, niveau = de_l_attendu, classe
        # sans notion écrite, le libellé de l'attendu en tient lieu (coupé à la longueur permise par le schéma)
        notion = notion or programmes.notion_de(corps.attendu)
    if not (notion or phrase):
        raise HTTPException(422, "indiquer la notion, ou la demande de l'enseignant")
    demande = {"type": corps.type, "matiere": matiere, "niveau": niveau, "notion": notion,
               "nb_questions": corps.nb_questions, "difficulte": corps.difficulte, "demande_enseignant": phrase,
               "attendu": corps.attendu}
    return {k: v for k, v in demande.items() if v is not None}


def _procedural(requete: dict) -> dict | None:
    """Le générateur procédural qui traiterait cette demande, s'il y en a un (affiché à l'enseignant)."""
    nom = procedural.aiguiller(requete) if requete.get("type", "qcm") == "qcm" else None
    return {"nom": nom, "notion": procedural.notions()[nom].NOTION} if nom else None


def decharger_si_inactif(file: File, delai_s: float, maintenant: float | None = None) -> bool:
    """Libère le modèle (llama.cpp, dans ce processus) si rien ne s'en est servi depuis `delai_s` secondes.
    Jamais pendant une génération ou une analyse : le verrou du modèle doit être libre, et aucune tâche en
    attente. Renvoie True si le modèle a été libéré. (Ollama, lui, se décharge seul : KEEP_ALIVE.)"""
    if delai_s <= 0 or not file.modele.acquire(blocking=False):
        return False
    try:
        inactif = (maintenant or time.monotonic()) - file.derniere_activite >= delai_s
        if not (inactif and file.inactive()):
            return False
        libere = llamacpp.decharger()
    finally:
        file.modele.release()
    if libere:
        print(f"Modèle déchargé après {delai_s / 60:g} min sans génération : il sera rechargé à la prochaine "
              "demande (quelques secondes).", flush=True)
    return libere


def _surveiller(file: File, delai_s: float, arret: threading.Event) -> None:
    while not arret.wait(min(60.0, max(delai_s / 4, 1.0))):
        decharger_si_inactif(file, delai_s)


def entretenir(base: Base, dossier_sauvegardes: Path) -> None:
    """Une sauvegarde par jour, gardée 7 jours (SEC-13) ; le ménage : sessions expirées, journal de plus de
    6 mois."""
    try:
        base.sauvegarder_si_besoin(dossier_sauvegardes)
        sessions.purger(base)
    except (OSError, sqlite3.Error) as e:
        print(f"Entretien de la base impossible : {e}", flush=True)


def _entretenir_chaque_heure(base: Base, dossier_sauvegardes: Path, arret: threading.Event) -> None:
    entretenir(base, dossier_sauvegardes)
    while not arret.wait(ENTRETIEN_S):
        entretenir(base, dossier_sauvegardes)


# --- l'application -------------------------------------------------------------------------------

def creer_application(file: File | None = None, base: Base | None = None) -> FastAPI:
    reglages = config.charger().get("interface") or {}
    file = file or File(int(reglages.get("file_max", 5)), decrire_erreur)
    base = base or Base(config.chemin("base"))  # créée et migrée à la première utilisation
    delai_dechargement_s = float(reglages.get("decharger_apres_min", 10)) * 60

    @asynccontextmanager
    async def cycle_de_vie(_app):
        """Pendant que le serveur tourne : décharger le modèle après un moment sans génération (3.3, C3) ;
        sauvegarder la base chaque jour et faire le ménage (E1)."""
        arret = threading.Event()
        base.preparer()
        if not comptes.nombre(base):
            print("Aucun compte : créez le compte administrateur avec\n"
                  "    python -m generateur.donnees.comptes creer-admin", flush=True)
        threading.Thread(target=_entretenir_chaque_heure, args=(base, config.chemin("sauvegardes"), arret),
                         name="entretien", daemon=True).start()
        if delai_dechargement_s > 0:
            threading.Thread(target=_surveiller, args=(file, delai_dechargement_s, arret), name="dechargement",
                             daemon=True).start()
        yield
        arret.set()

    # pas de page /api/docs : elle charge ses scripts sur internet (le PC enseignant peut être hors ligne, et la
    # page n'en charge aucun d'ailleurs) ; la description de l'API reste lisible dans /api/openapi.json
    app = FastAPI(lifespan=cycle_de_vie, title="Générateur d'exercices — interface enseignant", docs_url=None, redoc_url=None,
                  openapi_url="/api/openapi.json")
    app.state.file = file
    app.state.base = base

    async def refuser(request: Request) -> Response | None:
        """Une réponse de refus, ou None si la requête peut passer.
        1. Deux attaques venues du navigateur de l'enseignant :
           - le « DNS rebinding » : un site dont le nom pointe soudain vers 127.0.0.1 → l'en-tête Host le trahit ;
           - la requête intersite : une page d'un autre site poste un formulaire vers 127.0.0.1 → l'en-tête
             Origin le trahit, et un formulaire ne peut pas envoyer de JSON sans demander la permission (CORS).
        2. La session (SEC-8) : toute l'API la demande, sauf la connexion ; refus par défaut, pour qu'une route
           ajoutée plus tard ne soit jamais ouverte par oubli. La page et ses fichiers statiques, eux, ne
           contiennent aucune donnée : ils restent publics."""
        hote = request.headers.get("host", "")
        if _hote(hote) not in HOTES:
            return PlainTextResponse("hôte refusé : l'interface ne répond qu'à 127.0.0.1", status_code=400)
        if request.method not in METHODES_SURES:
            origine = request.headers.get("origin")
            if origine is not None and origine != f"http://{hote}":
                return PlainTextResponse("origine refusée", status_code=403)
            if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                return PlainTextResponse("le corps de la requête doit être du JSON", status_code=415)
        route = (request.method, request.url.path)
        if not request.url.path.startswith("/api/") or route in PUBLIQUES:
            return None
        compte = await run_in_threadpool(sessions.session, base, request.cookies.get(COOKIE))
        if compte is None:
            sans_compte = await run_in_threadpool(comptes.nombre, base) == 0
            return JSONResponse({"detail": "connexion requise", "sans_compte": sans_compte}, status_code=401)
        if compte["doit_changer"] and route not in AVANT_CHANGEMENT:
            return JSONResponse({"detail": "mot de passe provisoire : choisissez d'abord le vôtre",
                                 "doit_changer": True}, status_code=403)
        request.state.compte = compte
        return None

    @app.middleware("http")
    async def proteger(request: Request, call_next):
        reponse = await refuser(request) or await call_next(request)
        reponse.headers.setdefault("X-Content-Type-Options", "nosniff")
        reponse.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api/"):
            # rien de l'API dans le cache du navigateur (SEC-11)
            reponse.headers.setdefault("Cache-Control", "no-store")
        elif request.url.path.startswith("/statique/"):
            reponse.headers.setdefault("Cache-Control", "no-cache")
        return reponse

    @app.get("/", include_in_schema=False)
    def page():
        return FileResponse(STATIQUE / "index.html", media_type="text/html",
                            headers={"Content-Security-Policy": CSP_PAGE, "Cache-Control": "no-cache"})

    @app.get("/favicon.ico", include_in_schema=False)
    def icone():
        return Response(status_code=204)  # pas d'icône : le navigateur la demande quand même

    app.mount("/statique", StaticFiles(directory=STATIQUE), name="statique")

    # --- connexion et comptes (E1) ----------------------------------------------------------------

    def admin(request: Request) -> dict:
        compte = request.state.compte
        if compte["role"] != "admin":
            raise HTTPException(403, "réservé aux administrateurs")
        return compte

    def confirmer(compte: dict, mot_de_passe: str) -> None:
        try:
            sessions.confirmer(base, compte, mot_de_passe)
        except sessions.CompteVerrouille as e:
            raise HTTPException(429, str(e)) from None
        except sessions.ConnexionRefusee:
            raise HTTPException(403, "mot de passe incorrect") from None

    def pas_soi_meme(compte: dict, identifiant: str, conseil: str) -> None:
        if identifiant.strip().lower() == compte["identifiant"]:
            raise HTTPException(409, f"impossible sur votre propre compte : {conseil}")

    @app.post("/api/session")
    def connexion(corps: Identifiants, request: Request, response: Response):
        # pas de fixation de session (M3) : l'ancien jeton de ce navigateur meurt, un nouveau est tiré
        sessions.deconnecter(base, request.cookies.get(COOKIE))
        try:
            jeton, compte = sessions.connecter(base, corps.identifiant, corps.mot_de_passe)
        except sessions.CompteVerrouille as e:
            raise HTTPException(429, str(e)) from None
        except sessions.ConnexionRefusee as e:
            raise HTTPException(401, str(e)) from None
        # pas de Secure : l'interface est en HTTP sur 127.0.0.1 ; le serveur de classe (E8), en HTTPS, l'aura
        response.set_cookie(COOKIE, jeton, httponly=True, samesite="strict", path="/")
        return {"compte": compte}

    @app.get("/api/session")
    def compte_connecte(request: Request):
        return {"compte": request.state.compte}

    @app.delete("/api/session")
    def deconnexion(request: Request, response: Response):
        sessions.deconnecter(base, request.cookies.get(COOKIE), request.state.compte)
        response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
        return {"deconnecte": True}

    @app.post("/api/session/mot-de-passe")
    def changer_mot_de_passe(corps: ChangementMotDePasse, request: Request):
        try:
            compte = sessions.changer_mot_de_passe(base, request.state.compte, corps.ancien, corps.nouveau,
                                                   request.cookies.get(COOKIE))
        except sessions.CompteVerrouille as e:
            raise HTTPException(429, str(e)) from None
        except sessions.ConnexionRefusee:
            raise HTTPException(403, "mot de passe actuel incorrect") from None
        except comptes.CompteInvalide as e:
            raise HTTPException(422, str(e)) from None
        return {"compte": compte}

    @app.get("/api/comptes")
    def lister_comptes(request: Request):
        admin(request)
        return {"comptes": comptes.lister(base)}

    @app.post("/api/comptes", status_code=201)
    def creer_compte(corps: NouveauCompte, request: Request):
        """Le compte reçoit un mot de passe provisoire, affiché une seule fois, à changer à la connexion."""
        auteur = admin(request)
        confirmer(auteur, corps.mot_de_passe)
        mot_de_passe = comptes.provisoire()
        try:
            compte = comptes.creer(base, corps.identifiant, corps.nom, mot_de_passe, corps.role, doit_changer=True,
                                   par=auteur)
        except comptes.CompteInvalide as e:
            raise HTTPException(422, str(e)) from None
        return {"compte": compte, "mot_de_passe_provisoire": mot_de_passe}

    @app.post("/api/comptes/{identifiant}/reinitialiser")
    def reinitialiser_compte(identifiant: str, corps: Confirmation, request: Request):
        auteur = admin(request)
        pas_soi_meme(auteur, identifiant, "changez votre mot de passe dans « Mon compte »")
        confirmer(auteur, corps.mot_de_passe)
        try:
            return {"mot_de_passe_provisoire": comptes.reinitialiser(base, identifiant, par=auteur)}
        except comptes.CompteInconnu as e:
            raise HTTPException(404, str(e)) from None

    @app.post("/api/comptes/{identifiant}/debloquer")
    def debloquer_compte(identifiant: str, request: Request):
        try:
            comptes.debloquer(base, identifiant, par=admin(request))
        except comptes.CompteInconnu as e:
            raise HTTPException(404, str(e)) from None
        return {"debloque": identifiant}

    @app.delete("/api/comptes/{identifiant}")
    def supprimer_compte(identifiant: str, corps: Confirmation, request: Request):
        auteur = admin(request)
        pas_soi_meme(auteur, identifiant, "demandez à un autre administrateur")
        confirmer(auteur, corps.mot_de_passe)
        try:
            comptes.supprimer(base, identifiant, par=auteur)
        except comptes.CompteInconnu as e:
            raise HTTPException(404, str(e)) from None
        except comptes.CompteInvalide as e:
            raise HTTPException(409, str(e)) from None
        return {"supprime": identifiant}

    @app.get("/api/journal")
    def lire_journal(request: Request, limite: int = 100):
        admin(request)
        return {"journal": journal.lire(base, max(1, min(limite, 500)))}

    # --- classes et élèves (E3) ---------------------------------------------------------------------

    def cle_codes() -> bytes:
        return codes.cle_secrete(config.chemin("cle_codes"))

    def faire(action, *arguments):
        """Les erreurs de classes.py en réponses HTTP : introuvable (ou pas à soi) → 404, saisie refusée → 422."""
        try:
            return action(*arguments)
        except classes.Introuvable as e:
            raise HTTPException(404, str(e)) from None
        except classes.ClasseInvalide as e:
            raise HTTPException(422, str(e)) from None

    def saisis(eleves: list[EleveSaisi]) -> list[dict]:
        return [{"nom": e.nom, "prenom": e.prenom} for e in eleves]

    @app.get("/api/classes")
    def lister_classes(request: Request, archivees: bool = False):
        return {"classes": classes.lister(base, request.state.compte, archivees),
                "annee_courante": classes.annee_scolaire(), "niveaux": list(classes.NIVEAUX),
                # tant que le dossier RGPD n'est pas validé : « élèves fictifs uniquement » (docs/rgpd/)
                "aipd_validee": bool((config.charger().get("rgpd") or {}).get("aipd_validee"))}

    @app.post("/api/classes/liste")
    def lire_liste(corps: ListeCollee):
        eleves, remarques = classes.lire_liste(corps.texte)
        return {"eleves": eleves, "remarques": remarques}

    @app.post("/api/classes", status_code=201)
    def creer_classe(corps: NouvelleClasse, request: Request):
        classe, cartes = faire(classes.creer, base, request.state.compte, corps.nom, corps.niveau, corps.annee,
                               saisis(corps.eleves), cle_codes())
        return {"classe": classe, "cartes": cartes}

    # avant /api/classes/{classe_id} : « purge » n'est pas un identifiant
    @app.get("/api/classes/purge")
    def apercu_purge(request: Request):
        return classes.apercu_purge(base, request.state.compte)

    @app.post("/api/classes/purge")
    def purger(corps: Confirmation, request: Request):
        confirmer(request.state.compte, corps.mot_de_passe)
        return classes.purger(base, request.state.compte)

    @app.get("/api/classes/{classe_id}")
    def lire_classe(classe_id: int, request: Request):
        return {"classe": faire(classes.lire, base, request.state.compte, classe_id)}

    @app.post("/api/classes/{classe_id}/eleves")
    def ajouter_eleves(classe_id: int, corps: NouveauxEleves, request: Request):
        return {"cartes": faire(classes.ajouter, base, request.state.compte, classe_id, saisis(corps.eleves), cle_codes())}

    @app.post("/api/classes/{classe_id}/codes")
    def nouveaux_codes(classe_id: int, corps: Confirmation, request: Request):
        """Toutes les cartes de la classe à refaire : les anciens codes ne marchent plus."""
        confirmer(request.state.compte, corps.mot_de_passe)
        return {"cartes": faire(classes.nouveaux_codes, base, request.state.compte, classe_id, cle_codes())}

    @app.post("/api/classes/{classe_id}/archiver")
    def archiver_classe(classe_id: int, corps: Archivage, request: Request):
        return {"classe": faire(classes.archiver, base, request.state.compte, classe_id, corps.archivee)}

    @app.put("/api/eleves/{eleve_id}")
    def modifier_eleve(eleve_id: int, corps: EleveSaisi, request: Request):
        return {"eleve": faire(classes.modifier, base, request.state.compte, eleve_id, corps.nom, corps.prenom)}

    @app.post("/api/eleves/{eleve_id}/code")
    def nouveau_code(eleve_id: int, request: Request):
        """Un clic, en classe : la carte perdue d'un élève."""
        return {"carte": faire(classes.nouveau_code, base, request.state.compte, eleve_id, cle_codes())}

    @app.post("/api/eleves/{eleve_id}/actif")
    def activer_eleve(eleve_id: int, corps: EtatEleve, request: Request):
        return {"eleve": faire(classes.activer, base, request.state.compte, eleve_id, corps.actif)}

    @app.post("/api/eleves/{eleve_id}/export")
    def exporter_eleve(eleve_id: int, corps: Confirmation, request: Request):
        """Le droit d'accès : un CSV, remis à l'établissement (docs/rgpd/procedures.md §2)."""
        confirmer(request.state.compte, corps.mot_de_passe)
        nom, contenu = faire(classes.exporter, base, request.state.compte, eleve_id)
        return Response(contenu, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{nom}"'})

    @app.delete("/api/eleves/{eleve_id}")
    def supprimer_eleve(eleve_id: int, corps: Confirmation, request: Request):
        confirmer(request.state.compte, corps.mot_de_passe)
        faire(classes.supprimer, base, request.state.compte, eleve_id)
        return {"supprime": eleve_id}

    # --- suivi des élèves (E4) ----------------------------------------------------------------------

    @app.get("/api/classes/{classe_id}/suivi")
    def suivi_classe(classe_id: int, request: Request):
        return faire(suivi.indicateurs, base, request.state.compte, classe_id)

    @app.get("/api/eleves/{eleve_id}/suivi")
    def suivi_eleve(eleve_id: int, request: Request):
        return faire(suivi.fiche, base, request.state.compte, eleve_id)

    @app.post("/api/tentatives/{tentative_id}/annuler")
    def annuler_tentative(tentative_id: int, corps: Annulation, request: Request):
        faire(suivi.annuler_tentative, base, request.state.compte, tentative_id, corps.annulee)
        return {"tentative": tentative_id, "annulee": corps.annulee}

    @app.get("/api/classes/{classe_id}/groupes")
    def groupes(classe_id: int, request: Request):
        compte = request.state.compte
        return {"groupes": faire(suivi.lister_groupes, base, compte, classe_id),
                "proposes": faire(suivi.proposer_groupes, base, compte, classe_id)}

    @app.post("/api/classes/{classe_id}/groupes", status_code=201)
    def creer_groupe(classe_id: int, corps: NouveauGroupe, request: Request):
        return {"groupe": faire(suivi.creer_groupe, base, request.state.compte, classe_id, corps.nom, corps.attendu,
                                corps.nature, corps.eleves)}

    @app.put("/api/groupes/{groupe_id}")
    def modifier_groupe(groupe_id: int, corps: GroupeModifie, request: Request):
        return {"groupe": faire(suivi.modifier_groupe, base, request.state.compte, groupe_id, corps.nom, corps.eleves)}

    @app.delete("/api/groupes/{groupe_id}")
    def supprimer_groupe(groupe_id: int, request: Request):
        faire(suivi.supprimer_groupe, base, request.state.compte, groupe_id)
        return {"supprime": groupe_id}

    @app.get("/api/classes/{classe_id}/propositions")
    def propositions(classe_id: int, request: Request):
        compte = request.state.compte
        return {"validees": faire(suivi.lister_propositions, base, compte, classe_id),
                "proposees": faire(suivi.proposer_exercices, base, compte, classe_id)}

    @app.post("/api/classes/{classe_id}/propositions")
    def valider_propositions(classe_id: int, corps: Propositions, request: Request):
        nombre = faire(suivi.valider_propositions, base, request.state.compte, classe_id,
                       [p.model_dump() for p in corps.propositions])
        return {"validees": nombre}

    @app.delete("/api/propositions/{proposition_id}")
    def supprimer_proposition(proposition_id: int, request: Request):
        faire(suivi.supprimer_proposition, base, request.state.compte, proposition_id)
        return {"supprime": proposition_id}

    # --- serveur de classe (E8) : publier, retirer, débloquer -----------------------------------------

    @app.get("/api/classes/{classe_id}/publications")
    def publications_classe(classe_id: int, request: Request):
        return {"publications": faire(publications.lister, base, request.state.compte, classe_id)}

    @app.get("/api/exercices/{ident}/publications")
    def publications_exercice(ident: str, request: Request):
        _charger(ident)
        return {"publications": publications.de_l_exercice(base, request.state.compte, ident)}

    @app.post("/api/exercices/{ident}/publications", status_code=201)
    def publier(ident: str, corps: Publication, request: Request):
        _charger(ident)
        return {"publication": faire(publications.publier, base, request.state.compte, ident, corps.classe_id,
                                     corps.groupe_id, corps.eleve_id, corps.debut, corps.fin)}

    @app.delete("/api/publications/{publication_id}")
    def retirer_publication(publication_id: int, request: Request):
        faire(publications.retirer, base, request.state.compte, publication_id)
        return {"retiree": publication_id}

    @app.get("/api/eleves/bloques")
    def eleves_bloques(request: Request):
        return {"eleves": classes.bloques(base, request.state.compte)}

    @app.post("/api/eleves/{eleve_id}/debloquer")
    def debloquer_eleve(eleve_id: int, request: Request):
        return {"eleve": faire(classes.debloquer, base, request.state.compte, eleve_id)}

    @app.get("/api/serveur-classe")
    def etat_serveur_classe():
        return serveur_classe.etat()

    # --- les cours des enseignants (plan IA, IA2) ---------------------------------------------------------

    @app.get("/api/cours")
    def lister_cours(request: Request):
        return {"cours": cours_enseignant.lister(base, request.state.compte), "formats": ["pdf", "docx", "odt", "txt"],
                "taille_max_mo": 20}

    @app.post("/api/cours", status_code=201)
    def deposer_cours(corps: NouveauCours, request: Request):
        proprietes = registre.charger("qcm").schema.get("properties", {})
        for champ in ("matiere", "niveau"):
            valeur = getattr(corps, champ)
            if valeur and valeur not in proprietes.get(champ, {}).get("enum", []):
                raise HTTPException(422, f"{champ} « {valeur} » inconnue")
        try:
            contenu = base64.b64decode(corps.contenu, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(422, "le fichier n'a pas été transmis correctement (base64 attendu)") from None
        try:
            return {"cours": cours_enseignant.deposer(base, request.state.compte, corps.nom, contenu, corps.matiere,
                                                      corps.niveau)}
        except cours_enseignant.CoursRefuse as e:
            raise HTTPException(422, str(e)) from None

    @app.get("/api/cours/{cours_id}")
    def lire_cours(cours_id: int, request: Request):
        return {"cours": faire(cours_enseignant.lire, base, request.state.compte, cours_id)}

    @app.delete("/api/cours/{cours_id}")
    def retirer_cours(cours_id: int, request: Request):
        faire(cours_enseignant.retirer, base, request.state.compte, cours_id)
        return {"retire": cours_id}

    # --- génération et banque (phase 3) -------------------------------------------------------------

    @app.get("/api/types")
    def types():
        """Les types d'exercice, avec ce que le formulaire doit proposer (matières, classes, bornes)."""
        resultat = []
        for nom in registre.lister():
            proprietes = registre.charger(nom).schema.get("properties", {})
            questions = proprietes.get("questions", {})
            difficultes = questions.get("items", {}).get("properties", {}).get("difficulte", {}).get("enum", [])
            resultat.append({"nom": nom, "titre": registre.charger(nom).schema.get("title", nom),
                             "matieres": proprietes.get("matiere", {}).get("enum", []),
                             "niveaux": proprietes.get("niveau", {}).get("enum", []),
                             "questions_min": questions.get("minItems", 1), "questions_max": questions.get("maxItems", 50),
                             "difficultes": difficultes})
        return {"types": resultat}

    # --- sécurité de l'IA (plan IA, IA1) : une demande refusée n'atteint jamais le modèle -----------------

    ETIQUETTES_REFUS = {"injection": "consigne adressée au modèle", "contenu_interdit": "contenu interdit",
                        "fausse_reponse": "réponse fausse imposée", "lien": "lien",
                        "donnees_personnelles": "données personnelles", "hors_sujet": "pas un exercice"}

    def refuser_demande(compte: dict, categorie: str, message: str):
        """Le refus au journal (la catégorie seulement, jamais le texte : il peut contenir un nom), puis 422."""
        with base.ecrire() as conn:
            journal.noter(conn, "demande_refusee", compte, detail=ETIQUETTES_REFUS.get(categorie, categorie))
        raise HTTPException(422, message)

    @app.post("/api/analyser")
    def analyser(corps: Phrase, request: Request):
        """Règles d'abord ; le modèle complète la matière ou la notion s'il est libre (jamais pendant une
        génération : il ne sert qu'une demande à la fois). Une phrase refusée par la sécurité de l'IA : 422."""
        par_le_modele = bool(reglages.get("analyse_par_modele", True))
        pris = par_le_modele and file.modele.acquire(blocking=False)
        try:
            fournisseur = None
            if pris:
                try:
                    fournisseur = generation.creer_fournisseur()
                except ErreurFournisseur:
                    fournisseur = None
            resultat = analyse.analyser(corps.phrase, fournisseur,
                                        classes.noms_des_eleves(base, request.state.compte)).en_dict()
        finally:
            if pris:
                file.noter_activite()
                file.modele.release()
        if resultat["refus"]:
            refuser_demande(request.state.compte, resultat["refus"]["categorie"], resultat["refus"]["message"])
        if par_le_modele and not pris and {"matiere", "notion"} & set(resultat["a_verifier"]):
            resultat["remarques"].append("le modèle est occupé par une génération : analyse par les règles seules")
        resultat["procedural"] = _procedural(resultat["requete"])
        return resultat

    @app.post("/api/generations", status_code=202)
    def lancer(corps: Demande, request: Request):
        noms = classes.noms_des_eleves(base, request.state.compte)
        try:  # avant la file : la génération refuserait aussi, mais l'enseignant attendrait pour rien
            demande = securite.controler_demande(_verifier(corps), noms)
        except securite.DemandeRefusee as e:
            refuser_demande(request.state.compte, e.categorie, e.message)
        sujet = demande.get("notion") or demande.get("demande_enseignant", "")[:60]
        description = f"{corps.type.upper()} — {sujet}" + (f" ({demande['niveau']})" if demande.get("niveau") else "")
        passages = None
        if corps.cours:  # plan IA, IA2.5 : les passages de ses cours les plus proches de la demande
            cherche = " ".join(filter(None, [demande.get("notion"), demande.get("demande_enseignant"),
                                             programmes.libelle(demande["attendu"]) if demande.get("attendu") else None]))
            passages = cours_enseignant.chercher(base, request.state.compte, cherche, corps.cours_ids,
                                                 demande.get("matiere"), demande.get("niveau"))
            if not passages:
                raise HTTPException(422, "aucun passage de vos cours ne correspond à cette demande : déposez le cours "
                                         "(rubrique « Mes cours »), ou décochez « M'appuyer sur mes cours »")
            description += " — d'après vos cours"

        def executer(suivi):
            instance = generation.generer(demande, corps.type, corps.fournisseur, corps.mode, suivi=suivi,
                                          noms_proteges=noms, passages=passages)
            banque.enregistrer(instance)
            return {"exercice": instance["meta"]["id"]}

        try:
            tache = file.soumettre("generation", description, executer)
        except FilePleine as e:
            raise HTTPException(429, str(e)) from None
        return file.lire(tache.id)

    @app.get("/api/generations")
    def taches():
        return {"taches": file.lister()}

    @app.get("/api/generations/{ident}")
    def tache(ident: str):
        vue = file.lire(ident)
        if vue is None:
            raise HTTPException(404, "tâche inconnue (le serveur a peut-être redémarré)")
        return vue

    @app.post("/api/generations/{ident}/annuler")
    def annuler(ident: str):
        """Rien n'est enregistré d'une tâche annulée : ni exercice, ni question régénérée."""
        try:
            vue = file.annuler(ident)
        except DejaFinie as e:
            raise HTTPException(409, str(e)) from None
        if vue is None:
            raise HTTPException(404, "tâche inconnue (le serveur a peut-être redémarré)")
        return vue

    @app.get("/api/exercices")
    def exercices(matiere: str | None = None, niveau: str | None = None, statut: str | None = None,
                  recherche: str | None = None, attendu: str | None = None):
        return {"exercices": banque.lister(matiere or None, niveau or None, statut or None, (recherche or "")[:200],
                                           (attendu or "")[:80] or None)}

    @app.get("/api/programmes")
    def programmes_officiels(matiere: str, niveau: str, tous: bool = False):
        """Les thèmes et attendus du programme pour cette matière à cette classe (par défaut, ceux qui se prêtent
        à un QCM) ; `couvert: false` si le référentiel ne l'a pas (E2 : maths et français, 6e et 5e)."""
        contenu = programmes.arbre(matiere, niveau, None if tous else True)
        return {"couvert": contenu is not None, **(contenu or {"matiere": matiere, "niveau": niveau, "themes": []})}

    @app.get("/api/exercices/{ident}")
    def exercice(ident: str):
        instance = _charger(ident)
        fond = controler(instance)  # avec les règles du jour, pas le verdict enregistré à la génération
        return {"exercice": instance, "resume": banque.resume(instance, fond),
                "relecture": banque.relecture(instance, fond), "occupe": file.occupee_pour(ident)}

    @app.get("/api/exercices/{ident}/apercu", response_class=HTMLResponse)
    def apercu(ident: str):
        return HTMLResponse(banque.rendre(_charger(ident)), headers={"Content-Security-Policy": CSP_APERCU})

    @app.get("/api/exercices/{ident}/telecharger")
    def telecharger(ident: str):
        html = banque.rendre(_charger(ident))
        return Response(html, media_type="text/html; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{ident}.html"',
                                 "Content-Security-Policy": CSP_APERCU})

    @app.post("/api/exercices/{ident}/decision")
    def decider(ident: str, corps: Decision):
        _charger(ident)
        if file.occupee_pour(ident):
            raise HTTPException(409, "une question de cet exercice est en cours de régénération : attendre la fin")
        try:
            instance = banque.decider(ident, corps.decision, corps.motif)
        except banque.ExerciceInconnu as e:
            raise HTTPException(404, str(e)) from None
        except banque.ExerciceFaux as e:
            raise HTTPException(409, str(e)) from None
        return {"resume": banque.resume(instance)}

    @app.post("/api/exercices/{ident}/questions/{numero}/regenerer", status_code=202)
    def regenerer(ident: str, numero: int, corps: Regeneration, request: Request):
        instance = _charger(ident)
        noms = classes.noms_des_eleves(base, request.state.compte)
        try:  # le motif de l'enseignant va au modèle : mêmes contrôles que sa phrase
            securite.controler_texte(securite.nettoyer(corps.motif), noms)
        except securite.DemandeRefusee as e:
            refuser_demande(request.state.compte, e.categorie, e.message)
        if not 1 <= numero <= len(instance.get("questions") or []):
            raise HTTPException(422, f"question {numero} inexistante")
        if file.occupee_pour(ident):
            raise HTTPException(409, "une question de cet exercice est déjà en cours de régénération")

        def executer(suivi):
            actuelle = banque.charger(ident)  # relu au moment du travail : une décision a pu passer entre-temps
            nouvelle = generation.regenerer_question(actuelle, numero, corps.motif, suivi=suivi, noms_proteges=noms)
            banque.ecrire(nouvelle)
            return {"exercice": ident, "question": numero}

        try:
            tache = file.soumettre("regeneration", f"Question {numero} — {instance.get('titre')}", executer, ident)
        except FilePleine as e:
            raise HTTPException(429, str(e)) from None
        return file.lire(tache.id)

    @app.put("/api/exercices/{ident}/questions/{numero}")
    def modifier(ident: str, numero: int, corps: Question):
        """La question corrigée à la main : enregistrée seulement si N2 → N4 l'acceptent ; sinon 422 et la liste
        des défauts, pour que l'enseignant corrige sa saisie."""
        _charger(ident)
        if file.occupee_pour(ident):
            raise HTTPException(409, "une question de cet exercice est en cours de régénération : attendre la fin")
        question = {"enonce": corps.enonce.strip(), "propositions": [p.strip() for p in corps.propositions],
                    "index_correct": corps.index_correct, "explication": corps.explication.strip(),
                    "difficulte": corps.difficulte}
        try:
            instance = banque.modifier_question(ident, numero, question)
        except banque.ExerciceInconnu as e:
            raise HTTPException(404, str(e)) from None
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        except ErreurValidation as e:
            raise HTTPException(422, f"modification refusée ({e.niveau}) : " + " ; ".join(e.erreurs)) from None
        return {"resume": banque.resume(instance)}

    @app.delete("/api/exercices/{ident}")
    def supprimer(ident: str):
        _charger(ident)
        if file.occupee_pour(ident):
            raise HTTPException(409, "une question de cet exercice est en cours de régénération : attendre la fin")
        try:
            banque.supprimer(ident)
        except banque.ExerciceInconnu as e:
            raise HTTPException(404, str(e)) from None
        except banque.SuppressionRefusee as e:
            raise HTTPException(409, str(e)) from None
        return {"supprime": ident}

    return app


app = creer_application()


def main() -> None:
    reglages = config.charger().get("interface") or {}
    parser = argparse.ArgumentParser(description="Interface enseignant : générer, relire et accepter des exercices.")
    parser.add_argument("--port", type=int, default=int(reglages.get("port", 8000)))
    parser.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir le navigateur")
    args = parser.parse_args()
    import uvicorn

    url = f"http://127.0.0.1:{args.port}/"
    print(f"Interface enseignant : {url}   (Ctrl-C pour arrêter)", flush=True)
    if not args.sans_navigateur:
        threading.Timer(1.5, webbrowser.open, (url,)).start()
    # toujours 127.0.0.1 : jamais une adresse joignable depuis le réseau de la salle (seul le serveur de
    # classe, application séparée et sans route enseignant, y sera ouvert : E8)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
