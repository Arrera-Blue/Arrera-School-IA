"""E8, le serveur de classe (generateur/classe/serveur.py) : connexion des élèves, accueil, exercice servi sans les
bonnes réponses, réponses recalculées ; tests d'attaque du plan (E8) : un « juste » forgé est recalculé, un élève ne
lit ni n'écrit les réponses d'un autre, aucune route enseignant, requête intersite refusée, code deviné → bloqué."""

import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from generateur.classe import serveur
from generateur.donnees import classes, comptes, connexion_eleve, publications, suivi
from generateur.donnees.base import Base
from generateur.moteur import banque, config, registre

CLE = b"k" * 32
REGLAGES = {"adresse": "192.168.1.20", "port": 8001, "hotes": ["classe.local", "testserver"], "certificat": None, "cle_privee": None}


@pytest.fixture
def monde(tmp_path, monkeypatch):
    """Une base, un enseignant, une 6e et une 4e, un exercice accepté publié pour la 6e, le serveur de classe."""
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    base = Base(tmp_path / "arrera.sqlite3")
    comptes.creer(base, "prof", "Professeur", "un mot de passe de test", "admin")
    prof = comptes.lire(base, "prof")
    sixieme, cartes6 = classes.creer(base, prof, "6e B", "6e", "2026-2027",
                                     [{"nom": "DUPONT", "prenom": "Marie"}, {"nom": "MARTIN", "prenom": "Lucas"}], CLE)
    quatrieme, cartes4 = classes.creer(base, prof, "4e A", "4e", "2026-2027", [{"nom": "DURAND", "prenom": "Jade"}], CLE)
    instance = json.loads(json.dumps(registre.charger("qcm").exemple))
    instance.update(titre="Pythagore en classe", niveau="6e")
    instance["meta"] = {"id": "qcm-classe-1", "statut": "accepte", "date": "2026-10-27T10:00:00"}
    banque.ecrire(instance)
    autre = dict(instance, titre="Non publié")
    autre["meta"] = {"id": "qcm-non-publie", "statut": "accepte", "date": "2026-10-27T10:00:00"}
    banque.ecrire(autre)
    publications.publier(base, prof, "qcm-classe-1", sixieme["id"])
    app = serveur.creer_application(base=base, cle=CLE, r=REGLAGES)
    return {"base": base, "prof": prof, "app": app, "sixieme": sixieme, "quatrieme": quatrieme, "cartes6": cartes6,
            "cartes4": cartes4, "instance": instance}


def client(monde):
    return TestClient(monde["app"])


def code(carte):
    return [i["image"] for i in carte["code"]] if carte["connexion"] == "images" else carte["mot_de_passe"]


def connecte(monde, carte):
    c = client(monde)
    r = c.post("/api/session", json={"eleve": carte["eleve_id"], "code": code(carte)})
    assert r.status_code == 200, r.text
    return c


# --- la page, la connexion ------------------------------------------------------------------------------------

def test_la_page_et_ses_protections(monde):
    r = client(monde).get("/")
    assert r.status_code == 200 and "Choisis ta classe" in r.text
    assert r.headers["content-security-policy"] == serveur.CSP_PAGE and "connect-src 'self'" in serveur.CSP_PAGE
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"
    for chemin in ("/statique/eleve.js", "/statique/eleve.css", "/polices/andika-400.woff2", "/codes/soleil.svg"):
        assert client(monde).get(chemin).status_code == 200, chemin
    assert not re.search(r"(src|href)\s*=\s*[\"'](https?:)?//", r.text)  # rien d'extérieur


def test_choisir_sa_classe_puis_son_nom(monde):
    c = client(monde)
    assert [x["nom"] for x in c.get("/api/classes").json()["classes"]] == ["4e A", "6e B"]
    vue = c.get(f"/api/classes/{monde['sixieme']['id']}/eleves").json()
    assert [e["nom"] for e in vue["eleves"]] == ["Lucas M.", "Marie D."] and vue["classe"]["connexion"] == "images"
    assert len(vue["images"]) == 12 and vue["images"][0] == {"image": "soleil", "nom": "soleil"}
    assert "DUPONT" not in json.dumps(vue)  # le nom de famille ne sort pas, seulement l'initiale (D6)
    assert c.get("/api/classes/999/eleves").status_code == 404


@pytest.mark.parametrize("niveau", ["sixieme", "quatrieme"])
def test_se_connecter_avec_sa_carte(monde, niveau):
    carte = monde["cartes6" if niveau == "sixieme" else "cartes4"][0]
    c = client(monde)
    r = c.post("/api/session", json={"eleve": carte["eleve_id"], "code": code(carte)})
    assert r.status_code == 200 and r.json()["eleve"]["prenom"] == carte["prenom"]
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/" in cookie
    assert c.get("/api/session").json()["eleve"]["id"] == carte["eleve_id"]
    c.request("DELETE", "/api/session", json={})
    assert c.get("/api/session").status_code == 401


def test_cinq_essais_puis_bloque(monde):
    carte = monde["cartes4"][0]
    c = client(monde)
    for restants in (4, 3, 2, 1):
        r = c.post("/api/session", json={"eleve": carte["eleve_id"], "code": "lion-vert-11"})
        assert r.status_code == 401 and r.json()["restants"] == restants and r.json()["bloque"] is False
    r = c.post("/api/session", json={"eleve": carte["eleve_id"], "code": "lion-vert-11"})
    assert r.status_code == 423 and r.json()["bloque"] is True
    assert c.post("/api/session", json={"eleve": carte["eleve_id"], "code": code(carte)}).status_code == 423
    classes.debloquer(monde["base"], monde["prof"], carte["eleve_id"])
    assert c.post("/api/session", json={"eleve": carte["eleve_id"], "code": code(carte)}).status_code == 200


@pytest.mark.parametrize("corps", [{}, {"eleve": 0, "code": "x"}, {"eleve": "1", "code": "x"}, {"eleve": 1, "code": 42},
                                   {"eleve": 1, "code": "x" * 101}, {"eleve": 1, "code": ["a"] * 101}])
def test_une_connexion_mal_formee_est_refusee(monde, corps):
    assert client(monde).post("/api/session", json=corps).status_code in (401, 404, 422)


# --- l'accueil, l'exercice --------------------------------------------------------------------------------------

def test_l_accueil_de_l_eleve(monde):
    c = connecte(monde, monde["cartes6"][0])
    accueil = c.get("/api/accueil").json()
    assert accueil["eleve"]["prenom"] == "Marie" and [x["exercice"] for x in accueil["exercices"]] == ["qcm-classe-1"]
    assert accueil["exercices"][0]["fait"] is None
    assert connecte(monde, monde["cartes4"][0]).get("/api/accueil").json()["exercices"] == []  # publié pour la 6e seulement


def test_l_exercice_est_servi_sans_les_bonnes_reponses(monde):
    c = connecte(monde, monde["cartes6"][0])
    r = c.get("/exercice/qcm-classe-1")
    assert r.status_code == 200 and r.headers["content-security-policy"] == serveur.CSP_EXERCICE
    html = r.text
    assert 'data-correct="' not in html and 'data-mode="classe"' in html and "connect-src 'self'" in html
    for q in monde["instance"]["questions"]:
        assert q["explication"] not in html  # l'explication dirait la réponse : elle reste au serveur
    assert '"exercice": "qcm-classe-1"' in html


def test_un_exercice_non_publie_ou_mal_nomme_est_introuvable(monde):
    c = connecte(monde, monde["cartes6"][0])
    for ident in ("qcm-non-publie", "qcm-absent", "..%2F..%2Fconfig", "A-MAJUSCULE"):
        assert c.get(f"/exercice/{ident}").status_code == 404, ident
        assert c.post(f"/api/exercices/{ident}/reponses", json={"question": 1, "choix": 0}).status_code == 404, ident
    autre = connecte(monde, monde["cartes4"][0])  # publié pour la 6e : pas pour un élève de 4e
    assert autre.get("/exercice/qcm-classe-1").status_code == 404


def test_sans_session_l_exercice_renvoie_a_la_connexion(monde):
    r = client(monde).get("/exercice/qcm-classe-1", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert client(monde).get("/api/accueil").status_code == 401
    assert client(monde).post("/api/exercices/qcm-classe-1/reponses", json={"question": 1, "choix": 0}).status_code == 401


# --- répondre ---------------------------------------------------------------------------------------------------

def test_les_reponses_sont_recalculees_par_le_serveur(monde):
    c = connecte(monde, monde["cartes6"][0])
    q1 = monde["instance"]["questions"][0]
    faux = (q1["index_correct"] + 1) % len(q1["propositions"])
    # un « juste » forgé par le navigateur n'a aucun effet : le serveur ne lit que la proposition choisie
    r = c.post("/api/exercices/qcm-classe-1/reponses", json={"question": 1, "choix": faux, "temps": 3.5, "juste": True})
    assert r.status_code == 200
    d = r.json()
    assert d["juste"] is False and d["correct"] == q1["index_correct"] and d["explication"] == q1["explication"]
    assert d["compte"] is True and d["voix"] is None  # pas de voix de Piper dans les tests
    r = c.post("/api/exercices/qcm-classe-1/reponses", json={"tentative": d["tentative"], "question": 2,
                                                            "choix": monde["instance"]["questions"][1]["index_correct"]})
    assert r.json()["juste"] is True and r.json()["tentative"] == d["tentative"]
    assert c.post("/api/exercices/qcm-classe-1/reponses",
                  json={"tentative": d["tentative"], "question": 2, "choix": 0}).status_code == 422  # déjà répondue
    for corps in ({"question": 99, "choix": 0}, {"question": 1, "choix": 9}, {"question": 1, "choix": -1},
                  {"question": 1, "choix": 0, "temps": 99999}, {"question": "un", "choix": 0}):
        assert c.post("/api/exercices/qcm-classe-1/reponses", json=corps).status_code == 422, corps
    # dans la base et dans le suivi de l'enseignant
    fiche = suivi.fiche(monde["base"], monde["prof"], monde["cartes6"][0]["eleve_id"])
    assert fiche["tentatives"][0]["origine"] == "classe" and fiche["tentatives"][0]["questions"] == 2
    assert c.get("/api/accueil").json()["exercices"][0]["fait"] == {"date": fiche["tentatives"][0]["date"], "justes": 1, "questions": 2}


def test_un_eleve_n_ecrit_pas_dans_la_tentative_d_un_autre(monde):
    marie = connecte(monde, monde["cartes6"][0])
    t = marie.post("/api/exercices/qcm-classe-1/reponses", json={"question": 1, "choix": 0}).json()["tentative"]
    lucas = connecte(monde, monde["cartes6"][1])
    assert lucas.post("/api/exercices/qcm-classe-1/reponses", json={"tentative": t, "question": 2, "choix": 0}).status_code == 404
    assert lucas.get("/api/accueil").json()["exercices"][0]["fait"] is None  # il ne voit pas le score de Marie


def test_une_premiere_reponse_refusee_n_ouvre_pas_de_tentative(monde):
    """Sinon une tentative vide « compterait » à la place de la vraie, qui deviendrait un entraînement."""
    c = connecte(monde, monde["cartes6"][0])
    assert c.post("/api/exercices/qcm-classe-1/reponses", json={"question": 99, "choix": 0}).status_code == 422
    with monde["base"].lire() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tentative").fetchone()[0] == 0
    assert c.post("/api/exercices/qcm-classe-1/reponses", json={"question": 1, "choix": 0}).json()["compte"] is True


def test_rejouer_est_un_entrainement(monde):
    c = connecte(monde, monde["cartes6"][0])
    premiere = c.post("/api/exercices/qcm-classe-1/reponses", json={"question": 1, "choix": 0}).json()
    seconde = c.post("/api/exercices/qcm-classe-1/reponses", json={"question": 1, "choix": 0}).json()
    assert premiere["compte"] is True and seconde["compte"] is False and seconde["tentative"] != premiere["tentative"]


# --- tests d'attaque : routes, origine, hôte ---------------------------------------------------------------------------

@pytest.mark.parametrize("methode, chemin", [
    ("GET", "/api/exercices"), ("GET", "/api/exercices/qcm-classe-1"), ("POST", "/api/generations"), ("GET", "/api/comptes"),
    ("GET", "/api/journal"), ("GET", "/api/classes/1"), ("GET", "/api/classes/1/suivi"), ("GET", "/api/eleves/1/suivi"),
    ("POST", "/api/classes"), ("GET", "/api/openapi.json"), ("GET", "/docs"), ("GET", "/api/exercices/qcm-classe-1/telecharger"),
])
def test_aucune_route_enseignant(monde, methode, chemin):
    c = connecte(monde, monde["cartes6"][0])
    r = c.request(methode, chemin, json={} if methode == "POST" else None)
    assert r.status_code in (404, 405), (chemin, r.status_code)


def test_une_requete_d_un_autre_site_est_refusee(monde):
    c = client(monde)
    carte = monde["cartes6"][0]
    corps = {"eleve": carte["eleve_id"], "code": code(carte)}
    assert c.post("/api/session", json=corps, headers={"Origin": "http://site-pirate.example"}).status_code == 403
    assert c.post("/api/session", content="eleve=1", headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 415
    assert c.post("/api/session", json=corps, headers={"Origin": "http://testserver"}).status_code == 200


@pytest.mark.parametrize("hote, attendu", [("192.168.1.20:8001", 200), ("classe.local", 200), ("127.0.0.1:8001", 200),
                                           ("site-pirate.example", 400), ("192.168.1.99", 400)])
def test_seuls_les_noms_du_serveur_sont_acceptes(monde, hote, attendu):
    assert client(monde).get("/api/classes", headers={"Host": hote}).status_code == attendu


def test_la_session_expire_apres_10_minutes(monde, monkeypatch):
    c = connecte(monde, monde["cartes6"][0])
    maintenant = time.time()
    monkeypatch.setattr(time, "time", lambda: maintenant + connexion_eleve.INACTIVITE_S + 5)
    assert c.get("/api/accueil").status_code == 401


def test_jamais_toutes_les_interfaces_par_defaut():
    with pytest.raises(SystemExit, match="0.0.0.0"):
        serveur.verifier_adresse("0.0.0.0", forcer=False)
    with pytest.raises(SystemExit, match="invalide"):
        serveur.verifier_adresse("classe.local", forcer=False)
    serveur.verifier_adresse("192.168.1.20", forcer=False)
    serveur.verifier_adresse("0.0.0.0", forcer=True)
