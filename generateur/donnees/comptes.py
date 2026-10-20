"""Les comptes enseignants (évolution E1) : mots de passe, rôles, et la ligne de commande de l'installation.

    python -m generateur.donnees.comptes creer-admin                   # le premier compte (⚖2)
    python -m generateur.donnees.comptes creer                         # un compte enseignant
    python -m generateur.donnees.comptes lister
    python -m generateur.donnees.comptes reinitialiser <identifiant>   # mot de passe provisoire, à changer
    python -m generateur.donnees.comptes debloquer <identifiant>       # après 5 échecs de connexion
    python -m generateur.donnees.comptes supprimer <identifiant>

Le premier compte administrateur se crée ici, et non par une page web : aucune page « le premier venu devient
administrateur » (menace M25). Ensuite, un administrateur gère les comptes depuis l'interface.

Mots de passe (SEC-3) : 12 caractères au moins ; hachés avec scrypt (n = 2¹⁷, r = 8, p = 1 : 128 Mo et ~0,3 s
par calcul sur le Mac, la recommandation de l'OWASP) et un sel de 16 octets propre au compte. L'empreinte
garde ses paramètres : on pourra les durcir sans invalider les comptes existants.
"""

import argparse
import base64
import getpass
import hashlib
import hmac
import re
import secrets
import sqlite3
import sys
import unicodedata

from generateur.donnees import journal
from generateur.donnees.base import Base, maintenant_iso

ROLES = ("admin", "enseignant")
LONGUEUR_MIN, LONGUEUR_MAX = 12, 128
SCRYPT_RECOMMANDE = {"n": 2 ** 17, "r": 8, "p": 1}  # OWASP, fiche « Password Storage »
SCRYPT = dict(SCRYPT_RECOMMANDE)  # les tests l'allègent (tests/conftest.py)
MEMOIRE_MAX = 2 ** 28  # 256 Mo : le calcul en demande 128 (OpenSSL refuse au-delà de 32 Mo par défaut)
IDENTIFIANT = re.compile(r"^[a-z0-9][a-z0-9._-]{1,39}$")
NOM_MAX = 60
# mot de passe provisoire : sans 0/o, 1/l/i, faciles à confondre quand on le recopie
ALPHABET_PROVISOIRE = "abcdefghjkmnpqrstuvwxyz23456789"


class CompteInvalide(ValueError):
    """Une saisie refusée : le message dit quoi corriger."""


class CompteInconnu(LookupError):
    pass


# --- mots de passe --------------------------------------------------------------------------------

def _octets(mot_de_passe: str) -> bytes:
    # même mot de passe, mêmes octets, quelle que soit la façon dont le clavier compose « é »
    return unicodedata.normalize("NFC", mot_de_passe).encode("utf-8")


def empreinte(mot_de_passe: str, *, sel: bytes | None = None) -> str:
    """« scrypt$n$r$p$sel$cle » (sel et clé en base64)."""
    n, r, p = SCRYPT["n"], SCRYPT["r"], SCRYPT["p"]
    sel = sel or secrets.token_bytes(16)
    cle = hashlib.scrypt(_octets(mot_de_passe), salt=sel, n=n, r=r, p=p, maxmem=MEMOIRE_MAX, dklen=32)
    return "$".join(["scrypt", str(n), str(r), str(p), base64.b64encode(sel).decode(), base64.b64encode(cle).decode()])


def verifier_mot_de_passe(mot_de_passe: str, enregistree: str) -> bool:
    """Recalcule avec les paramètres de l'empreinte ; comparaison en temps constant."""
    try:
        nom, n, r, p, sel, cle = enregistree.split("$")
        if nom != "scrypt":
            return False
        attendue = base64.b64decode(cle)
        calculee = hashlib.scrypt(_octets(mot_de_passe), salt=base64.b64decode(sel), n=int(n), r=int(r), p=int(p),
                                  maxmem=MEMOIRE_MAX, dklen=len(attendue))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculee, attendue)


def provisoire() -> str:
    """Un mot de passe provisoire lisible, à recopier : « k7mp-x3rd-9qwz-tb4h » (16 lettres, ~79 bits)."""
    return "-".join("".join(secrets.choice(ALPHABET_PROVISOIRE) for _ in range(4)) for _ in range(4))


# --- contrôles des saisies ------------------------------------------------------------------------

def controler_identifiant(identifiant: str) -> str:
    identifiant = (identifiant or "").strip().lower()
    if not IDENTIFIANT.match(identifiant):
        raise CompteInvalide("identifiant : 2 à 40 caractères, lettres minuscules sans accent, chiffres, « . », "
                             "« _ » ou « - »")
    return identifiant


def controler_nom(nom: str) -> str:
    nom = " ".join((nom or "").split())
    if not nom or len(nom) > NOM_MAX or any(unicodedata.category(c).startswith("C") for c in nom):
        raise CompteInvalide(f"nom affiché : 1 à {NOM_MAX} caractères, sans caractère de contrôle")
    return nom


def controler_mot_de_passe(mot_de_passe: str, identifiant: str | None = None) -> None:
    if len(mot_de_passe) < LONGUEUR_MIN:
        raise CompteInvalide(f"mot de passe trop court : {LONGUEUR_MIN} caractères au moins")
    if len(mot_de_passe) > LONGUEUR_MAX:
        raise CompteInvalide(f"mot de passe trop long : {LONGUEUR_MAX} caractères au plus")
    if identifiant and mot_de_passe.strip().lower() == identifiant.lower():
        raise CompteInvalide("le mot de passe ne doit pas être l'identifiant")


# --- les comptes ----------------------------------------------------------------------------------

# requêtes écrites en entier : jamais de texte de requête assemblé (SEC-2)
LIRE_COMPTE = ("SELECT id, identifiant, nom, role, doit_changer, cree, mot_de_passe_change FROM enseignant "
               "WHERE identifiant = ?")
LISTER_COMPTES = ("SELECT id, identifiant, nom, role, doit_changer, cree, mot_de_passe_change FROM enseignant "
                  "ORDER BY identifiant")


def _vue(ligne: sqlite3.Row | None) -> dict | None:
    if ligne is None:
        return None
    compte = dict(ligne)
    compte.pop("empreinte", None)
    compte["doit_changer"] = bool(compte["doit_changer"])
    return compte


def nombre(base: Base) -> int:
    with base.lire() as conn:
        return conn.execute("SELECT COUNT(*) FROM enseignant").fetchone()[0]


def lire(base: Base, identifiant: str) -> dict | None:
    with base.lire() as conn:
        return _vue(conn.execute(LIRE_COMPTE, ((identifiant or "").strip().lower(),)).fetchone())


def lister(base: Base) -> list[dict]:
    """Les comptes, avec l'état de verrouillage (sessions.py) ; jamais les empreintes."""
    from generateur.donnees import sessions  # sessions importe ce module

    with base.lire() as conn:
        lignes = conn.execute(LISTER_COMPTES).fetchall()
    comptes = [_vue(ligne) for ligne in lignes]
    for compte in comptes:
        compte["verrouille"] = sessions.verrouille(base, compte["identifiant"])
    return comptes


def creer(base: Base, identifiant: str, nom: str, mot_de_passe: str, role: str = "enseignant", *,
          doit_changer: bool = False, par: dict | None = None) -> dict:
    identifiant, nom = controler_identifiant(identifiant), controler_nom(nom)
    controler_mot_de_passe(mot_de_passe, identifiant)
    if role not in ROLES:
        raise CompteInvalide(f"rôle inconnu : {role} (permis : {', '.join(ROLES)})")
    calculee = empreinte(mot_de_passe)  # hors de la transaction : ~0,3 s
    with base.ecrire() as conn:
        try:
            conn.execute("INSERT INTO enseignant (identifiant, nom, role, empreinte, doit_changer, cree) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         (identifiant, nom, role, calculee, int(doit_changer), maintenant_iso()))
        except sqlite3.IntegrityError:
            raise CompteInvalide(f"l'identifiant « {identifiant} » existe déjà") from None
        journal.noter(conn, "compte_cree", par, cible=identifiant, detail=role)
    return lire(base, identifiant)


def _exiger(conn: sqlite3.Connection, identifiant: str) -> sqlite3.Row:
    ligne = conn.execute("SELECT * FROM enseignant WHERE identifiant = ?",
                         ((identifiant or "").strip().lower(),)).fetchone()
    if ligne is None:
        raise CompteInconnu(f"compte inconnu : {identifiant}")
    return ligne


def changer_mot_de_passe(base: Base, identifiant: str, nouveau: str, *, par: dict | None = None,
                         garder_session: str | None = None) -> dict:
    """Le nouveau mot de passe, choisi par la personne : le compte n'est plus « provisoire ». Toutes ses
    sessions sont fermées, sauf `garder_session` (l'empreinte de celle d'où vient la demande)."""
    controler_mot_de_passe(nouveau, identifiant)
    calculee = empreinte(nouveau)
    with base.ecrire() as conn:
        compte = _exiger(conn, identifiant)
        conn.execute("UPDATE enseignant SET empreinte = ?, doit_changer = 0, mot_de_passe_change = ? WHERE id = ?",
                     (calculee, maintenant_iso(), compte["id"]))
        conn.execute("DELETE FROM session WHERE enseignant_id = ? AND empreinte IS NOT ?",
                     (compte["id"], garder_session))
        journal.noter(conn, "mot_de_passe_change", par, cible=compte["identifiant"])
    return lire(base, identifiant)


def reinitialiser(base: Base, identifiant: str, *, par: dict | None = None) -> str:
    """Un mot de passe provisoire, à transmettre à la personne : elle devra le changer à sa connexion. Ses
    sessions sont fermées et son verrou levé. Renvoie le mot de passe provisoire (il n'est gardé nulle part)."""
    from generateur.donnees import sessions

    mot_de_passe = provisoire()
    calculee = empreinte(mot_de_passe)
    with base.ecrire() as conn:
        compte = _exiger(conn, identifiant)
        conn.execute("UPDATE enseignant SET empreinte = ?, doit_changer = 1, mot_de_passe_change = ? WHERE id = ?",
                     (calculee, maintenant_iso(), compte["id"]))
        conn.execute("DELETE FROM session WHERE enseignant_id = ?", (compte["id"],))
        sessions.lever_verrou(conn, compte["identifiant"])
        journal.noter(conn, "mot_de_passe_reinitialise", par, cible=compte["identifiant"])
    return mot_de_passe


def debloquer(base: Base, identifiant: str, *, par: dict | None = None) -> None:
    from generateur.donnees import sessions

    with base.ecrire() as conn:
        compte = _exiger(conn, identifiant)
        sessions.lever_verrou(conn, compte["identifiant"])
        journal.noter(conn, "compte_debloque", par, cible=compte["identifiant"])


def supprimer(base: Base, identifiant: str, *, par: dict | None = None) -> None:
    """Supprime le compte et ses sessions ; refusé pour le dernier administrateur (plus personne ne pourrait
    gérer les comptes depuis l'interface)."""
    with base.ecrire() as conn:
        compte = _exiger(conn, identifiant)
        if compte["role"] == "admin" and conn.execute(
                "SELECT COUNT(*) FROM enseignant WHERE role = 'admin'").fetchone()[0] <= 1:
            raise CompteInvalide("c'est le dernier compte administrateur : créez-en un autre avant de le supprimer")
        conn.execute("DELETE FROM enseignant WHERE id = ?", (compte["id"],))
        journal.noter(conn, "compte_supprime", par, cible=compte["identifiant"])


# --- la ligne de commande -------------------------------------------------------------------------

def _base() -> Base:
    from generateur.moteur import config

    return Base(config.chemin("base"))


def _demander_mot_de_passe(identifiant: str) -> str:
    """Saisi deux fois, sans écho ; jamais en argument (il resterait dans l'historique du terminal)."""
    while True:
        premier = getpass.getpass(f"Mot de passe ({LONGUEUR_MIN} caractères au moins) : ")
        try:
            controler_mot_de_passe(premier, identifiant)
        except CompteInvalide as e:
            print(e)
            continue
        if getpass.getpass("Le même, encore une fois : ") == premier:
            return premier
        print("Les deux saisies diffèrent : recommencez.")


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m generateur.donnees.comptes",
                                     description="Gérer les comptes de l'interface enseignant.")
    commandes = parser.add_subparsers(dest="commande", required=True)
    commandes.add_parser("creer-admin", help="créer un compte administrateur (le premier, à l'installation)")
    commandes.add_parser("creer", help="créer un compte enseignant")
    commandes.add_parser("lister", help="lister les comptes")
    for nom, aide in (("reinitialiser", "donner un mot de passe provisoire, à changer à la connexion"),
                      ("debloquer", "lever le verrou posé après 5 échecs de connexion"),
                      ("supprimer", "supprimer un compte")):
        commandes.add_parser(nom, help=aide).add_argument("identifiant")
    args = parser.parse_args(arguments)
    base = _base()
    try:
        if args.commande in ("creer-admin", "creer"):
            identifiant = controler_identifiant(input("Identifiant (ex. : m.dupont) : "))
            nom = controler_nom(input("Nom affiché (ex. : M. Dupont) : "))
            role = "admin" if args.commande == "creer-admin" else "enseignant"
            compte = creer(base, identifiant, nom, _demander_mot_de_passe(identifiant), role)
            print(f"Compte {compte['role']} « {compte['identifiant']} » créé ({base.chemin}).")
        elif args.commande == "lister":
            for compte in lister(base):
                etats = [e for e, oui in (("mot de passe provisoire", compte["doit_changer"]),
                                          ("verrouillé", compte["verrouille"])) if oui]
                print(f"{compte['identifiant']:<20} {compte['role']:<11} {compte['nom']}"
                      + (f"  ({', '.join(etats)})" if etats else ""))
            if not nombre(base):
                print("Aucun compte : python -m generateur.donnees.comptes creer-admin")
        elif args.commande == "reinitialiser":
            mot_de_passe = reinitialiser(base, args.identifiant)
            print(f"Mot de passe provisoire de « {args.identifiant} » : {mot_de_passe}\n"
                  "À transmettre à la personne : il ne sera plus affiché, et devra être changé à la connexion.")
        elif args.commande == "debloquer":
            debloquer(base, args.identifiant)
            print(f"Compte « {args.identifiant} » débloqué.")
        elif args.commande == "supprimer":
            supprimer(base, args.identifiant)
            print(f"Compte « {args.identifiant} » supprimé.")
    except (CompteInvalide, CompteInconnu) as e:
        print(f"Refusé : {e}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nAbandon.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
