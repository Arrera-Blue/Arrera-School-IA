"""Le serveur de classe (évolution E8) : la porte des élèves, sur le PC enseignant.

    python -m generateur.classe            (réglages : config.yaml, section `classe`)

Une application **séparée** de l'interface enseignant, **sans aucune route enseignant** : une faille côté élève ne
donne accès ni à la génération, ni à la banque, ni au suivi. Elle écoute l'interface réseau de la salle (jamais
`0.0.0.0` par défaut), en HTTPS avec le certificat de la salle (étape 3).

L'élève choisit sa classe, son nom, tape son code (connexion_eleve.py) ; il voit son accueil (publications.py) ; il
ouvre un exercice, servi **sans les bonnes réponses ni les explications** ; chaque réponse est envoyée au serveur,
qui la recalcule, l'enregistre (suivi.py) et renvoie le verdict avec l'explication (⚖4). Rien dans le stockage du
navigateur (postes partagés) : un cookie de session `HttpOnly`, 10 minutes sans activité.
"""

import argparse
import ipaddress
import socket
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from generateur.donnees import classes, codes, connexion_eleve, images, publications, suivi
from generateur.donnees.base import Base
from generateur.moteur import banque, config, lecture, rendu

ICI = Path(__file__).parent
STATIQUE = ICI / "statique"
POLICES = config.RACINE / "generateur" / "types" / "qcm" / "polices"
IMAGES_CODES = config.RACINE / "generateur" / "interface" / "statique" / "codes"
COOKIE = "eleve"
METHODES_SURES = {"GET", "HEAD", "OPTIONS"}
# sans session : l'écran de connexion et ce qu'il lit ; tout le reste de l'API la demande (refus par défaut)
PUBLIQUES = {("GET", "/api/classes"), ("POST", "/api/session")}
# la page de connexion et d'accueil : ses scripts, styles, polices et images ; ne parle qu'à ce serveur
CSP_PAGE = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; "
            "form-action 'none'; base-uri 'none'; frame-ancestors 'none'")
# la page d'un exercice : celle du gabarit, plus l'envoi des réponses à ce serveur
CSP_EXERCICE = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; media-src data:; "
                "font-src data:; connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'")
ENTRETIEN_S = 600


class Connexion(BaseModel):
    eleve: int = Field(ge=1)
    code: list[str] | str = Field(max_length=100)  # 4 noms d'images (CP à 6e), ou le mot de passe (5e à 3e)


class Reponse(BaseModel):
    tentative: int | None = Field(None, ge=1)  # vide : la première réponse ouvre la tentative
    question: int = Field(ge=1, le=50)
    choix: int = Field(ge=0, le=9)
    temps: float | None = Field(None, ge=0, le=3600)


def reglages() -> dict:
    return {"adresse": "127.0.0.1", "port": 8001, "hotes": ["classe.local"], "certificat": None, "cle_privee": None,
            **(config.charger().get("classe") or {})}


def _hote(entete: str) -> str:
    """« 192.168.1.20:8001 » → « 192.168.1.20 » ; « [::1]:8001 » → « [::1] »."""
    if entete.startswith("["):
        return entete.split("]")[0] + "]"
    return entete.rsplit(":", 1)[0] if ":" in entete else entete


def hotes_acceptes(r: dict) -> set[str]:
    """Les noms sous lesquels le serveur répond : son adresse, les noms de la configuration, et 127.0.0.1 pour
    l'essai sur le PC lui-même. Un autre nom (« DNS rebinding ») est refusé."""
    adresse = r["adresse"]
    return {adresse, f"[{adresse}]" if ":" in adresse else adresse, "127.0.0.1", "localhost", *r.get("hotes", [])}


def adresse_publique(r: dict) -> str:
    """L'adresse à donner aux élèves, d'après les réglages : http(s)://adresse:port."""
    adresse = f"[{r['adresse']}]" if ":" in r["adresse"] else r["adresse"]
    return f"{'https' if r.get('certificat') else 'http'}://{adresse}:{int(r['port'])}"


def etat(r: dict | None = None, delai_s: float = 0.3) -> dict:
    """Pour l'interface enseignant : le serveur de classe répond-il ? (une connexion TCP, rien de plus)"""
    r = r or reglages()
    hote = "127.0.0.1" if r["adresse"] in ("0.0.0.0", "::") else r["adresse"]
    try:
        with socket.create_connection((hote, int(r["port"])), timeout=delai_s):
            en_marche = True
    except OSError:
        en_marche = False
    return {"en_marche": en_marche, "adresse": adresse_publique(r), "https": bool(r.get("certificat"))}


def _entretenir(base: Base, arret: threading.Event) -> None:
    while not arret.wait(ENTRETIEN_S):
        try:
            connexion_eleve.purger(base)
        except Exception as e:  # l'entretien ne doit jamais arrêter le serveur
            print(f"entretien du serveur de classe : {e}", flush=True)


def creer_application(base: Base | None = None, cle: bytes | None = None, r: dict | None = None) -> FastAPI:
    r = r or reglages()
    base = base or Base(config.chemin("base"))
    cle = cle or codes.cle_secrete(config.chemin("cle_codes"))
    hotes = hotes_acceptes(r)
    https = bool(r.get("certificat"))
    schema = "https" if https else "http"

    @asynccontextmanager
    async def cycle_de_vie(_app):
        arret = threading.Event()
        base.preparer()
        threading.Thread(target=_entretenir, args=(base, arret), name="entretien-classe", daemon=True).start()
        yield
        arret.set()

    # ni /docs ni /openapi.json : rien à décrire aux postes des élèves
    app = FastAPI(lifespan=cycle_de_vie, title="Serveur de classe", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.base = base

    async def refuser(request: Request) -> Response | None:
        """Comme l'interface enseignant : le Host (DNS rebinding), l'Origin et le JSON seul (requête intersite), puis
        la session de l'élève sur toute l'API sauf la connexion (refus par défaut)."""
        hote = request.headers.get("host", "")
        if _hote(hote) not in hotes:
            return PlainTextResponse("hôte refusé", status_code=400)
        if request.method not in METHODES_SURES:
            origine = request.headers.get("origin")
            if origine is not None and origine != f"{schema}://{hote}":
                return PlainTextResponse("origine refusée", status_code=403)
            if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                return PlainTextResponse("le corps de la requête doit être du JSON", status_code=415)
        chemin = request.url.path
        route = (request.method, chemin)
        public = route in PUBLIQUES or (request.method == "GET" and chemin.startswith("/api/classes/") and chemin.endswith("/eleves"))
        if not (chemin.startswith("/api/") or chemin.startswith("/exercice/")) or public:
            return None
        eleve = await run_in_threadpool(connexion_eleve.session, base, request.cookies.get(COOKIE))
        if eleve is None:
            if chemin.startswith("/exercice/"):
                return Response(status_code=303, headers={"Location": "/"})
            return JSONResponse({"detail": "connexion requise"}, status_code=401)
        request.state.eleve = eleve
        return None

    @app.middleware("http")
    async def proteger(request: Request, call_next):
        reponse = await refuser(request) or await call_next(request)
        reponse.headers.setdefault("X-Content-Type-Options", "nosniff")
        reponse.headers.setdefault("Referrer-Policy", "no-referrer")
        reponse.headers.setdefault("Cache-Control", "no-store" if not request.url.path.startswith(("/statique/", "/polices/", "/codes/")) else "no-cache")
        if https:
            reponse.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return reponse

    @app.get("/", include_in_schema=False)
    def page():
        return FileResponse(STATIQUE / "index.html", media_type="text/html", headers={"Content-Security-Policy": CSP_PAGE})

    @app.get("/favicon.ico", include_in_schema=False)
    def icone():
        return Response(status_code=204)

    app.mount("/statique", StaticFiles(directory=STATIQUE), name="statique")
    app.mount("/polices", StaticFiles(directory=POLICES), name="polices")
    app.mount("/codes", StaticFiles(directory=IMAGES_CODES), name="codes")

    # --- se connecter -------------------------------------------------------------------------------

    @app.get("/api/classes")
    def lister_classes():
        return {"classes": connexion_eleve.classes_ouvertes(base)}

    @app.get("/api/classes/{classe_id}/eleves")
    def lister_eleves(classe_id: int):
        try:
            vue = connexion_eleve.eleves_de_la_classe(base, classe_id)
        except connexion_eleve.Introuvable:
            raise HTTPException(404, "classe introuvable") from None
        # les 12 images du clavier de code (du CP à la 6e), dans l'ordre des cartes
        return {**vue, "images": [{"image": i, "nom": n} for i, n in images.IMAGES]}

    @app.post("/api/session")
    def se_connecter(corps: Connexion, request: Request, response: Response):
        connexion_eleve.deconnecter(base, request.cookies.get(COOKIE))
        try:
            jeton, eleve = connexion_eleve.connecter(base, corps.eleve, corps.code, cle)
        except connexion_eleve.EleveBloque as e:
            return JSONResponse({"detail": str(e), "bloque": True, "restants": 0}, status_code=423)
        except connexion_eleve.ConnexionRefusee as e:
            return JSONResponse({"detail": str(e), "bloque": False, "restants": e.restants}, status_code=401)
        except connexion_eleve.Introuvable:
            raise HTTPException(404, "élève introuvable") from None
        response.set_cookie(COOKIE, jeton, httponly=True, samesite="strict", secure=https, path="/")
        return {"eleve": eleve}

    @app.get("/api/session")
    def qui_suis_je(request: Request):
        return {"eleve": request.state.eleve}

    @app.delete("/api/session")
    def se_deconnecter(request: Request, response: Response):
        connexion_eleve.deconnecter(base, request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict", secure=https)
        return {"ok": True}

    # --- l'accueil, les exercices ---------------------------------------------------------------------

    @app.get("/api/accueil")
    def accueil(request: Request):
        return {"eleve": request.state.eleve, **publications.pour_l_eleve(base, request.state.eleve)}

    def _exercice(request: Request, ident: str) -> dict:
        """L'exercice, s'il est sur l'accueil de l'élève ; sinon « introuvable » (qu'il existe ou non)."""
        try:
            banque.chemin(ident)  # refuse un identifiant mal formé (« ../ »…)
        except banque.ExerciceInconnu:
            raise HTTPException(404, "exercice introuvable") from None
        if not publications.autorise(base, request.state.eleve, ident):
            raise HTTPException(404, "exercice introuvable")
        return banque.charger(ident)

    @app.get("/exercice/{ident}", include_in_schema=False)
    def exercice(ident: str, request: Request):
        instance = _exercice(request, ident)
        html = rendu.rendre(instance, instance.get("type", "qcm"), mode="classe")
        return HTMLResponse(html, headers={"Content-Security-Policy": CSP_EXERCICE})

    @app.post("/api/exercices/{ident}/reponses")
    def repondre(ident: str, corps: Reponse, request: Request):
        instance = _exercice(request, ident)
        eleve = request.state.eleve
        try:
            verdict = suivi.repondre(base, eleve["id"], corps.tentative, instance, corps.question, corps.choix, corps.temps)
        except classes.Introuvable:
            raise HTTPException(404, "tentative introuvable") from None
        except classes.ClasseInvalide as e:
            raise HTTPException(422, str(e)) from None
        explication = instance["questions"][corps.question - 1]["explication"]
        return {**verdict, "explication": explication, "voix": lecture.morceau_base64(explication)}

    return app


def verifier_adresse(adresse: str, forcer: bool) -> None:
    """Jamais toutes les interfaces par défaut : le serveur écoute le réseau de la salle, pas internet."""
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        raise SystemExit(f"adresse invalide : {adresse} (l'adresse IP du PC enseignant sur le réseau de la salle)") from None
    if ip.is_unspecified and not forcer:
        raise SystemExit("refusé : 0.0.0.0 ouvrirait le serveur sur toutes les interfaces du PC ; donnez l'adresse du PC "
                         "sur le réseau de la salle (ou --toutes-les-interfaces, en connaissance de cause)")


def main() -> None:
    r = reglages()
    parser = argparse.ArgumentParser(description="Serveur de classe : la connexion des élèves et leurs exercices.")
    parser.add_argument("--adresse", default=r["adresse"], help="l'adresse IP du PC enseignant sur le réseau de la salle")
    parser.add_argument("--port", type=int, default=int(r["port"]))
    parser.add_argument("--toutes-les-interfaces", action="store_true", help="accepter 0.0.0.0 (déconseillé)")
    args = parser.parse_args()
    verifier_adresse(args.adresse, args.toutes_les_interfaces)
    r = {**r, "adresse": args.adresse, "port": args.port}
    import uvicorn

    https = bool(r.get("certificat"))
    options = {}
    if https:
        options = {"ssl_certfile": str(config.RACINE / r["certificat"]), "ssl_keyfile": str(config.RACINE / r["cle_privee"])}
    print(f"Serveur de classe : {adresse_publique(r)}/   (Ctrl-C pour arrêter)", flush=True)
    if not https:
        print("  sans HTTPS : pour un essai sur ce PC seulement ; en classe, le certificat de la salle (étape 3)", flush=True)
    uvicorn.run(creer_application(r=r), host=args.adresse, port=args.port, log_level="warning", **options)


if __name__ == "__main__":
    main()
