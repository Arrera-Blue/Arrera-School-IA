"""Interface enseignant (phase 3) : générer, relire et accepter un exercice, sans terminal.

    python -m generateur.interface.api                       # http://127.0.0.1:8000, ouvre le navigateur
    python -m generateur.interface.api --port 8001 --sans-navigateur

L'application n'écoute que sur 127.0.0.1 : elle n'a aucune authentification (architecture §11, §16). Elle
refuse aussi les requêtes qu'un autre site, ouvert dans le navigateur de l'enseignant, pourrait lui adresser
(voir `proteger`). L'aperçu d'un exercice tourne dans un bac à sable : ses scripts ne peuvent ni appeler
l'API, ni lire la page qui l'affiche.

Points d'entrée (plan-suite 3.2) :
    POST /api/analyser                               phrase → requête structurée, à confirmer
    POST /api/generations                            requête → tâche (file d'attente, une génération à la fois)
    GET  /api/generations[/{id}]                     avancement : en attente | en cours (étape, question) | …
    POST /api/generations/{id}/annuler               arrêter une génération ou une régénération
    GET  /api/exercices                              la banque, filtrée par matière, classe, statut, recherche
    GET  /api/exercices/{id}[/apercu|/telecharger]   l'exercice, sa relecture, son rendu HTML
    POST /api/exercices/{id}/decision                accepter | rejeter
    POST /api/exercices/{id}/questions/{n}/regenerer remplacer la question n (tâche)
    PUT  /api/exercices/{id}/questions/{n}           la question n corrigée à la main (revalidée N2 → N4)
    DELETE /api/exercices/{id}                       retirer l'exercice de la banque (déplacé dans banque/supprimes/)
"""

import argparse
import threading
import time
import traceback
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from generateur import procedural
from generateur.interface.taches import DejaFinie, File, FilePleine
from generateur.moteur import analyse, banque, config, generation, registre
from generateur.moteur.fournisseurs import ErreurFournisseur, llamacpp
from generateur.moteur.validation import ErreurValidation
from generateur.moteur.validation.fond import controler

STATIQUE = Path(__file__).with_name("statique")
HOTES = {"127.0.0.1", "localhost", "[::1]"}
METHODES_SURES = {"GET", "HEAD", "OPTIONS"}
# la page : ses propres scripts et styles seulement, aucune ressource extérieure (le PC enseignant peut être
# hors ligne), et l'aperçu ne peut venir que d'ici
CSP_PAGE = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "frame-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'")
# l'aperçu : la politique du gabarit, plus un bac à sable (origine opaque) même ouvert hors de l'iframe
CSP_APERCU = ("sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
              "img-src data:; frame-ancestors 'self'")


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
    mode: Literal["auto", "ia", "procedural"] = "auto"
    fournisseur: Literal["llamacpp", "ollama", "maquette"] | None = None


class Decision(BaseModel):
    decision: Literal["accepter", "rejeter"]
    motif: str | None = Field(None, max_length=500)


class Regeneration(BaseModel):
    motif: str | None = Field(None, max_length=500)  # le moteur n'en transmet que 200 au modèle


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
    if not (notion or phrase):
        raise HTTPException(422, "indiquer la notion, ou la demande de l'enseignant")
    demande = {"type": corps.type, "matiere": corps.matiere or None, "niveau": corps.niveau or None, "notion": notion,
               "nb_questions": corps.nb_questions, "difficulte": corps.difficulte, "demande_enseignant": phrase}
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


# --- l'application -------------------------------------------------------------------------------

def creer_application(file: File | None = None) -> FastAPI:
    reglages = config.charger().get("interface") or {}
    file = file or File(int(reglages.get("file_max", 5)), decrire_erreur)
    delai_dechargement_s = float(reglages.get("decharger_apres_min", 10)) * 60

    @asynccontextmanager
    async def cycle_de_vie(_app):
        """Pendant que le serveur tourne : décharger le modèle après un moment sans génération (3.3, C3)."""
        arret = threading.Event()
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

    @app.middleware("http")
    async def proteger(request: Request, call_next):
        """Sans authentification, la seule barrière est l'adresse 127.0.0.1. Deux attaques la contournent
        depuis le navigateur de l'enseignant, et sont refusées ici :
        - le « DNS rebinding » : un site dont le nom pointe soudain vers 127.0.0.1 → l'en-tête Host le trahit ;
        - la requête intersite : une page d'un autre site poste un formulaire vers 127.0.0.1 → l'en-tête Origin
          le trahit, et un formulaire ne peut pas envoyer de JSON sans demander la permission (CORS)."""
        hote = request.headers.get("host", "")
        if _hote(hote) not in HOTES:
            return PlainTextResponse("hôte refusé : l'interface ne répond qu'à 127.0.0.1", status_code=400)
        if request.method not in METHODES_SURES:
            origine = request.headers.get("origin")
            if origine is not None and origine != f"http://{hote}":
                return PlainTextResponse("origine refusée", status_code=403)
            if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                return PlainTextResponse("le corps de la requête doit être du JSON", status_code=415)
        reponse = await call_next(request)
        reponse.headers.setdefault("X-Content-Type-Options", "nosniff")
        reponse.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith(("/api/", "/statique/")):
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

    @app.post("/api/analyser")
    def analyser(corps: Phrase):
        """Règles d'abord ; le modèle complète la matière ou la notion s'il est libre (jamais pendant une
        génération : il ne sert qu'une demande à la fois)."""
        par_le_modele = bool(reglages.get("analyse_par_modele", True))
        pris = par_le_modele and file.modele.acquire(blocking=False)
        try:
            fournisseur = None
            if pris:
                try:
                    fournisseur = generation.creer_fournisseur()
                except ErreurFournisseur:
                    fournisseur = None
            resultat = analyse.analyser(corps.phrase, fournisseur).en_dict()
        finally:
            if pris:
                file.noter_activite()
                file.modele.release()
        if par_le_modele and not pris and {"matiere", "notion"} & set(resultat["a_verifier"]):
            resultat["remarques"].append("le modèle est occupé par une génération : analyse par les règles seules")
        resultat["procedural"] = _procedural(resultat["requete"])
        return resultat

    @app.post("/api/generations", status_code=202)
    def lancer(corps: Demande):
        demande = _verifier(corps)
        sujet = demande.get("notion") or demande.get("demande_enseignant", "")[:60]
        description = f"{corps.type.upper()} — {sujet}" + (f" ({demande['niveau']})" if demande.get("niveau") else "")

        def executer(suivi):
            instance = generation.generer(demande, corps.type, corps.fournisseur, corps.mode, suivi=suivi)
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
                  recherche: str | None = None):
        return {"exercices": banque.lister(matiere or None, niveau or None, statut or None, (recherche or "")[:200])}

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
    def regenerer(ident: str, numero: int, corps: Regeneration):
        instance = _charger(ident)
        if not 1 <= numero <= len(instance.get("questions") or []):
            raise HTTPException(422, f"question {numero} inexistante")
        if file.occupee_pour(ident):
            raise HTTPException(409, "une question de cet exercice est déjà en cours de régénération")

        def executer(suivi):
            actuelle = banque.charger(ident)  # relu au moment du travail : une décision a pu passer entre-temps
            nouvelle = generation.regenerer_question(actuelle, numero, corps.motif, suivi=suivi)
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
    # toujours 127.0.0.1 : jamais une adresse joignable depuis le réseau de la salle (aucune authentification)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
