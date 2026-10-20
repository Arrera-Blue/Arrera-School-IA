"""E1 : comptes enseignants et connexion (generateur/donnees/comptes.py, sessions.py) ; menaces M1 à M4, M25."""

import hashlib
import unicodedata

import pytest

from generateur.donnees import comptes, journal, sessions
from generateur.donnees.base import Base
from generateur.moteur import config

MOT_DE_PASSE = "correct cheval pile agrafe"


@pytest.fixture
def base(tmp_path):
    base = Base(tmp_path / "arrera.sqlite3")
    comptes.creer(base, "m.dupont", "M. Dupont", MOT_DE_PASSE, "admin")
    return base


# --- mots de passe (SEC-3) ------------------------------------------------------------------------

def test_scrypt_aux_parametres_recommandes(monkeypatch):
    assert comptes.SCRYPT_RECOMMANDE == {"n": 2 ** 17, "r": 8, "p": 1}  # OWASP : n ≥ 2¹⁷, r = 8, p = 1
    monkeypatch.setattr(comptes, "SCRYPT", comptes.SCRYPT_RECOMMANDE)
    empreinte = comptes.empreinte(MOT_DE_PASSE)  # le vrai coût : ~0,3 s, 128 Mo
    assert empreinte.startswith("scrypt$131072$8$1$")
    assert comptes.verifier_mot_de_passe(MOT_DE_PASSE, empreinte)


def test_empreinte_salee_et_verifiable():
    a, b = comptes.empreinte(MOT_DE_PASSE), comptes.empreinte(MOT_DE_PASSE)
    assert a != b  # un sel par compte : deux comptes, même mot de passe, empreintes différentes
    assert MOT_DE_PASSE not in a
    assert comptes.verifier_mot_de_passe(MOT_DE_PASSE, a)
    assert not comptes.verifier_mot_de_passe(MOT_DE_PASSE + "!", a)
    for cassee in ("", "scrypt$1$2", "md5$x$y$z$a$b", "scrypt$abc$8$1$AAAA$AAAA"):
        assert not comptes.verifier_mot_de_passe(MOT_DE_PASSE, cassee)


def test_empreinte_garde_ses_parametres(monkeypatch):
    ancienne = comptes.empreinte(MOT_DE_PASSE)
    monkeypatch.setattr(comptes, "SCRYPT", {"n": 2 ** 11, "r": 8, "p": 1})  # paramètres durcis plus tard
    assert comptes.verifier_mot_de_passe(MOT_DE_PASSE, ancienne)


def test_accents_composes_ou_decomposes():
    compose = "mot de passe élève"
    empreinte = comptes.empreinte(compose)
    assert comptes.verifier_mot_de_passe(unicodedata.normalize("NFD", compose), empreinte)


@pytest.mark.parametrize("mot_de_passe, message", [("court", "trop court"), ("x" * 129, "trop long"),
                                                   ("M.Dupont    ", "l'identifiant")])
def test_mots_de_passe_refuses(mot_de_passe, message):
    with pytest.raises(comptes.CompteInvalide, match=message):
        comptes.controler_mot_de_passe(mot_de_passe, "m.dupont")


def test_mot_de_passe_provisoire():
    provisoire = comptes.provisoire()
    assert len(provisoire) == 19 and provisoire.count("-") == 3
    assert not set(provisoire.replace("-", "")) - set(comptes.ALPHABET_PROVISOIRE)
    comptes.controler_mot_de_passe(provisoire)


@pytest.mark.parametrize("identifiant", ["a", "Élève", "m dupont", "-x", "x" * 41, "a;DROP", ""])
def test_identifiants_refuses(identifiant):
    with pytest.raises(comptes.CompteInvalide):
        comptes.controler_identifiant(identifiant)


def test_identifiant_en_minuscules_et_nom_nettoye():
    assert comptes.controler_identifiant("  M.Dupont ") == "m.dupont"
    assert comptes.controler_nom("  M.   Dupont ") == "M. Dupont"
    with pytest.raises(comptes.CompteInvalide):
        comptes.controler_nom("M. Dupont\x07")


# --- les comptes ----------------------------------------------------------------------------------

def test_creer_lister_sans_empreinte(base):
    comptes.creer(base, "a.martin", "A. Martin", "un autre mot de passe")
    liste = comptes.lister(base)
    assert [c["identifiant"] for c in liste] == ["a.martin", "m.dupont"]
    assert all("empreinte" not in c for c in liste) and liste[0]["role"] == "enseignant"
    with pytest.raises(comptes.CompteInvalide, match="existe déjà"):
        comptes.creer(base, "A.Martin", "Autre", "un autre mot de passe")
    with pytest.raises(comptes.CompteInvalide, match="rôle"):
        comptes.creer(base, "b.durand", "B. Durand", "un autre mot de passe", "eleve")


def test_le_dernier_administrateur_reste(base):
    with pytest.raises(comptes.CompteInvalide, match="dernier compte administrateur"):
        comptes.supprimer(base, "m.dupont")
    comptes.creer(base, "admin2", "Second admin", "un autre mot de passe", "admin")
    comptes.supprimer(base, "m.dupont")
    assert comptes.lire(base, "m.dupont") is None
    with pytest.raises(comptes.CompteInconnu):
        comptes.supprimer(base, "m.dupont")


def test_reinitialiser(base):
    jeton, _ = sessions.connecter(base, "m.dupont", MOT_DE_PASSE)
    provisoire = comptes.reinitialiser(base, "m.dupont")
    assert sessions.session(base, jeton) is None  # ses sessions sont fermées
    with pytest.raises(sessions.ConnexionRefusee):
        sessions.connecter(base, "m.dupont", MOT_DE_PASSE)
    _, compte = sessions.connecter(base, "m.dupont", provisoire)
    assert compte["doit_changer"] is True


# --- la connexion (SEC-5 à SEC-7) -----------------------------------------------------------------

def test_connexion_et_session(base):
    jeton, compte = sessions.connecter(base, " M.Dupont ", MOT_DE_PASSE)
    assert compte["identifiant"] == "m.dupont" and len(jeton) >= 43  # 32 octets
    assert sessions.session(base, jeton)["role"] == "admin"
    assert sessions.session(base, "jeton inventé") is None and sessions.session(base, None) is None
    jeton2, _ = sessions.connecter(base, "m.dupont", MOT_DE_PASSE)
    assert jeton2 != jeton  # un nouveau jeton à chaque connexion
    sessions.deconnecter(base, jeton, compte)
    assert sessions.session(base, jeton) is None and sessions.session(base, jeton2) is not None


def test_ni_jeton_ni_mot_de_passe_dans_la_base(base):
    jeton, _ = sessions.connecter(base, "m.dupont", MOT_DE_PASSE)
    with pytest.raises(sessions.ConnexionRefusee):
        sessions.connecter(base, MOT_DE_PASSE, "tapé dans le mauvais champ")
    contenu = b"".join(f.read_bytes() for f in base.chemin.parent.glob("arrera.sqlite3*"))
    for secret in (jeton, MOT_DE_PASSE, "tapé dans le mauvais champ"):
        assert secret.encode() not in contenu
    assert hashlib.sha256(jeton.encode()).hexdigest().encode() in contenu  # seulement son empreinte


def test_meme_message_identifiant_inconnu(base):
    with pytest.raises(sessions.ConnexionRefusee) as inconnu:
        sessions.connecter(base, "personne", MOT_DE_PASSE)
    with pytest.raises(sessions.ConnexionRefusee) as mauvais:
        sessions.connecter(base, "m.dupont", "mauvais mot de passe")
    assert str(inconnu.value) == str(mauvais.value) == sessions.MESSAGE


def test_meme_calcul_identifiant_inconnu(base, monkeypatch):
    """Un identifiant inconnu coûte un calcul scrypt, comme un connu : la durée ne trahit rien (M2)."""
    appels = []
    vrai = hashlib.scrypt
    monkeypatch.setattr(hashlib, "scrypt", lambda *a, **k: appels.append(1) or vrai(*a, **k))
    sessions._factice()  # l'empreinte factice est calculée une fois pour toutes
    for identifiant in ("m.dupont", "personne"):
        appels.clear()
        with pytest.raises(sessions.ConnexionRefusee):
            sessions.connecter(base, identifiant, "mauvais mot de passe")
        assert len(appels) == 1, identifiant


def test_verrou_apres_5_echecs_meme_avec_le_bon_mot_de_passe(base):
    t = 1_000_000.0
    for i in range(4):
        with pytest.raises(sessions.ConnexionRefusee) as e:
            sessions.connecter(base, "m.dupont", "mauvais", maintenant=t + i)
        assert not isinstance(e.value, sessions.CompteVerrouille)
    with pytest.raises(sessions.CompteVerrouille):
        sessions.connecter(base, "m.dupont", "mauvais", maintenant=t + 4)
    with pytest.raises(sessions.CompteVerrouille, match="15 min"):
        sessions.connecter(base, "m.dupont", MOT_DE_PASSE, maintenant=t + 5)  # le 6e essai, bon : refusé
    assert sessions.verrouille(base, "m.dupont", maintenant=t + 5)
    sessions.connecter(base, "m.dupont", MOT_DE_PASSE, maintenant=t + 4 + sessions.VERROU_S + 1)


def test_un_identifiant_inconnu_se_verrouille_aussi(base):
    t = 1_000_000.0
    for i in range(4):
        with pytest.raises(sessions.ConnexionRefusee):
            sessions.connecter(base, "personne", "x", maintenant=t + i)
    with pytest.raises(sessions.CompteVerrouille):  # comme un vrai compte : on ne peut pas les distinguer
        sessions.connecter(base, "personne", "x", maintenant=t + 4)


def test_les_echecs_s_oublient_apres_15_min(base):
    t = 1_000_000.0
    for i in range(4):
        with pytest.raises(sessions.ConnexionRefusee):
            sessions.connecter(base, "m.dupont", "mauvais", maintenant=t + i)
    with pytest.raises(sessions.ConnexionRefusee) as e:
        sessions.connecter(base, "m.dupont", "mauvais", maintenant=t + 3 + sessions.VERROU_S + 1)
    assert not isinstance(e.value, sessions.CompteVerrouille)  # le compteur est reparti de 1


def test_debloquer(base):
    t = 1_000_000.0
    for i in range(5):
        with pytest.raises(sessions.ConnexionRefusee):
            sessions.connecter(base, "m.dupont", "mauvais", maintenant=t + i)
    comptes.debloquer(base, "m.dupont")
    sessions.connecter(base, "m.dupont", MOT_DE_PASSE, maintenant=t + 6)


def test_pause_croissante(base, monkeypatch):
    pauses = []
    monkeypatch.setattr(sessions, "PAUSE_S", 0.5)
    monkeypatch.setattr(sessions.time, "sleep", pauses.append)
    for i in range(5):
        with pytest.raises(sessions.ConnexionRefusee):
            sessions.connecter(base, "m.dupont", "mauvais", maintenant=1_000_000.0 + i)
    assert pauses == [0.5, 1.0, 2.0, 4.0, 4.0]


def test_session_expiree_apres_30_min_sans_requete(base):
    t = 1_000_000.0
    jeton, _ = sessions.connecter(base, "m.dupont", MOT_DE_PASSE, maintenant=t)
    assert sessions.session(base, jeton, maintenant=t + 29 * 60)  # une requête : l'horloge repart
    assert sessions.session(base, jeton, maintenant=t + 58 * 60)
    assert sessions.session(base, jeton, maintenant=t + 89 * 60) is None
    assert sessions.session(base, jeton, maintenant=t + 59 * 60) is None  # supprimée, pas seulement refusée


def test_confirmer_compte_comme_un_echec(base):
    compte = comptes.lire(base, "m.dupont")
    sessions.confirmer(base, compte, MOT_DE_PASSE)
    for i in range(4):
        with pytest.raises(sessions.ConnexionRefusee):
            sessions.confirmer(base, compte, "mauvais", maintenant=1_000_000.0 + i)
    with pytest.raises(sessions.CompteVerrouille):
        sessions.confirmer(base, compte, "mauvais", maintenant=1_000_004.0)


def test_changer_son_mot_de_passe(base):
    ici, compte = sessions.connecter(base, "m.dupont", MOT_DE_PASSE)
    ailleurs, _ = sessions.connecter(base, "m.dupont", MOT_DE_PASSE)
    with pytest.raises(sessions.ConnexionRefusee):
        sessions.changer_mot_de_passe(base, compte, "mauvais ancien", "un tout nouveau mot de passe", ici)
    with pytest.raises(comptes.CompteInvalide, match="différent"):
        sessions.changer_mot_de_passe(base, compte, MOT_DE_PASSE, MOT_DE_PASSE, ici)
    sessions.changer_mot_de_passe(base, compte, MOT_DE_PASSE, "un tout nouveau mot de passe", ici)
    assert sessions.session(base, ici) and sessions.session(base, ailleurs) is None
    sessions.connecter(base, "m.dupont", "un tout nouveau mot de passe")


# --- le journal (SEC-10) --------------------------------------------------------------------------

def test_journal_des_acces(base):
    jeton, compte = sessions.connecter(base, "m.dupont", MOT_DE_PASSE)
    with pytest.raises(sessions.ConnexionRefusee):
        sessions.connecter(base, MOT_DE_PASSE, "x")  # un mot de passe tapé dans le champ identifiant
    sessions.deconnecter(base, jeton, compte)
    entrees = journal.lire(base)
    assert [e["action"] for e in entrees] == ["deconnexion", "echec_connexion", "connexion", "compte_cree"]
    assert entrees[1]["identifiant"] == "(inconnu)" and entrees[1]["detail"] == "échec 1 sur 5"
    assert MOT_DE_PASSE not in str(entrees)


def test_purge(base):
    t = 1_000_000.0
    jeton, _ = sessions.connecter(base, "m.dupont", MOT_DE_PASSE, maintenant=t)
    with base.ecrire() as conn:
        conn.execute("INSERT INTO journal (date, action) VALUES (?, ?)", ("2020-01-01T00:00:00", "tres_ancien"))
    sessions.purger(base, maintenant=t + sessions.INACTIVITE_S + 1)
    with base.lire() as conn:
        assert conn.execute("SELECT COUNT(*) FROM session").fetchone()[0] == 0
    assert "tres_ancien" not in [e["action"] for e in journal.lire(base)]


# --- la ligne de commande (⚖2) --------------------------------------------------------------------

def test_ligne_de_commande(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "chemin", lambda nom: tmp_path / nom)
    reponses = iter(["M.Dupont", "M. Dupont"])
    monkeypatch.setattr("builtins.input", lambda invite: next(reponses))
    saisies = iter(["court", MOT_DE_PASSE, "différent", MOT_DE_PASSE, MOT_DE_PASSE])
    monkeypatch.setattr(comptes.getpass, "getpass", lambda invite: next(saisies))
    assert comptes.main(["creer-admin"]) == 0
    sortie = capsys.readouterr().out
    assert "trop court" in sortie and "diffèrent" in sortie and "Compte admin « m.dupont » créé" in sortie
    assert MOT_DE_PASSE not in sortie
    assert comptes.main(["lister"]) == 0 and "m.dupont" in capsys.readouterr().out
    assert comptes.main(["reinitialiser", "m.dupont"]) == 0
    provisoire = capsys.readouterr().out.split(" : ")[1].split()[0]
    sessions.connecter(Base(tmp_path / "base"), "m.dupont", provisoire)
    assert comptes.main(["supprimer", "m.dupont"]) == 1  # le dernier administrateur
    assert "dernier compte administrateur" in capsys.readouterr().err
    assert comptes.main(["debloquer", "personne"]) == 1
