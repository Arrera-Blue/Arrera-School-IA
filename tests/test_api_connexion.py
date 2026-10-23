"""E1 : la connexion à l'interface enseignant, vue de l'extérieur — les tests d'attaque du jalon S
(docs/etapes/etape-E1-securite.md : SEC-4 à SEC-11, menaces M1 à M6, M22, M25)."""

import sqlite3
import warnings

import pytest

from generateur.donnees import comptes, sessions
from generateur.interface.api import COOKIE, PUBLIQUES, creer_application, entretenir
from generateur.interface.taches import File
from generateur.moteur import config

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

ADMIN = {"identifiant": "prof", "mot_de_passe": "le mot de passe de l'admin"}
ENSEIGNANT = {"identifiant": "a.martin", "mot_de_passe": "le mot de passe d'Alice"}


@pytest.fixture
def app(tmp_path, monkeypatch):
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    return creer_application(File())


def client(app) -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.fixture
def avec_comptes(app):
    comptes.creer(app.state.base, ADMIN["identifiant"], "Administrateur", ADMIN["mot_de_passe"], "admin")
    comptes.creer(app.state.base, ENSEIGNANT["identifiant"], "A. Martin", ENSEIGNANT["mot_de_passe"])
    return app


def connecte(app, identifiants=ADMIN) -> TestClient:
    c = client(app)
    r = c.post("/api/session", json=identifiants)
    assert r.status_code == 200, r.text
    return c


def routes_api(app) -> list[tuple[str, str]]:
    """Toutes les routes /api/ déclarées, avec des valeurs d'exemple pour les paramètres de chemin."""
    trouvees = []
    for route in app.routes:
        chemin = getattr(route, "path", "")
        if chemin.startswith("/api/"):
            exemple = chemin.replace("{ident}", "qcm-x-6e-20261020-100000").replace("{numero}", "1")
            exemple = exemple.replace("{identifiant}", "prof").replace("{classe_id}", "1").replace("{eleve_id}", "1")
            trouvees += [(methode, exemple) for methode in getattr(route, "methods", {"GET"}) if methode != "HEAD"]
    return trouvees


# --- refus par défaut (SEC-8) ---------------------------------------------------------------------

def test_toute_l_api_exige_une_session(avec_comptes):
    """Chaque route /api/ que l'application déclare — y compris une route ajoutée plus tard et oubliée —
    répond 401 sans session ; seule la connexion est ouverte."""
    c = client(avec_comptes)
    routes = routes_api(avec_comptes)
    assert len(routes) >= 20 and ("POST", "/api/session") in routes
    for methode, chemin in routes:
        if (methode, chemin) in PUBLIQUES:
            continue
        r = c.request(methode, chemin, json={} if methode != "GET" else None)
        assert r.status_code == 401, (methode, chemin, r.status_code)
        assert r.json() == {"detail": "connexion requise", "sans_compte": False}


def test_la_page_reste_publique(avec_comptes):
    c = client(avec_comptes)
    assert c.get("/").status_code == 200 and c.get("/statique/app.js").status_code == 200


def test_sans_aucun_compte(app):
    """Premier lancement : rien n'est ouvert ; l'interface dit de créer le compte en ligne de commande (M25)."""
    r = client(app).get("/api/session")
    assert r.status_code == 401 and r.json()["sans_compte"] is True
    assert client(app).post("/api/session", json=ADMIN).status_code == 401


# --- se connecter (SEC-5 à SEC-7) -----------------------------------------------------------------

def test_cookie_de_session(avec_comptes):
    c = client(avec_comptes)
    r = c.post("/api/session", json=ADMIN)
    assert r.json()["compte"]["identifiant"] == "prof" and r.json()["compte"]["role"] == "admin"
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=") and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Path=/" in cookie and "Max-Age" not in cookie and "expires" not in cookie.lower()  # cookie de session
    assert ADMIN["mot_de_passe"] not in r.text
    assert c.get("/api/session").json()["compte"]["nom"] == "Administrateur"


def test_echecs(avec_comptes):
    c = client(avec_comptes)
    inconnu = c.post("/api/session", json={"identifiant": "personne", "mot_de_passe": "x"})
    mauvais = c.post("/api/session", json={**ADMIN, "mot_de_passe": "mauvais"})
    assert inconnu.status_code == mauvais.status_code == 401
    assert inconnu.json() == mauvais.json() == {"detail": sessions.MESSAGE}
    assert "set-cookie" not in mauvais.headers


def test_force_brute_verrouillee(avec_comptes):
    c = client(avec_comptes)
    codes = [c.post("/api/session", json={**ADMIN, "mot_de_passe": f"essai {i}"}).status_code for i in range(5)]
    assert codes == [401, 401, 401, 401, 429]
    r = c.post("/api/session", json=ADMIN)  # le bon mot de passe, au 6e essai
    assert r.status_code == 429 and "15 min" in r.json()["detail"]
    assert connecte(avec_comptes, ENSEIGNANT)  # les autres comptes ne sont pas touchés


def test_injection_sql_sans_effet(avec_comptes):
    c = client(avec_comptes)
    for identifiant in ("' OR 1=1 --", "prof' --", "prof'; DROP TABLE enseignant; --"):
        r = c.post("/api/session", json={"identifiant": identifiant, "mot_de_passe": "' OR '1'='1"})
        assert r.status_code == 401, identifiant
    assert len(comptes.lister(avec_comptes.state.base)) == 2


def test_nouveau_jeton_a_chaque_connexion(avec_comptes):
    """Pas de fixation de session (M3) : se reconnecter tue le jeton précédent du navigateur."""
    c = connecte(avec_comptes)
    ancien = c.cookies.get(COOKIE)
    assert c.post("/api/session", json=ADMIN).status_code == 200
    assert c.cookies.get(COOKIE) != ancien
    voleur = client(avec_comptes)
    voleur.cookies.set(COOKIE, ancien)
    assert voleur.get("/api/session").status_code == 401


def test_cookie_vole_inutile_apres_deconnexion(avec_comptes):
    c = connecte(avec_comptes)
    jeton = c.cookies.get(COOKIE)
    voleur = client(avec_comptes)
    voleur.cookies.set(COOKIE, jeton)
    assert voleur.get("/api/exercices").status_code == 200  # avant : le cookie suffit…
    r = c.delete("/api/session", headers={"Content-Type": "application/json"})
    assert r.status_code == 200 and r.json() == {"deconnecte": True}
    assert voleur.get("/api/exercices").status_code == 401  # … après la déconnexion, plus rien
    assert c.get("/api/session").status_code == 401


def test_session_expiree(avec_comptes, monkeypatch):
    c = connecte(avec_comptes)
    monkeypatch.setattr(sessions, "INACTIVITE_S", -1)
    assert c.get("/api/exercices").status_code == 401


# --- mot de passe provisoire, comptes, administrateurs ---------------------------------------------

def test_mot_de_passe_provisoire_a_changer_d_abord(avec_comptes):
    admin = connecte(avec_comptes)
    r = admin.post("/api/comptes", json={"identifiant": "b.durand", "nom": "B. Durand",
                                         "mot_de_passe": ADMIN["mot_de_passe"]})
    assert r.status_code == 201 and r.json()["compte"]["doit_changer"] is True
    provisoire = r.json()["mot_de_passe_provisoire"]
    nouveau = connecte(avec_comptes, {"identifiant": "b.durand", "mot_de_passe": provisoire})
    bloque = nouveau.get("/api/exercices")
    assert bloque.status_code == 403 and bloque.json()["doit_changer"] is True
    assert nouveau.get("/api/session").json()["compte"]["doit_changer"] is True
    trop_court = nouveau.post("/api/session/mot-de-passe", json={"ancien": provisoire, "nouveau": "court"})
    assert trop_court.status_code == 422 and "trop court" in trop_court.json()["detail"]
    faux = nouveau.post("/api/session/mot-de-passe", json={"ancien": "faux", "nouveau": "mon mot de passe à moi"})
    assert faux.status_code == 403
    ok = nouveau.post("/api/session/mot-de-passe", json={"ancien": provisoire, "nouveau": "mon mot de passe à moi"})
    assert ok.status_code == 200 and ok.json()["compte"]["doit_changer"] is False
    assert nouveau.get("/api/exercices").status_code == 200  # la session en cours continue


def test_reserve_aux_administrateurs(avec_comptes):
    enseignant = connecte(avec_comptes, ENSEIGNANT)
    confirmation = {"mot_de_passe": ENSEIGNANT["mot_de_passe"]}
    for methode, chemin, corps in [("GET", "/api/comptes", None), ("GET", "/api/journal", None),
                                   ("POST", "/api/comptes", {"identifiant": "x.y", "nom": "X", **confirmation}),
                                   ("POST", "/api/comptes/prof/reinitialiser", confirmation),
                                   ("POST", "/api/comptes/prof/debloquer", {}),
                                   ("DELETE", "/api/comptes/prof", confirmation)]:
        r = enseignant.request(methode, chemin, json=corps)
        assert r.status_code == 403 and r.json()["detail"] == "réservé aux administrateurs", (methode, chemin)
    assert enseignant.get("/api/exercices").status_code == 200


def test_actions_sensibles_redemandent_le_mot_de_passe(avec_comptes):
    """⚖1 : un élève devant une session d'administrateur restée ouverte ne peut rien faire aux comptes."""
    admin = connecte(avec_comptes)
    faux = {"mot_de_passe": "pas le bon"}
    assert admin.post("/api/comptes", json={"identifiant": "x.y", "nom": "X", **faux}).status_code == 403
    assert admin.post("/api/comptes/a.martin/reinitialiser", json=faux).status_code == 403
    assert admin.request("DELETE", "/api/comptes/a.martin", json=faux).status_code == 403
    assert len(comptes.lister(avec_comptes.state.base)) == 2
    bon = {"mot_de_passe": ADMIN["mot_de_passe"]}
    r = admin.post("/api/comptes/a.martin/reinitialiser", json=bon)
    assert r.status_code == 200 and len(r.json()["mot_de_passe_provisoire"]) == 19
    assert admin.request("DELETE", "/api/comptes/a.martin", json=bon).status_code == 200
    assert admin.request("DELETE", "/api/comptes/a.martin", json=bon).status_code == 404


def test_pas_sur_son_propre_compte(avec_comptes):
    admin = connecte(avec_comptes)
    bon = {"mot_de_passe": ADMIN["mot_de_passe"]}
    assert admin.request("DELETE", "/api/comptes/prof", json=bon).status_code == 409
    assert admin.post("/api/comptes/PROF/reinitialiser", json=bon).status_code == 409


def test_debloquer_et_lister(avec_comptes):
    c = client(avec_comptes)
    for i in range(5):
        c.post("/api/session", json={**ENSEIGNANT, "mot_de_passe": f"essai {i}"})
    admin = connecte(avec_comptes)
    etats = {x["identifiant"]: x["verrouille"] for x in admin.get("/api/comptes").json()["comptes"]}
    assert etats == {"a.martin": True, "prof": False}
    assert admin.post("/api/comptes/a.martin/debloquer", json={}).status_code == 200
    assert connecte(avec_comptes, ENSEIGNANT)


def test_journal_lisible_par_l_admin(avec_comptes):
    client(avec_comptes).post("/api/session", json={**ENSEIGNANT, "mot_de_passe": "mauvais"})
    admin = connecte(avec_comptes)
    actions = [e["action"] for e in admin.get("/api/journal").json()["journal"]]
    assert actions[:2] == ["connexion", "echec_connexion"]


# --- ce qui ne doit fuir nulle part (SEC-10, SEC-11, M22) -----------------------------------------

def test_en_tetes_de_securite(avec_comptes):
    c = connecte(avec_comptes)
    for r in (c.get("/api/session"), client(avec_comptes).get("/api/exercices")):
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"


def test_un_mot_de_passe_essaye_n_apparait_nulle_part(avec_comptes, tmp_path, capfd):
    secret = "secret-tape-par-erreur-2026"
    c = client(avec_comptes)
    c.post("/api/session", json={"identifiant": secret, "mot_de_passe": "x"})  # dans le champ identifiant
    c.post("/api/session", json={**ADMIN, "mot_de_passe": secret})
    admin = connecte(avec_comptes)
    admin.post("/api/comptes", json={"identifiant": "x.y", "nom": "X", "mot_de_passe": secret})
    sortie = capfd.readouterr()
    assert secret not in sortie.out + sortie.err
    assert secret not in admin.get("/api/journal").text
    contenu = b"".join(f.read_bytes() for f in tmp_path.glob("base*"))
    assert contenu and secret.encode() not in contenu


def test_entretien_sauvegarde_et_purge(avec_comptes, tmp_path):
    base = avec_comptes.state.base
    with base.ecrire() as conn:
        conn.execute("INSERT INTO journal (date, action) VALUES (?, ?)", ("2020-01-01T00:00:00", "tres_ancien"))
    entretenir(base, tmp_path / "sauvegardes")
    copies = list((tmp_path / "sauvegardes").glob("base-*.sqlite3"))
    assert len(copies) == 1
    assert sqlite3.connect(copies[0]).execute("SELECT COUNT(*) FROM enseignant").fetchone()[0] == 2
    with base.lire() as conn:
        assert conn.execute("SELECT COUNT(*) FROM journal WHERE action = 'tres_ancien'").fetchone()[0] == 0
