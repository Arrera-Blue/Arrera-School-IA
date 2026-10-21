"""Contrôle du niveau (évolution E2.6) : une notion d'une classe supérieure dans l'exercice → un AVERTISSEMENT.

Les notions repères viennent des programmes officiels (generateur/programmes/reperes.yaml) : « racine carrée »
n'apparaît qu'en 4e, « nombres relatifs » qu'en 5e… Jamais un rejet : une notion peut être citée sans être
travaillée, et l'enseignant tranche à la relecture. Rien n'est contrôlé pour une matière ou une classe inconnue.
"""

from generateur import programmes


def _texte(question: dict) -> str:
    return " ".join([question.get("enonce") or "", *(question.get("propositions") or []), question.get("explication") or ""])


def _repere_cite(texte: str, matiere: str, niveau: str) -> list[programmes.Repere]:
    texte = programmes.sans_accents(texte)
    return [r for r in programmes.reperes()
            if r.matiere == matiere and programmes.rang(r.niveau) > programmes.rang(niveau) and r.motif.search(texte)]


def _message(debut: str, repere: programmes.Repere, niveau: str) -> str:
    source = programmes.libelle(repere.source) if programmes.attendu(repere.source) else repere.source
    return (f"{debut} : « {repere.notion} » est au programme de {repere.niveau}, pas de {niveau} ({source}) : "
            "vérifier que la question reste au niveau de la classe")


def avertissements(instance: dict) -> list[str]:
    """« question 2 : « racine carrée » est au programme de 4e, pas de 6e (…) : vérifier… », une fois par notion et
    par question ; le titre et la notion de l'exercice sont regardés aussi."""
    matiere, niveau = instance.get("matiere"), instance.get("niveau")
    if programmes.rang(niveau) < 0:
        return []
    messages = []
    for repere in _repere_cite(f"{instance.get('titre') or ''} {instance.get('notion') or ''}", matiere, niveau):
        messages.append(_message("l'exercice", repere, niveau))
    for n, question in enumerate(instance.get("questions") or [], start=1):
        for repere in _repere_cite(_texte(question), matiere, niveau):
            messages.append(_message(f"question {n}", repere, niveau))
    return messages
