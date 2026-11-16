"""Les générateurs procéduraux de l'histoire-géographie, du CP au CE2 (lot 2 du générateur procédural du cycle 2 :
docs/Generateur-Procedural/lot-2-questionner-le-monde.md). Le programme de 2026 : histoire-géographie du cycle 2
(BO n° 22 du 28 mai 2026), en vigueur au CP depuis la rentrée 2026, au CE1 et au CE2 à la rentrée 2027.

La réponse se calcule (le calendrier, les durées, l'ordre des périodes) ou se lit dans une **table de référence
relue par l'enseignant** (../tables.py, donnees/histoire-geo/) ; les mauvaises réponses sont fausses par
construction ; l'explication sort d'une règle. Aucun énoncé n'est écrit par le modèle. Un fait discuté n'est jamais
demandé (le nombre de continents, le premier jour de la semaine, le nombre de saisons).

Un générateur dont une table n'est pas relue n'est jamais proposé (procedural.candidats).
"""

import re

MATIERE = "histoire-geo"
CYCLE_2 = ("CP", "CE1", "CE2")

# les notions de l'histoire-géographie qu'aucun générateur ne couvre (sans accents, en début de mot) : une demande qui
# en cite une part au modèle. La géographie viendra à l'étape 2.4 (sans carte) ; la vie à Rome, le royaume de France,
# les traces du passé, l'heure ne sont pas dans le générateur.
AUTRES_NOTIONS = re.compile(r"\b(?:geographi|continent|ocean|carte|planisphere|globe|paysage|relief|montagne|massif|"
                            r"fleuve|riviere|climat|desert|foret|pays\b|villes?\b|village|campagne|quartier|"
                            r"points? cardinaux|nord\b|rome\b|romain|gaule|gaulois|gallo|royaume|rois?\b|reine|sacre|"
                            r"capetien|valois|traces? du passe|archeolog|historien|arbre genealogique|generation|"
                            r"jour et (?:de )?la nuit|l'heure|horloge|montre|pendule|sablier|figure historique|"
                            r"revolution|guerre mondiale|napoleon|chateau|chevalier|seigneur|egypt|grec)")


def generateurs() -> tuple:
    """Les modules de la matière. Import local : le paquet reste léger à charger."""
    from generateur.procedural.histoire_geo import histoire
    return (histoire,)
