"""Phase 3 : l'interface enseignant (generateur/interface/) — file d'attente, points d'entrée, protections."""

import json
import threading
import warnings

import pytest

from generateur.donnees import comptes
from generateur.interface.taches import ANNULE, ECHEC, EN_ATTENTE, EN_COURS, TERMINE, DejaFinie, File, FilePleine
from generateur.moteur import config, generation, registre
from generateur.moteur.fournisseurs.base import Fournisseur

with warnings.catch_warnings():  # starlette signale que son client de test préférera bientôt httpx2
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from generateur.interface.api import CSP_APERCU, creer_application, decrire_erreur

NOUVELLE = {"enonce": "Dans un triangle rectangle, comment s'appelle le côté opposé à l'angle droit ?",
            "propositions": ["la médiane", "l'hypoténuse", "la hauteur"], "index_correct": 1,
            "explication": "Le côté opposé à l'angle droit est le plus long : c'est l'hypoténuse."}
MOT_DE_PASSE = "un mot de passe de test"
QCM_MAQUETTE = {"type": "qcm", "matiere": "maths", "niveau": "4e", "notion": "Pythagore", "fournisseur": "maquette",
                "mode": "ia"}


# --- la file d'attente -----------------------------------------------------------------------------

def test_une_tache_a_la_fois_dans_l_ordre():
    file = File()
    porte = threading.Event()
    ordre = []

    def premiere(suivi):
        suivi({"etape": "modele", "message": "lecture…"})
        suivi({"etape": "ecriture", "message": "écriture, question 1 sur 2…", "question": 1, "sur": 2})
        porte.wait(5)
        ordre.append(1)
        return {"exercice": "qcm-a-4e-20261013-100000"}

    a = file.soumettre("generation", "A", premiere)
    b = file.soumettre("generation", "B", lambda suivi: ordre.append(2) or {"exercice": "qcm-b-4e-20261013-100000"})
    for _ in range(100):
        if file.lire(a.id)["progression"].get("etape") == "ecriture":
            break
        threading.Event().wait(0.02)
    vue_a, vue_b = file.lire(a.id), file.lire(b.id)
    assert vue_a["etat"] == EN_COURS and vue_a["progression"]["question"] == 1
    assert [j["message"] for j in vue_a["journal"]] == ["lecture…"]  # l'écriture ne remplit pas le journal
    assert vue_b["etat"] == EN_ATTENTE and vue_b["devant"] == 1
    porte.set()
    assert file.attendre(b.id, 5)["etat"] == TERMINE and ordre == [1, 2]
    assert file.lire(a.id)["exercice"] == "qcm-a-4e-20261013-100000"


def test_un_echec_n_arrete_pas_la_file():
    file = File(decrire_erreur=decrire_erreur)

    def plante(suivi):
        raise RuntimeError("bogue")

    echec = file.soumettre("generation", "plante", plante)
    suivante = file.soumettre("generation", "ok", lambda suivi: {"exercice": "x"})
    vue = file.attendre(echec.id, 5)
    assert vue["etat"] == ECHEC and "RuntimeError" in vue["erreur"]["message"]
    assert file.attendre(suivante.id, 5)["etat"] == TERMINE


def test_la_file_survit_a_une_description_d_erreur_qui_echoue():
    def description_cassee(e):
        raise KeyError("bogue dans la description")

    file = File(decrire_erreur=description_cassee)
    echec = file.soumettre("generation", "plante", lambda suivi: 1 / 0)
    suivante = file.soumettre("generation", "ok", lambda suivi: {"exercice": "x"})
    assert file.attendre(echec.id, 5)["erreur"]["message"] == "Erreur inattendue (ZeroDivisionError)"
    assert file.attendre(suivante.id, 5)["etat"] == TERMINE


def test_file_pleine():
    file = File(taille_max=1)
    porte = threading.Event()
    file.soumettre("generation", "occupe", lambda suivi: porte.wait(5) and {})
    for _ in range(100):  # la première tâche quitte l'attente pour le travail
        if file.lister()[0]["etat"] == EN_COURS:
            break
        threading.Event().wait(0.02)
    file.soumettre("generation", "attend", lambda suivi: {})
    with pytest.raises(FilePleine):
        file.soumettre("generation", "de trop", lambda suivi: {})
    porte.set()


# --- l'application -------------------------------------------------------------------------------

class Modele(Fournisseur):
    """Le modèle des tests : l'exemple pour une génération, NOUVELLE pour une régénération, une matière et une
    notion pour l'analyse."""
    nom, modele = "faux", "faux-modele"

    def generer(self, messages, schema):
        proprietes = schema["properties"]
        if "questions" not in proprietes:
            return json.dumps({"matiere": "svt", "notion": "le cycle de l'eau"})
        if set(proprietes) == {"questions"}:
            return json.dumps({"questions": [NOUVELLE] * proprietes["questions"]["minItems"]})
        return json.dumps(registre.charger("qcm").exemple)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """L'interface, avec une base neuve dans tmp_path et un administrateur « prof » connecté (E1)."""
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    monkeypatch.setattr(generation, "creer", lambda nom, reglages: Modele())  # jamais le vrai modèle en test
    app = creer_application(File(decrire_erreur=decrire_erreur))
    comptes.creer(app.state.base, "prof", "Professeur Essai", MOT_DE_PASSE, "admin")
    c = TestClient(app, base_url="http://127.0.0.1:8000")
    c.file, c.base, c.app = app.state.file, app.state.base, app
    assert c.post("/api/session", json={"identifiant": "prof", "mot_de_passe": MOT_DE_PASSE}).status_code == 200
    return c


def generer(client, **demande) -> dict:
    tache = client.post("/api/generations", json={**QCM_MAQUETTE, **demande})
    assert tache.status_code == 202, tache.text
    return client.file.attendre(tache.json()["id"], 10)


def test_la_page_et_sa_politique_de_securite(client):
    page = client.get("/")
    assert page.status_code == 200 and "<title>Générateur d'exercices</title>" in page.text
    csp = page.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp
    assert client.get("/statique/app.js").status_code == 200
    assert client.get("/api/types").json()["types"][0]["niveaux"] == ["6e", "5e", "4e", "3e"]


def test_analyser(client):
    resultat = client.post("/api/analyser", json={"phrase": "un QCM sur les pourcentages pour des 5e"}).json()
    assert resultat["requete"]["matiere"] == "maths" and resultat["procedural"] == {"nom": "pourcentages",
                                                                                     "notion": "pourcentages"}
    complete = client.post("/api/analyser", json={"phrase": "un QCM sur le cycle de l'eau pour des 5e"}).json()
    assert complete["requete"]["matiere"] == "svt" and complete["sources"]["matiere"] == "modele"


def test_analyser_pendant_une_generation(client):
    # le modèle ne sert qu'une demande à la fois : l'analyse se contente des règles, et le dit
    with client.file.modele:
        resultat = client.post("/api/analyser", json={"phrase": "un QCM sur le cycle de l'eau pour des 5e"}).json()
    assert resultat["requete"]["matiere"] is None
    assert any("occupé" in r for r in resultat["remarques"])


def test_generer_relire_accepter(client):
    tache = generer(client)
    assert tache["etat"] == TERMINE and tache["journal"][0]["message"].startswith("Le modèle lit la demande")
    ident = tache["exercice"]
    vue = client.get(f"/api/exercices/{ident}").json()
    assert vue["resume"]["statut"] == "genere" and vue["occupe"] is False
    assert [q["n4"] for q in vue["relecture"]["questions"]] == ["a_relire", "verifie", "verifie"]
    apercu = client.get(f"/api/exercices/{ident}/apercu")
    assert apercu.headers["content-security-policy"] == CSP_APERCU and "Le théorème de Pythagore" in apercu.text
    fichier = client.get(f"/api/exercices/{ident}/telecharger")
    assert fichier.headers["content-disposition"] == f'attachment; filename="{ident}.html"'
    decision = client.post(f"/api/exercices/{ident}/decision", json={"decision": "accepter"})
    assert decision.json()["resume"]["statut"] == "accepte"
    assert [x["id"] for x in client.get("/api/exercices?statut=accepte").json()["exercices"]] == [ident]
    assert client.get("/api/exercices?statut=rejete").json()["exercices"] == []


def test_regenerer_une_question(client):
    ident = generer(client)["exercice"]
    client.post(f"/api/exercices/{ident}/decision", json={"decision": "accepter"})
    tache = client.post(f"/api/exercices/{ident}/questions/2/regenerer", json={"motif": "trop facile"})
    assert tache.status_code == 202 and tache.json()["exercice"] == ident
    assert client.file.attendre(tache.json()["id"], 10)["etat"] == TERMINE
    vue = client.get(f"/api/exercices/{ident}").json()
    assert vue["exercice"]["questions"][1] == NOUVELLE and vue["resume"]["statut"] == "genere"
    assert vue["relecture"]["questions"][1]["regeneree"] is True
    assert client.post(f"/api/exercices/{ident}/questions/9/regenerer", json={}).status_code == 422


def test_pas_de_decision_pendant_une_regeneration(client):
    ident = generer(client)["exercice"]
    with client.file.modele:  # le fil de travail attend le modèle : la régénération reste en cours
        tache = client.post(f"/api/exercices/{ident}/questions/1/regenerer", json={}).json()
        assert client.post(f"/api/exercices/{ident}/decision", json={"decision": "accepter"}).status_code == 409
        assert client.post(f"/api/exercices/{ident}/questions/2/regenerer", json={}).status_code == 409
        assert client.get(f"/api/exercices/{ident}").json()["occupe"] is True
    assert client.file.attendre(tache["id"], 10)["etat"] == TERMINE


def test_un_exercice_faux_ne_peut_pas_etre_accepte(client):
    ident = generer(client)["exercice"]
    fichier = config.chemin("banque") / f"{ident}.json"
    instance = json.loads(fichier.read_text(encoding="utf-8"))
    instance["questions"][1]["index_correct"] = 0  # une réponse fausse que le meta ne signale pas
    fichier.write_text(json.dumps(instance, ensure_ascii=False), encoding="utf-8")
    vue = client.get(f"/api/exercices/{ident}").json()
    assert vue["relecture"]["valide"] is False and vue["relecture"]["a_corriger"] == [2]
    assert vue["resume"]["a_corriger"] == 1
    refus = client.post(f"/api/exercices/{ident}/decision", json={"decision": "accepter"})
    assert refus.status_code == 409 and "à corriger" in refus.json()["detail"]
    tache = client.post(f"/api/exercices/{ident}/questions/2/regenerer", json={"motif": "x" * 500}).json()
    assert client.file.attendre(tache["id"], 10)["etat"] == TERMINE
    assert client.post(f"/api/exercices/{ident}/decision", json={"decision": "accepter"}).status_code == 200


def test_un_echec_est_explique(client):
    # la maquette écrit une 4e : une 5e demandée est refusée par N2, même après les reprises
    tache = generer(client, niveau="5e")
    assert tache["etat"] == ECHEC and tache["erreur"]["message"].startswith("Réponse du modèle refusée (N2)")
    assert tache["erreur"]["rejet"].endswith(".json") and tache["erreur"]["erreurs"]


@pytest.mark.parametrize("demande, message", [
    ({"matiere": "cuisine"}, "matiere « cuisine » inconnue"),
    ({"niveau": "CM2"}, "niveau « CM2 » inconnue"),
    ({"nb_questions": 40}, "de 3 à 15"),
    ({"notion": " ", "demande_enseignant": None}, "indiquer la notion"),
    ({"type": "dissertation"}, "type « dissertation » inconnu"),
])
def test_demandes_refusees(client, demande, message):
    reponse = client.post("/api/generations", json={**QCM_MAQUETTE, **demande})
    assert reponse.status_code == 422 and message in reponse.json()["detail"]


def test_inconnus(client):
    assert client.get("/api/generations/abc").status_code == 404
    assert client.get("/api/exercices/qcm-absent-4e-20261013-100000").status_code == 404
    assert client.get("/api/exercices/..%2Fconfig").status_code == 404
    assert client.get("/api/exercices/qcm-absent-4e-20261013-100000/apercu").status_code == 404


# --- les protections du navigateur : hôte, origine, JSON seul (la session : test_api_connexion.py) --

def test_dns_rebinding_refuse(client):
    # un site dont le nom pointe soudain vers 127.0.0.1 : son nom reste dans l'en-tête Host
    assert client.get("/api/exercices", headers={"host": "attaquant.example:8000"}).status_code == 400
    assert client.get("/", headers={"host": "localhost:8000"}).status_code == 200


def test_requete_d_un_autre_site_refusee(client):
    corps = {"phrase": "un QCM sur les fractions"}
    assert client.post("/api/analyser", json=corps, headers={"origin": "http://attaquant.example"}).status_code == 403
    assert client.post("/api/analyser", json=corps, headers={"origin": "http://127.0.0.1:8000"}).status_code == 200
    # un formulaire HTML ne peut pas envoyer de JSON sans demander la permission (CORS) : seul le JSON passe
    formulaire = client.post("/api/analyser", content="phrase=x",
                             headers={"content-type": "application/x-www-form-urlencoded"})
    assert formulaire.status_code == 415
    texte = client.post("/api/generations", content=json.dumps(QCM_MAQUETTE), headers={"content-type": "text/plain"})
    assert texte.status_code == 415


# --- modifier une question, rechercher, supprimer -----------------------------------------------------

HYPOTENUSE_6_8 = {"enonce": "Un triangle rectangle a pour côtés de l'angle droit 6 cm et 8 cm. Quelle est la longueur "
                            "de l'hypoténuse ?",
                  "propositions": [" 14 cm ", "10 cm", "48 cm"], "index_correct": 1,
                  "explication": "6² + 8² = 36 + 64 = 100, et 100 = 10², donc l'hypoténuse mesure 10 cm."}


def test_modifier_une_question(client):
    ident = generer(client)["exercice"]
    client.post(f"/api/exercices/{ident}/decision", json={"decision": "accepter"})
    reponse = client.put(f"/api/exercices/{ident}/questions/2", json=HYPOTENUSE_6_8)
    assert reponse.status_code == 200 and reponse.json()["resume"]["statut"] == "genere"
    vue = client.get(f"/api/exercices/{ident}").json()
    assert vue["exercice"]["questions"][1]["propositions"][0] == "14 cm"  # espaces retirés
    assert vue["relecture"]["questions"][1]["modifiee"] is True
    faux = client.put(f"/api/exercices/{ident}/questions/2", json={**HYPOTENUSE_6_8, "index_correct": 0})
    assert faux.status_code == 422 and faux.json()["detail"].startswith("modification refusée (N4)")
    trop_peu = client.put(f"/api/exercices/{ident}/questions/2", json={**HYPOTENUSE_6_8, "propositions": ["a", "b"]})
    assert trop_peu.status_code == 422 and "au moins 3" in trop_peu.json()["detail"]
    assert client.put(f"/api/exercices/{ident}/questions/9", json=HYPOTENUSE_6_8).status_code == 422
    # PUT est une requête qui modifie : mêmes protections que POST
    assert client.put(f"/api/exercices/{ident}/questions/2", content=json.dumps(HYPOTENUSE_6_8),
                      headers={"content-type": "text/plain"}).status_code == 415


def test_pas_de_modification_ni_de_suppression_pendant_une_regeneration(client):
    ident = generer(client)["exercice"]
    with client.file.modele:
        tache = client.post(f"/api/exercices/{ident}/questions/1/regenerer", json={}).json()
        assert client.put(f"/api/exercices/{ident}/questions/2", json=HYPOTENUSE_6_8).status_code == 409
        assert client.delete(f"/api/exercices/{ident}", headers={"content-type": "application/json"}).status_code == 409
    assert client.file.attendre(tache["id"], 10)["etat"] == TERMINE


def test_rechercher_et_supprimer(client):
    ident = generer(client)["exercice"]
    assert [x["id"] for x in client.get("/api/exercices?recherche=hypotenuse").json()["exercices"]] == [ident]
    assert client.get("/api/exercices?recherche=revolution").json()["exercices"] == []
    json_ = {"content-type": "application/json"}
    assert client.delete(f"/api/exercices/{ident}").status_code == 415  # sans en-tête JSON : refusée
    client.post(f"/api/exercices/{ident}/decision", json={"decision": "accepter"})
    refus = client.delete(f"/api/exercices/{ident}", headers=json_)
    assert refus.status_code == 409 and "rejeter" in refus.json()["detail"]
    client.post(f"/api/exercices/{ident}/decision", json={"decision": "rejeter"})
    assert client.delete(f"/api/exercices/{ident}", headers=json_).json() == {"supprime": ident}
    assert client.get(f"/api/exercices/{ident}").status_code == 404
    assert client.delete(f"/api/exercices/{ident}", headers=json_).status_code == 404


def test_pas_de_page_de_documentation_qui_charge_des_scripts_sur_internet(client):
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").json()["info"]["title"].startswith("Générateur d'exercices")


# --- annuler une génération (3.3, C5) ---------------------------------------------------------------

def test_annuler_une_tache_en_attente():
    file = File(decrire_erreur=decrire_erreur)
    porte = threading.Event()
    premiere = file.soumettre("generation", "occupe", lambda suivi: porte.wait(5) and {})
    lancee = []
    seconde = file.soumettre("generation", "attend", lambda suivi: lancee.append(1) or {})
    assert file.annuler(seconde.id)["etat"] == ANNULE
    porte.set()
    assert file.attendre(premiere.id, 5)["etat"] == TERMINE
    assert file.attendre(seconde.id, 5)["etat"] == ANNULE and lancee == []  # jamais exécutée
    with pytest.raises(DejaFinie):
        file.annuler(seconde.id)
    assert file.annuler("inconnue") is None


def test_annuler_une_tache_en_cours_au_prochain_signe_de_vie():
    file = File(decrire_erreur=decrire_erreur)
    demarree, apres = threading.Event(), []

    def longue(suivi):
        demarree.set()
        for i in range(500):  # comme llama.cpp, qui signale l'écriture au fil des morceaux
            suivi({"etape": "ecriture", "message": f"morceau {i}"})
            threading.Event().wait(0.01)
        apres.append("fin atteinte")
        return {"exercice": "x"}

    tache = file.soumettre("generation", "longue", longue)
    demarree.wait(5)
    vue = file.annuler(tache.id)
    assert vue["etat"] == EN_COURS and vue["annulation"] is True
    fin = file.attendre(tache.id, 5)
    assert fin["etat"] == ANNULE and fin["resultat"] is None and apres == []
    assert fin["journal"][-1]["message"] == "Annulée"
    assert file.soumettre("generation", "suivante", lambda suivi: {"exercice": "y"}).etat  # la file continue


def test_une_annulation_n_est_pas_arretee_par_un_except_exception():
    file = File(decrire_erreur=decrire_erreur)
    demarree = threading.Event()

    def avec_repli(suivi):
        demarree.set()
        for _ in range(500):
            try:  # un repli (habillage…) qui rattrape les erreurs ne doit pas avaler l'annulation
                suivi({"etape": "habillage", "message": "réécriture"})
            except Exception:
                pass
            threading.Event().wait(0.01)
        return {"exercice": "x"}

    tache = file.soumettre("generation", "repli", avec_repli)
    demarree.wait(5)
    file.annuler(tache.id)
    assert file.attendre(tache.id, 5)["etat"] == ANNULE


def test_annuler_par_l_api(client):
    ident = generer(client)["exercice"]
    avant = client.get(f"/api/exercices/{ident}").json()["exercice"]
    with client.file.modele:  # le fil de travail attend le modèle : la régénération n'a pas commencé son travail
        tache = client.post(f"/api/exercices/{ident}/questions/2/regenerer", json={}).json()
        vue = client.post(f"/api/generations/{tache['id']}/annuler", json={})
        assert vue.status_code == 200 and vue.json()["annulation"] is True
    assert client.file.attendre(tache["id"], 10)["etat"] == ANNULE
    assert client.get(f"/api/exercices/{ident}").json()["exercice"] == avant  # rien n'a changé
    assert client.post(f"/api/generations/{tache['id']}/annuler", json={}).status_code == 409
    assert client.post("/api/generations/inconnue/annuler", json={}).status_code == 404


# --- décharger le modèle après un moment sans génération (3.3, C3) -----------------------------------

class FauxLlama:
    fermes = 0

    def close(self):
        FauxLlama.fermes += 1


def test_decharger_le_modele_apres_inactivite(monkeypatch):
    from generateur.interface.api import decharger_si_inactif
    from generateur.moteur.fournisseurs import llamacpp
    monkeypatch.setattr(llamacpp, "_CHARGES", {("modele",): FauxLlama()})
    file = File()
    file.derniere_activite = 1000.0
    assert not decharger_si_inactif(file, 600, maintenant=1300.0)  # 5 min seulement
    with file.modele:  # une génération ou une analyse en cours
        assert not decharger_si_inactif(file, 600, maintenant=2000.0)
    assert not decharger_si_inactif(file, 0, maintenant=2000.0)  # 0 : jamais
    assert decharger_si_inactif(file, 600, maintenant=2000.0)
    assert llamacpp._CHARGES == {} and FauxLlama.fermes == 1
    assert not decharger_si_inactif(file, 600, maintenant=3000.0)  # rien à décharger


def test_pas_de_dechargement_si_une_tache_attend(monkeypatch):
    from generateur.interface.api import decharger_si_inactif
    from generateur.moteur.fournisseurs import llamacpp
    monkeypatch.setattr(llamacpp, "_CHARGES", {("modele",): FauxLlama()})
    file = File()
    porte = threading.Event()
    file.soumettre("generation", "attend", lambda suivi: porte.wait(5) and {})
    file.derniere_activite = 0.0
    try:
        assert not decharger_si_inactif(file, 600, maintenant=10_000.0)
    finally:
        porte.set()


# --- le programme officiel (E2) ----------------------------------------------------------------------

def test_programmes_pour_le_formulaire(client):
    maths = client.get("/api/programmes", params={"matiere": "maths", "niveau": "6e"}).json()
    assert maths["couvert"] and maths["source"]["bo"] == "BO n° 16 du 17 avril 2025"
    assert any(t["theme"] == "Les fractions" for t in maths["themes"])
    assert client.get("/api/programmes", params={"matiere": "svt", "niveau": "6e"}).json() == {
        "couvert": False, "matiere": "svt", "niveau": "6e", "themes": []}


def test_l_analyse_propose_un_attendu(client):
    resultat = client.post("/api/analyser", json={"phrase": "un QCM sur les fractions pour des 6e"}).json()
    assert resultat["requete"]["attendu"] == "maths.6e.fractions" and "attendu" in resultat["a_verifier"]
    assert resultat["procedural"]["nom"] == "fractions"


def test_generer_un_exercice_vise_puis_filtrer_la_banque(client):
    for attendu, attendue in (("maths.6e.inconnu.01", "inconnu"), ("maths.5e.nombres-relatifs", "ne correspond pas")):
        refus = client.post("/api/generations", json={"type": "qcm", "niveau": "6e", "attendu": attendu})
        assert refus.status_code == 422 and attendue in refus.json()["detail"]
    tache = client.post("/api/generations", json={"type": "qcm", "attendu": "maths.6e.fractions.09",
                                                  "fournisseur": "maquette"})
    assert tache.status_code == 202, tache.text
    ident = client.file.attendre(tache.json()["id"], 10)["exercice"]
    exercice = client.get(f"/api/exercices/{ident}").json()["exercice"]
    assert exercice["matiere"] == "maths" and exercice["niveau"] == "6e"
    assert exercice["meta"]["demande"]["notion"] == "Comparer et encadrer des fractions"  # le libellé, faute de notion
    assert exercice["meta"]["programme"]["attendus"] == ["maths.6e.fractions.09"]
    trouves = lambda attendu: [x["id"] for x in client.get("/api/exercices", params={"attendu": attendu}).json()["exercices"]]
    assert trouves("maths.6e.fractions") == [ident] == trouves("maths.6e.fractions.09")  # le thème trouve son attendu
    assert trouves("maths.6e.fractions.08") == [] == trouves("maths.5e.nombres-relatifs")


# --- classes et élèves (E3) ----------------------------------------------------------------------------

LISTE = "DUPONT;Marie\nLE GOFF Anne-Sophie\nMARTIN;Alice;12/03/2014"


def creer_classe(client) -> dict:
    lue = client.post("/api/classes/liste", json={"texte": LISTE}).json()
    assert [e["prenom"] for e in lue["eleves"]] == ["Marie", "Anne-Sophie", "Alice"] and lue["remarques"]
    r = client.post("/api/classes", json={"nom": "6e B", "niveau": "6e", "eleves": lue["eleves"]})
    assert r.status_code == 201, r.text
    return r.json()


def test_creer_une_classe_et_ses_cartes(client):
    cree = creer_classe(client)
    assert cree["classe"]["eleves"] == 3 and [c["numero"] for c in cree["cartes"]] == [1, 2, 3]
    assert all(len(c["code"]) == 4 for c in cree["cartes"])
    liste = client.get("/api/classes").json()
    assert liste["aipd_validee"] is False and liste["classes"][0]["nom"] == "6e B"  # « élèves fictifs uniquement »
    detail = client.get(f"/api/classes/{cree['classe']['id']}").json()["classe"]
    assert [e["prenom"] for e in detail["liste"]] == ["Marie", "Anne-Sophie", "Alice"]
    assert "code" not in str(detail["liste"])  # ni code ni empreinte après la création
    refus = client.post("/api/classes", json={"nom": "6e C", "niveau": "6e", "eleves": [{"nom": "<b>", "prenom": "x"}]})
    assert refus.status_code == 422
    assert client.post("/api/classes", json={"nom": "6e B", "niveau": "6e"}).status_code == 422  # déjà
    assert client.get("/api/classes/999").status_code == 404


def test_une_classe_d_un_autre_est_introuvable(client):
    cree = creer_classe(client)
    comptes.creer(client.base, "autre", "Autre", "le mot de passe d'un autre")
    autre = TestClient(client.app, base_url="http://127.0.0.1:8000")
    autre.post("/api/session", json={"identifiant": "autre", "mot_de_passe": "le mot de passe d'un autre"})
    eleve = cree["cartes"][0]["eleve_id"]
    assert autre.get("/api/classes").json()["classes"] == []
    assert autre.get(f"/api/classes/{cree['classe']['id']}").status_code == 404
    assert autre.post(f"/api/eleves/{eleve}/code", json={}).status_code == 404
    assert autre.put(f"/api/eleves/{eleve}", json={"nom": "X", "prenom": "Y"}).status_code == 404
    export = autre.post(f"/api/eleves/{eleve}/export", json={"mot_de_passe": "le mot de passe d'un autre"})
    assert export.status_code == 404


def test_exporter_supprimer_refaire_les_codes_redemandent_le_mot_de_passe(client):
    cree = creer_classe(client)
    eleve, classe = cree["cartes"][1]["eleve_id"], cree["classe"]["id"]
    faux = {"mot_de_passe": "pas le bon"}
    assert client.post(f"/api/eleves/{eleve}/export", json=faux).status_code == 403
    assert client.request("DELETE", f"/api/eleves/{eleve}", json=faux).status_code == 403
    assert client.post(f"/api/classes/{classe}/codes", json=faux).status_code == 403
    assert client.post("/api/classes/purge", json=faux).status_code == 403
    bon = {"mot_de_passe": MOT_DE_PASSE}
    export = client.post(f"/api/eleves/{eleve}/export", json=bon)
    assert export.status_code == 200 and export.headers["content-type"].startswith("text/csv")
    assert export.headers["content-disposition"] == f'attachment; filename="eleve-{eleve}.csv"'
    assert export.headers["cache-control"] == "no-store" and "LE GOFF" in export.content.decode("utf-8-sig")
    assert len(client.post(f"/api/classes/{classe}/codes", json=bon).json()["cartes"]) == 3
    assert client.request("DELETE", f"/api/eleves/{eleve}", json=bon).status_code == 200
    assert client.get(f"/api/classes/{classe}").json()["classe"]["eleves"] == 2


def test_corriger_desactiver_ajouter_archiver(client):
    cree = creer_classe(client)
    eleve, classe = cree["cartes"][0]["eleve_id"], cree["classe"]["id"]
    assert client.put(f"/api/eleves/{eleve}", json={"nom": "DUPOND", "prenom": "Marie"}).json()["eleve"]["nom"] == "DUPOND"
    assert client.post(f"/api/eleves/{eleve}/actif", json={"actif": False}).json()["eleve"]["actif"] is False
    assert len(client.post(f"/api/eleves/{eleve}/code", json={}).json()["carte"]["code"]) == 4
    ajout = client.post(f"/api/classes/{classe}/eleves", json={"eleves": [{"nom": "PETIT", "prenom": "Emma"}]}).json()
    assert ajout["cartes"][0]["numero"] == 4
    assert client.post(f"/api/classes/{classe}/archiver", json={"archivee": True}).json()["classe"]["archivee"]
    assert client.get("/api/classes").json()["classes"] == []
    assert len(client.get("/api/classes", params={"archivees": True}).json()["classes"]) == 1


def test_purge(client):
    creer_classe(client)
    apercu = client.get("/api/classes/purge").json()  # pas pris pour l'identifiant d'une classe
    assert apercu["classes"] == [] and apercu["eleves"] == 0 and apercu["annee_courante"]
    assert client.post("/api/classes/purge", json={"mot_de_passe": MOT_DE_PASSE}).json() == {"classes": 0, "eleves": 0}
