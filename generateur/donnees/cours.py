"""Les cours des enseignants (plan IA, IA2 : docs/plan-ia.md §3) : le modèle les LIT au moment de générer, il ne
les apprend pas. Un cours retiré disparaît ; chaque enseignant ne lit que les siens ; chaque question cite sa source.

- `deposer` : le fichier est lu dans un processus à part (generateur/cours/extraction.py) ; seul le texte est gardé,
  découpé en passages d'environ 300 mots (avec leur page, pour un PDF) et indexé (SQLite FTS5, sans accents). Refusé
  s'il contient le nom d'un élève de l'enseignant (données personnelles) ou une consigne adressée au modèle (texte
  caché dans un document téléchargé, par exemple).
- `chercher` : les passages les plus proches d'une demande (classement BM25 de FTS5), dans les cours de l'enseignant.
- `retirer` : le cours, ses passages et leur index sont effacés.
Les liens sont retirés du texte gardé (« [lien retiré] ») : un exercice n'en contient jamais, et une consigne cachée
peut demander au modèle de les recopier (banc des cours du 29/10 : N3 bloquait chaque question, la génération
échouait).
Le journal note le dépôt et le retrait (jamais le texte, ni le nom du fichier : il peut contenir un nom).
"""

import hashlib
import re
import sqlite3

from generateur.cours.extraction import CoursIllisible, extraire_a_part
from generateur.donnees import classes, journal
from generateur.donnees.base import Base, maintenant_iso
from generateur.moteur import securite

MOTS_PAR_PASSAGE = 300
COURS_MAX = 200          # cours déposés par enseignant
NOM_MAX = 120
PASSAGES_PAR_DEFAUT = 4  # passages donnés au modèle (plan IA : 3 à 5)

# mots sans poids pour chercher dans un cours (la forme de comparaison : minuscules, sans accents)
MOTS_VIDES = set("""
a au aux avec ce ces cet cette dans de des du elle en entre et est etre il ils je la le les leur leurs lui mais me
meme mes mon ne ni nos notre nous on ou par pas pour qu que qui sa se ses si son sont sur ta te tes ton tu un une vos
votre vous y d l qcm quiz exercice exercices question questions classe eleve eleves sixieme cinquieme quatrieme
troisieme 6e 5e 4e 3e niveau facile moyen difficile sujet notion theme cours propos travailler revoir
""".split())


class CoursRefuse(Exception):
    """Le cours n'est pas gardé ; le message est pour l'enseignant."""


def _decouper(blocs: list[dict], mots_max: int = MOTS_PAR_PASSAGE) -> list[dict]:
    """Des paragraphes aux passages d'environ `mots_max` mots, sans couper un paragraphe s'il tient ; un passage garde
    la page de son premier paragraphe. Un paragraphe trop long est coupé entre deux phrases."""
    morceaux = []
    for b in blocs:
        mots = b["texte"].split()
        if len(mots) <= mots_max:
            morceaux.append(b)
            continue
        phrase, courant = re.split(r"(?<=[.!?])\s+", b["texte"]), []
        for p in phrase:
            if courant and len(" ".join(courant + [p]).split()) > mots_max:
                morceaux.append({"page": b["page"], "texte": " ".join(courant)})
                courant = []
            courant.append(p)
        if courant:
            morceaux.append({"page": b["page"], "texte": " ".join(courant)})
    passages, courant, page = [], [], None
    for m in morceaux:
        if courant and len(" ".join(courant + [m["texte"]]).split()) > mots_max:
            passages.append({"page": page, "texte": " ".join(courant)})
            courant = []
        if not courant:
            page = m["page"]
        courant.append(m["texte"])
    if courant:
        passages.append({"page": page, "texte": " ".join(courant)})
    return passages


def _nom(nom: str) -> str:
    nom = securite.nettoyer(nom or "") or "cours"
    return nom[:NOM_MAX]


def deposer(base: Base, compte: dict, nom: str, contenu: bytes, matiere: str | None = None, niveau: str | None = None,
            noms_proteges=None) -> dict:
    """Lit, contrôle, découpe et range un cours ; lève CoursRefuse (avec un message pour l'enseignant)."""
    try:
        lu = extraire_a_part(contenu, nom)
    except CoursIllisible as e:
        raise CoursRefuse(str(e)) from None
    blocs = [{"page": b["page"], "texte": securite.LIEN.sub("[lien retiré]", t)} for b in lu["blocs"]
             if (t := securite.nettoyer(b["texte"]))]
    texte = "\n".join(b["texte"] for b in blocs)
    if not texte.strip():
        raise CoursRefuse("aucun texte trouvé dans ce document")
    # un cours ne contient pas d'élève : ses noms iraient au modèle avec les passages
    noms = list(noms_proteges if noms_proteges is not None else classes.noms_des_eleves(base, compte))
    for prenom, nom_eleve in noms:
        if securite.nom_d_eleve(texte, [(prenom, nom_eleve)]):
            raise CoursRefuse(f"ce document contient le nom d'un de vos élèves (« {prenom} {nom_eleve} ») : un cours "
                              "déposé ne doit contenir aucune donnée personnelle. Retirez-le du document.")
    # une consigne adressée au modèle, souvent cachée (texte blanc, minuscule) dans un document téléchargé
    if passage := securite._cherche(securite.INJECTION, texte):
        raise CoursRefuse(f"ce document contient une consigne adressée au modèle (« {passage} »), peut-être cachée "
                          "(texte blanc ou minuscule) : il n'est pas gardé.")
    passages = _decouper(blocs)
    empreinte = hashlib.sha256(texte.encode("utf-8")).hexdigest()
    with base.ecrire() as conn:
        if conn.execute("SELECT COUNT(*) FROM cours WHERE enseignant_id = ?", (compte["id"],)).fetchone()[0] >= COURS_MAX:
            raise CoursRefuse(f"vous avez déjà {COURS_MAX} cours : retirez-en un avant d'en déposer un autre")
        if deja := conn.execute("SELECT nom FROM cours WHERE enseignant_id = ? AND empreinte = ?",
                                (compte["id"], empreinte)).fetchone():
            raise CoursRefuse(f"ce cours est déjà déposé (« {deja['nom']} »)")
        cours_id = conn.execute(
            "INSERT INTO cours (enseignant_id, nom, matiere, niveau, format, pages, mots, empreinte, ajoute) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (compte["id"], _nom(nom), matiere or None, niveau or None, lu["format"], lu["pages"], len(texte.split()),
             empreinte, maintenant_iso())).lastrowid
        for rang, p in enumerate(passages, start=1):
            passage_id = conn.execute("INSERT INTO cours_passage (cours_id, rang, page, texte) VALUES (?, ?, ?, ?)",
                                      (cours_id, rang, p["page"], p["texte"])).lastrowid
            conn.execute("INSERT INTO cours_fts (rowid, texte) VALUES (?, ?)", (passage_id, p["texte"]))
        journal.noter(conn, "cours_depose", compte, cible=f"cours:{cours_id}",
                      detail=f"{lu['format'].upper()}, {len(passages)} passage(s)")
        return _vue(conn.execute("SELECT * FROM cours WHERE id = ?", (cours_id,)).fetchone(), len(passages))


def _vue(c: sqlite3.Row, passages: int) -> dict:
    return {"id": c["id"], "nom": c["nom"], "matiere": c["matiere"], "niveau": c["niveau"], "format": c["format"],
            "pages": c["pages"], "mots": c["mots"], "passages": passages, "ajoute": c["ajoute"]}


def _cours(conn: sqlite3.Connection, compte: dict, cours_id: int) -> sqlite3.Row:
    c = conn.execute("SELECT * FROM cours WHERE id = ? AND enseignant_id = ?", (cours_id, compte["id"])).fetchone()
    if c is None:
        raise classes.Introuvable("cours introuvable")
    return c


def lister(base: Base, compte: dict) -> list[dict]:
    with base.lire() as conn:
        return [_vue(c, c["n"]) for c in conn.execute(
            "SELECT c.*, (SELECT COUNT(*) FROM cours_passage p WHERE p.cours_id = c.id) AS n FROM cours c "
            "WHERE c.enseignant_id = ? ORDER BY c.id DESC", (compte["id"],))]


def lire(base: Base, compte: dict, cours_id: int) -> dict:
    """Le cours et son texte extrait, passage par passage : l'enseignant vérifie ce que le modèle lira."""
    with base.lire() as conn:
        c = _cours(conn, compte, cours_id)
        passages = [dict(p) for p in conn.execute("SELECT id, rang, page, texte FROM cours_passage WHERE cours_id = ? "
                                                  "ORDER BY rang", (cours_id,))]
    return {**_vue(c, len(passages)), "texte": passages}


def retirer(base: Base, compte: dict, cours_id: int) -> None:
    """Le cours, ses passages et leur index sont effacés ; les exercices déjà générés gardent leurs citations."""
    with base.ecrire() as conn:
        _cours(conn, compte, cours_id)
        for (passage_id,) in conn.execute("SELECT id FROM cours_passage WHERE cours_id = ?", (cours_id,)).fetchall():
            conn.execute("DELETE FROM cours_fts WHERE rowid = ?", (passage_id,))
        conn.execute("DELETE FROM cours WHERE id = ?", (cours_id,))  # les passages suivent (ON DELETE CASCADE)
        journal.noter(conn, "cours_retire", compte, cible=f"cours:{cours_id}")


def requete_fts(texte: str) -> str | None:
    """La demande → une requête FTS5 : les mots qui portent le sens, au singulier approché, en préfixe, reliés par OR
    (BM25 classe les passages qui en ont le plus) ; None s'il n'en reste aucun."""
    mots = []
    for mot in re.findall(r"[a-z0-9]+", securite.forme(texte or "")):
        if mot in MOTS_VIDES or len(mot) < 3:
            continue
        racine = mot[:-1] if len(mot) > 4 and mot[-1] in "sx" else mot  # fractions → fraction*, châteaux → chateau*
        if racine not in mots:
            mots.append(racine)
    return " OR ".join(f'"{m}"*' for m in mots[:20]) or None


def chercher(base: Base, compte: dict, texte: str, cours_ids: list[int] | None = None, matiere: str | None = None,
             niveau: str | None = None, k: int = PASSAGES_PAR_DEFAUT) -> list[dict]:
    """Les `k` passages des cours de l'enseignant les plus proches de `texte` : {"id", "cours_id", "cours", "page",
    "texte"}. Restreint à `cours_ids` si donnés ; sinon, aux cours de la matière (et du niveau) quand il y en a."""
    requete = requete_fts(texte)
    if not requete:
        return []
    with base.lire() as conn:
        tous = conn.execute("SELECT id, matiere, niveau FROM cours WHERE enseignant_id = ?", (compte["id"],)).fetchall()
        if cours_ids:
            permis = {c["id"] for c in tous if c["id"] in set(cours_ids)}
        else:
            permis = {c["id"] for c in tous if (not matiere or c["matiere"] in (None, matiere))
                      and (not niveau or c["niveau"] in (None, niveau))} or {c["id"] for c in tous}
        if not permis:
            return []
        # requête fixe (jamais assemblée : tests/test_donnees.py), les cours permis filtrés ensuite
        lignes = [l for l in conn.execute(
            "SELECT p.id, p.cours_id, c.nom AS cours, p.page, p.texte, bm25(cours_fts) AS score FROM cours_fts "
            "JOIN cours_passage p ON p.id = cours_fts.rowid JOIN cours c ON c.id = p.cours_id "
            "WHERE cours_fts MATCH ? AND c.enseignant_id = ? ORDER BY score LIMIT 500", (requete, compte["id"]))
                  if l["cours_id"] in permis][:k]
    return [{"id": l["id"], "cours_id": l["cours_id"], "cours": l["cours"], "page": l["page"], "texte": l["texte"]}
            for l in lignes]
