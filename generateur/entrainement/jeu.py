"""Le jeu de données (plan IA, IA3.3 à IA3.5) : mettre en forme, séparer par notion, figer, décrire.

    python -m generateur.entrainement jeu          # → donnees/entrainement/jeux/<AAAAMMJJ-HHMMSS>/

Ce qui entre (choix du 29/10, docs/etapes/etape-IA3-donnees.md §6) :
- les exercices **acceptés** : relus dans le lot, et ceux de la banque de l'enseignant ;
- les exercices du générateur procédural du lot, non relus mais sans erreur (calculs justes par construction), au plus
  un tiers du jeu (`--part-procedurale`) : ils ne couvrent que quatre notions ;
- **jamais un exercice du modèle que personne n'a relu** : passer les contrôles ne suffit pas (essai du 29/10 : 2
  exercices sur 4 avaient une erreur que seule la relecture voyait). Un exercice pré-relu par Claude mais pas encore
  décidé par l'enseignant n'entre pas non plus (prerelecture.py) : la fiche dit combien de décisions ont suivi son avis.
Chacun est contrôlé de nouveau (le fond, avec les règles du jour) et écarté s'il contient une donnée personnelle (nom
d'un élève de la base, nom écrit comme dans une liste, courriel, téléphone, adresse, lien) ; les doublons aussi.

Le format : celui de `mlx_lm.lora` (IA4), une conversation par ligne, `{"messages": [système, utilisateur,
assistant]}`. Le système et l'utilisateur sont **le vrai prompt** de la génération (`generation.construire_messages`,
avec les extraits de cours s'il y en avait) ; l'assistant, l'exercice tel que le modèle doit l'écrire (sans meta, les
champs dans l'ordre du schéma, la source de chaque question pour un exercice tiré d'un cours). Un adaptateur entraîné
sur ce format sert la génération telle qu'elle est, sans rien y changer.

La séparation : 80 % entraînement, 10 % validation, 10 % test, **par notion** (l'attendu du programme, sinon la notion
écrite) : aucune notion du test n'est vue à l'entraînement. À côté : les paires « avant → après » (questions corrigées
ou régénérées par l'enseignant, pour une 2e passe qui apprend à préférer la version corrigée) et les exercices à éviter
(rejetés par l'enseignant avec leurs motifs, ou par N1 → N4). Le dossier est daté, ses fichiers en lecture seule, leurs
empreintes dans manifeste.json ; fiche.md décrit le jeu.
"""

import copy
import hashlib
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from generateur.entrainement import prerelecture, relecture
from generateur.moteur import banque, contre_verification, generation, registre, securite
from generateur.moteur.validation import ErreurValidation
from generateur.moteur.validation.fond import controler
from generateur.moteur.validation.n2_schema import valider

PART_PROCEDURALE = 1 / 3
PARTS = {"valid": 0.10, "test": 0.10}  # le reste : l'entraînement
GRAINE = 2026
FICHIERS = ("train.jsonl", "valid.jsonl", "test.jsonl", "paires.jsonl", "a_eviter.jsonl")
SOURCES = {"lot": "relus et acceptés dans le lot", "banque": "acceptés dans la banque de l'enseignant",
           "procedural": "générateur procédural du lot, sans erreur (non relus)"}


@dataclass
class Exemple:
    instance: dict
    source: str  # « lot », « banque », « procedural »
    notion: str = ""
    messages: list[dict] = field(default_factory=list)

    @property
    def id(self) -> str:
        return (self.instance.get("meta") or {}).get("id") or "?"


# --- un exercice → une conversation ----------------------------------------------------------------------

def _sources(instance: dict) -> dict[int, int] | None:
    """{numéro : extrait cité} pour un exercice tiré d'un cours dont aucune question n'a changé depuis ; None sinon (il
    est alors appris comme un exercice sans cours)."""
    cours = (instance.get("meta") or {}).get("cours") or {}
    if not cours.get("passages"):
        return None
    questions = instance.get("questions") or []
    sources = {s["numero"]: s["source"] for s in cours.get("sources") or []
               if 1 <= s.get("numero", 0) <= len(questions)
               and s.get("empreinte") == contre_verification.empreinte(questions[s["numero"] - 1])}
    return sources if len(sources) == len(questions) else None


def sortie(instance: dict, demande: dict, sources: dict[int, int] | None = None) -> str:
    """L'exercice tel que le modèle doit l'écrire : sans meta, les champs dans l'ordre du schéma qu'on lui impose."""
    type_exo = registre.charger(instance.get("type", "qcm"))
    passages = ((instance.get("meta") or {}).get("cours") or {}).get("passages") if sources else None
    schema = generation.schema_de_sortie(type_exo.schema, demande, len(passages or []))
    exercice = {k: copy.deepcopy(v) for k, v in instance.items() if k != "meta"}
    for n, q in enumerate(exercice.get("questions") or [], start=1):
        if sources:
            q["source"] = sources[n]
    rang = {cle: i for i, cle in enumerate(schema["properties"])}
    ordonne = dict(sorted(exercice.items(), key=lambda kv: rang.get(kv[0], len(rang))))
    ordre_q = {cle: i for i, cle in enumerate(generation.ORDRE_DES_CHAMPS)}
    ordonne["questions"] = [dict(sorted(q.items(), key=lambda kv: ordre_q.get(kv[0], len(ordre_q))))
                            for q in ordonne.get("questions") or []]
    valider(ordonne, schema)  # lève ErreurValidation : ce que le modèle apprendrait à écrire doit passer N2
    return json.dumps(ordonne, ensure_ascii=False, indent=2)


def messages(instance: dict) -> list[dict]:
    """La conversation d'entraînement : le vrai prompt de la génération, puis l'exercice."""
    demande = generation._demande_d_origine(instance)
    type_exo = registre.charger(instance.get("type", "qcm"))
    sources = _sources(instance)
    passages = (instance.get("meta") or {})["cours"]["passages"] if sources else None
    return generation.construire_messages(type_exo, demande, passages) + [
        {"role": "assistant", "content": sortie(instance, demande, sources)}]


def notion(instance: dict) -> str:
    """La notion qui sépare les jeux : l'attendu du programme visé, sinon la notion écrite (sans accents ni casse)."""
    attendus = ((instance.get("meta") or {}).get("programme") or {}).get("attendus") or []
    if attendus:
        return attendus[0]
    return " ".join(securite.forme(instance.get("notion") or instance.get("titre") or "?").split())


# --- les contrôles ----------------------------------------------------------------------------------------

def _textes(instance: dict) -> str:
    morceaux = [instance.get("titre"), instance.get("notion"), instance.get("consigne")]
    for q in instance.get("questions") or []:
        morceaux += [q.get("enonce"), q.get("explication"), *(q.get("propositions") or [])]
    demande = (instance.get("meta") or {}).get("demande") or {}
    morceaux.append(demande.get("demande_enseignant"))
    return "\n".join(m for m in morceaux if isinstance(m, str))


def donnee_personnelle(texte: str, noms) -> str | None:
    """Ce qui ne doit pas entrer dans les données : un nom d'élève (de la base, ou écrit comme dans une liste), un
    courriel, un téléphone, une adresse, un lien, un jeton spécial du modèle. None si rien."""
    if nom := securite.nom_d_eleve(texte, noms):
        return f"un nom de personne (« {nom} »)"
    for motif, quoi in ((securite.COURRIEL, "un courriel"), (securite.TELEPHONE, "un téléphone"),
                        (securite.ADRESSE_POSTALE, "une adresse"), (securite.LIEN, "un lien")):
        if m := motif.search(texte):
            return f"{quoi} (« {m.group(0)} »)"
    if jeton := securite.jetons(texte):
        return f"un jeton spécial du modèle (« {jeton} »)"
    return None


def _ecarter(instance: dict, noms) -> str | None:
    """Pourquoi un exercice accepté n'entre pas, ou None."""
    if raison := donnee_personnelle(_textes(instance), noms):
        return raison
    if erreurs := controler(instance)["erreurs"]:
        return "une erreur, avec les règles du jour : " + erreurs[0]
    return None


# --- choisir, séparer -------------------------------------------------------------------------------------

def _empreinte(texte: str, graine: int) -> str:
    return hashlib.sha256(f"{graine}:{texte}".encode()).hexdigest()


def plafonner(exemples: list[Exemple], part: float, graine: int) -> tuple[list[Exemple], list[Exemple]]:
    """Les exemples gardés, et les procéduraux laissés de côté : ceux-ci ne dépassent pas `part` du jeu. Le choix varie
    les notions (un par notion à tour de rôle, dans un ordre tiré par la graine)."""
    proceduraux = [e for e in exemples if e.source == "procedural"]
    autres = [e for e in exemples if e.source != "procedural"]
    maximum = int(part * len(autres) / (1 - part) + 1e-9) if part < 1 else len(proceduraux)  # 1/3 × 6 / (2/3) = 3
    if len(proceduraux) <= maximum:
        return exemples, []
    par_notion: dict[str, list[Exemple]] = defaultdict(list)
    for e in sorted(proceduraux, key=lambda e: _empreinte(e.id, graine)):
        par_notion[e.notion].append(e)
    files = [par_notion[n] for n in sorted(par_notion, key=lambda n: _empreinte(n, graine))]
    alternes = [f[i] for i in range(max(map(len, files))) for f in files if i < len(f)]
    return autres + alternes[:maximum], alternes[maximum:]


def separer(exemples: list[Exemple], graine: int = GRAINE) -> dict[str, list[Exemple]]:
    """train, valid, test : par notion. Dans un ordre tiré par la graine, le test puis la validation prennent les notions
    entières qui tiennent dans environ 10 % des exemples chacun (au moins la plus petite, s'il reste une notion pour
    l'entraînement) ; le reste va à l'entraînement."""
    par_notion: dict[str, list[Exemple]] = defaultdict(list)
    for e in exemples:
        par_notion[e.notion].append(e)
    notions = sorted(par_notion, key=lambda n: _empreinte(n, graine))
    jeux: dict[str, list[Exemple]] = {"train": [], "valid": [], "test": []}
    for nom in ("test", "valid"):
        visee = max(1, round(PARTS[nom] * len(exemples)))
        for n in list(notions):
            if len(notions) > 1 and len(jeux[nom]) + len(par_notion[n]) <= visee:
                jeux[nom] += par_notion[n]
                notions.remove(n)
        if not jeux[nom] and len(notions) > 1:  # aucune notion ne tient : la plus petite
            n = min(notions, key=lambda n: len(par_notion[n]))
            jeux[nom] += par_notion[n]
            notions.remove(n)
    for n in notions:
        jeux["train"] += par_notion[n]
    return jeux


# --- les paires et les exercices à éviter ------------------------------------------------------------------

def _q(question: dict) -> dict:
    ordre = {cle: i for i, cle in enumerate(generation.ORDRE_DES_CHAMPS)}
    return dict(sorted(((k, v) for k, v in question.items() if k != "source"), key=lambda kv: ordre.get(kv[0], 99)))


def paires(instance: dict, source: str) -> list[dict]:
    """Chaque version écartée d'une question (corrigée à la main ou régénérée), face à la version acceptée."""
    questions = instance.get("questions") or []
    resultat = []
    for evenement in banque.historique(instance):
        n = evenement.get("question")
        if not isinstance(n, int) or not 1 <= n <= len(questions) or not evenement.get("ancienne"):
            continue
        resultat.append({"exercice": (instance.get("meta") or {}).get("id"), "source": source, "question": n,
                         "nature": evenement["nature"], "motif": evenement.get("motif"),
                         "corrige_par": evenement.get("par") or "enseignant",  # Claude : sa pré-relecture (IA3)
                         "demande": generation._demande_d_origine(instance),
                         "rejete": _q(evenement["ancienne"]), "choisi": _q(questions[n - 1])})
    return resultat


def _rejets_automatiques(dossier: Path | None) -> list[dict]:
    lus = []
    for fichier in sorted(dossier.glob("*.json")) if dossier and dossier.is_dir() else []:
        try:
            rejet = json.loads(fichier.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(rejet, dict) and rejet.get("instance") and rejet.get("fournisseur") != "maquette":
            lus.append({"id": fichier.stem, "source": "rejet automatique", "niveau": rejet.get("niveau"),
                        "erreurs": rejet.get("erreurs") or [], "demande": rejet.get("demande") or {},
                        "exercice": rejet["instance"]})
    return lus


# --- le jeu ---------------------------------------------------------------------------------------------

def _ecrire_jsonl(chemin: Path, lignes: list[dict]) -> None:
    chemin.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lignes), encoding="utf-8")


def construire(lot: Path, banque_enseignant: Path | None, rejets: list[Path], noms, dossier: Path,
               part_procedurale: float = PART_PROCEDURALE, graine: int = GRAINE) -> dict:
    """Fabrique le jeu dans `dossier` (neuf) ; renvoie son manifeste."""
    du_lot, enseignant = relecture.instances(lot), relecture.instances(banque_enseignant)
    candidats: list[Exemple] = []
    for i in du_lot:
        if banque.statut(i) == banque.ACCEPTE:
            candidats.append(Exemple(i, "lot"))
        elif (banque.statut(i) == banque.GENERE and (i.get("meta") or {}).get("origine") == "procedural"
              and not relecture.corrections(i)):
            candidats.append(Exemple(i, "procedural"))
    candidats += [Exemple(i, "banque") for i in enseignant if banque.statut(i) == banque.ACCEPTE]

    ecartes, gardes, vus = [], [], set()
    for e in candidats:
        if raison := _ecarter(e.instance, noms):
            ecartes.append({"id": e.id, "source": e.source, "raison": raison})
            continue
        empreinte = json.dumps([q.get("enonce") for q in e.instance.get("questions") or []], ensure_ascii=False)
        if empreinte in vus:
            ecartes.append({"id": e.id, "source": e.source, "raison": "doublon d'un exercice déjà retenu"})
            continue
        try:
            e.messages, e.notion = messages(e.instance), notion(e.instance)
        except (ErreurValidation, KeyError, ValueError) as erreur:
            ecartes.append({"id": e.id, "source": e.source, "raison": f"mise en forme impossible : {erreur}"})
            continue
        vus.add(empreinte)
        gardes.append(e)
    gardes, de_cote = plafonner(gardes, part_procedurale, graine)
    ecartes += [{"id": e.id, "source": e.source, "raison": "au-delà de la part procédurale"} for e in de_cote]
    jeux = separer(gardes, graine)

    toutes_paires = [p for i, s in [(i, "lot") for i in du_lot if banque.statut(i) == banque.ACCEPTE]
                     + [(i, "banque") for i in enseignant if banque.statut(i) == banque.ACCEPTE] for p in paires(i, s)]
    toutes_paires = [p for p in toutes_paires
                     if not donnee_personnelle(json.dumps([p["rejete"], p["choisi"], p["motif"]], ensure_ascii=False), noms)]
    a_eviter = []
    for i, s in [(i, "lot") for i in du_lot] + [(i, "banque") for i in enseignant]:
        if banque.statut(i) != banque.REJETE or donnee_personnelle(_textes(i), noms):
            continue
        decision = ((i.get("meta") or {}).get("decisions") or [{}])[-1]
        a_eviter.append({"id": (i.get("meta") or {}).get("id"), "source": f"rejeté par l'enseignant ({s})",
                         "motifs": decision.get("motifs") or [], "motif": decision.get("motif"),
                         "demande": generation._demande_d_origine(i),
                         "exercice": {k: v for k, v in i.items() if k != "meta"}})
    for r in [r for d in rejets for r in _rejets_automatiques(d)]:
        if not donnee_personnelle(json.dumps(r["exercice"], ensure_ascii=False), noms):
            a_eviter.append(r)

    dossier.mkdir(parents=True, exist_ok=False)
    for nom, liste in jeux.items():
        _ecrire_jsonl(dossier / f"{nom}.jsonl", [{"messages": e.messages} for e in liste])
    _ecrire_jsonl(dossier / "paires.jsonl", toutes_paires)
    _ecrire_jsonl(dossier / "a_eviter.jsonl", a_eviter)
    manifeste = {
        "date": datetime.now().isoformat(timespec="seconds"), "graine": graine, "part_procedurale": part_procedurale,
        "objectif": relecture.OBJECTIF_ACCEPTES,
        "jeux": {nom: [{"id": e.id, "source": e.source, "notion": e.notion, "matiere": e.instance.get("matiere"),
                        "niveau": e.instance.get("niveau")} for e in liste] for nom, liste in jeux.items()},
        "paires": len(toutes_paires), "a_eviter": len(a_eviter), "ecartes": ecartes,
        "paires_claude": sum(p["corrige_par"] == prerelecture.PAR for p in toutes_paires),
        "relecture": {"relus": sum(bool((i.get("meta") or {}).get("decisions")) for i in du_lot),
                      **{cle: n for cle, n in prerelecture.compter(du_lot).items() if cle in ("decides", "suivis")}},
        "empreintes": {f: hashlib.sha256((dossier / f).read_bytes()).hexdigest() for f in FICHIERS},
    }
    (dossier / "manifeste.json").write_text(json.dumps(manifeste, ensure_ascii=False, indent=2), encoding="utf-8")
    (dossier / "fiche.md").write_text(fiche(manifeste, a_eviter), encoding="utf-8")
    for f in dossier.iterdir():  # figé : en lecture seule
        os.chmod(f, 0o444)
    return manifeste


# --- la fiche des données (IA3.5) ------------------------------------------------------------------------

MATIERES = {"maths": "maths", "francais": "français", "histoire-geo": "histoire-géo"}


def _pourcent(x: float) -> str:
    return f"{round(100 * x)} %"


def _aide(r: dict) -> str:
    """La pré-relecture de Claude, s'il y en a eu une : combien de décisions elle a précédées, combien l'ont suivie."""
    if not r.get("decides"):
        return "."
    return (f" ; {r['decides']} des {r['relus']} exercices relus du lot l'ont été après une pré-relecture de "
            f"{prerelecture.PAR}, un autre modèle que celui qui les a écrits : son avis (bon, à corriger, à rejeter) a été "
            f"suivi {r['suivis']} fois. Les décisions restent humaines, mais aidées.")


def fiche(m: dict, a_eviter: list[dict]) -> str:
    jeux = m["jeux"]
    tous = [x for liste in jeux.values() for x in liste]
    total = len(tous)

    def ligne(titre: str, compte) -> str:
        valeurs = [sum(1 for x in jeux[j] if compte(x)) for j in ("train", "valid", "test")]
        return f"| {titre} | " + " | ".join(map(str, valeurs)) + f" | {sum(valeurs)} |"

    matieres = Counter((x["matiere"], x["niveau"]) for x in tous)
    par_matiere = Counter(x["matiere"] for x in tous)
    lignes = [
        f"# Fiche des données : le jeu du {datetime.fromisoformat(m['date']):%d/%m/%Y à %H:%M}", "",
        "Produit par `python -m generateur.entrainement jeu` (plan IA, IA3), graine "
        f"{m['graine']}, part procédurale au plus {_pourcent(m['part_procedurale'])}. Le lot d'entraînement "
        "(`donnees/entrainement/banque/`) et la banque de l'enseignant, lue seulement. Fichiers en lecture seule ; "
        "leurs empreintes dans `manifeste.json`.", "",
        "## Ce qu'il contient", "",
        "| | Entraînement | Validation | Test | Total |", "|---|---|---|---|---|",
        ligne("**Exercices**", lambda x: True)]
    lignes += [ligne(SOURCES[s].capitalize(), lambda x, s=s: x["source"] == s) for s in SOURCES]
    lignes += [ligne(f"{MATIERES.get(mat, mat)}, {niv}", lambda x, c=(mat, niv): (x["matiere"], x["niveau"]) == c)
               for mat, niv in sorted(matieres, key=lambda c: (str(c[0]), str(c[1])))]
    notions = {j: sorted({x["notion"] for x in jeux[j]}) for j in jeux}
    lignes += [
        "", f"**{total} exercices** ; objectif avant d'entraîner : {m['objectif']}"
        + (" (atteint)." if total >= m["objectif"] else f" (**il en manque {m['objectif'] - total}**)."), "",
        "## La séparation, par notion", "",
        f"Entraînement : {len(notions['train'])} notion(s) ; validation : {len(notions['valid'])} ; test : "
        f"{len(notions['test'])}. Aucune notion du test ni de la validation n'est vue à l'entraînement.", "",
        "- Validation : " + (", ".join(notions["valid"]) or "aucune"),
        "- Test : " + (", ".join(notions["test"]) or "aucune"), "",
        "## À côté", "",
        f"- `paires.jsonl` : {m['paires']} paire(s) « avant → après » (une question corrigée à la main ou régénérée, "
        "face à la version acceptée), pour une 2e passe qui apprend à préférer la version corrigée (IA4, si la 1re "
        "est adoptée)" + (f" ; dont {m['paires_claude']} corrections écrites par {prerelecture.PAR} d'après sa "
                          "pré-relecture, vérifiées et acceptées par l'enseignant (`corrige_par`)."
                          if m.get("paires_claude") else "."),
        f"- `a_eviter.jsonl` : {len(a_eviter)} exercice(s) à éviter : "
        f"{sum(1 for a in a_eviter if a['source'] != 'rejet automatique')} rejeté(s) par l'enseignant (dont "
        f"{sum(1 for a in a_eviter if a.get('motifs') or a.get('motif'))} avec un motif), "
        f"{sum(1 for a in a_eviter if a['source'] == 'rejet automatique')} rejeté(s) par N1 → N4.", "",
        "## Écartés", ""]
    if m["ecartes"]:
        lignes += ["| Exercice | Source | Raison |", "|---|---|---|"]
        lignes += [f"| {e['id']} | {e['source']} | {e['raison']} |" for e in m["ecartes"]]
    else:
        lignes.append("Aucun.")
    maths = par_matiere.get("maths", 0)
    lignes += [
        "", "## Le format", "",
        "Celui de `mlx_lm.lora` : une conversation par ligne, `{\"messages\": [système, utilisateur, assistant]}`. "
        "Système et utilisateur : le vrai prompt de la génération (consignes, schéma, exemple, demande ; les extraits "
        "de cours s'il y en avait). Assistant : l'exercice tel que le modèle doit l'écrire (sans meta, les champs dans "
        "l'ordre du schéma).", "",
        "## Les limites", "",
        f"- **La taille** : {total} exercices" + ("" if total >= m["objectif"] else
                                                   f", sous l'objectif de {m['objectif']} : un entraînement serait un essai."),
        f"- **Les matières** : {maths} exercice(s) de maths sur {total}" + (f" ({_pourcent(maths / total)})" if total else "")
        + " ; pas d'autre matière que les maths et le français dans le lot (les programmes du référentiel).",
        "- **Une partie est écrite par le modèle lui-même**, puis relue : elle lui apprend surtout la forme ; ce sont les "
        "corrections qui le font progresser (`paires.jsonl`)" + (
            f" : celles de l'enseignant, et {m['paires_claude']} de {prerelecture.PAR}, qu'il a vérifiées. Ces dernières "
            "apprennent au modèle à corriger comme Claude, un autre modèle : c'est de la distillation, pas un jugement "
            "humain." if m.get("paires_claude") else ", celles de l'enseignant."),
        "- **Les procéduraux** ne couvrent que quatre notions (calcul mental, fractions, pourcentages, Pythagore) : "
        "plafonnés pour ne pas déséquilibrer le jeu.",
        "- **L'échantillon relu alterne les matières et les classes** : le français y pèse plus que dans le lot.",
        "- **Une seule personne a relu et décidé** (le développeur du projet), pas des enseignants en classe"
        + _aide(m.get("relecture") or {}),
        "- **Aucune donnée personnelle** : les noms de tous les élèves de la base, les noms écrits comme dans une liste, "
        "courriels, téléphones, adresses et liens sont cherchés ; un exercice qui en contient est écarté."]
    return "\n".join(lignes) + "\n"
