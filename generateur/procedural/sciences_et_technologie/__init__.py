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

# les notions des sciences qu'aucun générateur ne couvre encore (sans accents, en début de mot) : une demande qui en
# cite une part au modèle. Le corps, la matière et les objets viendront à l'étape 2.3.
AUTRES_NOTIONS = re.compile(r"\b(?:corps humain|squelette|os\b|articulation|muscle|dents?\b|aliments?\b|hygiene|sante|"
                            r"sommeil|etats? de l'eau|cycle de l'eau|glace|matiere|masse|volume|temperature|"
                            r"thermometre|electri|circuit|conducteur|isolant|objets? techniques?|ordinateur|robot|"
                            r"programmation|environnement|pollution|dechets|biodiversite|saisons?|respiration|"
                            r"cerveau|attention)")


def generateurs() -> tuple:
    """Les modules de la matière. Import local : le paquet reste léger à charger."""
    from generateur.procedural.sciences_et_technologie import vivant
    return (vivant,)
