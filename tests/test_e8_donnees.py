"""E8, les données du serveur de classe : mots de passe des classes de collège (codes.py, classes.py), connexion des
élèves (connexion_eleve.py), exercices publiés (publications.py), réponses une à une et première tentative seule
comptée (suivi.py). Le serveur lui-même : tests/test_classe_serveur.py."""

import json

import pytest

from generateur.donnees import classes, codes, comptes, connexion_eleve, journal, publications, suivi
from generateur.donnees.base import Base
from generateur.moteur import banque, config, registre

CLE = b"k" * 32


@pytest.fixture
def base(tmp_path, monkeypatch):
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    base = Base(tmp_path / "arrera.sqlite3")
    comptes.creer(base, "prof", "Professeur", "un mot de passe de test", "admin")
    comptes.creer(base, "autre", "Autre professeur", "un autre mot de passe")
    return base


@pytest.fixture
def prof(base):
    return comptes.lire(base, "prof")


@pytest.fixture
def autre(base):
    return comptes.lire(base, "autre")


def classe(base, compte, nom="6e B", niveau="6e", noms=(("DUPONT", "Marie"), ("MARTIN", "Lucas"), ("DURAND", "Marie"))):
    return classes.creer(base, compte, nom, niveau, "2026-2027", [{"nom": n, "prenom": p} for n, p in noms], CLE)


def exercice_en_banque(ident="qcm-essai", statut="accepte", titre="Essai"):
    instance = json.loads(json.dumps(registre.charger("qcm").exemple))
    instance.update(titre=titre, niveau="6e")
    instance["meta"] = {"id": ident, "statut": statut, "date": "2026-10-27T10:00:00"}
    banque.ecrire(instance)
    return instance


def saisie(carte):
    """Ce que l'élève tape : les 4 images de sa carte, ou son mot de passe."""
    return [i["image"] for i in carte["code"]] if carte["connexion"] == "images" else carte["mot_de_passe"]


# --- les mots de passe du collège --------------------------------------------------------------------------

def test_un_mot_de_passe_tire_au_sort():
    mots = {codes.tirer_mot_de_passe() for _ in range(200)}
    assert len(mots) > 190  # ~185 000 possibilités
    for mot in mots:
        nom, adjectif, nombre = mot.split("-")
        assert nom in codes.NOMS and adjectif in codes.ADJECTIFS and 10 <= int(nombre) <= 99


@pytest.mark.parametrize("tape", ["tigre-bleu-27", "Tigre Bleu 27", "TIGRE-BLEU27", " tigre_bleu-27 ", "tîgre-bleu-27"])
def test_majuscules_espaces_et_tirets_oublies_sont_pardonnes(tape):
    assert codes.verifier(tape, codes.empreinte("tigre-bleu-27", CLE), CLE)


def test_un_mot_de_passe_faux_ou_vide_est_refuse():
    enregistree = codes.empreinte("tigre-bleu-27", CLE)
    for faux in ("tigre-bleu-28", "", "   ", "----", None):
        assert not codes.verifier(faux, enregistree, CLE)
    assert not codes.verifier("tigre-bleu-27", enregistree, b"z" * 32)  # sans la clé de l'installation, rien


def test_un_code_d_images_ne_vaut_pas_un_mot_de_passe():
    assert not codes.verifier("0-1-2-3", codes.empreinte((0, 1, 2, 3), CLE), CLE)


@pytest.mark.parametrize("niveau, connexion", [("6e", "images"), ("5e", "mot_de_passe"), ("4e", "mot_de_passe"), ("3e", "mot_de_passe")])
def test_la_connexion_suit_le_niveau_de_la_classe(base, prof, niveau, connexion):
    vue, cartes = classe(base, prof, f"{niveau} B", niveau)
    assert vue["connexion"] == connexion and all(c["connexion"] == connexion for c in cartes)
    if connexion == "mot_de_passe":
        assert all("code" not in c and c["mot_de_passe"].count("-") == 2 for c in cartes)
        with base.lire() as conn:
            empreintes = [r[0] for r in conn.execute("SELECT code FROM eleve")]
        assert not any(c["mot_de_passe"] in e for c in cartes for e in empreintes)  # jamais en clair
    # un nouveau code (élève, classe, ajout) garde la sorte de la classe
    seul = classes.nouveau_code(base, prof, cartes[0]["eleve_id"], CLE)
    toute = classes.nouveaux_codes(base, prof, vue["id"], CLE)
    ajout = classes.ajouter(base, prof, vue["id"], [{"nom": "NOUVEAU", "prenom": "Élève"}], CLE)
    assert {c["connexion"] for c in [seul, *toute, *ajout]} == {connexion}


# --- se connecter -------------------------------------------------------------------------------------

def test_les_classes_ouvertes_et_les_noms_affiches(base, prof):
    vue, _ = classe(base, prof)
    vide, _ = classe(base, prof, "5e Vide", "5e", ())
    archivee, _ = classe(base, prof, "4e Ancienne", "4e")
    classes.archiver(base, prof, archivee["id"], True)
    assert [c["nom"] for c in connexion_eleve.classes_ouvertes(base)] == ["6e B"]
    noms = [e["nom"] for e in connexion_eleve.eleves_de_la_classe(base, vue["id"])["eleves"]]
    assert noms == ["Lucas M.", "Marie D. (n° 1)", "Marie D. (n° 3)"]  # deux « Marie D. » : le numéro les distingue
    with pytest.raises(connexion_eleve.Introuvable):
        connexion_eleve.eleves_de_la_classe(base, archivee["id"])


@pytest.mark.parametrize("niveau", ["6e", "4e"])
def test_se_connecter_avec_sa_carte(base, prof, niveau):
    _, cartes = classe(base, prof, f"{niveau} B", niveau)
    jeton, eleve = connexion_eleve.connecter(base, cartes[1]["eleve_id"], saisie(cartes[1]), CLE)
    assert eleve == {"id": cartes[1]["eleve_id"], "prenom": "Lucas", "nom": "Lucas M.", "classe_id": eleve["classe_id"],
                     "classe": f"{niveau} B", "niveau": niveau}
    assert connexion_eleve.session(base, jeton)["id"] == cartes[1]["eleve_id"]
    with pytest.raises(connexion_eleve.ConnexionRefusee):  # la carte d'un autre élève ne marche pas
        connexion_eleve.connecter(base, cartes[0]["eleve_id"], saisie(cartes[1]), CLE)


def test_cinq_essais_manques_bloquent_l_eleve_jusqu_au_deblocage(base, prof):
    vue, cartes = classe(base, prof, "5e B", "5e")
    eleve = cartes[0]["eleve_id"]
    for restants in (4, 3, 2, 1):
        with pytest.raises(connexion_eleve.ConnexionRefusee, match=f"il te reste {restants} essai") as refus:
            connexion_eleve.connecter(base, eleve, "lion-vert-11", CLE)
        assert refus.value.restants == restants and not isinstance(refus.value, connexion_eleve.EleveBloque)
    with pytest.raises(connexion_eleve.EleveBloque):
        connexion_eleve.connecter(base, eleve, "lion-vert-11", CLE)
    with pytest.raises(connexion_eleve.EleveBloque):  # bloqué : même le bon mot de passe est refusé
        connexion_eleve.connecter(base, eleve, saisie(cartes[0]), CLE)
    assert classes.lire(base, prof, vue["id"])["liste"][0]["bloque"]  # l'enseignant le voit bloqué
    classes.debloquer(base, prof, eleve)
    connexion_eleve.connecter(base, eleve, saisie(cartes[0]), CLE)
    actions = [e["action"] for e in journal.lire(base)]
    assert actions.count("connexion_eleve_echec") == 4 and "eleve_bloque" in actions and "eleve_debloque" in actions


def test_une_bonne_connexion_remet_les_essais_a_zero(base, prof):
    _, cartes = classe(base, prof)
    eleve = cartes[0]["eleve_id"]
    for _ in range(4):
        with pytest.raises(connexion_eleve.ConnexionRefusee):
            connexion_eleve.connecter(base, eleve, ["pomme"] * 4, CLE)  # jamais tiré : 4 fois la même image
    connexion_eleve.connecter(base, eleve, saisie(cartes[0]), CLE)
    with base.lire() as conn:
        assert tuple(conn.execute("SELECT echecs, bloque FROM eleve WHERE id = ?", (eleve,)).fetchone()) == (0, 0)


def test_un_nouveau_code_debloque_et_ferme_les_sessions(base, prof):
    _, cartes = classe(base, prof)
    jeton, _ = connexion_eleve.connecter(base, cartes[0]["eleve_id"], saisie(cartes[0]), CLE)
    carte = classes.nouveau_code(base, prof, cartes[0]["eleve_id"], CLE)
    assert connexion_eleve.session(base, jeton) is None  # l'ancienne carte (vue par un autre ?) ne sert plus
    connexion_eleve.connecter(base, cartes[0]["eleve_id"], saisie(carte), CLE)


@pytest.mark.parametrize("saisie_fausse", [None, 42, "x" * 101, ["soleil"] * 3, ["soleil", "lune", "etoile", "inconnue"], [1, 2, 3, 4], {"a": 1}])
def test_une_saisie_mal_formee_compte_comme_un_echec(base, prof, saisie_fausse):
    _, cartes = classe(base, prof)
    with pytest.raises(connexion_eleve.ConnexionRefusee):
        connexion_eleve.connecter(base, cartes[0]["eleve_id"], saisie_fausse, CLE)


def test_la_session_expire_apres_10_minutes_sans_activite(base, prof):
    _, cartes = classe(base, prof)
    jeton, _ = connexion_eleve.connecter(base, cartes[0]["eleve_id"], saisie(cartes[0]), CLE, maintenant=1000.0)
    assert connexion_eleve.session(base, jeton, maintenant=1000.0 + 9 * 60)  # repousse l'expiration
    assert connexion_eleve.session(base, jeton, maintenant=1000.0 + 18 * 60)
    assert connexion_eleve.session(base, jeton, maintenant=1000.0 + 28 * 60 + 1) is None
    assert connexion_eleve.session(base, jeton, maintenant=1000.0 + 29 * 60) is None  # effacée


def test_une_seule_session_par_eleve_et_la_deconnexion(base, prof):
    _, cartes = classe(base, prof)
    premier, _ = connexion_eleve.connecter(base, cartes[0]["eleve_id"], saisie(cartes[0]), CLE)
    second, _ = connexion_eleve.connecter(base, cartes[0]["eleve_id"], saisie(cartes[0]), CLE)
    assert connexion_eleve.session(base, premier) is None and connexion_eleve.session(base, second)
    connexion_eleve.deconnecter(base, second)
    assert connexion_eleve.session(base, second) is None
    assert connexion_eleve.session(base, None) is None and connexion_eleve.session(base, "x" * 500) is None


def test_desactive_ou_archive_ne_se_connecte_plus(base, prof):
    vue, cartes = classe(base, prof)
    jeton, _ = connexion_eleve.connecter(base, cartes[0]["eleve_id"], saisie(cartes[0]), CLE)
    classes.activer(base, prof, cartes[0]["eleve_id"], False)
    assert connexion_eleve.session(base, jeton) is None
    with pytest.raises(connexion_eleve.Introuvable):
        connexion_eleve.connecter(base, cartes[0]["eleve_id"], saisie(cartes[0]), CLE)
    jeton, _ = connexion_eleve.connecter(base, cartes[1]["eleve_id"], saisie(cartes[1]), CLE)
    classes.archiver(base, prof, vue["id"], True)
    assert connexion_eleve.session(base, jeton) is None


def test_ni_code_ni_nom_dans_le_journal(base, prof):
    _, cartes = classe(base, prof, "4e B", "4e")
    with pytest.raises(connexion_eleve.ConnexionRefusee):
        connexion_eleve.connecter(base, cartes[0]["eleve_id"], "le-mot-tape-99", CLE)
    connexion_eleve.connecter(base, cartes[0]["eleve_id"], saisie(cartes[0]), CLE)
    with base.lire() as conn:
        lignes = " ".join(str(tuple(r)) for r in conn.execute("SELECT * FROM journal"))
    assert "le-mot-tape" not in lignes and cartes[0]["mot_de_passe"] not in lignes and "DUPONT" not in lignes


# --- publier --------------------------------------------------------------------------------------------

def test_seul_un_exercice_accepte_se_publie(base, prof):
    vue, _ = classe(base, prof)
    exercice_en_banque("qcm-a-relire", statut="genere")
    with pytest.raises(classes.ClasseInvalide, match="accepté"):
        publications.publier(base, prof, "qcm-a-relire", vue["id"])
    with pytest.raises(classes.Introuvable):
        publications.publier(base, prof, "qcm-absent", vue["id"])


def test_publier_pour_une_classe_un_groupe_ou_un_eleve(base, prof, autre):
    vue, cartes = classe(base, prof)
    marie, lucas, marie2 = (c["eleve_id"] for c in cartes)
    for ident in ("qcm-classe", "qcm-groupe", "qcm-eleve"):
        exercice_en_banque(ident, titre=ident)
    groupe = suivi.creer_groupe(base, prof, vue["id"], "Mardi", None, "approfondir", [lucas])
    publications.publier(base, prof, "qcm-classe", vue["id"])
    publications.publier(base, prof, "qcm-groupe", vue["id"], groupe_id=groupe["id"])
    publications.publier(base, prof, "qcm-eleve", vue["id"], eleve_id=marie2)
    voit = lambda e: [c["exercice"] for c in publications.pour_l_eleve(base, {"id": e, "classe_id": vue["id"]})["exercices"]]
    assert sorted(voit(marie)) == ["qcm-classe"]
    assert sorted(voit(lucas)) == ["qcm-classe", "qcm-groupe"]
    assert sorted(voit(marie2)) == ["qcm-classe", "qcm-eleve"]
    assert [p["pour"] for p in publications.lister(base, prof, vue["id"])] == ["Marie DURAND", "groupe « Mardi »", "toute la classe"]
    with pytest.raises(classes.Introuvable):  # la classe d'un autre enseignant
        publications.publier(base, autre, "qcm-classe", vue["id"])
    autre_classe, autres = classe(base, autre, "5e Z", "5e")
    with pytest.raises(classes.Introuvable):  # un élève d'une autre classe
        publications.publier(base, prof, "qcm-classe", vue["id"], eleve_id=autres[0]["eleve_id"])


def test_qui_l_a_fait_parmi_les_eleves_concernes_et_l_etat_de_la_publication(base, prof):
    vue, cartes = classe(base, prof)
    marie, lucas, marie2 = (c["eleve_id"] for c in cartes)
    instance = exercice_en_banque("qcm-faits")
    groupe = suivi.creer_groupe(base, prof, vue["id"], "Jeudi", None, "consolider", [lucas, marie2])
    publications.publier(base, prof, "qcm-faits", vue["id"], groupe_id=groupe["id"], debut="2026-11-03", fin="2026-11-14")
    suivi.commencer_tentative(base, marie, instance)   # hors du groupe : ne compte pas
    suivi.commencer_tentative(base, lucas, instance)
    vue_pub = lambda jour: publications.lister(base, prof, vue["id"], jour)[0]
    p = vue_pub("2026-11-05")
    assert (p["concernes"], p["faits"], p["etat"], p["visible"]) == (2, 1, "en_cours", True)
    assert (vue_pub("2026-11-02")["etat"], vue_pub("2026-11-14")["etat"], vue_pub("2026-11-15")["etat"]) == ("a_venir", "en_cours", "terminee")
    classes.activer(base, prof, marie2, False)  # un élève désactivé n'est plus attendu
    assert vue_pub("2026-11-05")["concernes"] == 1
    assert [x["classe"] for x in publications.de_l_exercice(base, prof, "qcm-faits")] == ["6e B"]
    instance["meta"]["statut"] = "genere"  # modifié depuis : caché aux élèves, signalé à l'enseignant
    banque.ecrire(instance)
    assert vue_pub("2026-11-05")["visible"] is False
    classes.archiver(base, prof, vue["id"], True)
    assert publications.de_l_exercice(base, prof, "qcm-faits") == []


def test_les_eleves_bloques(base, prof, autre):
    vue, cartes = classe(base, prof)
    with base.ecrire() as conn:
        conn.execute("UPDATE eleve SET bloque = 1 WHERE id IN (?, ?)", (cartes[0]["eleve_id"], cartes[2]["eleve_id"]))
    assert [(b["prenom"], b["classe"]) for b in classes.bloques(base, prof)] == [("Marie", "6e B"), ("Marie", "6e B")]
    assert classes.bloques(base, autre) == []
    classes.activer(base, prof, cartes[2]["eleve_id"], False)  # désactivé : plus rien à débloquer
    assert len(classes.bloques(base, prof)) == 1
    classes.debloquer(base, prof, cartes[0]["eleve_id"])
    assert classes.bloques(base, prof) == []


def test_les_dates_de_debut_et_de_fin(base, prof):
    vue, cartes = classe(base, prof)
    exercice_en_banque("qcm-date")
    publications.publier(base, prof, "qcm-date", vue["id"], debut="2026-11-02", fin="2026-11-06")
    eleve = {"id": cartes[0]["eleve_id"], "classe_id": vue["id"]}
    assert [publications.autorise(base, eleve, "qcm-date", jour) for jour in ("2026-11-01", "2026-11-02", "2026-11-06", "2026-11-07")] == \
        [False, True, True, False]
    for debut, fin in (("2026-13-01", None), ("demain", None), ("2026-11-06", "2026-11-02")):
        with pytest.raises(classes.ClasseInvalide):
            publications.publier(base, prof, "qcm-date", vue["id"], debut=debut, fin=fin)


def test_les_exercices_valides_par_l_enseignant_viennent_en_tete(base, prof):
    vue, cartes = classe(base, prof)
    exercice_en_banque("qcm-a-retravailler")
    exercice_en_banque("qcm-plus-loin")
    exercice_en_banque("qcm-publie")
    with base.ecrire() as conn:
        conn.executemany("INSERT INTO proposition (eleve_id, nature, attendu, exercice, cree) VALUES (?, ?, ?, ?, ?)",
                         [(cartes[0]["eleve_id"], "retravailler", "maths.6e.fractions.09", "qcm-a-retravailler", "2026-10-27"),
                          (cartes[0]["eleve_id"], "plus_loin", "maths.6e.fractions.09", "qcm-plus-loin", "2026-10-27")])
    publications.publier(base, prof, "qcm-publie", vue["id"])
    publications.publier(base, prof, "qcm-a-retravailler", vue["id"])  # déjà en tête : pas deux fois
    accueil = publications.pour_l_eleve(base, {"id": cartes[0]["eleve_id"], "classe_id": vue["id"]})
    assert [[c["exercice"] for c in accueil[s]] for s in ("a_retravailler", "plus_loin", "exercices")] == \
        [["qcm-a-retravailler"], ["qcm-plus-loin"], ["qcm-publie"]]
    assert accueil["a_retravailler"][0]["difficulte"] == "facile" and accueil["exercices"][0]["fait"] is None


def test_un_exercice_modifie_depuis_disparait_jusqu_a_sa_nouvelle_acceptation(base, prof):
    vue, cartes = classe(base, prof)
    instance = exercice_en_banque("qcm-modifie")
    publications.publier(base, prof, "qcm-modifie", vue["id"])
    instance["meta"]["statut"] = "genere"
    banque.ecrire(instance)
    assert not publications.autorise(base, {"id": cartes[0]["eleve_id"], "classe_id": vue["id"]}, "qcm-modifie")


def test_retirer_une_publication(base, prof, autre):
    vue, cartes = classe(base, prof)
    exercice_en_banque("qcm-retire")
    p = publications.publier(base, prof, "qcm-retire", vue["id"])
    with pytest.raises(classes.Introuvable):
        publications.retirer(base, autre, p["id"])
    publications.retirer(base, prof, p["id"])
    assert not publications.autorise(base, {"id": cartes[0]["eleve_id"], "classe_id": vue["id"]}, "qcm-retire")


def test_publier_en_ligne_de_commande(base, capsys):
    base = Base(config.chemin("base"))  # celle que lit la ligne de commande (une copie de travail du test)
    comptes.creer(base, "prof", "Professeur", "un mot de passe de test", "admin")
    vue, _ = classe(base, comptes.lire(base, "prof"), nom="6e Démo")
    exercice_en_banque("qcm-cli")
    exercice_en_banque("qcm-cli-brouillon", statut="genere")
    assert publications.main(["prof", "qcm-cli", "--classe", "6e Démo"]) == 0
    assert "publié : « Essai » pour 6e Démo (toute la classe)" in capsys.readouterr().out
    assert publications.main(["prof", "qcm-cli-brouillon", "--classe", "6e Démo"]) == 1
    assert "seul un exercice accepté se publie" in capsys.readouterr().out
    assert publications.main(["prof", "qcm-cli", "--classe", "5e Z"]) == 1
    assert publications.main(["personne", "qcm-cli", "--classe", "6e Démo"]) == 1
    assert [p["exercice"] for p in publications.lister(base, comptes.lire(base, "prof"), vue["id"])] == ["qcm-cli"]


# --- répondre, une question à la fois ----------------------------------------------------------------------

def test_les_reponses_une_a_une_sont_recalculees(base, prof):
    _, cartes = classe(base, prof)
    instance = exercice_en_banque("qcm-reponses")
    eleve = cartes[0]["eleve_id"]
    t = suivi.commencer_tentative(base, eleve, instance)
    assert t["compte"] is True
    bonne = instance["questions"][0]["index_correct"]
    assert suivi.ajouter_reponse(base, eleve, t["id"], instance, 1, bonne, 4.2) == {"juste": True, "correct": bonne}
    assert suivi.ajouter_reponse(base, eleve, t["id"], instance, 2, (instance["questions"][1]["index_correct"] + 1) % 3, None)["juste"] is False
    with pytest.raises(classes.ClasseInvalide, match="déjà répondue"):
        suivi.ajouter_reponse(base, eleve, t["id"], instance, 1, bonne, 1)
    for numero, choix, temps in ((0, 0, 1), (99, 0, 1), (3, 9, 1), (3, True, 1), (3, 0, -1), (3, 0, 99999), ("1", 0, 1)):
        with pytest.raises(classes.ClasseInvalide):
            suivi.ajouter_reponse(base, eleve, t["id"], instance, numero, choix, temps)


def test_la_tentative_d_un_autre_ou_d_une_autre_version_est_refusee(base, prof):
    _, cartes = classe(base, prof)
    instance = exercice_en_banque("qcm-version")
    t = suivi.commencer_tentative(base, cartes[0]["eleve_id"], instance)
    with pytest.raises(classes.Introuvable):  # un autre élève ne répond pas dans ma tentative
        suivi.ajouter_reponse(base, cartes[1]["eleve_id"], t["id"], instance, 1, 0, 1)
    change = json.loads(json.dumps(instance))
    change["questions"][0]["enonce"] += " (modifié)"
    with pytest.raises(classes.Introuvable):  # l'exercice a changé depuis le début de la tentative
        suivi.ajouter_reponse(base, cartes[0]["eleve_id"], t["id"], change, 1, 0, 1)


def test_seule_la_premiere_tentative_compte_dans_le_suivi(base, prof):
    vue, cartes = classe(base, prof)
    instance = exercice_en_banque("qcm-rejoue")
    instance["meta"]["programme"] = {"attendus": ["maths.6e.fractions.09"], "choisi": True}
    eleve = cartes[0]["eleve_id"]
    premiere = suivi.commencer_tentative(base, eleve, instance)
    for n, q in enumerate(instance["questions"], start=1):
        suivi.ajouter_reponse(base, eleve, premiere["id"], instance, n, (q["index_correct"] + 1) % len(q["propositions"]), None)
    seconde = suivi.commencer_tentative(base, eleve, instance)
    assert seconde["compte"] is False
    for n, q in enumerate(instance["questions"], start=1):
        suivi.ajouter_reponse(base, eleve, seconde["id"], instance, n, q["index_correct"], None)
    case = suivi.fiche(base, prof, eleve)["attendus"][0]
    assert case["justes"] == 0 and case["vues"] == len(instance["questions"])  # l'entraînement ne compte pas
    assert [t["compte"] for t in suivi.fiche(base, prof, eleve)["tentatives"]] == [False, True]
    resultat = publications._resultat
    with base.lire() as conn:
        assert resultat(conn, eleve, "qcm-rejoue")["justes"] == 0  # l'accueil montre la tentative qui compte
    # annulée (faite par erreur), la première ne compte plus : la suivante devient la première
    with base.lire() as conn:
        assert conn.execute("SELECT compte FROM tentative WHERE id = ?", (seconde["id"],)).fetchone()[0] == 0
    suivi.annuler_tentative(base, prof, premiere["id"])
    troisieme = suivi.commencer_tentative(base, eleve, instance)
    assert troisieme["compte"] is True
