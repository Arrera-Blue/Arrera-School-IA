"""La relecture à l'aveugle (plan IA, IA4.3) : les demandes jamais vues par l'entraînement ; les deux modèles sur les
mêmes demandes, avec reprise ; les exercices mélangés sans rien qui dise quel modèle ; l'interface restreinte ; le bilan,
refusé tant que tout n'est pas relu."""

import copy
import json
import sys
import warnings
from collections import Counter

import pytest

from generateur import procedural, programmes
from generateur.donnees import comptes
from generateur.entrainement import __main__ as cli
from generateur.entrainement import aveugle
from generateur.interface.api import creer_application, decrire_erreur
from generateur.interface.taches import File
from generateur.moteur import banque, config, generation, registre
from generateur.moteur.fournisseurs.base import Fournisseur

with warnings.catch_warnings():  # starlette signale que son client de test préférera bientôt httpx2
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

QUESTIONS = [
    ("Quel mot est un nom commun ?", ["maison", "rapide", "courir", "très"], "« maison » désigne une chose."),
    ("Quel mot est un verbe ?", ["chanter", "table", "joli", "sous"], "« chanter » exprime une action."),
    ("Quel mot est un adjectif ?", ["grand", "pomme", "partir", "avec"], "« grand » qualifie un nom."),
    ("Quel mot est un déterminant ?", ["le", "chat", "dormir", "vite"], "« le » précède le nom."),
    ("Quel mot est une préposition ?", ["dans", "arbre", "manger", "bleu"], "« dans » introduit un complément."),
]
FRANCAIS = sorted(a.id for a in programmes.lister(qcm=True) if a.matiere == "francais" and a.niveau in ("6e", "5e"))


class Modele(Fournisseur):
    """Le faux modèle : un QCM de grammaire à la demande ; le titre dit s'il porte l'adaptateur (pour vérifier la clé)."""
    nom, modele = "faux", "faux-modele"

    def __init__(self, adaptateur=None):
        self.chemin_adaptateur = adaptateur

    @property
    def adaptateur(self):
        return {"nom": "essai.gguf", "sha256": "0" * 64} if self.chemin_adaptateur else None

    def generer(self, messages, schema):
        p = schema["properties"]
        exercice = copy.deepcopy(registre.charger("qcm").exemple)
        exercice |= {"matiere": p["matiere"]["enum"][0], "niveau": p["niveau"]["enum"][0],
                     "titre": "Entraîné" if self.chemin_adaptateur else "De base", "notion": "les classes de mots"}
        exercice["questions"] = []
        for i in range(p["questions"]["minItems"]):
            enonce, propositions, explication = QUESTIONS[i]
            rang = i % 4
            exercice["questions"].append({"enonce": enonce, "explication": explication, "index_correct": rang,
                                          "propositions": propositions[1:rang + 1] + [propositions[0]] + propositions[rang + 1:],
                                          "difficulte": "facile"})
        return json.dumps(exercice, ensure_ascii=False)


@pytest.fixture
def comparaison(tmp_path, monkeypatch):
    """Les dossiers du projet dans tmp_path, le faux modèle (l'adaptateur passé par `utiliser_adaptateur`), un adaptateur
    et un jeu d'entraînement qui a vu les deux premiers attendus de français."""
    monkeypatch.setattr(config, "_REDIRIGES", {nom: tmp_path / nom for nom in
                                              ("banque", "rejets", "supprimes", "sortie", "base", "entrainement")})
    appels = []
    monkeypatch.setattr(generation, "creer", lambda nom, reglages: appels.append(reglages.get("adaptateur"))
                        or Modele(reglages.get("adaptateur")))
    adaptateur = tmp_path / "adaptateurs" / "20261106-1925-0000053.gguf"
    adaptateur.parent.mkdir()
    adaptateur.write_bytes(b"un adaptateur")
    jeu = tmp_path / "jeux" / "1"
    jeu.mkdir(parents=True)
    vu = lambda ident: {"id": ident, "notion": ident}
    (jeu / "manifeste.json").write_text(json.dumps({"jeux": {"train": [vu(FRANCAIS[0])], "valid": [vu(FRANCAIS[1])],
                                                             "test": [vu(FRANCAIS[2])]}}))
    (adaptateur.parent / "20261106-1925").mkdir()
    (adaptateur.parent / "20261106-1925" / "entrainement.json").write_text(json.dumps({"jeu": str(jeu)}))
    return {"dossier": tmp_path / "entrainement" / "aveugle" / "1", "adaptateur": adaptateur, "jeu": jeu, "appels": appels}


def _francais_seulement(monkeypatch):
    """Les demandes du faux modèle restent en français : il n'écrit que de la grammaire."""
    vrai = programmes.lister
    monkeypatch.setattr(programmes, "lister", lambda *a, **k: [x for x in vrai(*a, **k) if x.matiere == "francais"])


# --- les demandes -----------------------------------------------------------------------------------------------

def test_les_demandes_jamais_vues_le_test_d_abord_en_alternance():
    vues = {FRANCAIS[0], FRANCAIS[1]}
    demandes = aveugle.choisir(vues, {FRANCAIS[2]}, nombre=8)
    assert [d["n"] for d in demandes] == list(range(1, 9))
    attendus = [d["demande"]["attendu"] for d in demandes]
    assert not set(attendus) & vues and len(set(attendus)) == 8
    assert FRANCAIS[2] in attendus and [d["test"] for d in demandes].count(True) == 1
    groupes = [(d["demande"]["matiere"], d["demande"]["niveau"]) for d in demandes]
    assert groupes[:4] == [("francais", "5e"), ("francais", "6e"), ("maths", "5e"), ("maths", "6e")] == groupes[4:]
    assert all(procedural.aiguiller(d["demande"]) is None for d in demandes)  # le modèle écrit tout
    assert all(d["demande"]["nb_questions"] == aveugle.QUESTIONS and d["demande"]["notion"] for d in demandes)
    assert aveugle.choisir(vues, {FRANCAIS[2]}, nombre=8) == demandes  # la graine fixe le choix
    assert aveugle.choisir(vues, set(), nombre=8, graine=1) != demandes


def test_le_jeu_de_l_adaptateur_et_de_son_point_d_etape(tmp_path):
    (tmp_path / "20261106-1925").mkdir()
    (tmp_path / "20261106-1925" / "entrainement.json").write_text(json.dumps({"jeu": "donnees/entrainement/jeux/x"}))
    for nom in ("20261106-1925.gguf", "20261106-1925-0000053.gguf"):
        assert aveugle.jeu_de_l_adaptateur(tmp_path / nom) == config.RACINE / "donnees/entrainement/jeux/x"
    assert aveugle.jeu_de_l_adaptateur(tmp_path / "autre.gguf") is None


def test_preparer(comparaison):
    c = comparaison
    plan = aveugle.preparer(c["adaptateur"], c["jeu"], c["dossier"], nombre=4)
    assert plan["adaptateur"]["nom"] == "20261106-1925-0000053.gguf" and len(plan["adaptateur"]["sha256"]) == 64
    assert len(plan["demandes"]) == 4 and aveugle.lire_plan(c["dossier"]) == plan
    with pytest.raises(FileExistsError):  # une comparaison ne s'écrase pas
        aveugle.preparer(c["adaptateur"], c["jeu"], c["dossier"], nombre=4)
    with pytest.raises(ValueError, match="adaptateur introuvable"):
        aveugle.preparer(c["adaptateur"].with_name("pas-la.gguf"), c["jeu"], c["dossier"].with_name("2"))
    with pytest.raises(ValueError, match="jeu de données introuvable"):
        aveugle.preparer(c["adaptateur"], c["jeu"].with_name("pas-la"), c["dossier"].with_name("3"))


# --- générer, reprendre, mélanger -------------------------------------------------------------------------------

def test_generer_les_deux_modeles_puis_melanger(comparaison, monkeypatch):
    c = comparaison
    _francais_seulement(monkeypatch)
    aveugle.preparer(c["adaptateur"], c["jeu"], c["dossier"], nombre=3)
    lignes = []
    resultats = aveugle.generer(c["dossier"], lignes.append)
    assert resultats == {"genere": 6}
    assert c["appels"][0] is None and str(c["adaptateur"]) in c["appels"][-1]  # la base d'abord, puis l'entraîné
    assert lignes[0].startswith("Modèle de base : 3 demande(s)") and "mélangés" in lignes[-1]
    assert sorted(p.name for p in (c["dossier"] / "originaux").iterdir()) == [
        "base-01.json", "base-02.json", "base-03.json", "entraine-01.json", "entraine-02.json", "entraine-03.json"]
    # mélangés, sans rien qui dise quel modèle
    cle = json.loads((c["dossier"] / "cle.json").read_text())
    instances = aveugle.chemins(c["dossier"])["banque"]
    assert sorted(cle) == sorted(p.stem for p in instances.glob("*.json")) == [f"aveugle-0{i}" for i in range(1, 7)]
    assert [cle[i]["modele"] for i in sorted(cle)] != ["base"] * 3 + ["entraine"] * 3
    for ident, quoi in cle.items():
        x = json.loads((instances / f"{ident}.json").read_text())
        assert x["titre"] == ("Entraîné" if quoi["modele"] == "entraine" else "De base")  # la clé est juste
        assert not set(x["meta"]) & set(aveugle.CACHES) and x["meta"]["statut"] == "genere" and x["meta"]["aveugle"]
        original = json.loads((c["dossier"] / quoi["original"]).read_text())
        assert original["meta"]["duree_s"] is not None and x["questions"] == original["questions"]
    dates = [json.loads((instances / f"{i}.json").read_text())["meta"]["date"] for i in sorted(cle)]
    assert dates == sorted(dates)  # l'ordre des dates est celui du tirage
    assert (aveugle.chemins(c["dossier"])["sortie"] / "aveugle-01.html").is_file()
    assert not (config.chemin("entrainement") / "banque").exists()  # rien dans le lot


def test_une_coupure_reprend_la_ou_elle_s_est_arretee(comparaison, monkeypatch):
    c = comparaison
    _francais_seulement(monkeypatch)
    aveugle.preparer(c["adaptateur"], c["jeu"], c["dossier"], nombre=2)
    vrai = aveugle.faire
    pannes = iter([True, False, False])

    def faire(dossier, modele, d, noms):
        if modele == "entraine" and next(pannes):
            return {"modele": modele, "n": d["n"], "attendu": "x", "resultat": "erreur", "erreur": "panne",
                    "duree_totale_s": 0}
        return vrai(dossier, modele, d, noms)

    monkeypatch.setattr(aveugle, "faire", faire)
    assert aveugle.generer(c["dossier"], lambda _: None) == {"genere": 3, "erreur": 1}
    assert not aveugle.melanges(c["dossier"]) and aveugle.reste_a_faire(c["dossier"]) == [
        ("entraine", aveugle.lire_plan(c["dossier"])["demandes"][0])]
    assert aveugle.generer(c["dossier"], lambda _: None) == {"genere": 1}  # seule la génération en panne est refaite
    assert aveugle.melanges(c["dossier"]) and len(json.loads((c["dossier"] / "cle.json").read_text())) == 4
    with pytest.raises(ValueError, match="déjà mélangés"):
        aveugle.melanger(c["dossier"])


def test_un_adaptateur_change_en_cours_de_route_est_refuse(comparaison):
    c = comparaison
    aveugle.preparer(c["adaptateur"], c["jeu"], c["dossier"], nombre=1)
    c["adaptateur"].write_bytes(b"un autre adaptateur")
    with pytest.raises(ValueError, match="a changé"):
        aveugle.generer(c["dossier"], lambda _: None)


def test_un_rejet_compte_et_ne_va_pas_dans_la_vraie_banque(comparaison, monkeypatch):
    c = comparaison
    _francais_seulement(monkeypatch)
    aveugle.preparer(c["adaptateur"], c["jeu"], c["dossier"], nombre=2)
    vrai = Modele.generer
    monkeypatch.setattr(Modele, "generer", lambda self, m, s: "pas du JSON" if self.chemin_adaptateur else vrai(self, m, s))
    assert aveugle.generer(c["dossier"], lambda _: None) == {"genere": 2, "rejete": 2}
    assert len(json.loads((c["dossier"] / "cle.json").read_text())) == 2  # les rejets ne sont pas à relire
    assert list((c["dossier"] / "rejets").glob("*.json")) and not (config.chemin("rejets")).exists()


# --- l'interface (--aveugle) ------------------------------------------------------------------------------------

MOT_DE_PASSE = "un mot de passe de test"


@pytest.fixture
def relue(comparaison, monkeypatch):
    """Une comparaison de 2 demandes générée et mélangée, et l'interface lancée avec --aveugle."""
    c = comparaison
    _francais_seulement(monkeypatch)
    aveugle.preparer(c["adaptateur"], c["jeu"], c["dossier"], nombre=2)
    aveugle.generer(c["dossier"], lambda _: None)
    monkeypatch.setattr(config, "_REDIRIGES", config._REDIRIGES | aveugle.chemins(c["dossier"]))
    app = creer_application(File(decrire_erreur=decrire_erreur), aveugle=True)
    comptes.creer(app.state.base, "prof", "Professeur Essai", MOT_DE_PASSE, "admin")
    client = TestClient(app, base_url="http://127.0.0.1:8003")
    session = client.post("/api/session", json={"identifiant": "prof", "mot_de_passe": MOT_DE_PASSE}).json()
    assert session["entrainement"] is True and session["aveugle"] is True
    return c | {"client": client, "cle": json.loads((c["dossier"] / "cle.json").read_text())}


def test_l_interface_a_l_aveugle_ne_sert_qu_a_relire_et_decider(relue):
    c = relue["client"]
    etat = c.get("/api/entrainement").json()
    assert etat["aveugle"] is True and etat["objectif_relus"] == 4 and len(etat["ordre"]) == 4
    assert {x["id"] for x in c.get("/api/exercices").json()["exercices"]} == set(relue["cle"])
    x = c.get("/api/exercices/aveugle-01").json()["exercice"]
    assert "adaptateur" not in x["meta"] and "duree_s" not in x["meta"]
    for methode, chemin, corps in [("POST", "/api/exercices/aveugle-01/questions/1/regenerer", {"motif": "x"}),
                                   ("DELETE", "/api/exercices/aveugle-01", {}),
                                   ("POST", "/api/generations", {"notion": "les fractions"}),
                                   ("POST", "/api/exercices/aveugle-01/publications", {"classe_id": 1}),
                                   ("GET", "/api/classes", None), ("GET", "/api/cours", None)]:
        reponse = c.request(methode, chemin, json=corps)
        assert reponse.status_code == 404 and "à l'aveugle" in reponse.json()["detail"], chemin
    question = dict(x["questions"][0]) | {"explication": "Un nom désigne une chose : « maison »."}
    assert c.put("/api/exercices/aveugle-01/questions/1", json=question).status_code == 200
    assert c.post("/api/exercices/aveugle-02/decision", json={"decision": "rejeter",
                                                              "motifs": ["reponse_fausse"]}).status_code == 200
    etat = c.get("/api/entrainement").json()
    assert (etat["relus"], etat["rejetes"], etat["corrections"]) == (1, 1, 1)
    assert sorted(etat["ordre"]) == ["aveugle-01", "aveugle-03", "aveugle-04"]


def test_le_bilan_attend_la_fin_de_la_relecture_puis_devoile(relue):
    c, cle, dossier = relue["client"], relue["cle"], relue["dossier"]
    with pytest.raises(ValueError, match="pas encore décidé"):
        aveugle.bilan(dossier)
    assert "pas décidé" in aveugle.bilan(dossier, meme_si_pas_fini=True)
    for ident, quoi in cle.items():  # la base acceptée ; l'entraîné : une réponse fausse, puis un rejet sans motif
        if quoi["modele"] == "base":
            corps = {"decision": "accepter"}
        else:
            corps = {"decision": "rejeter", "motifs": ["reponse_fausse", "enonce_ambigu"] if quoi["n"] == 1 else None}
        assert c.post(f"/api/exercices/{ident}/decision", json=corps).status_code == 200
    texte = aveugle.bilan(dossier)
    assert texte == (dossier / "bilan.md").read_text(encoding="utf-8")
    b = json.loads((dossier / "bilan.json").read_text())
    base, entraine = b["modeles"]["base"], b["modeles"]["entraine"]
    assert (base["acceptes"], base["rejetes"], entraine["acceptes"], entraine["rejetes"]) == (2, 0, 0, 2)
    assert entraine["motifs"] == {"reponse_fausse": 1, "enonce_ambigu": 1} and entraine["reponses_fausses"] == 1
    assert entraine["rejets_sans_motif"] == 1 and base["produits"] == 2 and base["du_premier_coup"] == 2
    assert b["regle"] == {"pas_plus_de_reponses_fausses": False, "mieux_accepte": False, "remplie": False}
    assert "| **Acceptés à la relecture** | **2 sur 2** | **0 sur 2** |" in texte
    assert "| … une bonne réponse est fausse | 0 | 1 |" in texte and "on garde le modèle de base" in texte
    assert "✗ rejeté : une bonne réponse est fausse, énoncé mal formulé ou ambigu" in texte
    assert "20261106-1925-0000053.gguf" in texte


# --- la commande ------------------------------------------------------------------------------------------------

def test_la_commande_aveugle(comparaison, monkeypatch, capsys):
    c = comparaison
    _francais_seulement(monkeypatch)
    monkeypatch.setattr(cli, "_rester_eveille", lambda: None)
    monkeypatch.setattr(aveugle, "NOMBRE", 2)

    def lancer(*arguments):
        monkeypatch.setattr(sys, "argv", ["entrainement", "aveugle", *arguments])
        cli.main()
        return capsys.readouterr().out

    with pytest.raises(SystemExit, match="préciser le modèle entraîné"):
        lancer("generer")
    with pytest.raises(SystemExit, match="aucune comparaison"):
        lancer("bilan")
    vrai = aveugle.generer
    monkeypatch.setattr(aveugle, "generer", lambda dossier, afficher: Counter())  # coupée avant la 1re génération
    sortie = lancer("generer", "--adaptateur", str(c["adaptateur"]), "--nombre", "2")
    assert "2 demandes, chacune par le modèle de base puis par le modèle entraîné" in sortie and "Pas fini" in sortie
    monkeypatch.setattr(aveugle, "generer", vrai)
    with pytest.raises(SystemExit, match="n'est pas finie, avec l'adaptateur"):
        lancer("generer", "--adaptateur", str(c["jeu"] / "manifeste.json"))
    sortie = lancer("generer")  # reprise de la dernière, sans redire l'adaptateur
    assert "Reprise de la comparaison" in sortie and "4 exercices mélangés" in sortie
    with pytest.raises(SystemExit, match="pas encore décidé"):
        lancer("bilan")
    assert "Écrit dans" in lancer("bilan", "--meme-si-pas-fini")
    assert len(list(aveugle.racine().iterdir())) == 1



# --- les deux chemins : le modèle seul contre le générateur procédural (critère de fin d'un lot du cycle 2) ----------

DEMANDES = [{"phrase": "l'imparfait en CE2", "graine": 4},
            {"phrase": "les pluriels en -aux et les féminins particuliers, CE2",
             "formulaire": {"notion": "pluriels et féminins particuliers"}}]


@pytest.fixture
def chemins(comparaison, tmp_path, monkeypatch):
    """Les tables du générateur copiées et relues : il est proposé, quel que soit l'état des relectures du dépôt."""
    from generateur.procedural import tables
    import shutil
    copie = tmp_path / "tables"
    shutil.copytree(tables.DOSSIER, copie)
    monkeypatch.setattr(tables, "DOSSIER", copie)
    for matiere, nom in tables.lister():
        tables.relire(matiere, nom, "Essai")
    return comparaison | {"dossier": tmp_path / "entrainement" / "aveugle" / "chemins"}


def test_les_deux_chemins_sur_des_demandes_reelles(chemins, tmp_path):
    c = chemins
    plan = aveugle.preparer_chemins(DEMANDES, c["dossier"])
    assert aveugle.des_chemins(plan) and aveugle.cotes(plan) == ("modele", "procedural")
    d1, d2 = plan["demandes"]
    assert d1["demande"]["attendu"] == "francais.ce2.orthographe-grammaticale.03"  # l'attendu proposé, gardé
    assert d2["demande"]["notion"] == "pluriels et féminins particuliers" and d2["demande"]["niveau"] == "CE2"
    lignes = []
    assert aveugle.generer(c["dossier"], lignes.append) == {"genere": 4}
    assert set(c["appels"]) == {None}  # le modèle de base, jamais un adaptateur
    assert lignes[0].startswith("Modèle seul : 2 demande(s)") and "mélangés" in lignes[-1]
    # la graine donnée : le même exercice que celui déjà relu
    deja = generation.generer(dict(d1["demande"]), mode="procedural", graine=4)
    original = json.loads((c["dossier"] / "originaux" / "procedural-01.json").read_text())
    assert original["meta"]["origine"] == "procedural" and original["questions"] == deja["questions"]
    # mélangés : la meta ne garde que ce que les deux chemins ont en commun
    cle = json.loads((c["dossier"] / "cle.json").read_text())
    instances = aveugle.chemins(c["dossier"])["banque"]
    for ident, quoi in cle.items():
        x = json.loads((instances / f"{ident}.json").read_text())
        assert set(x["meta"]) <= set(aveugle.GARDES) | {"id", "date", "statut", "aveugle"}, quoi["modele"]
        assert x["meta"]["demande"] == plan["demandes"][quoi["n"] - 1]["demande"]
    assert not list((tmp_path / "banque").glob("*.json"))  # rien dans la banque de l'enseignant


def test_le_bilan_des_deux_chemins(chemins):
    c = chemins
    aveugle.preparer_chemins(DEMANDES, c["dossier"])
    aveugle.generer(c["dossier"], lambda _: None)
    cle = json.loads((c["dossier"] / "cle.json").read_text())
    config.rediriger(aveugle.chemins(c["dossier"]))
    for ident, quoi in cle.items():  # le générateur accepté ; le modèle : une réponse fausse (deux motifs), un accepté
        rejet = quoi["modele"] == "modele" and quoi["n"] == 1
        banque.decider(ident, "rejeter" if rejet else "accepter",
                       motifs=["reponse_fausse", "plusieurs_justes"] if rejet else None)
    texte = aveugle.bilan(c["dossier"])
    b = json.loads((c["dossier"] / "bilan.json").read_text())
    assert b["regle"] == {"tous_justes": True, "plus_juste": True, "remplie": True}
    # un exercice, même rejeté pour deux motifs de réponse fausse
    assert (b["modeles"]["procedural"]["acceptes"], b["modeles"]["modele"]["reponses_fausses"]) == (2, 1)
    assert "Une seule personne relit" in texte and "Les décisions sont de Claude" not in texte
    assert texte.startswith("# Relecture à l'aveugle : le modèle seul contre le générateur procédural")
    assert "| **Acceptés à la relecture** | **1 sur 2** | **2 sur 2** |" in texte
    assert ("| 1 | l'imparfait en CE2 | ✗ rejeté : une bonne réponse est fausse, plusieurs propositions sont justes | "
            "✓ accepté |") in texte
    assert "Les deux conditions sont remplies." in texte
    # des décisions déléguées à Claude : le bilan le dit
    ident = next(i for i, q in cle.items() if q["modele"] == "procedural")
    banque.decider(ident, "accepter", f"{aveugle.PAR_CLAUDE} (Opus 5.5) (relecture à l'aveugle déléguée par l'enseignant)")
    assert "Les décisions sont de Claude" in aveugle.bilan(c["dossier"])


def test_la_commande_aveugle_chemins(chemins, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "_rester_eveille", lambda: None)
    fichier = tmp_path / "demandes.json"
    fichier.write_text(json.dumps(DEMANDES, ensure_ascii=False), encoding="utf-8")

    def lancer(*arguments):
        monkeypatch.setattr(sys, "argv", ["entrainement", "aveugle", *arguments])
        cli.main()
        return capsys.readouterr().out

    with pytest.raises(SystemExit, match="préciser les demandes"):
        lancer("chemins")
    vrai = aveugle.generer
    monkeypatch.setattr(aveugle, "generer", lambda dossier, afficher: Counter())  # coupée avant la 1re génération
    sortie = lancer("chemins", "--demandes", str(fichier))
    assert "2 demandes, chacune par le modèle seul puis par le générateur procédural" in sortie and "Pas fini" in sortie
    with pytest.raises(SystemExit, match="des deux chemins .* n'est pas finie"):
        lancer("generer", "--adaptateur", str(chemins["adaptateur"]))
    monkeypatch.setattr(aveugle, "generer", vrai)
    sortie = lancer("chemins")  # reprise, sans redire les demandes
    assert "Reprise de la comparaison" in sortie and "4 exercices mélangés" in sortie
