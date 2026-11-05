"""La pré-relecture du lot d'entraînement (plan IA, IA3, 05/11) : les avis de Claude, enregistrés par paquets, tout ou
rien ; « en cours de relecture » ; l'avis gardé par chaque décision, et combien de fois il a été suivi ; l'interface du lot
et la fiche du jeu."""

import copy
import json
import sys
import warnings

import pytest

from generateur import entrainement
from generateur.donnees import comptes
from generateur.entrainement import __main__ as cli
from generateur.entrainement import bilan, jeu, prerelecture, relecture
from generateur.interface.api import creer_application, decrire_erreur
from generateur.interface.taches import File
from generateur.moteur import banque, config, registre

with warnings.catch_warnings():  # starlette signale que son client de test préférera bientôt httpx2
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient


def _ranger(dossier, ident, statut="genere", **meta):
    """Un exercice du lot : l'exemple du QCM (3 questions), écrit par « le modèle »."""
    instance = copy.deepcopy(registre.charger("qcm").exemple)
    instance["meta"] = {"id": ident, "statut": statut, "fournisseur": "llamacpp", "date": "2026-10-30T16:00:00", **meta}
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"{ident}.json").write_text(json.dumps(instance, ensure_ascii=False), encoding="utf-8")
    return instance


def _avis(ident, avis="a_corriger", fausses=(2,), **autres):
    """Une ligne de paquet : chaque question relue, celles de `fausses` avec une remarque et une proposition."""
    return {"id": ident, "avis": avis, "resume": "La question 2 a deux propositions justes.",
            "questions": [{"numero": n, "juste": n not in fausses,
                           **({"remarque": "Deux propositions sont justes. AC² = AB² + BC² l'est aussi.",
                               "proposition": "remplacer « AC² = AB² + BC² » par « AB = AC + BC »"} if n in fausses else {})}
                          for n in (1, 2, 3)], **autres}


def _paquet(chemin, *lignes):
    chemin.write_text("\n".join(json.dumps(l, ensure_ascii=False) if l else "" for l in lignes) + "\n", encoding="utf-8")
    return chemin


@pytest.fixture
def lot(tmp_path, monkeypatch):
    """Les dossiers de la banque sont ceux d'un lot dans tmp_path, comme après `entrainement.utiliser()`."""
    monkeypatch.setattr(config, "_REDIRIGES", {nom: tmp_path / nom for nom in ("banque", "rejets", "supprimes", "sortie",
                                                                              "base", "entrainement")})
    return tmp_path / "banque"


# --- l'avis d'une ligne ------------------------------------------------------------------------------------

def test_preparer_garde_l_avis_et_l_empreinte_de_chaque_question():
    instance = copy.deepcopy(registre.charger("qcm").exemple)
    p = prerelecture.preparer(_avis("x", motifs=["plusieurs_justes", "enonce_ambigu"], precisions="  Q2 : deux justes.  "),
                              instance, "2026-11-05T10:00:00")
    assert (p["par"], p["avis"], p["date"]) == ("Claude (Opus 5.5)", "a_corriger", "2026-11-05T10:00:00")
    assert [q["numero"] for q in p["questions"]] == [1, 2, 3] and [q["juste"] for q in p["questions"]] == [True, False, True]
    assert p["questions"][1]["proposition"].startswith("remplacer") and "remarque" not in p["questions"][0]
    assert all(q["empreinte"] == prerelecture.empreinte(instance["questions"][q["numero"] - 1]) for q in p["questions"])
    assert p["motifs"] == ["plusieurs_justes", "enonce_ambigu"] and p["precisions"] == "Q2 : deux justes."
    assert prerelecture.preparer(_avis("x", "bon", fausses=()), instance, "d")["motifs"] == []


@pytest.mark.parametrize("ligne, message", [
    (_avis("x", "excellent"), "avis inconnu"),
    (_avis("x") | {"questions": _avis("x")["questions"][:2]}, "question(s) 3 sans avis"),
    (_avis("x") | {"questions": _avis("x")["questions"] + [{"numero": 4, "juste": True}]}, "question 4 inexistante"),
    (_avis("x") | {"questions": _avis("x")["questions"] + [{"numero": 1, "juste": True}]}, "question 1 relue deux fois"),
    (_avis("x") | {"questions": [{"numero": 1, "juste": "oui"}]}, "« juste » vaut true ou false"),
    (_avis("x") | {"questions": [{"numero": n, "juste": n != 2} for n in (1, 2, 3)]}, "question 2, remarque"),
    (_avis("x", "bon"), "avis « bon », mais la question 2"),
    (_avis("x", fausses=()), "toutes les questions sont justes"),
    (_avis("x", motifs=["trop_long"]), "motif de rejet inconnu : 'trop_long'"),
    (_avis("x", "bon", fausses=(), motifs=["enonce_ambigu"]), "ni motif de rejet"),
    (_avis("x", precisions="x" * 501), "501 caractères, 500 au plus"),
    (_avis("x") | {"resume": " "}, "« resume » : un texte"),
])
def test_preparer_refuse_un_avis_qui_ne_va_pas(ligne, message):
    with pytest.raises(ValueError, match=message.replace("(", r"\(").replace(")", r"\)")):
        prerelecture.preparer(ligne, copy.deepcopy(registre.charger("qcm").exemple), "d")


# --- enregistrer un paquet ---------------------------------------------------------------------------------

def test_un_paquet_s_enregistre_tout_ou_rien(lot, tmp_path):
    _ranger(lot, "qcm-a")
    _ranger(lot, "qcm-b", "accepte", decisions=[{"statut": "accepte", "date": "2026-10-29T12:00:00"}])
    _ranger(lot, "qcm-c")
    avant = (lot / "qcm-a.json").read_text(encoding="utf-8")
    mauvais = _paquet(tmp_path / "mauvais.jsonl", _avis("qcm-a"), _avis("qcm-inconnu"), _avis("qcm-c", "peut-être"),
                      _avis("qcm-a"))
    with pytest.raises(ValueError) as e:
        prerelecture.importer(mauvais)
    assert "rien n'est enregistré" in str(e.value)
    assert "ligne 2 : exercice « qcm-inconnu » introuvable" in str(e.value) and "ligne 3 : avis inconnu" in str(e.value)
    assert "ligne 4 : « qcm-a » a déjà un avis plus haut" in str(e.value)
    assert (lot / "qcm-a.json").read_text(encoding="utf-8") == avant  # rien d'écrit

    bon = _paquet(tmp_path / "bon.jsonl", _avis("qcm-a"), "", _avis("qcm-b", "a_rejeter", motifs=["plusieurs_justes"]))
    assert prerelecture.importer(bon) == {"bon": 0, "a_corriger": 1, "a_rejeter": 1, "deja_decides": 1}
    a, b = banque.charger("qcm-a"), banque.charger("qcm-b")
    assert a["meta"]["prerelecture"]["avis"] == "a_corriger" and a["meta"]["statut"] == "genere"
    assert a["questions"] == registre.charger("qcm").exemple["questions"]  # l'avis ne touche à rien d'autre
    assert b["meta"]["statut"] == "accepte" and b["meta"]["prerelecture"]["motifs"] == ["plusieurs_justes"]
    assert prerelecture.en_cours(a) and not prerelecture.en_cours(b) and not prerelecture.en_cours(banque.charger("qcm-c"))


def test_la_vue_dit_quelle_question_a_change_depuis_l_avis(lot, tmp_path):
    _ranger(lot, "qcm-a")
    prerelecture.importer(_paquet(tmp_path / "p.jsonl", _avis("qcm-a", fausses=(2, 3))))
    instance = banque.charger("qcm-a")
    v = prerelecture.vue(instance)
    assert (v["avis"], v["libelle"], v["par"]) == ("a_corriger", "à corriger", "Claude (Opus 5.5)")
    assert [q["modifiee"] for q in v["questions"]] == [False, False, False] and "empreinte" not in v["questions"][0]
    instance["questions"][1]["explication"] = "Corrigée par l'enseignant."
    assert [q["modifiee"] for q in prerelecture.vue(instance)["questions"]] == [False, True, False]
    assert prerelecture.vue(_ranger(lot, "qcm-b")) is None


# --- la décision garde l'avis ; l'a-t-elle suivi ? ------------------------------------------------------------

def _decide(avis, statut, date_avis="2026-11-05T10:00:00", historique=()):
    x = copy.deepcopy(registre.charger("qcm").exemple)
    x["meta"] = {"statut": statut, "prerelecture": {"avis": avis, "date": date_avis},
                 "decisions": [{"statut": statut, "avis_prerelecture": avis}], "modifications": list(historique)}
    return x


def test_l_avis_suivi_ou_non():
    assert prerelecture.suivi(_decide("bon", "accepte")) is True
    assert prerelecture.suivi(_decide("bon", "rejete")) is False
    assert prerelecture.suivi(_decide("a_rejeter", "rejete")) is True
    assert prerelecture.suivi(_decide("a_rejeter", "accepte")) is False
    assert prerelecture.suivi(_decide("a_corriger", "rejete")) is False
    assert prerelecture.suivi(_decide("a_corriger", "accepte")) is False  # accepté sans rien corriger
    assert prerelecture.suivi(_decide("a_corriger", "accepte", historique=[{"question": 2, "date": "2026-11-05T11:00:00"}]))
    assert not prerelecture.suivi(_decide("a_corriger", "accepte", historique=[{"question": 2, "date": "2026-11-01T11:00:00"}]))
    sans_avis = _decide("bon", "accepte")
    sans_avis["meta"]["decisions"] = [{"statut": "accepte"}]
    assert prerelecture.suivi(sans_avis) is None
    assert prerelecture.suivi(_decide("bon", "genere")) is None


def test_la_decision_garde_l_avis_et_les_comptes(lot, tmp_path):
    for ident in ("qcm-a", "qcm-b", "qcm-c"):
        _ranger(lot, ident)
    _ranger(lot, "qcm-d", "accepte", decisions=[{"statut": "accepte"}])  # accepté avant la pré-relecture
    _ranger(lot, "qcm-e", "accepte", decisions=[{"statut": "accepte"}])
    _ranger(lot, "qcm-f")  # pas pré-relu
    prerelecture.importer(_paquet(tmp_path / "p.jsonl", _avis("qcm-a", "bon", fausses=()), _avis("qcm-b"),
                                  _avis("qcm-c", "a_rejeter"), _avis("qcm-d"), _avis("qcm-e", "a_rejeter")))
    banque.decider("qcm-a", "accepter")
    banque.decider("qcm-c", "accepter")  # contre l'avis
    assert banque.charger("qcm-a")["meta"]["decisions"][-1]["avis_prerelecture"] == "bon"
    assert "avis_prerelecture" not in banque.charger("qcm-d")["meta"]["decisions"][-1]
    du_lot = relecture.instances(lot)
    assert prerelecture.compter(du_lot) == {"en_cours": 1, "decides": 2, "suivis": 1, "acceptes_avant": 2,
                                            "acceptes_a_corriger": 1, "acceptes_a_rejeter": 1}
    assert relecture.compter(du_lot, [])["prerelecture"]["en_cours"] == 1
    assert "Pré-relecture (Claude) : 1 en cours de relecture, à décider ; 2 décidé(s) après son avis, suivi 1 fois." \
        in bilan.bilan(lot, [], tmp_path / "vide")


def test_les_pre_relus_passent_devant_dans_l_ordre_de_relecture():
    def ligne(ident, matiere, heure, avis=None, statut="genere"):
        return {"id": ident, "matiere": matiere, "niveau": "6e", "date": f"2026-10-30T{heure}", "statut": statut,
                "origine": "modele", "prerelecture": {"avis": avis, "questions": []} if avis else None}
    lignes = [ligne("m1", "maths", "16:00"), ligne("m2", "maths", "16:01", "bon"), ligne("f1", "francais", "16:02"),
              ligne("f2", "francais", "16:03", "a_rejeter"), ligne("a1", "maths", "15:00", "bon", "accepte")]
    # l'alternance d'abord (f1, m1, f2, m2), puis les pré-relus devant, dans ce même ordre ; les relus à la fin
    assert [l["id"] for l in relecture.ordonner(lignes)] == ["f2", "m2", "f1", "m1", "a1"]


# --- l'interface du lot ------------------------------------------------------------------------------------

@pytest.fixture
def interface(tmp_path, monkeypatch):
    vrai = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai(nom) if nom == "types" else tmp_path / nom)
    for ident, heure in [("qcm-a", "16:00"), ("qcm-b", "16:01"), ("qcm-c", "16:02")]:
        _ranger(tmp_path / "banque", ident, date=f"2026-10-30T{heure}:00")
    _ranger(tmp_path / "banque", "qcm-d", "accepte", decisions=[{"statut": "accepte"}])
    prerelecture.importer(_paquet(tmp_path / "p.jsonl", _avis("qcm-c", motifs=["plusieurs_justes"], precisions="Q2."),
                                  _avis("qcm-d")))
    app = creer_application(File(decrire_erreur=decrire_erreur), entrainement=True, banque_enseignant=tmp_path / "vide")
    comptes.creer(app.state.base, "prof", "Professeur Essai", "un mot de passe de test", "admin")
    c = TestClient(app, base_url="http://127.0.0.1:8002")
    c.post("/api/session", json={"identifiant": "prof", "mot_de_passe": "un mot de passe de test"})
    return c


def test_l_interface_montre_l_avis_et_filtre_en_cours_de_relecture(interface):
    c = interface
    assert [x["id"] for x in c.get("/api/exercices?statut=prerelu").json()["exercices"]] == ["qcm-c"]
    assert [x["id"] for x in c.get("/api/exercices?statut=genere").json()["exercices"]] == ["qcm-a", "qcm-b"]
    tous = {x["id"]: x for x in c.get("/api/exercices").json()["exercices"]}
    assert tous["qcm-c"]["prerelecture"] == {"avis": "a_corriger", "questions": [2]} and tous["qcm-a"]["prerelecture"] is None
    assert tous["qcm-d"]["prerelecture"]["avis"] == "a_corriger"  # accepté avant : son avis reste visible
    etat = c.get("/api/entrainement").json()
    assert etat["ordre"] == ["qcm-c", "qcm-a", "qcm-b"]
    assert etat["prerelecture"] == {"en_cours": 1, "decides": 0, "suivis": 0, "acceptes_avant": 1,
                                    "acceptes_a_corriger": 1, "acceptes_a_rejeter": 0}
    detail = c.get("/api/exercices/qcm-c").json()["prerelecture"]
    assert (detail["libelle"], detail["motifs"], detail["precisions"]) == ("à corriger", ["plusieurs_justes"], "Q2.")
    assert c.get("/api/exercices/qcm-a").json()["prerelecture"] is None
    assert c.post("/api/exercices/qcm-c/decision", json={"decision": "rejeter", "motifs": ["plusieurs_justes"]}).status_code == 200
    assert banque.charger("qcm-c")["meta"]["decisions"][-1]["avis_prerelecture"] == "a_corriger"
    assert c.get("/api/entrainement").json()["prerelecture"]["decides"] == 1


# --- la commande, la fiche du jeu ---------------------------------------------------------------------------

def test_la_commande_prerelecture(lot, tmp_path, monkeypatch, capsys):
    entrainement.utiliser()  # le lot : tmp_path/entrainement/banque/instances
    dossier = config.chemin("banque")
    _ranger(dossier, "qcm-a")
    _ranger(dossier, "qcm-b", "rejete", decisions=[{"statut": "rejete"}])
    paquet = _paquet(tmp_path / "p.jsonl", _avis("qcm-a", "bon", fausses=()), _avis("qcm-b", "a_rejeter"))
    monkeypatch.setattr(sys, "argv", ["entrainement", "prerelecture", str(paquet)])
    cli.main()
    assert capsys.readouterr().out.strip() == ("2 avis enregistrés : 1 bon(s), 0 à corriger, 1 à rejeter ; dont 1 sur des "
                                               "exercices déjà décidés (leur statut ne change pas).")
    assert banque.charger("qcm-a")["meta"]["prerelecture"]["avis"] == "bon"
    monkeypatch.setattr(sys, "argv", ["entrainement", "prerelecture", str(_paquet(tmp_path / "q.jsonl", _avis("qcm-z")))])
    with pytest.raises(SystemExit, match="ligne 1 : exercice « qcm-z » introuvable"):
        cli.main()


def test_la_fiche_dit_que_les_decisions_ont_ete_aidees():
    m = {"date": "2026-11-05T12:00:00", "graine": 1, "part_procedurale": 1 / 3, "objectif": 300, "paires": 0,
         "a_eviter": 0, "ecartes": [], "jeux": {"train": [], "valid": [], "test": []},
         "relecture": {"relus": 150, "decides": 146, "suivis": 131}}
    texte = jeu.fiche(m, [])
    assert ("- **Une seule personne a relu et décidé** (le développeur du projet), pas des enseignants en classe ; 146 des "
            "150 exercices relus du lot l'ont été après une pré-relecture de Claude (Opus 5.5)") in texte
    assert "suivi 131 fois. Les décisions restent humaines, mais aidées." in texte
    del m["relecture"]  # un jeu d'avant la pré-relecture
    assert "pas des enseignants en classe.\n" in jeu.fiche(m, [])


# --- les corrections de Claude (choix de l'enseignant du 05/11) ---------------------------------------------------

Q2_CORRIGEE = {"enonce": "Un triangle rectangle a pour côtés de l'angle droit 6 cm et 8 cm. Quelle est la longueur de "
                         "l'hypoténuse ?", "propositions": ["14 cm", "48 cm", "10 cm", "100 cm"], "index_correct": 2,
               "explication": "6² + 8² = 36 + 64 = 100, et 100 = 10², donc l'hypoténuse mesure 10 cm."}


def test_claude_corrige_une_question_jugee_fausse_et_l_enseignant_la_verifie(lot, tmp_path):
    _ranger(lot, "qcm-a", "accepte", decisions=[{"statut": "accepte", "date": "2026-11-05T12:00:00"}])
    _ranger(lot, "qcm-b")
    prerelecture.importer(_paquet(tmp_path / "p.jsonl", _avis("qcm-a"), _avis("qcm-b", "bon", fausses=())))
    autre = copy.deepcopy(Q2_CORRIGEE)
    corrections = _paquet(tmp_path / "c.jsonl",
                          {"id": "qcm-a", "numero": 2, "question": Q2_CORRIGEE},
                          {"id": "qcm-a", "numero": 1, "question": Q2_CORRIGEE},       # jugée juste : rien à corriger
                          {"id": "qcm-b", "numero": 2, "question": Q2_CORRIGEE},       # avis « bon »
                          {"id": "qcm-a", "numero": 2, "question": "à la main"},       # pas une question
                          {"id": "qcm-a", "numero": 2, "question": autre | {"propositions": ["10 cm"]}})  # N2 la refuse
    r = prerelecture.corriger(corrections)
    assert r["appliquees"] == [("qcm-a", 2)]
    assert len(r["refusees"]) == 4 and "n'est pas jugée fausse" in r["refusees"][0] and "n'est pas jugée fausse" in r["refusees"][1]
    assert "la question corrigée entière" in r["refusees"][2] and "a changé depuis l'avis" in r["refusees"][3]
    a = banque.charger("qcm-a")
    assert a["questions"][1]["propositions"][2] == "10 cm" and a["questions"][1]["difficulte"] == "facile"
    assert a["meta"]["statut"] == "genere" and prerelecture.en_cours(a)  # de nouveau à vérifier et à accepter
    assert a["meta"]["modifications"][-1]["par"] == "Claude (Opus 5.5)"
    v = prerelecture.vue(a)
    assert [q["corrigee_par_claude"] for q in v["questions"]] == [False, True, False] and v["corrections"] == 1
    q2 = banque.relecture(a)["questions"][1]
    assert (q2["modifiee"], q2["corrigee_par"], q2["calcul"]) == (True, "Claude (Opus 5.5)", "claude")
    banque.decider("qcm-a", "accepter")
    assert prerelecture.suivi(banque.charger("qcm-a")) is True  # à corriger, corrigé, accepté : l'avis est suivi
    c = relecture.compter(relecture.instances(lot), [])
    assert (c["corrections"], c["corrections_claude"]) == (1, 1)
    paires = jeu.paires(banque.charger("qcm-a"), "lot")
    assert [p["corrige_par"] for p in paires] == ["Claude (Opus 5.5)"]


def test_une_correction_de_l_enseignant_reste_la_sienne(lot, tmp_path):
    _ranger(lot, "qcm-a")
    prerelecture.importer(_paquet(tmp_path / "p.jsonl", _avis("qcm-a")))
    banque.modifier_question("qcm-a", 2, Q2_CORRIGEE)
    a = banque.charger("qcm-a")
    assert "par" not in a["meta"]["modifications"][-1] and banque.relecture(a)["questions"][1]["calcul"] == "enseignant"
    assert (prerelecture.vue(a)["questions"][1]["modifiee"], prerelecture.vue(a)["questions"][1]["corrigee_par_claude"]) == (True, False)
    assert jeu.paires(a, "lot")[0]["corrige_par"] == "enseignant"
    # la question a changé : Claude ne la corrige plus
    r = prerelecture.corriger(_paquet(tmp_path / "c.jsonl", {"id": "qcm-a", "numero": 2, "question": Q2_CORRIGEE}))
    assert r["appliquees"] == [] and "a changé depuis l'avis" in r["refusees"][0]


def test_la_commande_corriger_et_la_fiche(lot, tmp_path, monkeypatch, capsys):
    entrainement.utiliser()
    _ranger(config.chemin("banque"), "qcm-a", "accepte", decisions=[{"statut": "accepte"}])
    prerelecture.importer(_paquet(tmp_path / "p.jsonl", _avis("qcm-a")))
    monkeypatch.setattr(sys, "argv", ["entrainement", "corriger", str(_paquet(tmp_path / "c.jsonl",
                                      {"id": "qcm-a", "numero": 2, "question": Q2_CORRIGEE},
                                      {"id": "qcm-a", "numero": 3, "question": Q2_CORRIGEE}))])
    cli.main()
    sortie = capsys.readouterr().out
    assert sortie.startswith("1 question(s) corrigée(s) dans 1 exercice(s) : ils sont de nouveau en cours de relecture")
    assert "1 refusée(s) :\n- ligne 2 (qcm-a, question 3) : la question 3 n'est pas jugée fausse" in sortie
    m = {"date": "2026-11-05T12:00:00", "graine": 1, "part_procedurale": 1 / 3, "objectif": 300, "paires": 3,
         "paires_claude": 2, "a_eviter": 0, "ecartes": [], "jeux": {"train": [], "valid": [], "test": []}}
    texte = jeu.fiche(m, [])
    assert "dont 2 corrections écrites par Claude (Opus 5.5) d'après sa pré-relecture, vérifiées et acceptées" in texte
    assert "c'est de la distillation, pas un jugement humain." in texte
    assert "celles de l'enseignant." in jeu.fiche(m | {"paires_claude": 0}, [])
