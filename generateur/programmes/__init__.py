"""Le référentiel des programmes officiels (évolution E2) : se baser sur les programmes de l'Éducation nationale.

Un fichier par matière et par classe (`maths-6e.yaml`…) : les « Objectifs d'apprentissage » du programme en vigueur,
recopiés MOT POUR MOT, rangés par thème, avec la source (arrêté, NOR, Bulletin officiel). Méthode, vérification et
corrections : docs/etapes/etape-E2-programmes.md.

Identifiants : `maths.6e.fractions` désigne un thème, `maths.6e.fractions.09` un attendu de ce thème. Un exercice
peut viser un attendu précis ou un thème entier ; un filtre sur un thème trouve aussi les exercices de ses attendus
(`couvre`).

`reperes.yaml` : des notions qui n'apparaissent qu'à partir d'une classe (« racine carrée » : 4e), pour avertir
quand un exercice sort de son niveau (validation/programme.py).
"""

import math
import re
import unicodedata
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path

import yaml

DOSSIER = Path(__file__).parent
NIVEAUX = ("6e", "5e", "4e", "3e")
ID_THEME = re.compile(r"^(maths|francais)\.(6e|5e|4e|3e)\.[a-z0-9]+(?:-[a-z0-9]+)*$")
ID_ATTENDU = re.compile(r"^(maths|francais)\.(6e|5e|4e|3e)\.[a-z0-9]+(?:-[a-z0-9]+)*\.\d{2}$")
CHAMPS_SOURCE = ("texte", "arrete", "nor", "bo", "url", "en_vigueur", "extrait", "releve")


@dataclass(frozen=True)
class Attendu:
    id: str
    libelle: str
    matiere: str
    niveau: str
    cycle: int
    domaine: str
    theme: str
    theme_id: str
    sous_theme: str | None
    qcm: bool
    source: str  # « BO n° 16 du 17 avril 2025 »

    def en_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Repere:
    matiere: str
    niveau: str
    notion: str
    motif: re.Pattern
    source: str


def sans_accents(texte: str) -> str:
    return unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode().lower()


# --- lecture --------------------------------------------------------------------------------------

@cache
def documents() -> tuple[dict, ...]:
    """Les fichiers du référentiel, tels quels (matière, classe, source, thèmes)."""
    return tuple(yaml.safe_load(f.read_text(encoding="utf-8"))
                 for f in sorted(DOSSIER.glob("*.yaml")) if f.name != "reperes.yaml")


@cache
def _index() -> dict[str, Attendu]:
    index = {}
    for doc in documents():
        for theme in doc["themes"]:
            for a in theme["attendus"]:
                index[a["id"]] = Attendu(a["id"], a["libelle"], doc["matiere"], doc["niveau"], doc["cycle"],
                                         theme["domaine"], theme["theme"], theme["id"], a.get("sous_theme"),
                                         bool(a["qcm"]), doc["source"]["bo"])
    return index


def attendu(ident: str | None) -> Attendu | None:
    return _index().get(ident or "")


def theme(ident: str | None) -> dict | None:
    """{id, domaine, theme, matiere, niveau, source, attendus: [Attendu…]} ; None si l'identifiant n'est pas un thème."""
    for doc in documents():
        for t in doc["themes"]:
            if t["id"] == ident:
                return {"id": t["id"], "domaine": t["domaine"], "theme": t["theme"], "matiere": doc["matiere"],
                        "niveau": doc["niveau"], "source": doc["source"]["bo"],
                        "attendus": [_index()[a["id"]] for a in t["attendus"]]}
    return None


def existe(ident: str | None) -> bool:
    """Un attendu ou un thème du référentiel."""
    return attendu(ident) is not None or theme(ident) is not None


def libelle(ident: str) -> str:
    """Le libellé d'un attendu, ou « Tout le thème : … » pour un thème."""
    if a := attendu(ident):
        return a.libelle
    t = theme(ident)
    return f"Tout le thème : {t['theme']}" if t else ident


def couvre(cible: str, ident: str) -> bool:
    """`ident` (un attendu ou un thème) relève-t-il de `cible` (un attendu ou un thème) ?"""
    return ident == cible or ident.startswith(cible + ".") or cible.startswith(ident + ".")


def suivant(ident: str) -> str | None:
    """L'attendu qui suit `ident` dans son thème, parmi ceux qui se prêtent à un QCM (« pour aller plus loin », E4)."""
    a = attendu(ident)
    if a is None:
        return None
    du_theme = [x.id for x in lister(a.matiere, a.niveau, qcm=True) if x.theme_id == a.theme_id]
    rang = du_theme.index(ident) if ident in du_theme else -1
    return du_theme[rang + 1] if 0 <= rang < len(du_theme) - 1 else None


def couvert(matiere: str | None, niveau: str | None) -> bool:
    """Le référentiel a-t-il cette matière à cette classe ?"""
    return any(d["matiere"] == matiere and d["niveau"] == niveau for d in documents())


def lister(matiere: str | None = None, niveau: str | None = None, qcm: bool | None = None) -> list[Attendu]:
    return [a for a in _index().values() if (matiere is None or a.matiere == matiere)
            and (niveau is None or a.niveau == niveau) and (qcm is None or a.qcm == qcm)]


def arbre(matiere: str, niveau: str, qcm: bool | None = True) -> dict | None:
    """Pour le formulaire : {source, themes: [{id, domaine, theme, attendus: [{id, libelle, sous_theme}]}]}, sans les
    thèmes vides ; None si la matière n'est pas au référentiel à cette classe."""
    for doc in documents():
        if doc["matiere"] == matiere and doc["niveau"] == niveau:
            themes = []
            for t in doc["themes"]:
                attendus = [{"id": a["id"], "libelle": a["libelle"], "sous_theme": a.get("sous_theme")}
                            for a in t["attendus"] if qcm is None or bool(a["qcm"]) == qcm]
                if attendus:
                    themes.append({"id": t["id"], "domaine": t["domaine"], "theme": t["theme"], "attendus": attendus})
            return {"matiere": matiere, "niveau": niveau, "source": doc["source"], "themes": themes}
    return None


# --- l'attendu le plus proche d'une notion (analyse d'une phrase, E2.3) -----------------------------

MOTS_VIDES = {"les", "des", "une", "aux", "sur", "pour", "par", "avec", "dans", "son", "ses", "qui", "que", "est",
              "exercice", "exercices", "qcm", "question", "questions", "classe", "niveau", "eleves", "notion", "cours",
              "travail", "travailler", "revoir", "reviser", "entrainement", "maths", "mathematiques", "francais",
              "sixieme", "cinquieme", "facile", "difficile", "moyen"}


def _racines(texte: str) -> set[str]:
    """Les mots utiles, réduits à leurs 6 premières lettres : « fractions » et « fraction », « comparer » et
    « comparaison » se rejoignent."""
    texte = re.sub(r"['’]", " ", texte or "")  # « l’accord » : deux mots, pas « laccord »
    return {m[:6] for m in re.findall(r"[a-z]+", sans_accents(texte)) if len(m) >= 3 and m not in MOTS_VIDES}


def _score(cherche: set[str], principal: str, secondaire: str = "") -> float:
    """Part des mots cherchés présents : 1 dans le libellé, 0,5 seulement dans le thème ou le sous-thème."""
    if not cherche:
        return 0.0
    dans_libelle, autour = _racines(principal), _racines(secondaire)
    return sum(1.0 if m in dans_libelle else 0.5 if m in autour else 0.0 for m in cherche) / len(cherche)


SEUIL = 0.6


def proposer(texte: str, matiere: str | None, niveau: str | None) -> tuple[str | None, list[str]]:
    """L'attendu (ou le thème) le plus proche de `texte`, parmi ceux qui se prêtent à un QCM, et les ex aequo.

    Renvoie (identifiant, []) si un seul se détache ; (None, [ex aequo…]) si plusieurs se valent (« les
    pourcentages » : cinq attendus) ; (None, []) si rien n'est assez proche. Un thème l'emporte sur ses propres
    attendus à égalité : « les fractions » vise le thème, « comparer des fractions » un attendu."""
    if not couvert(matiere, niveau):
        return None, []
    cherche = _racines(texte)
    candidats: list[tuple[float, int, str]] = []
    attendus = lister(matiere, niveau, qcm=True)
    for a in attendus:
        candidats.append((_score(cherche, a.libelle, f"{a.theme} {a.sous_theme or ''}"), 0, a.id))
    for theme_id in dict.fromkeys(a.theme_id for a in attendus):
        candidats.append((_score(cherche, theme(theme_id)["theme"]), 1, theme_id))
    candidats.sort(key=lambda c: (-c[0], -c[1]))
    if not candidats or candidats[0][0] < SEUIL:
        return None, []
    meilleur, est_theme, ident = candidats[0]
    egaux = [c[2] for c in candidats if math.isclose(c[0], meilleur) and not (est_theme and couvre(ident, c[2]))]
    if est_theme or len(egaux) == 1:
        return ident, []
    return None, egaux


# --- repères de niveau (E2.6) -----------------------------------------------------------------------

@cache
def reperes() -> tuple[Repere, ...]:
    donnees = yaml.safe_load((DOSSIER / "reperes.yaml").read_text(encoding="utf-8"))
    return tuple(Repere(r["matiere"], r["niveau"], r["notion"], re.compile(r["motif"]), r["source"])
                 for r in donnees["reperes"])


def rang(niveau: str | None) -> int:
    return NIVEAUX.index(niveau) if niveau in NIVEAUX else -1


# --- contrôle du référentiel ---------------------------------------------------------------------

def verifier() -> list[str]:
    """Les défauts du référentiel (vide : tout va bien) : identifiants mal formés ou en double, libellés vides,
    source incomplète, repère qui cite un attendu inconnu."""
    defauts, vus = [], set()
    for doc in documents():
        nom = f"{doc.get('matiere')}-{doc.get('niveau')}"
        if doc.get("niveau") not in NIVEAUX:
            defauts.append(f"{nom} : classe inconnue")
        manque = [c for c in CHAMPS_SOURCE if not (doc.get("source") or {}).get(c)]
        if manque:
            defauts.append(f"{nom} : source incomplète ({', '.join(manque)})")
        for t in doc.get("themes", []):
            if not ID_THEME.match(t.get("id", "")) or not t["id"].startswith(f"{doc['matiere']}.{doc['niveau']}."):
                defauts.append(f"{nom} : identifiant de thème mal formé : {t.get('id')}")
            if not t.get("attendus"):
                defauts.append(f"{nom} : thème vide : {t.get('id')}")
            for rang_, a in enumerate(t.get("attendus", []), 1):
                ident = a.get("id", "")
                if not ID_ATTENDU.match(ident) or ident != f"{t['id']}.{rang_:02d}":
                    defauts.append(f"{nom} : identifiant d'attendu mal formé ou mal numéroté : {ident}")
                if ident in vus:
                    defauts.append(f"{nom} : identifiant en double : {ident}")
                vus.add(ident)
                if not (a.get("libelle") or "").strip() or not isinstance(a.get("qcm"), bool):
                    defauts.append(f"{nom} : attendu incomplet : {ident}")
    for r in reperes():
        if ID_ATTENDU.match(r.source) and r.source not in vus:
            defauts.append(f"repère « {r.notion} » : attendu inconnu {r.source}")
    return defauts
