"""Le fond d'un exercice : N3 (cohérence pédagogique) puis N4 (calculs). N3 avertit aussi quand l'exercice cite une
notion d'une classe supérieure (programme.py, évolution E2.6) : jamais un rejet.

Utilisé à trois moments :
- à la génération, pour refuser (`valider_le_fond`) ;
- à la relecture, pour montrer avec les règles du jour ce qu'un exercice déjà enregistré contient de faux
  (`controler`) : le 16/10, 5 exercices de la banque, acceptés avant l'extension de N4 (07/10), contenaient
  une réponse fausse (« 12 + 15 = 25 ») que leur meta ne signalait pas ;
- à la régénération d'une question (`tolerant`).
"""

from collections.abc import Callable

from generateur.moteur.validation import ErreurValidation, n3_pedagogie, n4_calcul, numero_de_question, programme


def valider_le_fond(instance: dict) -> tuple[list[str], dict]:
    """N3 puis N4, en signalant TOUS les défauts d'un coup.

    S'arrêter au premier niveau en faute cacherait les erreurs de calcul quand N3 a déjà rejeté : la
    reprise sur erreur (1.4) corrigerait une partie des questions, puis échouerait sur le reste à l'essai
    suivant. Cas réel du 03/10 : N3 rejetait les questions 1, 2 et 4, et l'erreur de calcul de la
    question 3 n'apparaissait pas.
    """
    rejets: list[ErreurValidation] = []
    avertissements, bilan_n4 = [], {}
    try:
        avertissements = n3_pedagogie.valider(instance) + programme.avertissements(instance)
    except ErreurValidation as e:
        rejets.append(e)
    try:
        bilan_n4 = n4_calcul.valider(instance)
    except ErreurValidation as e:
        # « plusieurs propositions conviennent » sur une question déjà rejetée par N3 : même défaut, pas deux fois
        deja = set(rejets[0].questions) if rejets else set()
        messages = [m for m in e.erreurs
                    if not (numero_de_question(m) in deja and "plusieurs propositions conviennent" in m)]
        rejets.append(ErreurValidation("N4", messages, tuple(numero_de_question(m) for m in messages)))
    rejets = [r for r in rejets if r.erreurs]
    if rejets:
        raise ErreurValidation(", ".join(r.niveau for r in rejets),
                               sorted((m for r in rejets for m in r.erreurs), key=numero_de_question),
                               tuple(sorted({q for r in rejets for q in r.questions})))
    return avertissements, bilan_n4


def controler(instance: dict) -> dict:
    """Le fond de l'exercice tel qu'il est, avec les règles actuelles, sans rien lever :
    {"erreurs": défauts bloquants, "questions": leurs numéros, "niveau": « N3, N4 » ou None,
     "avertissements": défauts non bloquants de N3, "n4_questions": verdict de N4 pour chaque question}."""
    exercice = {k: v for k, v in instance.items() if k != "meta"}
    n4_questions = [v.statut for v in n4_calcul.verifier(exercice)]
    try:
        avertissements, _ = valider_le_fond(exercice)
    except ErreurValidation as e:
        avertissements = ([c.message for c in n3_pedagogie.verifier(exercice) if not c.bloquant]
                          + programme.avertissements(exercice))
        return {"erreurs": list(e.erreurs), "questions": list(e.questions), "niveau": e.niveau,
                "avertissements": avertissements, "n4_questions": n4_questions}
    return {"erreurs": [], "questions": [], "niveau": None, "avertissements": avertissements,
            "n4_questions": n4_questions}


def tolerant(avant: dict, numero: int) -> Callable[[dict], tuple[list[str], dict]]:
    """`valider_le_fond` pour la régénération de la question `numero` : les défauts d'AUTRES questions, déjà
    présents avant, ne bloquent pas. Sans cela, deux questions fausses s'empêcheraient mutuellement d'être
    corrigées (chacune revalide tout l'exercice). Ces défauts restent visibles à la relecture (`controler`)."""
    deja = {m for m in controler(avant)["erreurs"] if numero_de_question(m) != numero}

    def valider(instance: dict) -> tuple[list[str], dict]:
        try:
            return valider_le_fond(instance)
        except ErreurValidation as e:
            nouvelles = [m for m in e.erreurs if m not in deja]
            if nouvelles:
                raise ErreurValidation(e.niveau, nouvelles,
                                       tuple(sorted({numero_de_question(m) for m in nouvelles} - {0}))) from None
            bilan = controler(instance)
            return bilan["avertissements"], {"n4": n4_calcul.A_RELIRE, "n4_questions": bilan["n4_questions"]}
    return valider
