"""Les exercices publiés pour les élèves (évolution E8.4) : l'enseignant publie un exercice **accepté** pour une
classe, un de ses groupes de besoins ou un de ses élèves, avec des dates de début et de fin facultatives.

L'élève connecté au serveur de classe voit, sur son accueil : ses « À retravailler » et « Pour aller plus loin »
(les exercices à travailler validés par l'enseignant, E4), puis ses exercices publiés. Il ne peut ouvrir que ceux-là
(`autorise`) : un identifiant d'exercice deviné ou recopié ne suffit pas.
"""

import re
import sqlite3
from datetime import date

from generateur.donnees import classes, journal
from generateur.donnees.base import Base, maintenant_iso
from generateur.moteur import banque

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _jour(texte: str | None, champ: str) -> str | None:
    if not texte:
        return None
    try:
        if not DATE.match(texte):
            raise ValueError
        date.fromisoformat(texte)
    except ValueError:
        raise classes.ClasseInvalide(f"{champ} : date invalide (attendu AAAA-MM-JJ) : {texte}") from None
    return texte


def _exercice_accepte(ident: str) -> dict:
    try:
        instance = banque.charger(ident)
    except banque.ExerciceInconnu:
        raise classes.Introuvable("exercice introuvable") from None
    if banque.statut(instance) != banque.ACCEPTE:
        raise classes.ClasseInvalide("seul un exercice accepté se publie : relisez-le et acceptez-le d'abord")
    return instance


# --- côté enseignant ---------------------------------------------------------------------------------

def publier(base: Base, compte: dict, exercice: str, classe_id: int, groupe_id: int | None = None,
            eleve_id: int | None = None, debut: str | None = None, fin: str | None = None) -> dict:
    instance = _exercice_accepte(exercice)
    debut, fin = _jour(debut, "début"), _jour(fin, "fin")
    if debut and fin and fin < debut:
        raise classes.ClasseInvalide("la fin est avant le début")
    if groupe_id and eleve_id:
        raise classes.ClasseInvalide("publiez pour un groupe ou pour un élève, pas les deux")
    with base.ecrire() as conn:
        classe = classes._classe(conn, compte, classe_id)
        if groupe_id and not conn.execute("SELECT 1 FROM groupe WHERE id = ? AND classe_id = ?", (groupe_id, classe_id)).fetchone():
            raise classes.Introuvable("groupe introuvable dans cette classe")
        if eleve_id and not conn.execute("SELECT 1 FROM eleve WHERE id = ? AND classe_id = ?", (eleve_id, classe_id)).fetchone():
            raise classes.Introuvable("élève introuvable dans cette classe")
        publication_id = conn.execute("INSERT INTO publication (classe_id, groupe_id, eleve_id, exercice, titre, debut, fin, creee) "
                                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                      (classe_id, groupe_id, eleve_id, exercice, instance.get("titre"), debut, fin,
                                       maintenant_iso())).lastrowid
        journal.noter(conn, "exercice_publie", compte, cible=f"classe:{classe['id']}",
                      detail=f"{exercice}" + (f", groupe:{groupe_id}" if groupe_id else "") + (f", eleve:{eleve_id}" if eleve_id else ""))
        return _vue(conn, conn.execute("SELECT * FROM publication WHERE id = ?", (publication_id,)).fetchone())


def _concernes(conn: sqlite3.Connection, p: sqlite3.Row) -> list[int]:
    """Les élèves (actifs) à qui l'exercice est publié : l'élève, les membres du groupe, ou toute la classe."""
    if p["eleve_id"]:
        lignes = conn.execute("SELECT id FROM eleve WHERE id = ? AND actif = 1", (p["eleve_id"],))
    elif p["groupe_id"]:
        lignes = conn.execute("SELECT ge.eleve_id FROM groupe_eleve ge JOIN eleve e ON e.id = ge.eleve_id "
                              "WHERE ge.groupe_id = ? AND e.actif = 1", (p["groupe_id"],))
    else:
        lignes = conn.execute("SELECT id FROM eleve WHERE classe_id = ? AND actif = 1", (p["classe_id"],))
    return [l[0] for l in lignes]


def _etat(p: sqlite3.Row, jour: str) -> str:
    if p["debut"] and jour < p["debut"]:
        return "a_venir"
    if p["fin"] and p["fin"] < jour:
        return "terminee"
    return "en_cours"


def _vue(conn: sqlite3.Connection, p: sqlite3.Row, jour: str | None = None) -> dict:
    pour = "toute la classe"
    if p["groupe_id"]:
        g = conn.execute("SELECT nom FROM groupe WHERE id = ?", (p["groupe_id"],)).fetchone()
        pour = f"groupe « {g['nom']} »" if g else "un groupe"
    elif p["eleve_id"]:
        e = conn.execute("SELECT prenom, nom FROM eleve WHERE id = ?", (p["eleve_id"],)).fetchone()
        pour = f"{e['prenom']} {e['nom']}" if e else "un élève"
    concernes = set(_concernes(conn, p))
    # « faits » : parmi les élèves concernés, ceux qui ont au moins une tentative (non annulée) sur l'exercice
    faits = len(concernes & {l[0] for l in conn.execute("SELECT DISTINCT eleve_id FROM tentative WHERE exercice = ? "
                                                         "AND annulee = 0", (p["exercice"],))})
    classe = conn.execute("SELECT nom FROM classe WHERE id = ?", (p["classe_id"],)).fetchone()
    try:
        instance = banque.charger(p["exercice"])
        matiere, niveau, accepte = instance.get("matiere"), instance.get("niveau"), banque.statut(instance) == banque.ACCEPTE
    except banque.ExerciceInconnu:
        matiere = niveau = None
        accepte = False
    return {"id": p["id"], "classe_id": p["classe_id"], "classe": classe["nom"] if classe else None,
            "groupe_id": p["groupe_id"], "eleve_id": p["eleve_id"], "exercice": p["exercice"], "titre": p["titre"],
            "matiere": matiere, "niveau": niveau, "debut": p["debut"], "fin": p["fin"], "creee": p["creee"],
            "pour": pour, "concernes": len(concernes), "faits": faits,
            # « a_venir », « en_cours », « terminee » ; un exercice modifié depuis (plus accepté) n'est plus montré
            "etat": _etat(p, jour or date.today().isoformat()), "visible": accepte}


def lister(base: Base, compte: dict, classe_id: int, jour: str | None = None) -> list[dict]:
    """Les publications d'une classe, les plus récentes d'abord, avec le nombre d'élèves qui l'ont fait."""
    with base.lire() as conn:
        classes._classe(conn, compte, classe_id)
        return [_vue(conn, p, jour) for p in conn.execute("SELECT * FROM publication WHERE classe_id = ? ORDER BY id DESC",
                                                          (classe_id,))]


def de_l_exercice(base: Base, compte: dict, exercice: str, jour: str | None = None) -> list[dict]:
    """Où cet exercice est publié, dans les classes (non archivées) de l'enseignant."""
    with base.lire() as conn:
        lignes = conn.execute("SELECT p.* FROM publication p JOIN classe c ON c.id = p.classe_id WHERE p.exercice = ? "
                              "AND c.enseignant_id = ? AND c.archivee = 0 ORDER BY p.id DESC", (exercice, compte["id"])).fetchall()
        return [_vue(conn, p, jour) for p in lignes]


def retirer(base: Base, compte: dict, publication_id: int) -> None:
    """L'exercice n'apparaît plus chez les élèves ; leurs réponses restent dans le suivi."""
    with base.ecrire() as conn:
        p = conn.execute("SELECT p.* FROM publication p JOIN classe c ON c.id = p.classe_id WHERE p.id = ? AND c.enseignant_id = ?",
                         (publication_id, compte["id"])).fetchone()
        if p is None:
            raise classes.Introuvable("publication introuvable")
        conn.execute("DELETE FROM publication WHERE id = ?", (publication_id,))
        journal.noter(conn, "publication_retiree", compte, cible=f"classe:{p['classe_id']}", detail=p["exercice"])


# --- côté élève (serveur de classe) ----------------------------------------------------------------------

def _en_cours(p: sqlite3.Row, jour: str) -> bool:
    return (not p["debut"] or p["debut"] <= jour) and (not p["fin"] or jour <= p["fin"])


def _resultat(conn: sqlite3.Connection, eleve_id: int, exercice: str) -> dict | None:
    """La tentative qui compte (la première) : son score ; et la date de la dernière, s'il a rejoué."""
    t = conn.execute("SELECT t.id, t.date, COUNT(r.id) AS questions, COALESCE(SUM(r.juste), 0) AS justes FROM tentative t "
                     "LEFT JOIN reponse r ON r.tentative_id = t.id WHERE t.eleve_id = ? AND t.exercice = ? AND t.annulee = 0 "
                     "AND t.compte = 1 GROUP BY t.id", (eleve_id, exercice)).fetchone()
    if t is None or not t["questions"]:
        return None
    return {"date": t["date"], "justes": t["justes"], "questions": t["questions"]}


def _carte_exercice(conn: sqlite3.Connection, eleve_id: int, ident: str, extra: dict) -> dict | None:
    try:
        instance = banque.charger(ident)
    except banque.ExerciceInconnu:
        return None
    if banque.statut(instance) != banque.ACCEPTE:
        return None  # l'exercice a été modifié depuis : il attend d'être relu et accepté de nouveau
    return {"exercice": ident, "titre": instance.get("titre"), "matiere": instance.get("matiere"),
            "niveau": instance.get("niveau"), "questions": len(instance.get("questions") or []),
            "fait": _resultat(conn, eleve_id, ident), **extra}


def pour_l_eleve(base: Base, eleve: dict, jour: str | None = None) -> dict:
    """Son accueil : À retravailler, Pour aller plus loin (validés par l'enseignant), puis ses exercices publiés en
    cours ; un exercice n'apparaît qu'une fois."""
    jour = jour or date.today().isoformat()
    eleve_id, classe_id = eleve["id"], eleve["classe_id"]
    vus: set[str] = set()
    sections = {"a_retravailler": [], "plus_loin": [], "exercices": []}
    with base.lire() as conn:
        for p in conn.execute("SELECT * FROM proposition WHERE eleve_id = ? AND exercice IS NOT NULL ORDER BY id", (eleve_id,)):
            if p["exercice"] in vus:
                continue
            carte = _carte_exercice(conn, eleve_id, p["exercice"], {"difficulte": "facile" if p["nature"] == "retravailler" else "difficile"})
            if carte:
                vus.add(p["exercice"])
                sections["a_retravailler" if p["nature"] == "retravailler" else "plus_loin"].append(carte)
        publications = conn.execute(
            "SELECT * FROM publication WHERE classe_id = ? AND (eleve_id = ? OR (eleve_id IS NULL AND (groupe_id IS NULL OR "
            "groupe_id IN (SELECT groupe_id FROM groupe_eleve WHERE eleve_id = ?)))) ORDER BY id DESC",
            (classe_id, eleve_id, eleve_id)).fetchall()
        for p in publications:
            if p["exercice"] in vus or not _en_cours(p, jour):
                continue
            carte = _carte_exercice(conn, eleve_id, p["exercice"], {"fin": p["fin"]})
            if carte:
                vus.add(p["exercice"])
                sections["exercices"].append(carte)
    return sections


def autorise(base: Base, eleve: dict, exercice: str, jour: str | None = None) -> bool:
    """L'élève peut-il ouvrir cet exercice ? Seulement s'il est sur son accueil."""
    accueil = pour_l_eleve(base, eleve, jour)
    return any(c["exercice"] == exercice for liste in accueil.values() for c in liste)


# --- ligne de commande (essais, avant le bouton « Publier » de l'interface enseignant) --------------------------------

def main(argv: list[str] | None = None) -> int:
    """python -m generateur.donnees.publications <identifiant> <exercice> --classe "6e Démo" """
    import argparse

    from generateur.donnees import comptes
    from generateur.moteur import config

    parser = argparse.ArgumentParser(description="Publier un exercice accepté pour une classe (serveur de classe, E8).")
    parser.add_argument("identifiant", help="le compte de l'enseignant")
    parser.add_argument("exercice", help="l'identifiant de l'exercice (banque), accepté")
    parser.add_argument("--classe", required=True, help="le nom de la classe (« 6e Démo »)")
    parser.add_argument("--debut")
    parser.add_argument("--fin")
    args = parser.parse_args(argv)
    base = Base(config.chemin("base"))
    compte = comptes.lire(base, args.identifiant)
    if compte is None:
        print(f"compte inconnu : {args.identifiant}")
        return 1
    trouvees = [c for c in classes.lister(base, compte) if c["nom"] == args.classe]
    if not trouvees:
        print(f"classe inconnue pour {args.identifiant} : {args.classe}")
        return 1
    try:
        p = publier(base, compte, args.exercice, trouvees[0]["id"], debut=args.debut, fin=args.fin)
    except (classes.ClasseInvalide, classes.Introuvable) as e:
        print(f"refusé : {e}")
        return 1
    print(f"publié : « {p['titre']} » pour {args.classe} ({p['pour']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
