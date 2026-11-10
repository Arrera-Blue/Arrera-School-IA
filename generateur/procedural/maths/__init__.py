"""Les générateurs procéduraux des maths (étape 1.7) : un module par notion (calcul mental, fractions, pourcentages,
Pythagore). Le programme tire les nombres, calcule la réponse et fabrique les distracteurs ; le modèle ne fait que
réécrire l'énoncé, sous contrôle (../habillage.py). Conception : docs/etapes/etape-1.7-procedural.md.

Rangés ici depuis le générateur procédural du cycle 2 (lot 0, étape 0.2 : un sous-dossier par matière,
docs/Generateur-Procedural/cycle-2-cp-ce1-ce2.md), sans rien changer à leur comportement. Ils servent au collège
seulement (`COLLEGE`) : les maths du cycle 2 ne sont pas encore couvertes.
"""

import re

MATIERE = "maths"
COLLEGE = ("6e", "5e", "4e", "3e")

# d'autres notions de maths : si la demande en cite une, elle n'est pas couverte en entier par un générateur ;
# en début de mot (« aire » n'est pas dans « scolaire », ni « angle » dans « triangle »)
AUTRES_NOTIONS = re.compile(r"\b(?:decima|equation|relatif|proportionnal|aires?\b|perimetre|volume|"
                            r"puissance|racine|statisti|probabilit|thales|trigonometr|fonction|geometr|symetr|"
                            r"conversion|division euclidienne)")


def generateurs() -> tuple:
    """Les modules de la matière. Import local : le paquet reste léger à charger."""
    from generateur.procedural.maths import calcul_mental, fractions, pourcentages, pythagore
    return (calcul_mental, fractions, pourcentages, pythagore)
