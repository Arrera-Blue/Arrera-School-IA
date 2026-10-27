"""Le suivi des élèves (évolution E4) : voir, pour chaque élève, où il a des difficultés et où il a des facilités,
attendu par attendu du programme, pour savoir sur quels exercices il doit se concentrer (décision D1).

- Les réponses arrivent par `enregistrer_tentative` (le simulateur, simulation.py, toutes d'un coup), ou par
  `commencer_tentative` puis `ajouter_reponse` (le serveur de classe, E8, une à une). Juste ou faux est
  **recalculé** à partir de l'exercice, jamais cru de l'appelant. Seule la **première** tentative d'un élève sur un
  exercice compte dans le suivi ; les suivantes sont de l'entraînement (choix du 27/10).
- Les règles sont **lisibles** (seuils dans config.yaml, `suivi`) : « à consolider » sous 50 % de réussite sur au
  moins 6 questions d'un attendu, « en réussite » à partir de 85 %, « pas assez de réponses » en dessous de 6 ;
  chaque case dit pourquoi (« 2 réussites sur 8 questions »).
- **Aucune décision automatique** : les groupes et les exercices proposés n'existent qu'une fois enregistrés par
  l'enseignant. Vocabulaire : « à consolider », « en réussite » ; jamais « faible », ni « lacunes ».
- Chaque enseignant ne voit que ses classes (classes.py) ; consulter le suivi est noté au journal.
"""

import hashlib
import json
import sqlite3
from collections import defaultdict

from generateur import procedural, programmes
from generateur.donnees import classes, journal
from generateur.donnees.base import Base, maintenant_iso

ETATS = ("a_consolider", "en_cours", "en_reussite", "pas_assez")
LIBELLES_ETATS = {"a_consolider": "à consolider", "en_cours": "en cours", "en_reussite": "en réussite",
                  "pas_assez": "pas assez de réponses"}
SEUILS_PAR_DEFAUT = {"questions_min": 6, "a_consolider": 0.5, "en_reussite": 0.85}
RAPPEL = ("Un indicateur aide à repérer les besoins ; il ne juge pas l'élève et ne décide rien seul : les groupes "
          "et les exercices proposés n'existent qu'une fois validés par vous.")


def seuils() -> dict:
    from generateur.moteur import config

    return {**SEUILS_PAR_DEFAUT, **(config.charger().get("suivi") or {})}


# --- enregistrer une tentative (simulateur, puis serveur de classe) -----------------------------------

def empreinte_exercice(instance: dict) -> str:
    """SHA-256 du contenu de l'exercice (sans meta) : la version sur laquelle l'élève a répondu."""
    contenu = {k: v for k, v in instance.items() if k != "meta"}
    return hashlib.sha256(json.dumps(contenu, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def attendu_de_question(instance: dict, numero: int) -> str | None:
    """L'attendu (ou le thème) que la question travaille : celui choisi par l'enseignant ; sinon, pour un exercice du
    générateur procédural, celui de son genre ; sinon l'unique attendu de l'exercice ; sinon rien."""
    meta = instance.get("meta") or {}
    programme = meta.get("programme") or {}
    attendus = programme.get("attendus") or []
    if programme.get("choisi") and attendus:
        return attendus[0]
    questions = meta.get("questions") or []
    if meta.get("origine") == "procedural" and 0 < numero <= len(questions):
        module = procedural.notions().get(meta.get("generateur"))
        if module is not None:
            genre = questions[numero - 1].get("genre", "").split(".")[-1]
            trouves = procedural.attendus_du_genre(module, genre, instance.get("niveau"))
            if trouves:
                return trouves[0]
    return attendus[0] if len(attendus) == 1 else None


def _ligne(instance: dict, numero, choix, temps) -> tuple:
    """Une réponse contrôlée, juste ou faux recalculé à partir de l'exercice : (numéro, choix, juste, temps, attendu,
    difficulté). Une question ou une proposition qui n'existe pas, un temps impossible, sont refusés."""
    questions = instance.get("questions") or []
    if not (isinstance(numero, int) and not isinstance(numero, bool) and 0 < numero <= len(questions)):
        raise classes.ClasseInvalide(f"question inconnue : {numero}")
    q = questions[numero - 1]
    if not (isinstance(choix, int) and not isinstance(choix, bool) and 0 <= choix < len(q["propositions"])):
        raise classes.ClasseInvalide(f"question {numero} : proposition inconnue : {choix}")
    if temps is not None and not (isinstance(temps, (int, float)) and 0 <= float(temps) <= 3600):
        raise classes.ClasseInvalide(f"question {numero} : temps impossible : {temps}")
    return (numero, choix, int(choix == q["index_correct"]), temps, attendu_de_question(instance, numero),
            q.get("difficulte"))


def _premiere(conn: sqlite3.Connection, eleve_id: int, exercice: str) -> bool:
    """Aucune tentative de l'élève sur cet exercice ne compte encore : celle-ci comptera."""
    return conn.execute("SELECT 1 FROM tentative WHERE eleve_id = ? AND exercice = ? AND annulee = 0 AND compte = 1",
                        (eleve_id, exercice)).fetchone() is None


def _inserer_tentative(conn: sqlite3.Connection, eleve_id: int, instance: dict, origine: str, date: str | None) -> int:
    exercice = (instance.get("meta") or {}).get("id") or "?"
    return conn.execute("INSERT INTO tentative (eleve_id, exercice, titre, empreinte, origine, date, compte) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (eleve_id, exercice, instance.get("titre"), empreinte_exercice(instance), origine,
                         date or maintenant_iso(), int(_premiere(conn, eleve_id, exercice)))).lastrowid


def enregistrer_tentative(base: Base, eleve_id: int, instance: dict, reponses: list[tuple[int, int, float | None]],
                          origine: str, date: str | None = None) -> int:
    """Une tentative et ses réponses (numéro de question, proposition choisie, temps en secondes), toutes d'un coup."""
    lignes, vues = [], set()
    for numero, choix, temps in reponses:
        if numero in vues:
            raise classes.ClasseInvalide(f"question en double : {numero}")
        vues.add(numero)
        lignes.append(_ligne(instance, numero, choix, temps))
    with base.ecrire() as conn:
        tentative_id = _inserer_tentative(conn, eleve_id, instance, origine, date)
        conn.executemany("INSERT INTO reponse (tentative_id, question, choix, juste, temps_s, attendu, difficulte) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)", [(tentative_id, *ligne) for ligne in lignes])
    return tentative_id


def commencer_tentative(base: Base, eleve_id: int, instance: dict, origine: str = "classe") -> dict:
    """Le serveur de classe (E8) : une tentative ouverte au début de l'exercice ; les réponses arrivent une à une.
    Renvoie {"id", "compte"} : compte = False, c'est un entraînement (l'élève a déjà fait cet exercice)."""
    with base.ecrire() as conn:
        tentative_id = _inserer_tentative(conn, eleve_id, instance, origine, None)
        compte_ = conn.execute("SELECT compte FROM tentative WHERE id = ?", (tentative_id,)).fetchone()[0]
    return {"id": tentative_id, "compte": bool(compte_)}


def ajouter_reponse(base: Base, eleve_id: int, tentative_id: int, instance: dict, numero, choix, temps) -> dict:
    """Une réponse de l'élève, recalculée ; refusée si la tentative n'est pas la sienne, si l'exercice a changé depuis
    son début, ou si la question a déjà sa réponse. Renvoie {"juste", "correct"} (correct : le rang d'origine de la
    bonne proposition, que la page n'a pas : c'est le serveur qui corrige, ⚖4)."""
    ligne = _ligne(instance, numero, choix, temps)
    with base.ecrire() as conn:
        t = conn.execute("SELECT * FROM tentative WHERE id = ? AND eleve_id = ? AND annulee = 0",
                         (tentative_id, eleve_id)).fetchone()
        if t is None or t["exercice"] != ((instance.get("meta") or {}).get("id") or "?") \
                or t["empreinte"] != empreinte_exercice(instance):
            raise classes.Introuvable("tentative introuvable")
        try:
            conn.execute("INSERT INTO reponse (tentative_id, question, choix, juste, temps_s, attendu, difficulte) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)", (tentative_id, *ligne))
        except sqlite3.IntegrityError:
            raise classes.ClasseInvalide(f"question {numero} : déjà répondue") from None
    return {"juste": bool(ligne[2]), "correct": instance["questions"][numero - 1]["index_correct"]}


# --- les indicateurs (E4.1, E4.2) --------------------------------------------------------------------------

def etat(vues: int, justes: int, regles: dict) -> str:
    if vues < regles["questions_min"]:
        return "pas_assez"
    taux = justes / vues
    if taux < regles["a_consolider"]:
        return "a_consolider"
    return "en_reussite" if taux >= regles["en_reussite"] else "en_cours"


def _case(compte_: dict, regles: dict) -> dict:
    vues, justes = compte_["vues"], compte_["justes"]
    pluriel = lambda n, mot: f"{n} {mot}{'s' if n > 1 else ''}"
    explication = f"{pluriel(justes, 'réussite')} sur {pluriel(vues, 'question')}"
    if compte_["difficiles_vues"]:  # si l'exercice marque la difficulté de ses questions
        explication += f", dont {compte_['difficiles_justes']} sur {compte_['difficiles_vues']} difficile" \
                       f"{'s' if compte_['difficiles_vues'] > 1 else ''}"
    return {**compte_, "taux": round(justes / vues, 3) if vues else None, "etat": etat(vues, justes, regles),
            "explication": explication}


def _ordre(ident: str) -> tuple:
    """L'ordre du programme (thème, puis rang) ; les identifiants inconnus à la fin."""
    rangs = {a.id: i for i, a in enumerate(programmes.lister())}
    rang = rangs.get(ident)
    if rang is None:
        t = programmes.theme(ident)
        rang = rangs.get(t["attendus"][0].id, 10 ** 6) - 0.5 if t else 10 ** 6
    return (rang, ident)


def _decrire_attendu(ident: str, code: str) -> dict:
    a = programmes.attendu(ident)
    t = programmes.theme(ident)
    return {"id": ident, "code": code, "libelle": programmes.libelle(ident),
            "theme": a.theme if a else (t["theme"] if t else "")}


def _comptes(lignes) -> dict:
    """{(eleve, attendu): {vues, justes, difficiles_vues, difficiles_justes}}"""
    comptes_ = defaultdict(lambda: {"vues": 0, "justes": 0, "difficiles_vues": 0, "difficiles_justes": 0})
    for l in lignes:
        c = comptes_[(l["eleve_id"], l["attendu"])]
        c["vues"] += 1
        c["justes"] += l["juste"]
        if l["difficulte"] == "difficile":
            c["difficiles_vues"] += 1
            c["difficiles_justes"] += l["juste"]
    return comptes_


def indicateurs(base: Base, compte: dict, classe_id: int, noter: bool = True) -> dict:
    """La grille élèves × attendus, et « qui a besoin de quoi » par attendu. Les tentatives annulées, et les
    entraînements (exercice rejoué), ne comptent pas ; un élève désactivé reste affiché (ses données sont gardées),
    grisé."""
    regles = seuils()
    with base.ecrire() as conn:
        classe = classes._classe(conn, compte, classe_id)
        eleves = conn.execute("SELECT * FROM eleve WHERE classe_id = ? ORDER BY numero", (classe_id,)).fetchall()
        lignes = conn.execute("SELECT t.eleve_id, r.attendu, r.juste, r.difficulte FROM reponse r "
                              "JOIN tentative t ON t.id = r.tentative_id JOIN eleve e ON e.id = t.eleve_id "
                              "WHERE e.classe_id = ? AND t.annulee = 0 AND t.compte = 1 AND r.attendu IS NOT NULL",
                              (classe_id,)).fetchall()
        if noter:
            journal.noter(conn, "suivi_consulte", compte, cible=f"classe:{classe_id}")
    comptes_ = _comptes(lignes)
    attendus = sorted({a for _, a in comptes_}, key=_ordre)
    vue_eleves = []
    for e in eleves:
        cases = {a: _case(comptes_[(e["id"], a)], regles) for a in attendus if (e["id"], a) in comptes_}
        vue_eleves.append({**classes._vue_eleve(e), "cases": cases})
    besoins = [{"attendu": a,
                "a_consolider": [e["id"] for e in vue_eleves if e["cases"].get(a, {}).get("etat") == "a_consolider"],
                "en_reussite": [e["id"] for e in vue_eleves if e["cases"].get(a, {}).get("etat") == "en_reussite"]}
               for a in attendus]
    return {"classe": {"id": classe["id"], "nom": classe["nom"], "niveau": classe["niveau"], "annee": classe["annee"]},
            "seuils": regles, "etats": LIBELLES_ETATS, "rappel": RAPPEL,
            "attendus": [_decrire_attendu(a, f"A{i}") for i, a in enumerate(attendus, start=1)],
            "eleves": vue_eleves, "besoins": besoins}


# --- la fiche d'un élève (E4.3) --------------------------------------------------------------------------------

def fiche(base: Base, compte: dict, eleve_id: int) -> dict:
    """Ses indicateurs par attendu et ses tentatives (à annuler si faites par erreur) ; noté au journal."""
    regles = seuils()
    with base.ecrire() as conn:
        eleve = classes._eleve(conn, compte, eleve_id)
        lignes = conn.execute("SELECT t.eleve_id, r.attendu, r.juste, r.difficulte FROM reponse r "
                              "JOIN tentative t ON t.id = r.tentative_id WHERE t.eleve_id = ? AND t.annulee = 0 "
                              "AND t.compte = 1 AND r.attendu IS NOT NULL", (eleve_id,)).fetchall()
        tentatives = conn.execute("SELECT t.*, COUNT(r.id) AS questions, SUM(r.juste) AS justes FROM tentative t "
                                  "LEFT JOIN reponse r ON r.tentative_id = t.id WHERE t.eleve_id = ? "
                                  "GROUP BY t.id ORDER BY t.date DESC, t.id DESC", (eleve_id,)).fetchall()
        journal.noter(conn, "eleve_consulte", compte, cible=f"classe:{eleve['classe_id']}/eleve:{eleve_id}")
    comptes_ = _comptes(lignes)
    attendus = sorted({a for _, a in comptes_}, key=_ordre)
    return {"eleve": {**classes._vue_eleve(eleve), "classe_id": eleve["classe_id"], "classe": eleve["classe_nom"]},
            "seuils": regles, "etats": LIBELLES_ETATS,
            "attendus": [{**_decrire_attendu(a, ""), **_case(comptes_[(eleve_id, a)], regles)} for a in attendus],
            "tentatives": [{"id": t["id"], "date": t["date"], "exercice": t["exercice"], "titre": t["titre"],
                            "origine": t["origine"], "annulee": bool(t["annulee"]), "compte": bool(t["compte"]),
                            "questions": t["questions"],
                            "justes": t["justes"] or 0} for t in tentatives]}


def annuler_tentative(base: Base, compte: dict, tentative_id: int, annulee: bool = True) -> None:
    """Rectification (RGPD) : une tentative faite par erreur (un autre élève sur la session) ne compte plus."""
    with base.ecrire() as conn:
        ligne = conn.execute("SELECT t.id, t.eleve_id, e.classe_id FROM tentative t JOIN eleve e ON e.id = t.eleve_id "
                             "JOIN classe c ON c.id = e.classe_id WHERE t.id = ? AND c.enseignant_id = ?",
                             (tentative_id, compte["id"])).fetchone()
        if ligne is None:
            raise classes.Introuvable("tentative introuvable")
        conn.execute("UPDATE tentative SET annulee = ? WHERE id = ?", (int(annulee), tentative_id))
        journal.noter(conn, "tentative_annulee" if annulee else "tentative_retablie", compte,
                      cible=f"classe:{ligne['classe_id']}/eleve:{ligne['eleve_id']}", detail=f"tentative {tentative_id}")


# --- les groupes de besoins (E4.5) -------------------------------------------------------------------------

def _court(texte: str, n: int = 120) -> str:
    """Au plus n caractères, coupé entre deux mots."""
    return texte if len(texte) <= n else texte[:n - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def proposer_groupes(base: Base, compte: dict, classe_id: int) -> list[dict]:
    """Une proposition, rien d'enregistré : un groupe par attendu qui a des élèves à consolider, et un groupe « pour
    aller plus loin » (en réussite partout où ils ont assez de réponses, et jamais à consolider)."""
    indic = indicateurs(base, compte, classe_id, noter=False)
    groupes = []
    for besoin, attendu in zip(indic["besoins"], indic["attendus"]):
        if besoin["a_consolider"]:
            groupes.append({"nom": _court(f"À consolider : {attendu['libelle']}"), "attendu": attendu["id"],
                            "nature": "consolider", "eleves": besoin["a_consolider"]})
    plus_loin = []
    for e in indic["eleves"]:
        etats = [c["etat"] for c in e["cases"].values() if c["etat"] != "pas_assez"]
        if etats and all(x == "en_reussite" for x in etats):
            plus_loin.append(e["id"])
    if plus_loin:
        groupes.append({"nom": "Pour aller plus loin", "attendu": None, "nature": "approfondir", "eleves": plus_loin})
    return groupes


def _eleves_de_la_classe(conn: sqlite3.Connection, classe_id: int, eleves: list[int]) -> list[int]:
    connus = {r[0] for r in conn.execute("SELECT id FROM eleve WHERE classe_id = ?", (classe_id,))}
    inconnus = [e for e in eleves if e not in connus]
    if inconnus:
        raise classes.ClasseInvalide(f"élève(s) hors de la classe : {inconnus}")
    return list(dict.fromkeys(eleves))


def _vue_groupe(conn: sqlite3.Connection, g: sqlite3.Row) -> dict:
    eleves = [r[0] for r in conn.execute("SELECT ge.eleve_id FROM groupe_eleve ge JOIN eleve e ON e.id = ge.eleve_id "
                                         "WHERE ge.groupe_id = ? ORDER BY e.numero", (g["id"],))]
    return {"id": g["id"], "nom": g["nom"], "attendu": g["attendu"], "nature": g["nature"], "eleves": eleves,
            "libelle_attendu": programmes.libelle(g["attendu"]) if g["attendu"] else None}


def lister_groupes(base: Base, compte: dict, classe_id: int) -> list[dict]:
    with base.lire() as conn:
        classes._classe(conn, compte, classe_id)
        return [_vue_groupe(conn, g) for g in conn.execute("SELECT * FROM groupe WHERE classe_id = ? ORDER BY id",
                                                           (classe_id,))]


def creer_groupe(base: Base, compte: dict, classe_id: int, nom: str, attendu: str | None, nature: str,
                 eleves: list[int]) -> dict:
    nom = " ".join((nom or "").split())[:120]
    if not nom:
        raise classes.ClasseInvalide("donnez un nom au groupe")
    if nature not in ("consolider", "approfondir"):
        raise classes.ClasseInvalide(f"nature inconnue : {nature}")
    if attendu and not programmes.existe(attendu):
        raise classes.ClasseInvalide(f"attendu inconnu : {attendu}")
    with base.ecrire() as conn:
        classes._classe(conn, compte, classe_id)
        eleves = _eleves_de_la_classe(conn, classe_id, eleves)
        groupe_id = conn.execute("INSERT INTO groupe (classe_id, nom, attendu, nature, cree) VALUES (?, ?, ?, ?, ?)",
                                 (classe_id, nom, attendu, nature, maintenant_iso())).lastrowid
        conn.executemany("INSERT INTO groupe_eleve (groupe_id, eleve_id) VALUES (?, ?)", [(groupe_id, e) for e in eleves])
        journal.noter(conn, "groupe_cree", compte, cible=f"classe:{classe_id}", detail=f"{len(eleves)} élève(s)")
        return _vue_groupe(conn, conn.execute("SELECT * FROM groupe WHERE id = ?", (groupe_id,)).fetchone())


def _groupe(conn: sqlite3.Connection, compte: dict, groupe_id: int) -> sqlite3.Row:
    g = conn.execute("SELECT g.* FROM groupe g JOIN classe c ON c.id = g.classe_id WHERE g.id = ? AND c.enseignant_id = ?",
                     (groupe_id, compte["id"])).fetchone()
    if g is None:
        raise classes.Introuvable("groupe introuvable")
    return g


def modifier_groupe(base: Base, compte: dict, groupe_id: int, nom: str, eleves: list[int]) -> dict:
    """L'enseignant ajuste un groupe à la main : son nom, ses élèves."""
    nom = " ".join((nom or "").split())[:120]
    if not nom:
        raise classes.ClasseInvalide("donnez un nom au groupe")
    with base.ecrire() as conn:
        g = _groupe(conn, compte, groupe_id)
        eleves = _eleves_de_la_classe(conn, g["classe_id"], eleves)
        conn.execute("UPDATE groupe SET nom = ? WHERE id = ?", (nom, groupe_id))
        conn.execute("DELETE FROM groupe_eleve WHERE groupe_id = ?", (groupe_id,))
        conn.executemany("INSERT INTO groupe_eleve (groupe_id, eleve_id) VALUES (?, ?)", [(groupe_id, e) for e in eleves])
        journal.noter(conn, "groupe_modifie", compte, cible=f"classe:{g['classe_id']}", detail=f"{len(eleves)} élève(s)")
        return _vue_groupe(conn, conn.execute("SELECT * FROM groupe WHERE id = ?", (groupe_id,)).fetchone())


def supprimer_groupe(base: Base, compte: dict, groupe_id: int) -> None:
    with base.ecrire() as conn:
        g = _groupe(conn, compte, groupe_id)
        conn.execute("DELETE FROM groupe WHERE id = ?", (groupe_id,))
        journal.noter(conn, "groupe_supprime", compte, cible=f"classe:{g['classe_id']}")


# --- les exercices à travailler (E4.4) ---------------------------------------------------------------------

ORDRE_RETRAVAILLER = {"facile": 0, "moyen": 1, None: 2, "difficile": 3}


def _deja_faits(base: Base, eleve_id: int) -> set[str]:
    with base.lire() as conn:
        return {r[0] for r in conn.execute("SELECT DISTINCT exercice FROM tentative WHERE eleve_id = ? AND annulee = 0",
                                           (eleve_id,))}


def _choisir(banque_: list[dict], attendu: str, faits: set[str], niveau: str, difficile: bool) -> dict | None:
    """L'exercice accepté de la banque, de cette classe, qui travaille l'attendu, pas encore fait : le plus facile
    pour retravailler ; un difficile pour aller plus loin."""
    candidats = [x for x in banque_ if x["niveau"] == niveau and x["id"] not in faits
                 and any(programmes.couvre(attendu, a) for a in x.get("attendus") or [])]
    if difficile:
        candidats = [x for x in candidats if x.get("difficulte") == "difficile"]
        return candidats[0] if candidats else None
    candidats.sort(key=lambda x: ORDRE_RETRAVAILLER.get(x.get("difficulte"), 2))
    return candidats[0] if candidats else None


def proposer_exercices(base: Base, compte: dict, classe_id: int) -> list[dict]:
    """Une proposition par élève, rien d'enregistré : sur chaque attendu à consolider, un exercice facile puis moyen
    (« À retravailler ») ; sur chaque attendu en réussite, un exercice difficile du même attendu, ou un exercice de
    l'attendu suivant s'il n'est ni en réussite ni à consolider (« Pour aller plus loin »). Sans exercice dans la
    banque : « à générer »."""
    from generateur.moteur import banque

    indic = indicateurs(base, compte, classe_id, noter=False)
    niveau = indic["classe"]["niveau"]
    acceptes = banque.lister(statut_voulu="accepte")
    propositions = []
    for e in indic["eleves"]:
        if not e["actif"]:
            continue
        faits = _deja_faits(base, e["id"])
        for attendu, case in e["cases"].items():
            if case["etat"] == "a_consolider":
                choix = _choisir(acceptes, attendu, faits, niveau, difficile=False)
                propositions.append(_proposition(e["id"], "retravailler", attendu, choix, "facile"))
            elif case["etat"] == "en_reussite":
                choix = _choisir(acceptes, attendu, faits, niveau, difficile=True)
                cible = attendu
                suivant = programmes.suivant(attendu)
                # l'attendu suivant, sauf s'il est déjà en réussite, ou déjà à retravailler
                if choix is None and suivant and e["cases"].get(suivant, {}).get("etat") not in ("a_consolider",
                                                                                                 "en_reussite"):
                    choix, cible = _choisir(acceptes, suivant, faits, niveau, difficile=False), suivant
                propositions.append(_proposition(e["id"], "plus_loin", cible, choix, "difficile"))
    return propositions


def _proposition(eleve_id: int, nature: str, attendu: str, exercice: dict | None, difficulte: str) -> dict:
    return {"eleve_id": eleve_id, "nature": nature, "attendu": attendu, "libelle_attendu": programmes.libelle(attendu),
            "exercice": exercice["id"] if exercice else None, "titre": exercice["titre"] if exercice else None,
            "a_generer": exercice is None, "difficulte": difficulte}


def valider_propositions(base: Base, compte: dict, classe_id: int, propositions: list[dict]) -> int:
    """L'enseignant valide (après avoir retiré ou gardé ce qu'il veut) : les propositions de la classe sont remplacées
    par celles-ci. L'élève les verra avec le serveur de classe (E8)."""
    for p in propositions:
        if p.get("nature") not in ("retravailler", "plus_loin") or not programmes.existe(p.get("attendu")):
            raise classes.ClasseInvalide("proposition mal formée")
    with base.ecrire() as conn:
        classes._classe(conn, compte, classe_id)
        _eleves_de_la_classe(conn, classe_id, [p["eleve_id"] for p in propositions])
        conn.execute("DELETE FROM proposition WHERE eleve_id IN (SELECT id FROM eleve WHERE classe_id = ?)", (classe_id,))
        conn.executemany("INSERT INTO proposition (eleve_id, nature, attendu, exercice, cree) VALUES (?, ?, ?, ?, ?)",
                         [(p["eleve_id"], p["nature"], p["attendu"], p.get("exercice"), maintenant_iso()) for p in propositions])
        journal.noter(conn, "propositions_validees", compte, cible=f"classe:{classe_id}",
                      detail=f"{len(propositions)} proposition(s)")
    return len(propositions)


def lister_propositions(base: Base, compte: dict, classe_id: int) -> list[dict]:
    with base.lire() as conn:
        classes._classe(conn, compte, classe_id)
        lignes = conn.execute("SELECT p.* FROM proposition p JOIN eleve e ON e.id = p.eleve_id WHERE e.classe_id = ? "
                              "ORDER BY e.numero, p.nature DESC, p.id", (classe_id,)).fetchall()
    return [{"id": p["id"], "eleve_id": p["eleve_id"], "nature": p["nature"], "attendu": p["attendu"],
             "libelle_attendu": programmes.libelle(p["attendu"]), "exercice": p["exercice"],
             "a_generer": p["exercice"] is None} for p in lignes]


def supprimer_proposition(base: Base, compte: dict, proposition_id: int) -> None:
    with base.ecrire() as conn:
        ligne = conn.execute("SELECT p.id, e.classe_id FROM proposition p JOIN eleve e ON e.id = p.eleve_id "
                             "JOIN classe c ON c.id = e.classe_id WHERE p.id = ? AND c.enseignant_id = ?",
                             (proposition_id, compte["id"])).fetchone()
        if ligne is None:
            raise classes.Introuvable("proposition introuvable")
        conn.execute("DELETE FROM proposition WHERE id = ?", (proposition_id,))
        journal.noter(conn, "proposition_retiree", compte, cible=f"classe:{ligne['classe_id']}")
