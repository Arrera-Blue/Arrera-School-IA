"""La connexion des élèves au serveur de classe (évolution E8.3) : choisir sa classe, son nom (« Prénom N. », D6),
puis son code : 4 images en 6e, le mot de passe de sa carte de la 5e à la 3e (codes.py).

Règles (docs/etapes/etape-E1-securite.md, docs/etapes/etape-E8-serveur.md) :
- 5 essais manqués de suite : l'élève est **bloqué** jusqu'à ce que l'enseignant le débloque (ou refasse son code) ;
  le message dit combien d'essais il reste ;
- session **courte** : 10 minutes sans activité, puis il faut se reconnecter ; une seule session par élève (se
  reconnecter ailleurs ferme l'autre) ; le jeton n'est connu que du navigateur, la base garde son empreinte ;
- un élève désactivé (limitation, RGPD), ou d'une classe archivée, ne se connecte pas ;
- journal : connexions et échecs, avec l'identifiant interne de l'élève, jamais son nom ni son code (⚖5 : pas
  d'adresse IP).
"""

import hashlib
import secrets
import sqlite3
import time

from generateur.donnees import codes, journal
from generateur.donnees.base import Base

ESSAIS_MAX = 5
INACTIVITE_S = 10 * 60


class ConnexionRefusee(Exception):
    """Code faux : `restants` essais avant le blocage."""

    def __init__(self, message: str, restants: int):
        super().__init__(message)
        self.restants = restants


class EleveBloque(ConnexionRefusee):
    def __init__(self):
        super().__init__("trop d'essais : ta connexion est bloquée, demande à ton professeur de la débloquer", 0)


class Introuvable(LookupError):
    pass


def _empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("ascii", "replace")).hexdigest()


def _cible(eleve: sqlite3.Row) -> str:
    return f"classe:{eleve['classe_id']}/eleve:{eleve['id']}"


def nom_affiche(prenom: str, nom: str) -> str:
    """« Inès M. » : ce que les autres élèves voient dans la liste (D6)."""
    initiale = next((c for c in nom if c.isalpha()), "")
    return f"{prenom} {initiale.upper()}." if initiale else prenom


# --- ce que l'écran de connexion montre ---------------------------------------------------------------

def classes_ouvertes(base: Base) -> list[dict]:
    """Les classes où l'on peut se connecter : non archivées, avec au moins un élève actif."""
    with base.lire() as conn:
        lignes = conn.execute("SELECT c.id, c.nom, c.niveau, c.connexion FROM classe c WHERE c.archivee = 0 AND EXISTS "
                              "(SELECT 1 FROM eleve e WHERE e.classe_id = c.id AND e.actif = 1) ORDER BY c.niveau, c.nom"
                              ).fetchall()
    return [dict(l) for l in lignes]


def eleves_de_la_classe(base: Base, classe_id: int) -> dict:
    """La classe et ses élèves actifs, en « Prénom N. » ; deux mêmes « Prénom N. » sont distingués par le numéro."""
    with base.lire() as conn:
        classe = conn.execute("SELECT id, nom, niveau, connexion FROM classe WHERE id = ? AND archivee = 0",
                              (classe_id,)).fetchone()
        if classe is None:
            raise Introuvable("classe introuvable")
        eleves = conn.execute("SELECT id, numero, nom, prenom FROM eleve WHERE classe_id = ? AND actif = 1 "
                              "ORDER BY prenom COLLATE NOCASE, nom COLLATE NOCASE", (classe_id,)).fetchall()
    noms = [nom_affiche(e["prenom"], e["nom"]) for e in eleves]
    vus = {n: noms.count(n) for n in noms}
    return {"classe": dict(classe),
            "eleves": [{"id": e["id"], "nom": n if vus[n] == 1 else f"{n} (n° {e['numero']})"} for e, n in zip(eleves, noms)]}


# --- se connecter, la session ---------------------------------------------------------------------------

def _eleve_connectable(conn: sqlite3.Connection, eleve_id: int) -> sqlite3.Row:
    eleve = conn.execute("SELECT e.*, c.nom AS classe_nom, c.niveau, c.connexion FROM eleve e "
                         "JOIN classe c ON c.id = e.classe_id WHERE e.id = ? AND e.actif = 1 AND c.archivee = 0",
                         (eleve_id,)).fetchone()
    if eleve is None:
        raise Introuvable("élève introuvable")
    return eleve


def _code_saisi(connexion: str, saisie) -> tuple[int, ...] | str | None:
    if connexion == "mot_de_passe":
        return saisie if isinstance(saisie, str) and len(saisie) <= 100 else None
    return codes.depuis_images(saisie) if isinstance(saisie, list) and all(isinstance(s, str) for s in saisie) else None


def connecter(base: Base, eleve_id: int, saisie, cle: bytes, maintenant: float | None = None) -> tuple[str, dict]:
    """Vérifie le code (liste de 4 noms d'images, ou mot de passe) ; renvoie (jeton, élève). Un code faux est compté ;
    au 5e, l'élève est bloqué."""
    maintenant = maintenant or time.time()
    with base.lire() as conn:
        eleve = _eleve_connectable(conn, eleve_id)
    if eleve["bloque"]:
        raise EleveBloque()
    juste = codes.verifier(_code_saisi(eleve["connexion"], saisie), eleve["code"], cle)  # ~40 ms, hors transaction
    if not juste:
        # l'échec est compté dans sa propre transaction, AVANT de refuser : une exception levée dans la transaction
        # l'annulerait, et les essais seraient illimités
        with base.ecrire() as conn:
            eleve = _eleve_connectable(conn, eleve_id)
            echecs = eleve["echecs"] + (0 if eleve["bloque"] else 1)
            bloque = echecs >= ESSAIS_MAX
            conn.execute("UPDATE eleve SET echecs = ?, bloque = ? WHERE id = ?", (echecs, int(bloque), eleve_id))
            journal.noter(conn, "eleve_bloque" if bloque else "connexion_eleve_echec", identifiant="(élève)",
                          cible=_cible(eleve), detail=f"échec {echecs} sur {ESSAIS_MAX}")
        if bloque:
            raise EleveBloque()
        restants = ESSAIS_MAX - echecs
        mot = "mot de passe incorrect" if eleve["connexion"] == "mot_de_passe" else "ce n'est pas le bon code"
        raise ConnexionRefusee(f"{mot} : il te reste {restants} essai{'s' if restants > 1 else ''}", restants)
    with base.ecrire() as conn:
        eleve = _eleve_connectable(conn, eleve_id)
        if eleve["bloque"]:
            bloque_entre_temps = True
        else:
            bloque_entre_temps = False
            jeton = secrets.token_urlsafe(32)
            conn.execute("UPDATE eleve SET echecs = 0 WHERE id = ?", (eleve_id,))
            conn.execute("DELETE FROM session_eleve WHERE eleve_id = ?", (eleve_id,))  # une seule session par élève
            conn.execute("INSERT INTO session_eleve (empreinte, eleve_id, creee, activite) VALUES (?, ?, ?, ?)",
                         (_empreinte(jeton), eleve_id, maintenant, maintenant))
            journal.noter(conn, "connexion_eleve", identifiant="(élève)", cible=_cible(eleve))
    if bloque_entre_temps:
        raise EleveBloque()
    return jeton, vue(eleve)


def vue(eleve: sqlite3.Row) -> dict:
    """Ce que l'élève connecté voit de lui-même : jamais son code, ni le nom des autres."""
    return {"id": eleve["id"], "prenom": eleve["prenom"], "nom": nom_affiche(eleve["prenom"], eleve["nom"]),
            "classe_id": eleve["classe_id"], "classe": eleve["classe_nom"], "niveau": eleve["niveau"]}


def session(base: Base, jeton: str | None, maintenant: float | None = None) -> dict | None:
    """L'élève de cette session, ou None (inconnue, expirée après 10 minutes sans activité, élève désactivé ou
    bloqué). Chaque appel repousse l'expiration."""
    if not jeton or len(jeton) > 100:
        return None
    maintenant = maintenant or time.time()
    empreinte = _empreinte(jeton)
    with base.ecrire() as conn:
        ligne = conn.execute("SELECT * FROM session_eleve WHERE empreinte = ?", (empreinte,)).fetchone()
        if ligne is None:
            return None
        if maintenant - ligne["activite"] > INACTIVITE_S:
            conn.execute("DELETE FROM session_eleve WHERE empreinte = ?", (empreinte,))
            return None
        try:
            eleve = _eleve_connectable(conn, ligne["eleve_id"])
        except Introuvable:
            eleve = None
        if eleve is None or eleve["bloque"]:
            conn.execute("DELETE FROM session_eleve WHERE empreinte = ?", (empreinte,))
            return None
        conn.execute("UPDATE session_eleve SET activite = ? WHERE empreinte = ?", (maintenant, empreinte))
    return vue(eleve)


def deconnecter(base: Base, jeton: str | None) -> None:
    if jeton:
        with base.ecrire() as conn:
            conn.execute("DELETE FROM session_eleve WHERE empreinte = ?", (_empreinte(jeton),))


def purger(base: Base, maintenant: float | None = None) -> int:
    """Les sessions expirées : à l'entretien du serveur."""
    maintenant = maintenant or time.time()
    with base.ecrire() as conn:
        return conn.execute("DELETE FROM session_eleve WHERE activite < ?", (maintenant - INACTIVITE_S,)).rowcount
