"""Les générateurs procéduraux des sciences et technologie, du CP au CE2 (lot 2 du générateur procédural du cycle 2 :
docs/Generateur-Procedural/lot-2-questionner-le-monde.md). Le programme de 2026 : sciences et technologie du cycle 2
(BO n° 24 du 11 juin 2026), en vigueur au CP depuis la rentrée 2026, au CE1 et au CE2 à la rentrée 2027.

La réponse se lit dans une **table de référence relue par l'enseignant** (../tables.py,
donnees/sciences-et-technologie/), chaque ligne avec sa source (le programme d'abord, sinon Wikipédia ou le
Wiktionnaire) ; les mauvaises réponses sont fausses par construction (monde fermé) ; l'explication sort d'une règle.
Aucun énoncé n'est écrit par le modèle. Un fait discuté n'est jamais demandé (le régime de l'araignée, l'œuf « vivant
ou non », l'organe de l'oreille qui sert aussi à l'équilibre).

Un générateur dont une table n'est pas relue n'est jamais proposé (procedural.candidats).
"""

import re

MATIERE = "sciences-et-technologie"
CYCLE_2 = ("CP", "CE1", "CE2")

# les notions des sciences qu'aucun générateur ne couvre (sans accents, en début de mot) : une demande qui en cite une
# part au modèle. Les gestes et les observations du programme (mesurer, construire, programmer), l'hygiène et la santé
# (décision 5 du 16/11), ce qu'aucune source lue ne tranche (la respiration, la transpiration pendant l'effort).
AUTRES_NOTIONS = re.compile(r"\b(?:hygiene|sante|sommeil|equilibre alimentaire|apports?\b|menus?\b|cycle de l'eau|"
                            r"temperature|thermometre|degres? celsius|contenances?|verre gradue|litres?\b|"
                            r"volumes? de liquide|sabliers?|durees?|l'air\b|materialite|vent\b|robots?|programmation|"
                            r"moteur de recherche|traitement de texte|assemblage|maquette|environnement|pollution|"
                            r"dechets|biodiversite|saisons?|respiration|transpiration|essoufflement|cerveau|attention|"
                            r"croissance du corps|pointure)")


def generateurs() -> tuple:
    """Les modules de la matière. Import local : le paquet reste léger à charger."""
    from generateur.procedural.sciences_et_technologie import corps, matiere, vivant
    return (vivant, corps, matiere)
