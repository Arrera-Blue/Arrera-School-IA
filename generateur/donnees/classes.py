"""Les classes et les élèves (évolution E3) : créer une classe à partir d'une liste collée, tirer les codes et
préparer les cartes de connexion, corriger, désactiver, exporter, supprimer un élève, purger les années passées.

Règles (docs/etapes/etape-E1-securite.md §6, docs/rgpd/) :
- chaque enseignant ne voit et ne touche que **ses** classes (une classe d'un autre est « introuvable ») ;
- minimisation : nom, prénom, classe, numéro, empreinte du code ; une liste collée avec d'autres colonnes (date
  de naissance…) n'en garde que le nom et le prénom ;
- le code n'est montré qu'une fois, sur la carte ; ensuite, on ne peut que le refaire (codes.py) : 4 images du CP à
  la 6e, un mot de passe imprimé de la 5e à la 3e (E8) ;
- chaque action est notée au journal, avec l'identifiant interne de l'élève, jamais son nom ;
- l'export d'un élève est un CSV lisible, sans formule (une cellule « =… » serait exécutée par un tableur).
"""

import csv
import io
import re
import sqlite3
import unicodedata
from datetime import date, datetime

from generateur import programmes
from generateur.donnees import codes, images, journal
from generateur.donnees.base import Base, maintenant_iso

NIVEAUX = programmes.NIVEAUX  # du CP à la 3e (le CM1 et le CM2 pas encore)
ELEVES_MAX = 40
NOM_MAX = 60
NOM_CLASSE_MAX = 30
# un nom ou un prénom : des lettres (accentuées comprises), des espaces, des tirets, des apostrophes, des points
CARACTERES_NOM = re.compile(r"^[^\W\d_]+(?:[ '’.-]+[^\W\d_]+)*\.?$")
CARACTERES_CLASSE = re.compile(r"^[\w °'’.-]+$")


class ClasseInvalide(ValueError):
    """Une saisie refusée : le message dit quoi corriger."""


class Introuvable(LookupError):
    """La classe ou l'élève n'existe pas, ou n'appartient pas à cet enseignant (on ne dit pas lequel)."""


# --- dates et saisies ------------------------------------------------------------------------------

def annee_scolaire(jour: date | None = None) -> str:
    """« 2026-2027 » du 1er août 2026 au 31 juillet 2027 : la purge se fait en juillet."""
    jour = jour or date.today()
    debut = jour.year if jour.month >= 8 else jour.year - 1
    return f"{debut}-{debut + 1}"


def controler_nom(texte: str, champ: str = "nom") -> str:
    texte = " ".join(unicodedata.normalize("NFC", texte or "").split())
    if not texte or len(texte) > NOM_MAX or not CARACTERES_NOM.match(texte):
        raise ClasseInvalide(f"{champ} « {texte[:40]} » : des lettres, espaces, tirets ou apostrophes, "
                             f"{NOM_MAX} caractères au plus")
    return texte


def controler_classe(nom: str, niveau: str, annee: str) -> tuple[str, str, str]:
    nom = " ".join((nom or "").split())
    if not nom or len(nom) > NOM_CLASSE_MAX or not CARACTERES_CLASSE.match(nom):
        raise ClasseInvalide(f"nom de la classe : 1 à {NOM_CLASSE_MAX} caractères (lettres, chiffres, espaces)")
    if niveau not in NIVEAUX:
        raise ClasseInvalide(f"classe inconnue : {niveau} (permises : {', '.join(NIVEAUX)})")
    m = re.match(r"^(\d{4})-(\d{4})$", annee or "")
    if not m or int(m[2]) != int(m[1]) + 1:
        raise ClasseInvalide("année scolaire attendue sous la forme 2026-2027")
    return nom, niveau, annee


def _majuscules(mot: str) -> bool:
    lettres = [c for c in mot if c.isalpha()]
    return len(lettres) > 1 and all(c.isupper() for c in lettres)


def lire_liste(texte: str) -> tuple[list[dict], list[str]]:
    """Une liste collée → ([{nom, prenom}], remarques). Une ligne par élève :
    - « DUPONT;Marie », « DUPONT⇥Marie », « DUPONT, Marie » : le nom, puis le prénom (colonnes en plus ignorées) ;
    - « DUPONT Marie », « LE GOFF Anne-Sophie » : les mots en majuscules au début forment le nom ;
    - « Dupont Marie » : le premier mot est pris pour le nom (à vérifier : signalé).
    Une ligne illisible est signalée et écartée ; rien n'est enregistré ici."""
    eleves, remarques, en_trop, supposes = [], [], False, 0
    for numero, ligne in enumerate((texte or "").splitlines(), start=1):
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        separateur = next((s for s in ("\t", ";", ",") if s in ligne), None)
        if separateur:
            morceaux = [m.strip() for m in ligne.split(separateur)]
            nom, prenom = morceaux[0], morceaux[1] if len(morceaux) > 1 else ""
            en_trop = en_trop or any(m for m in morceaux[2:])
        else:
            mots = ligne.split()
            debut = 0
            while debut < len(mots) - 1 and _majuscules(mots[debut]):
                debut += 1
            if debut == 0:
                debut, supposes = 1, supposes + 1
            nom, prenom = " ".join(mots[:debut]), " ".join(mots[debut:])
        try:
            eleves.append({"nom": controler_nom(nom, "nom"), "prenom": controler_nom(prenom, "prénom")})
        except ClasseInvalide as e:
            remarques.append(f"ligne {numero} écartée : {e} (attendu : le nom, puis le prénom)")
    if en_trop:
        remarques.append("des colonnes en plus (date de naissance…) ont été ignorées : seuls le nom et le prénom "
                         "sont gardés")
    if supposes:
        remarques.append(f"{supposes} ligne(s) sans nom en majuscules : le premier mot a été pris pour le nom ; "
                         "vérifier, ou écrire « NOM;Prénom »")
    vus = set()
    for e in eleves:
        cle = (e["nom"].casefold(), e["prenom"].casefold())
        if cle in vus:
            remarques.append(f"« {e['prenom']} {e['nom']} » apparaît deux fois : homonymes, ou doublon ?")
        vus.add(cle)
    if len(eleves) > ELEVES_MAX:
        remarques.append(f"{len(eleves)} élèves : une classe en compte {ELEVES_MAX} au plus")
    return eleves, remarques


# --- lecture --------------------------------------------------------------------------------------

def _classe(conn: sqlite3.Connection, compte: dict, classe_id: int) -> sqlite3.Row:
    ligne = conn.execute("SELECT * FROM classe WHERE id = ? AND enseignant_id = ?", (classe_id, compte["id"])).fetchone()
    if ligne is None:
        raise Introuvable("classe introuvable")
    return ligne


def _eleve(conn: sqlite3.Connection, compte: dict, eleve_id: int) -> sqlite3.Row:
    ligne = conn.execute("SELECT e.*, c.nom AS classe_nom, c.annee, c.niveau FROM eleve e JOIN classe c ON c.id = e.classe_id "
                         "WHERE e.id = ? AND c.enseignant_id = ?", (eleve_id, compte["id"])).fetchone()
    if ligne is None:
        raise Introuvable("élève introuvable")
    return ligne


def _vue_classe(ligne: sqlite3.Row, eleves: int) -> dict:
    return {"id": ligne["id"], "nom": ligne["nom"], "niveau": ligne["niveau"], "annee": ligne["annee"],
            "archivee": bool(ligne["archivee"]), "eleves": eleves, "creee": ligne["creee"], "connexion": ligne["connexion"]}


def _vue_eleve(ligne: sqlite3.Row) -> dict:
    return {"id": ligne["id"], "numero": ligne["numero"], "nom": ligne["nom"], "prenom": ligne["prenom"],
            "actif": bool(ligne["actif"]), "bloque": bool(ligne["bloque"])}


# les élèves qui se connectent avec 4 images : un enfant de CP ne tape pas un mot de passe (choix du 10/11)
CLASSES_AUX_IMAGES = ("CP", "CE1", "CE2", "6e")


def connexion_du_niveau(niveau: str) -> str:
    """4 images du CP à la 6e ; un mot de passe imprimé de la 5e à la 3e (choix du 27/10)."""
    return "images" if niveau in CLASSES_AUX_IMAGES else "mot_de_passe"


def lister(base: Base, compte: dict, archivees: bool = False) -> list[dict]:
    """Les classes de cet enseignant, les plus récentes d'abord."""
    with base.lire() as conn:
        lignes = conn.execute("SELECT c.*, (SELECT COUNT(*) FROM eleve e WHERE e.classe_id = c.id) AS n FROM classe c "
                              "WHERE c.enseignant_id = ? AND (c.archivee = 0 OR ?) ORDER BY c.annee DESC, c.nom",
                              (compte["id"], int(archivees))).fetchall()
    return [_vue_classe(l, l["n"]) for l in lignes]


def lire(base: Base, compte: dict, classe_id: int) -> dict:
    """La classe et ses élèves, par numéro ; noté au journal (accès à des données d'élèves)."""
    with base.ecrire() as conn:
        classe = _classe(conn, compte, classe_id)
        eleves = conn.execute("SELECT * FROM eleve WHERE classe_id = ? ORDER BY numero", (classe_id,)).fetchall()
        journal.noter(conn, "classe_consultee", compte, cible=f"classe:{classe_id}")
    return {**_vue_classe(classe, len(eleves)), "liste": [_vue_eleve(e) for e in eleves]}


# --- les cartes de connexion --------------------------------------------------------------------------

def _carte(eleve: dict, classe: sqlite3.Row, code: tuple[int, ...] | str) -> dict:
    """Ce qu'imprime la carte ; le seul moment où le code existe en clair : les 4 images, ou le mot de passe."""
    carte = {"eleve_id": eleve["id"], "numero": eleve["numero"], "nom": eleve["nom"], "prenom": eleve["prenom"],
             "classe": classe["nom"], "annee": classe["annee"]}
    if isinstance(code, str):
        return {**carte, "connexion": "mot_de_passe", "mot_de_passe": code}
    return {**carte, "connexion": "images", "code": images.decrire(code)}


def _tirer(connexion: str) -> tuple[int, ...] | str:
    return codes.tirer_mot_de_passe() if connexion == "mot_de_passe" else codes.tirer()


def _avec_codes(eleves: list[dict], cle: bytes, connexion: str) -> list[tuple[dict, tuple[int, ...] | str, str]]:
    """Tire et calcule les codes HORS de la transaction : ~40 ms par élève."""
    resultat = []
    for e in eleves:
        code = _tirer(connexion)
        resultat.append((e, code, codes.empreinte(code, cle)))
    return resultat


# --- créer, compléter ------------------------------------------------------------------------------

def creer(base: Base, compte: dict, nom: str, niveau: str, annee: str | None, eleves: list[dict],
          cle: bytes) -> tuple[dict, list[dict]]:
    """La classe et ses élèves, numérotés dans l'ordre de la liste ; renvoie (classe, cartes)."""
    nom, niveau, annee = controler_classe(nom, niveau, annee or annee_scolaire())
    eleves = [{"nom": controler_nom(e.get("nom"), "nom"), "prenom": controler_nom(e.get("prenom"), "prénom")}
              for e in eleves]
    if len(eleves) > ELEVES_MAX:
        raise ClasseInvalide(f"une classe compte {ELEVES_MAX} élèves au plus")
    connexion = connexion_du_niveau(niveau)
    tires = _avec_codes(eleves, cle, connexion)
    with base.ecrire() as conn:
        try:
            classe_id = conn.execute("INSERT INTO classe (enseignant_id, nom, niveau, annee, creee, connexion) "
                                     "VALUES (?, ?, ?, ?, ?, ?)",
                                     (compte["id"], nom, niveau, annee, maintenant_iso(), connexion)).lastrowid
        except sqlite3.IntegrityError:
            raise ClasseInvalide(f"vous avez déjà une classe « {nom} » en {annee}") from None
        cartes = _inserer(conn, _classe(conn, compte, classe_id), tires)
        classe = _classe(conn, compte, classe_id)
        journal.noter(conn, "classe_creee", compte, cible=f"classe:{classe_id}", detail=f"{len(eleves)} élève(s)")
    return _vue_classe(classe, len(eleves)), cartes


def _inserer(conn: sqlite3.Connection, classe: sqlite3.Row, tires: list) -> list[dict]:
    """Numérotés à la suite du dernier numéro donné dans la classe : un numéro n'est jamais redonné, même après
    une suppression (le mode sans réseau, E8.9, identifie l'élève par son numéro)."""
    cartes, numero = [], classe["dernier_numero"]
    for e, code, empreinte in tires:
        numero += 1
        eleve_id = conn.execute("INSERT INTO eleve (classe_id, numero, nom, prenom, code, cree) VALUES (?, ?, ?, ?, ?, ?)",
                                (classe["id"], numero, e["nom"], e["prenom"], empreinte, maintenant_iso())).lastrowid
        cartes.append(_carte({"id": eleve_id, "numero": numero, **e}, classe, code))
    conn.execute("UPDATE classe SET dernier_numero = ? WHERE id = ?", (numero, classe["id"]))
    return cartes


def ajouter(base: Base, compte: dict, classe_id: int, eleves: list[dict], cle: bytes) -> list[dict]:
    """De nouveaux élèves, numérotés à la suite."""
    eleves = [{"nom": controler_nom(e.get("nom"), "nom"), "prenom": controler_nom(e.get("prenom"), "prénom")}
              for e in eleves]
    with base.lire() as conn:
        connexion = _classe(conn, compte, classe_id)["connexion"]
    tires = _avec_codes(eleves, cle, connexion)
    with base.ecrire() as conn:
        classe = _classe(conn, compte, classe_id)
        presents = conn.execute("SELECT COUNT(*) FROM eleve WHERE classe_id = ?", (classe_id,)).fetchone()[0]
        if presents + len(eleves) > ELEVES_MAX:
            raise ClasseInvalide(f"une classe compte {ELEVES_MAX} élèves au plus ({presents} déjà)")
        cartes = _inserer(conn, classe, tires)
        journal.noter(conn, "eleves_ajoutes", compte, cible=f"classe:{classe_id}", detail=f"{len(eleves)} élève(s)")
    return cartes


# --- les codes --------------------------------------------------------------------------------------

def nouveaux_codes(base: Base, compte: dict, classe_id: int, cle: bytes) -> list[dict]:
    """Un nouveau code pour chaque élève de la classe (cartes perdues) ; les anciens ne marchent plus."""
    with base.lire() as conn:
        connexion = _classe(conn, compte, classe_id)["connexion"]
        eleves = [dict(e) for e in conn.execute("SELECT * FROM eleve WHERE classe_id = ? ORDER BY numero", (classe_id,))]
    tires = _avec_codes(eleves, cle, connexion)
    with base.ecrire() as conn:
        classe = _classe(conn, compte, classe_id)
        for e, _, empreinte in tires:
            # un nouveau code débloque l'élève ; ses sessions en cours se ferment
            conn.execute("UPDATE eleve SET code = ?, echecs = 0, bloque = 0 WHERE id = ?", (empreinte, e["id"]))
            conn.execute("DELETE FROM session_eleve WHERE eleve_id = ?", (e["id"],))
        journal.noter(conn, "codes_classe", compte, cible=f"classe:{classe_id}", detail=f"{len(tires)} code(s)")
    return [_carte(e, classe, code) for e, code, _ in tires]


def nouveau_code(base: Base, compte: dict, eleve_id: int, cle: bytes) -> dict:
    """Un nouveau code pour un élève (carte perdue, code vu par un autre) : un clic, en classe. Il débloque l'élève."""
    with base.lire() as conn:
        connexion = _classe(conn, compte, _eleve(conn, compte, eleve_id)["classe_id"])["connexion"]
    code = _tirer(connexion)
    empreinte = codes.empreinte(code, cle)
    with base.ecrire() as conn:
        eleve = _eleve(conn, compte, eleve_id)
        conn.execute("UPDATE eleve SET code = ?, echecs = 0, bloque = 0 WHERE id = ?", (empreinte, eleve_id))
        conn.execute("DELETE FROM session_eleve WHERE eleve_id = ?", (eleve_id,))
        classe = _classe(conn, compte, eleve["classe_id"])
        journal.noter(conn, "code_eleve", compte, cible=f"classe:{classe['id']}/eleve:{eleve_id}")
    return _carte(dict(eleve), classe, code)


def debloquer(base: Base, compte: dict, eleve_id: int) -> dict:
    """Après 5 essais manqués, l'élève est bloqué sur le serveur de classe (E8) : l'enseignant le débloque."""
    with base.ecrire() as conn:
        eleve = _eleve(conn, compte, eleve_id)
        conn.execute("UPDATE eleve SET echecs = 0, bloque = 0 WHERE id = ?", (eleve_id,))
        journal.noter(conn, "eleve_debloque", compte, cible=f"classe:{eleve['classe_id']}/eleve:{eleve_id}")
        return _vue_eleve(conn.execute("SELECT * FROM eleve WHERE id = ?", (eleve_id,)).fetchone())


def noms_des_eleves(base: Base, compte: dict) -> list[tuple[str, str]]:
    """(prénom, nom) de tous les élèves de l'enseignant : ils ne doivent apparaître ni dans une demande au modèle, ni
    dans un exercice (plan IA, IA1). Ils ne quittent jamais le PC et ne sont jamais envoyés au modèle."""
    with base.lire() as conn:
        return [(l["prenom"], l["nom"]) for l in conn.execute(
            "SELECT e.prenom, e.nom FROM eleve e JOIN classe c ON c.id = e.classe_id WHERE c.enseignant_id = ?",
            (compte["id"],))]


def noms_de_tous_les_eleves(base: Base) -> list[tuple[str, str]]:
    """(prénom, nom) des élèves de tous les enseignants : aucun ne doit entrer dans les données d'entraînement du
    modèle (plan IA, IA3)."""
    with base.lire() as conn:
        return [(l["prenom"], l["nom"]) for l in conn.execute("SELECT prenom, nom FROM eleve")]


def bloques(base: Base, compte: dict) -> list[dict]:
    """Les élèves bloqués des classes (non archivées) de l'enseignant : « À faire », sur son accueil."""
    with base.lire() as conn:
        lignes = conn.execute("SELECT e.id, e.nom, e.prenom, c.id AS classe_id, c.nom AS classe FROM eleve e "
                              "JOIN classe c ON c.id = e.classe_id WHERE c.enseignant_id = ? AND c.archivee = 0 "
                              "AND e.bloque = 1 AND e.actif = 1 ORDER BY c.nom, e.numero", (compte["id"],)).fetchall()
    return [dict(l) for l in lignes]


# --- corriger, désactiver, supprimer ------------------------------------------------------------------

def modifier(base: Base, compte: dict, eleve_id: int, nom: str, prenom: str) -> dict:
    """Rectification (RGPD) : un nom mal écrit."""
    nom, prenom = controler_nom(nom, "nom"), controler_nom(prenom, "prénom")
    with base.ecrire() as conn:
        eleve = _eleve(conn, compte, eleve_id)
        conn.execute("UPDATE eleve SET nom = ?, prenom = ? WHERE id = ?", (nom, prenom, eleve_id))
        journal.noter(conn, "eleve_modifie", compte, cible=f"classe:{eleve['classe_id']}/eleve:{eleve_id}")
        return _vue_eleve(conn.execute("SELECT * FROM eleve WHERE id = ?", (eleve_id,)).fetchone())


def activer(base: Base, compte: dict, eleve_id: int, actif: bool) -> dict:
    """Désactiver (limitation, RGPD) : l'élève ne se connecte plus, rien n'est enregistré ; ses données restent."""
    with base.ecrire() as conn:
        eleve = _eleve(conn, compte, eleve_id)
        conn.execute("UPDATE eleve SET actif = ? WHERE id = ?", (int(actif), eleve_id))
        if not actif:
            conn.execute("DELETE FROM session_eleve WHERE eleve_id = ?", (eleve_id,))  # déconnecté sur-le-champ
        journal.noter(conn, "eleve_reactive" if actif else "eleve_desactive", compte,
                      cible=f"classe:{eleve['classe_id']}/eleve:{eleve_id}")
        return _vue_eleve(conn.execute("SELECT * FROM eleve WHERE id = ?", (eleve_id,)).fetchone())


def supprimer(base: Base, compte: dict, eleve_id: int) -> None:
    """Effacement (RGPD) : l'élève et toutes ses réponses (E4 : par les clés étrangères). Le journal garde la trace
    de la suppression et du numéro, pas le nom."""
    with base.ecrire() as conn:
        eleve = _eleve(conn, compte, eleve_id)
        conn.execute("DELETE FROM eleve WHERE id = ?", (eleve_id,))
        journal.noter(conn, "eleve_supprime", compte, cible=f"classe:{eleve['classe_id']}/eleve:{eleve_id}",
                      detail=f"numéro {eleve['numero']}")


# --- l'export d'un élève (droit d'accès) --------------------------------------------------------------

ORIGINES = {"simulation": "simulée (élève fictif)", "classe": "en classe", "import": "importée"}
NATURES = {"retravailler": "À retravailler", "plus_loin": "Pour aller plus loin"}


def cellule(valeur) -> str:
    """Une cellule de CSV qui ne s'exécute pas : « =… », « +… », « -… », « @… » sont précédés d'une apostrophe."""
    texte = "" if valeur is None else str(valeur)
    return "'" + texte if texte[:1] in ("=", "+", "-", "@", "\t", "\r") else texte


def exporter(base: Base, compte: dict, eleve_id: int) -> tuple[str, bytes]:
    """(nom du fichier, contenu) : un CSV lisible dans un tableur (point-virgule, UTF-8 avec BOM)."""
    with base.ecrire() as conn:
        eleve = _eleve(conn, compte, eleve_id)
        reponses = _reponses(conn, eleve_id)
        groupes = [r[0] for r in conn.execute("SELECT g.nom FROM groupe g JOIN groupe_eleve ge ON ge.groupe_id = g.id "
                                              "WHERE ge.eleve_id = ? ORDER BY g.id", (eleve_id,))]
        propositions = conn.execute("SELECT nature, attendu, exercice, cree FROM proposition WHERE eleve_id = ? "
                                    "ORDER BY id", (eleve_id,)).fetchall()
        journal.noter(conn, "eleve_exporte", compte, cible=f"classe:{eleve['classe_id']}/eleve:{eleve_id}")
    tampon = io.StringIO()
    ecrire = csv.writer(tampon, delimiter=";", lineterminator="\r\n").writerow
    for ligne in (["Données de l'élève (export du droit d'accès, RGPD)"],
                  ["Nom", eleve["nom"]], ["Prénom", eleve["prenom"]],
                  ["Classe", f"{eleve['classe_nom']} ({eleve['niveau']}, {eleve['annee']})"],
                  ["Numéro dans la classe", eleve["numero"]], ["État", "actif" if eleve["actif"] else "désactivé"],
                  ["Enregistré le", eleve["cree"]],
                  ["Code de connexion", "non exporté : seule son empreinte est gardée"], [],
                  ["Réponses aux exercices"],
                  ["Date", "Exercice", "Question", "Réponse choisie", "Juste", "Temps (s)", "Attendu du programme",
                   "Origine", "Compte dans le suivi"]):
        ecrire([cellule(v) for v in ligne])
    for r in reponses:
        ecrire([cellule(v) for v in r])
    if not reponses:
        ecrire(["aucune réponse enregistrée"])
    ecrire([])
    ecrire(["Groupes de besoins"])
    for nom in groupes or ["aucun groupe"]:
        ecrire([cellule(nom)])
    ecrire([])
    ecrire(["Exercices à travailler, validés par l'enseignant"])
    ecrire(["Pour", "Attendu du programme", "Exercice", "Validé le"])
    for p in propositions:
        ecrire([cellule(v) for v in (NATURES.get(p["nature"], p["nature"]), p["attendu"], p["exercice"] or "à générer",
                                      p["cree"])])
    if not propositions:
        ecrire(["aucun exercice validé"])
    ecrire([])
    ecrire([cellule(f"Exporté le {datetime.now().isoformat(timespec='seconds')} par {compte['identifiant']}")])
    return f"eleve-{eleve_id}.csv", ("﻿" + tampon.getvalue()).encode("utf-8")


def _reponses(conn: sqlite3.Connection, eleve_id: int) -> list[list]:
    """Les réponses de l'élève (tables du suivi, E4), annulées comprises : l'export montre tout ce qui est gardé."""
    lignes = conn.execute("SELECT t.date, COALESCE(t.titre, t.exercice) AS exercice, t.origine, t.annulee, t.compte, r.question, "
                          "r.choix, r.juste, r.temps_s, r.attendu FROM reponse r JOIN tentative t ON t.id = r.tentative_id "
                          "WHERE t.eleve_id = ? ORDER BY t.date, t.id, r.question", (eleve_id,)).fetchall()
    return [[r["date"], r["exercice"], r["question"], "ABCDEFGH"[r["choix"]] if r["choix"] < 8 else r["choix"],
             "oui" if r["juste"] else "non", r["temps_s"], r["attendu"] or "", ORIGINES.get(r["origine"], r["origine"]),
             "non (annulée)" if r["annulee"] else "non (entraînement)" if not r["compte"] else "oui"] for r in lignes]


# --- archiver, purger ---------------------------------------------------------------------------------

def archiver(base: Base, compte: dict, classe_id: int, archivee: bool) -> dict:
    """Une classe archivée disparaît de la liste (et ses élèves ne se connecteront plus, E8) ; rien n'est effacé."""
    with base.ecrire() as conn:
        _classe(conn, compte, classe_id)
        conn.execute("UPDATE classe SET archivee = ? WHERE id = ?", (int(archivee), classe_id))
        journal.noter(conn, "classe_archivee" if archivee else "classe_desarchivee", compte, cible=f"classe:{classe_id}")
        classe = _classe(conn, compte, classe_id)
        n = conn.execute("SELECT COUNT(*) FROM eleve WHERE classe_id = ?", (classe_id,)).fetchone()[0]
    return _vue_classe(classe, n)


def _a_purger(conn: sqlite3.Connection, compte: dict, annee: str) -> list[sqlite3.Row]:
    """Les classes des années passées : celles de l'enseignant ; toutes, pour un administrateur (sans les ouvrir)."""
    tous = compte.get("role") == "admin"
    return conn.execute("SELECT c.id, c.nom, c.annee, e.identifiant, (SELECT COUNT(*) FROM eleve WHERE classe_id = c.id) AS n "
                        "FROM classe c JOIN enseignant e ON e.id = c.enseignant_id "
                        "WHERE c.annee < ? AND (? OR c.enseignant_id = ?) ORDER BY c.annee, c.nom",
                        (annee, int(tous), compte["id"])).fetchall()


def apercu_purge(base: Base, compte: dict, jour: date | None = None) -> dict:
    annee = annee_scolaire(jour)
    with base.lire() as conn:
        lignes = _a_purger(conn, compte, annee)
    return {"annee_courante": annee, "classes": [{"nom": l["nom"], "annee": l["annee"], "eleves": l["n"],
                                                  "enseignant": l["identifiant"]} for l in lignes],
            "eleves": sum(l["n"] for l in lignes)}


def purger(base: Base, compte: dict, jour: date | None = None) -> dict:
    """Purge de fin d'année (RGPD) : les classes des années passées, leurs élèves et leurs réponses."""
    annee = annee_scolaire(jour)
    with base.ecrire() as conn:
        lignes = _a_purger(conn, compte, annee)
        for l in lignes:
            conn.execute("DELETE FROM classe WHERE id = ?", (l["id"],))
        eleves = sum(l["n"] for l in lignes)
        journal.noter(conn, "purge", compte, cible=f"avant {annee}", detail=f"{len(lignes)} classe(s), {eleves} élève(s)")
    return {"classes": len(lignes), "eleves": eleves}
