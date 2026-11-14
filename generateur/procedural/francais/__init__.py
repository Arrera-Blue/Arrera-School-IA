"""Les générateurs procéduraux du français, du CP au CE2 (lot 1 du générateur procédural du cycle 2 :
docs/Generateur-Procedural/lot-1-francais.md). La réponse ne se calcule pas : elle se lit dans une **table de
référence relue par l'enseignant** (../tables.py, donnees/francais/) ; les mauvaises réponses sont de vraies formes,
prises dans les tables ; l'explication sort d'une règle. Aucun énoncé n'est écrit par le modèle.

Un générateur dont une table n'est pas relue n'est jamais proposé (procedural.candidats).
"""

import random
import re

from generateur.procedural import Retirer

MATIERE = "francais"
CYCLE_2 = ("CP", "CE1", "CE2")

# les notions de français qu'aucun générateur ne couvre : une demande qui en cite une part au modèle (sans accents,
# en début de mot) ; les synonymes : pas de générateur (décision 6 du lot 1 : un piège pourrait être juste)
AUTRES_NOTIONS = re.compile(r"\b(?:homophone|passe simple|subjonctif|conditionnel|imperatif|plus-que-parfait|"
                            r"futur anterieur|participe passe|2e groupe|deuxieme groupe|lecture|comprehension|"
                            r"poesie|poeme|conte|dictee|redaction|production d'ecrit|oral|discours rapporte|"
                            r"synonyme|suffixe|sens propre|sens figure|polysemie|expression)")


def generateurs() -> tuple:
    """Les modules de la matière. Import local : le paquet reste léger à charger."""
    from generateur.procedural.francais import accords, conjugaison, phrase, vocabulaire
    return (conjugaison, accords, phrase, vocabulaire)


def respecte(ligne: dict, criteres: dict | None) -> bool:
    """La ligne d'une table respecte-t-elle les critères d'une notion précise ({"temps": ("imparfait",)}) ?"""
    return all(ligne.get(cle) in valeurs for cle, valeurs in (criteres or {}).items())


def une(rng: random.Random, lignes: list):
    """Une ligne tirée au sort ; aucune (les critères d'une notion précise n'en laissent pas) : on tire autrement."""
    if not lignes:
        raise Retirer("aucune ligne de la table ne répond à la demande")
    return rng.choice(lignes)


def avant_ou_egale(classe: str, depuis: str) -> bool:
    """La ligne d'une table (« depuis » : sa première classe) sert-elle à cette classe ?"""
    return CYCLE_2.index(depuis) <= CYCLE_2.index(classe)
