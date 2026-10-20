"""Se connecter à l'interface enseignant (évolution E1, SEC-5 à SEC-7 et SEC-9 ; menaces M1 à M4).

- Un seul message d'échec (« identifiant ou mot de passe incorrect »), et le même calcul pour un identifiant
  inconnu (une empreinte factice est vérifiée) : on ne peut pas savoir si un compte existe (M2).
- Les échecs se comptent par identifiant saisi, qu'il existe ou non : au 5e, 15 min de verrou, pendant
  lesquelles même le bon mot de passe est refusé (M1). Chaque échec est suivi d'une pause qui double
  (0,5 s, 1 s, 2 s, puis 4 s).
- Le jeton de session (32 octets de `secrets`) n'est connu que du navigateur : la base garde son empreinte
  SHA-256. Un nouveau jeton à chaque connexion ; une session meurt après 30 min sans requête (M3).
- Les actions sensibles redemandent le mot de passe (`confirmer`, ⚖1) : un élève assis devant une session
  restée ouverte ne peut ni exporter, ni gérer les comptes (M4).
"""

import hashlib
import secrets
import sqlite3
import time

from generateur.donnees import comptes, journal
from generateur.donnees.base import Base

ECHECS_MAX = 5
VERROU_S = 15 * 60
INACTIVITE_S = 30 * 60
PAUSE_S = 0.5            # après un échec, doublée à chaque échec suivant…
PAUSE_MAX_S = 4.0        # … jusqu'à 4 s
RAFRAICHIR_S = 60        # l'heure de la dernière requête d'une session n'est réécrite qu'une fois par minute
MESSAGE = "identifiant ou mot de passe incorrect"

_FACTICES: dict[tuple, str] = {}


class ConnexionRefusee(Exception):
    pass


class CompteVerrouille(ConnexionRefusee):
    def __init__(self, reste_s: float):
        self.minutes = max(1, round(reste_s / 60))
        super().__init__(f"trop d'essais : réessayez dans {self.minutes} min, ou demandez à un administrateur "
                         "de débloquer le compte")


def _cle(identifiant: str) -> str:
    """La clé du compteur d'échecs : l'empreinte de l'identifiant saisi, jamais ce qui a été tapé."""
    saisi = (identifiant or "").strip().lower()[:200]
    return hashlib.sha256(saisi.encode("utf-8")).hexdigest()


def _empreinte_jeton(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


def _factice() -> str:
    """Une empreinte aux paramètres du jour, calculée une fois : vérifier un identifiant inconnu coûte
    exactement un calcul scrypt, comme un identifiant connu."""
    parametres = tuple(sorted(comptes.SCRYPT.items()))
    if parametres not in _FACTICES:
        _FACTICES[parametres] = comptes.empreinte(secrets.token_urlsafe(16))
    return _FACTICES[parametres]


def _pause(echecs: int) -> None:
    if PAUSE_S > 0:
        time.sleep(min(PAUSE_S * 2 ** (echecs - 1), PAUSE_MAX_S))


def _verrou_restant(conn: sqlite3.Connection, identifiant: str, maintenant: float) -> float:
    ligne = conn.execute("SELECT verrou_jusqu_a FROM echec_connexion WHERE cle = ?", (_cle(identifiant),)).fetchone()
    if ligne is None or ligne["verrou_jusqu_a"] is None:
        return 0.0
    return max(0.0, ligne["verrou_jusqu_a"] - maintenant)


def verrouille(base: Base, identifiant: str, maintenant: float | None = None) -> bool:
    with base.lire() as conn:
        return _verrou_restant(conn, identifiant, maintenant or time.time()) > 0


def lever_verrou(conn: sqlite3.Connection, identifiant: str) -> None:
    conn.execute("DELETE FROM echec_connexion WHERE cle = ?", (_cle(identifiant),))


def _noter_echec(base: Base, identifiant: str, compte: dict | None, maintenant: float, action: str) -> int:
    """Compte l'échec (le compteur repart de zéro 15 min après le dernier) ; verrouille au 5e."""
    cle = _cle(identifiant)
    with base.ecrire() as conn:
        ligne = conn.execute("SELECT echecs, dernier FROM echec_connexion WHERE cle = ?", (cle,)).fetchone()
        echecs = 1 if ligne is None or maintenant - ligne["dernier"] > VERROU_S else ligne["echecs"] + 1
        verrou = maintenant + VERROU_S if echecs >= ECHECS_MAX else None
        conn.execute("INSERT INTO echec_connexion (cle, echecs, dernier, verrou_jusqu_a) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT (cle) DO UPDATE SET echecs = excluded.echecs, dernier = excluded.dernier, "
                     "verrou_jusqu_a = excluded.verrou_jusqu_a", (cle, echecs, maintenant, verrou))
        # un identifiant saisi qui n'est pas un compte est souvent un mot de passe tapé dans le mauvais champ
        nom = compte["identifiant"] if compte else "(inconnu)"
        journal.noter(conn, action, identifiant=nom, detail=f"échec {echecs} sur {ECHECS_MAX}")
        if verrou:
            journal.noter(conn, "verrouillage", identifiant=nom, detail=f"{VERROU_S // 60} min")
    return echecs


def _verifier(base: Base, identifiant: str, mot_de_passe: str, maintenant: float, action: str) -> dict:
    """Le compte, si le mot de passe est le bon et le compte n'est pas verrouillé ; sinon une exception."""
    with base.lire() as conn:
        restant = _verrou_restant(conn, identifiant, maintenant)
        ligne = conn.execute("SELECT * FROM enseignant WHERE identifiant = ?",
                             ((identifiant or "").strip().lower()[:200],)).fetchone()
    if restant > 0:
        raise CompteVerrouille(restant)  # sans même regarder le mot de passe
    juste = comptes.verifier_mot_de_passe(mot_de_passe or "", ligne["empreinte"] if ligne else _factice())
    if ligne is None or not juste:
        echecs = _noter_echec(base, identifiant, ligne, maintenant, action)
        _pause(echecs)
        if echecs >= ECHECS_MAX:
            raise CompteVerrouille(VERROU_S)
        raise ConnexionRefusee(MESSAGE)
    return comptes._vue(ligne)


def connecter(base: Base, identifiant: str, mot_de_passe: str, maintenant: float | None = None) -> tuple[str, dict]:
    """(jeton, compte) ; le jeton va dans le cookie, et nulle part ailleurs."""
    maintenant = maintenant or time.time()
    compte = _verifier(base, identifiant, mot_de_passe, maintenant, "echec_connexion")
    jeton = secrets.token_urlsafe(32)
    with base.ecrire() as conn:
        lever_verrou(conn, compte["identifiant"])
        conn.execute("INSERT INTO session (empreinte, enseignant_id, creee, activite) VALUES (?, ?, ?, ?)",
                     (_empreinte_jeton(jeton), compte["id"], maintenant, maintenant))
        journal.noter(conn, "connexion", compte)
    return jeton, compte


def session(base: Base, jeton: str | None, maintenant: float | None = None) -> dict | None:
    """Le compte de cette session, ou None (jeton inconnu, ou plus de 30 min sans requête)."""
    if not jeton or len(jeton) > 100:
        return None
    maintenant = maintenant or time.time()
    empreinte = _empreinte_jeton(jeton)
    with base.lire() as conn:
        ligne = conn.execute("SELECT s.activite, e.id, e.identifiant, e.nom, e.role, e.doit_changer FROM session s "
                             "JOIN enseignant e ON e.id = s.enseignant_id WHERE s.empreinte = ?",
                             (empreinte,)).fetchone()
    if ligne is None:
        return None
    if maintenant - ligne["activite"] > INACTIVITE_S:
        with base.ecrire() as conn:
            conn.execute("DELETE FROM session WHERE empreinte = ?", (empreinte,))
        return None
    if maintenant - ligne["activite"] > RAFRAICHIR_S:
        with base.ecrire() as conn:
            conn.execute("UPDATE session SET activite = ? WHERE empreinte = ?", (maintenant, empreinte))
    compte = {k: ligne[k] for k in ("id", "identifiant", "nom", "role")}
    compte["doit_changer"] = bool(ligne["doit_changer"])
    return compte


def empreinte_session(jeton: str | None) -> str | None:
    return _empreinte_jeton(jeton) if jeton else None


def deconnecter(base: Base, jeton: str | None, compte: dict | None = None) -> None:
    if not jeton:
        return
    with base.ecrire() as conn:
        supprimee = conn.execute("DELETE FROM session WHERE empreinte = ?", (_empreinte_jeton(jeton),)).rowcount
        if supprimee and compte:
            journal.noter(conn, "deconnexion", compte)


def confirmer(base: Base, compte: dict, mot_de_passe: str, maintenant: float | None = None) -> None:
    """Le mot de passe redemandé avant une action sensible (⚖1). Les échecs comptent comme ceux de la
    connexion : 5 échecs verrouillent le compte."""
    _verifier(base, compte["identifiant"], mot_de_passe, maintenant or time.time(), "echec_confirmation")


def changer_mot_de_passe(base: Base, compte: dict, ancien: str, nouveau: str, jeton: str | None) -> dict:
    """L'ancien mot de passe est exigé ; les autres sessions du compte sont fermées, pas celle-ci."""
    confirmer(base, compte, ancien)
    if nouveau == ancien:
        raise comptes.CompteInvalide("le nouveau mot de passe doit être différent de l'ancien")
    return comptes.changer_mot_de_passe(base, compte["identifiant"], nouveau, par=compte,
                                        garder_session=empreinte_session(jeton))


def purger(base: Base, maintenant: float | None = None) -> None:
    """Sessions expirées, compteurs d'échecs périmés, journal de plus de 6 mois."""
    maintenant = maintenant or time.time()
    with base.ecrire() as conn:
        conn.execute("DELETE FROM session WHERE activite < ?", (maintenant - INACTIVITE_S,))
        conn.execute("DELETE FROM echec_connexion WHERE dernier < ? AND (verrou_jusqu_a IS NULL OR verrou_jusqu_a < ?)",
                     (maintenant - VERROU_S, maintenant))
        journal.purger(conn)
