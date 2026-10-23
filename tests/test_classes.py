"""E3 : classes et élèves (generateur/donnees/classes.py, codes.py, demo.py) — saisies, codes, cartes, droits des
familles, purge, cloisonnement entre enseignants ; menaces M7 à M9 et M17 du modèle de menace."""

import csv
import io
import os
import stat
from datetime import date

import pytest

from generateur.donnees import classes, codes, comptes, demo, images, journal
from generateur.donnees.base import Base
from generateur.moteur import config

CLE = b"k" * 32


@pytest.fixture
def base(tmp_path):
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


def classe_6e(base, compte, noms=(("DUPONT", "Marie"), ("LE GOFF", "Anne-Sophie"), ("N'DIAYE", "Moussa"))):
    return classes.creer(base, compte, "6e B", "6e", "2026-2027", [{"nom": n, "prenom": p} for n, p in noms], CLE)


# --- saisies --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("jour, annee", [(date(2026, 10, 23), "2026-2027"), (date(2027, 7, 31), "2026-2027"),
                                         (date(2027, 8, 1), "2027-2028")])
def test_annee_scolaire(jour, annee):
    assert classes.annee_scolaire(jour) == annee


@pytest.mark.parametrize("nom", ["Anne-Sophie", "D'Artagnan", "N’Diaye", "Le  Goff", "Zoé", "St. Pierre", "Ångström"])
def test_noms_acceptes(nom):
    assert classes.controler_nom(nom) == " ".join(nom.split())


@pytest.mark.parametrize("nom", ["", "<script>alert(1)</script>", "Marie2", "=HYPERLINK(1)", "x" * 61, "-Marie", "Jean_"])
def test_noms_refuses(nom):
    """Rien qui ressemble à du code ou à une formule n'entre dans la base (M7, M8)."""
    with pytest.raises(classes.ClasseInvalide):
        classes.controler_nom(nom)


def test_lire_une_liste_collee():
    eleves, remarques = classes.lire_liste(
        "DUPONT;Marie;12/03/2014\nLE GOFF Anne-Sophie\nMARTIN\tAlice\n\n# un commentaire\nSeul\nBernard Hugo\nDUPONT;Marie")
    assert eleves == [{"nom": "DUPONT", "prenom": "Marie"}, {"nom": "LE GOFF", "prenom": "Anne-Sophie"},
                      {"nom": "MARTIN", "prenom": "Alice"}, {"nom": "Bernard", "prenom": "Hugo"},
                      {"nom": "DUPONT", "prenom": "Marie"}]
    texte = " | ".join(remarques)
    assert "ligne 6 écartée" in texte                       # « Seul » : pas de prénom
    assert "colonnes en plus" in texte                      # la date de naissance n'est pas gardée
    assert "premier mot a été pris pour le nom" in texte    # « Bernard Hugo »
    assert "apparaît deux fois" in texte
    assert any("40 au plus" in r for r in classes.lire_liste("\n".join("NOM;Prénom" for _ in range(41)))[1])


# --- les codes (⚖3) -------------------------------------------------------------------------------------

def test_codes_tires_et_proteges():
    tires = {codes.tirer() for _ in range(300)}
    assert all(len(c) == 4 and all(0 <= i < images.NOMBRE for i in c) and len(set(c)) > 1 for c in tires)
    assert len(tires) > 250  # tirés au hasard
    code = (0, 1, 2, 3)
    a, b = codes.empreinte(code, CLE), codes.empreinte(code, CLE)
    assert a != b and a.startswith("scrypt-hmac$1024$8$1$")
    assert codes.verifier(code, a, CLE) and not codes.verifier((0, 1, 2, 4), a, CLE)
    assert not codes.verifier(code, a, b"z" * 32)  # sans la clé de l'installation, la base seule ne suffit pas
    assert not codes.verifier(None, a, CLE) and not codes.verifier(code, "abimee", CLE)
    assert codes.depuis_images(["soleil", "lune", "etoile", "coeur"]) == (0, 1, 2, 3)
    assert codes.depuis_images(["soleil", "lune", "etoile"]) is None
    assert codes.depuis_images(["soleil", "lune", "etoile", "dragon"]) is None


def test_scrypt_leger_pour_les_codes():
    """~40 ms par code : sur 20 736 codes, un calcul plus lent ne protégerait guère mieux ; la clé secrète, si."""
    assert codes.SCRYPT_CODE_RECOMMANDE == {"n": 2 ** 14, "r": 8, "p": 1}


def test_cle_de_l_installation(tmp_path):
    chemin = tmp_path / "donnees" / "cle-codes"
    cle = codes.cle_secrete(chemin)
    assert len(cle) == 32 and stat.S_IMODE(os.stat(chemin).st_mode) == 0o600
    assert codes.cle_secrete(chemin) == cle  # la même, relue
    chemin.write_bytes(b"trop court")
    with pytest.raises(ValueError, match="illisible"):
        codes.cle_secrete(chemin)


# --- créer, lire, cloisonner ------------------------------------------------------------------------------

def test_creer_une_classe_et_ses_cartes(base, prof):
    classe, cartes = classe_6e(base, prof)
    assert classe["nom"] == "6e B" and classe["eleves"] == 3 and classe["annee"] == "2026-2027"
    assert [c["numero"] for c in cartes] == [1, 2, 3] and cartes[1]["prenom"] == "Anne-Sophie"
    assert all(len(c["code"]) == 4 and c["code"][0]["nom"] for c in cartes)
    with base.lire() as conn:
        empreintes = [r[0] for r in conn.execute("SELECT code FROM eleve ORDER BY numero")]
    code = codes.depuis_images([i["image"] for i in cartes[0]["code"]])
    assert codes.verifier(code, empreintes[0], CLE)
    assert not any(i["image"] in e for e in empreintes for i in cartes[0]["code"])  # jamais le code en clair
    with pytest.raises(classes.ClasseInvalide, match="déjà une classe"):
        classe_6e(base, prof)


def test_chaque_enseignant_ne_voit_que_ses_classes(base, prof, autre):
    classe, cartes = classe_6e(base, prof)
    assert [c["nom"] for c in classes.lister(base, prof)] == ["6e B"] and classes.lister(base, autre) == []
    eleve = cartes[0]["eleve_id"]
    for action in (lambda: classes.lire(base, autre, classe["id"]),
                   lambda: classes.ajouter(base, autre, classe["id"], [{"nom": "X", "prenom": "Y"}], CLE),
                   lambda: classes.nouveaux_codes(base, autre, classe["id"], CLE),
                   lambda: classes.nouveau_code(base, autre, eleve, CLE),
                   lambda: classes.modifier(base, autre, eleve, "A", "B"),
                   lambda: classes.activer(base, autre, eleve, False),
                   lambda: classes.exporter(base, autre, eleve),
                   lambda: classes.supprimer(base, autre, eleve),
                   lambda: classes.archiver(base, autre, classe["id"], True)):
        with pytest.raises(classes.Introuvable):
            action()


def test_lire_une_classe_est_note_au_journal(base, prof):
    classe, _ = classe_6e(base, prof)
    detail = classes.lire(base, prof, classe["id"])
    assert [e["numero"] for e in detail["liste"]] == [1, 2, 3] and detail["liste"][0]["actif"]
    assert journal.lire(base)[0]["action"] == "classe_consultee"


def test_les_numeros_ne_sont_jamais_redonnes(base, prof):
    classe, cartes = classe_6e(base, prof)
    classes.supprimer(base, prof, cartes[2]["eleve_id"])                    # le n° 3 part
    nouvelles = classes.ajouter(base, prof, classe["id"], [{"nom": "PETIT", "prenom": "Emma"}], CLE)
    assert nouvelles[0]["numero"] == 4                                          # pas 3
    with pytest.raises(classes.ClasseInvalide, match="40 élèves au plus"):
        classes.ajouter(base, prof, classe["id"], [{"nom": "NOM", "prenom": "Prénom"}] * 38, CLE)


def test_nouveaux_codes(base, prof):
    classe, cartes = classe_6e(base, prof)
    ancien = codes.depuis_images([i["image"] for i in cartes[0]["code"]])
    toute_la_classe = classes.nouveaux_codes(base, prof, classe["id"], CLE)
    seul = classes.nouveau_code(base, prof, cartes[1]["eleve_id"], CLE)
    with base.lire() as conn:
        empreintes = {r["numero"]: r["code"] for r in conn.execute("SELECT numero, code FROM eleve")}
    nouveau = codes.depuis_images([i["image"] for i in toute_la_classe[0]["code"]])
    assert codes.verifier(nouveau, empreintes[1], CLE)
    assert ancien == nouveau or not codes.verifier(ancien, empreintes[1], CLE)  # l'ancien ne marche plus
    assert codes.verifier(codes.depuis_images([i["image"] for i in seul["code"]]), empreintes[2], CLE)


# --- droits des familles ----------------------------------------------------------------------------------

def test_rectifier_desactiver_supprimer(base, prof):
    classe, cartes = classe_6e(base, prof)
    eleve = cartes[0]["eleve_id"]
    assert classes.modifier(base, prof, eleve, "DUPOND", "Marie")["nom"] == "DUPOND"
    assert classes.activer(base, prof, eleve, False)["actif"] is False
    assert classes.activer(base, prof, eleve, True)["actif"] is True
    classes.supprimer(base, prof, eleve)
    assert [e["numero"] for e in classes.lire(base, prof, classe["id"])["liste"]] == [2, 3]
    actions = [e["action"] for e in journal.lire(base)]
    assert {"eleve_modifie", "eleve_desactive", "eleve_reactive", "eleve_supprime"} <= set(actions)
    assert "Marie" not in str(journal.lire(base)) and "DUPOND" not in str(journal.lire(base))  # jamais un nom


def test_exporter_un_eleve(base, prof):
    _, cartes = classe_6e(base, prof)
    nom, contenu = classes.exporter(base, prof, cartes[1]["eleve_id"])
    assert nom == f"eleve-{cartes[1]['eleve_id']}.csv" and contenu.startswith("﻿".encode("utf-8"))
    lignes = list(csv.reader(io.StringIO(contenu.decode("utf-8-sig")), delimiter=";"))
    assert ["Nom", "LE GOFF"] in lignes and ["Prénom", "Anne-Sophie"] in lignes and ["Numéro dans la classe", "2"] in lignes
    assert ["aucune réponse enregistrée"] in lignes
    assert not any(i["image"] in contenu.decode("utf-8") for i in cartes[1]["code"])  # pas le code
    assert journal.lire(base)[0]["action"] == "eleve_exporte"


@pytest.mark.parametrize("valeur, attendue", [("=SOMME(A1)", "'=SOMME(A1)"), ("+33", "'+33"), ("-2", "'-2"),
                                              ("@cmd", "'@cmd"), ("Marie", "Marie"), (None, ""), (7, "7")])
def test_csv_sans_formule(valeur, attendue):
    assert classes.cellule(valeur) == attendue


def test_archiver(base, prof):
    classe, _ = classe_6e(base, prof)
    assert classes.archiver(base, prof, classe["id"], True)["archivee"]
    assert classes.lister(base, prof) == [] and len(classes.lister(base, prof, archivees=True)) == 1
    assert not classes.archiver(base, prof, classe["id"], False)["archivee"]


def test_purge_de_fin_d_annee(base, prof, autre):
    classes.creer(base, prof, "6e A", "6e", "2025-2026", [{"nom": "ANCIEN", "prenom": "Élève"}], CLE)
    classes.creer(base, autre, "5e C", "5e", "2024-2025", [{"nom": "ANCIENNE", "prenom": "Élève"}] * 2, CLE)
    classe_6e(base, prof)                                                         # l'année en cours : gardée
    jour = date(2026, 10, 23)
    apercu = classes.apercu_purge(base, autre, jour)                              # un enseignant : ses classes
    assert apercu["classes"] == [{"nom": "5e C", "annee": "2024-2025", "eleves": 2, "enseignant": "autre"}]
    apercu = classes.apercu_purge(base, prof, jour)                               # l'administrateur : toutes
    assert len(apercu["classes"]) == 2 and apercu["eleves"] == 3 and apercu["annee_courante"] == "2026-2027"
    assert classes.purger(base, prof, jour) == {"classes": 2, "eleves": 3}
    with base.lire() as conn:
        assert conn.execute("SELECT COUNT(*) FROM eleve").fetchone()[0] == 3     # ceux de 2026-2027
        assert [r[0] for r in conn.execute("SELECT annee FROM classe")] == ["2026-2027"]
    assert journal.lire(base)[0]["action"] == "purge"


def test_un_compte_qui_a_des_classes_ne_se_supprime_pas(base, prof, autre):
    classes.creer(base, autre, "5e C", "5e", "2026-2027", [], CLE)
    with pytest.raises(comptes.CompteInvalide, match="encore 1 classe"):
        comptes.supprimer(base, "autre")


# --- la classe de démonstration (E3.4) --------------------------------------------------------------------

def test_classe_de_demonstration(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "chemin", lambda nom: tmp_path / nom)
    base = Base(tmp_path / "base")
    comptes.creer(base, "prof", "Professeur", "un mot de passe de test", "admin")
    assert demo.main(["prof"]) == 0
    sortie = capsys.readouterr().out
    assert "« 6e Démo »" in sortie and "24 élèves fictifs" in sortie and sortie.count("n° ") == 24
    assert len(classes.lire(base, comptes.lire(base, "prof"), classes.lister(base, comptes.lire(base, "prof"))[0]["id"])["liste"]) == 24
    assert demo.main(["prof"]) == 1 and "déjà une classe" in capsys.readouterr().err
    assert demo.main(["personne"]) == 1
