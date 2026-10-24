"""Des réponses simulées, pour construire et vérifier le suivi sans aucun élève réel (évolution E4.0).

    python -m generateur.donnees.simulation <identifiant> [--classe "6e Démo"] [--remplacer]

Chaque élève de la classe reçoit un **profil connu**, selon son rang : les 6 premiers sont à consolider en fractions,
les 4 suivants à consolider en pourcentages, les 4 suivants en réussite partout, les autres en cours. Les profils
sont **déterministes** (2, 5 ou 7 réussites sur 8 questions par attendu) : le tableau de suivi doit les retrouver
exactement.

Les exercices sont tirés par le générateur procédural, sans le modèle, et **ne vont pas dans la banque** ; les
réponses passent par `suivi.enregistrer_tentative`, la fonction que le serveur de classe utilisera (E8), qui
recalcule juste ou faux.
"""

import argparse
import contextlib
import io
import random
import sys

from generateur.donnees import classes, comptes, journal, suivi
from generateur.donnees.base import Base

QUESTIONS = 8
JUSTES = {"a_consolider": 2, "en_cours": 5, "en_reussite": 7}   # sur 8 : 25 %, 62,5 %, 87,5 %
ATTENDUS = {
    "6e": {"fractions": ["maths.6e.fractions.08", "maths.6e.fractions.09", "maths.6e.fractions.11"],
           "pourcentages": ["maths.6e.fractions.16", "maths.6e.fractions.17", "maths.6e.nombres-decimaux.06"],
           "autres": ["maths.6e.nombres-decimaux.14"]},
    "5e": {"fractions": ["maths.5e.nombres-rationnels.01", "maths.5e.nombres-rationnels.02"],
           "pourcentages": ["maths.5e.proportionnalite.01", "maths.5e.proportionnalite.02"], "autres": []},
}
PROFILS = (("consolider_fractions", 6), ("consolider_pourcentages", 4), ("reussite", 4))


def profil(rang: int) -> str:
    """Le profil du rang-ième élève de la classe (0 pour le premier)."""
    for nom, nombre in PROFILS:
        if rang < nombre:
            return nom
        rang -= nombre
    return "en_cours"


def etat_attendu(nom_profil: str, famille: str) -> str:
    """L'état que le tableau doit trouver pour ce profil, sur un attendu de cette famille."""
    if nom_profil == "reussite":
        return "en_reussite"
    if (nom_profil, famille) in (("consolider_fractions", "fractions"), ("consolider_pourcentages", "pourcentages")):
        return "a_consolider"
    return "en_cours"


def _exercice(attendu: str, niveau: str, graine: int) -> dict:
    """Un exercice du générateur procédural sur cet attendu, sans le modèle ni la banque."""
    from generateur.moteur import generation
    from generateur import programmes

    demande = {"type": "qcm", "matiere": "maths", "niveau": niveau, "nb_questions": QUESTIONS, "attendu": attendu,
               "notion": programmes.libelle(attendu)[:120]}
    with contextlib.redirect_stdout(io.StringIO()):
        instance = generation.generer(demande, "qcm", "maquette", graine=graine)
    instance["meta"]["id"] = f"simulation-{attendu}"  # l'identifiant daté se répète d'un exercice à l'autre
    instance["titre"] = f"{instance['titre']} : {programmes.libelle(attendu)}"[:120]  # « Les fractions » ×3, sinon
    return instance


def simuler(base: Base, compte: dict, classe_id: int, graine: int = 0, remplacer: bool = False) -> dict:
    """Remplit la classe de réponses simulées ; renvoie {eleves, tentatives, profils: {numéro: profil}}."""
    classe = classes.lire(base, compte, classe_id)
    familles = ATTENDUS.get(classe["niveau"])
    if not familles:
        raise classes.ClasseInvalide("simulation possible en 6e et en 5e seulement (les générateurs procéduraux)")
    eleves = classe["liste"]
    with base.ecrire() as conn:
        deja = conn.execute("SELECT COUNT(*) FROM tentative t JOIN eleve e ON e.id = t.eleve_id "
                            "WHERE e.classe_id = ? AND t.origine = 'simulation'", (classe_id,)).fetchone()[0]
        if deja and not remplacer:
            raise classes.ClasseInvalide("la classe a déjà des réponses simulées (--remplacer pour les refaire)")
        conn.execute("DELETE FROM tentative WHERE origine = 'simulation' AND eleve_id IN "
                     "(SELECT id FROM eleve WHERE classe_id = ?)", (classe_id,))
    exercices = {a: (famille, _exercice(a, classe["niveau"], graine + i))
                 for i, (famille, a) in enumerate((f, a) for f, liste in familles.items() for a in liste)}
    profils, tentatives = {}, 0
    for rang, eleve in enumerate(eleves):
        nom_profil = profil(rang)
        profils[eleve["numero"]] = nom_profil
        for attendu, (famille, instance) in exercices.items():
            rng = random.Random(f"{graine}-{eleve['id']}-{attendu}")
            justes = set(rng.sample(range(1, QUESTIONS + 1), JUSTES[etat_attendu(nom_profil, famille)]))
            reponses = []
            for numero, q in enumerate(instance["questions"], start=1):
                fausses = [i for i in range(len(q["propositions"])) if i != q["index_correct"]]
                choix = q["index_correct"] if numero in justes else rng.choice(fausses)
                reponses.append((numero, choix, round(rng.uniform(5, 45), 1)))
            suivi.enregistrer_tentative(base, eleve["id"], instance, reponses, "simulation")
            tentatives += 1
    with base.ecrire() as conn:
        journal.noter(conn, "simulation", compte, cible=f"classe:{classe_id}",
                      detail=f"{len(eleves)} élève(s), {tentatives} tentative(s)")
    return {"eleves": len(eleves), "tentatives": tentatives, "profils": profils}


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m generateur.donnees.simulation",
                                     description="Remplir une classe fictive de réponses simulées, aux profils connus.")
    parser.add_argument("identifiant", help="le compte enseignant de la classe")
    parser.add_argument("--classe", default="6e Démo", help="le nom de la classe (par défaut : 6e Démo)")
    parser.add_argument("--remplacer", action="store_true", help="refaire les réponses simulées existantes")
    args = parser.parse_args(arguments)
    from generateur.moteur import config

    base = Base(config.chemin("base"))
    compte = comptes.lire(base, args.identifiant)
    if compte is None:
        print(f"Refusé : compte inconnu : {args.identifiant}", file=sys.stderr)
        return 1
    trouvee = next((c for c in classes.lister(base, compte) if c["nom"] == args.classe), None)
    if trouvee is None:
        print(f"Refusé : pas de classe « {args.classe} » pour {args.identifiant} "
              "(python -m generateur.donnees.demo en crée une)", file=sys.stderr)
        return 1
    try:
        resultat = simuler(base, compte, trouvee["id"], remplacer=args.remplacer)
    except classes.ClasseInvalide as e:
        print(f"Refusé : {e}", file=sys.stderr)
        return 1
    print(f"« {args.classe} » : {resultat['tentatives']} tentatives simulées pour {resultat['eleves']} élèves.\n"
          "Profils attendus dans le tableau de suivi :")
    libelles = {"consolider_fractions": "à consolider en fractions", "consolider_pourcentages": "à consolider en "
                "pourcentages", "reussite": "en réussite partout", "en_cours": "en cours partout"}
    for numero, nom_profil in resultat["profils"].items():
        print(f"  n° {numero:>2}  {libelles[nom_profil]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
