"""Le référentiel du programme de langues vivantes du cycle 2 (lot 3, étape 3.0) : du brouillon
(extraire_objectifs_lv.py) aux fichiers `generateur/programmes/anglais-cp.yaml`, `-ce1`, `-ce2`, au format d'E2. Les
libellés et les titres des compétences sont ceux du brouillon, mot pour mot ; seuls sont ajoutés ici les identifiants,
le code de la compétence (`code`, celui du programme : CO-CP…), le champ « qcm » (un classement du projet, pas du
programme), la colonne d'origine (`colonne` : « attendus » pour les attendus de fin d'année, « objectifs » pour la
colonne « Objectifs d'apprentissage ») et le niveau du CECRL (`niveau_cecrl`, lu dans la couleur du texte par
l'extraction : « pré-A1 », « A1 », ou « pré-A1 et A1 »).

Le programme vaut pour toutes les langues vivantes (ses exemples sont surtout en anglais) ; l'application n'a qu'une
langue, l'anglais (décision 5 du 10/11) : la matière est `anglais`.

Usage : python -I construire_referentiel_lv.py <brouillon.json> <dossier generateur/programmes>"""
import json
import sys
from pathlib import Path

import yaml

brouillon = json.load(open(sys.argv[1], encoding="utf-8"))
sortie = Path(sys.argv[2])

THEMES = {
    # compréhension de l'oral (CO)
    "Comprendre quelques mots familiers et expressions très courantes": "mots-familiers",
    "Suivre le fil d’une histoire adaptée à l’âge des élèves et suffisamment étayée": "suivre-histoire",
    "Comprendre et agir": "comprendre-agir",
    # expression orale en continu (EOC)
    "Repères phonologiques": "reperes-phonologiques",
    "Reproduire un modèle oral": "reproduire-modele",
    "Raconter": "raconter",
    "Se décrire en utilisant des expressions courtes ou proches des modèles rencontrés lors des apprentissages":
        "se-decrire",
    "Décrire ou se décrire en utilisant des expressions courtes ou proches des modèles rencontrés lors des "
    "apprentissages": "se-decrire",  # le titre du CE2
    # expression orale en interaction (EOI)
    "Échanger des informations simples": "echanger-informations",
    "Exprimer des émotions et formuler des souhaits élémentaires": "emotions-souhaits",
    "Clarifier ou faire clarifier un point": "clarifier",
    "Utiliser des procédés très simples pour commencer, poursuivre et terminer une conversation brève": "conversation",
    # compréhension de l'écrit (CE), expression écrite (EE) : au CE2 seulement
    "Reconnaitre des mots ou des messages écrits familiers": "mots-ecrits",
    "Trouver des informations dans des écrits très simples": "informations-ecrits",
    "Épeler, recopier ou écrire des éléments connus": "epeler-recopier",
    # médiation (M)
    "Identifier les repères culturels": "reperes-culturels",
    "Expliciter un message, une situation, un document pour autrui": "expliciter",
    "Animer un travail collectif, coopérer et contribuer à des échanges interculturels": "animer-cooperer",
}

# le champ « qcm », la règle d'E2 et des lots 1 et 2 : une connaissance qu'un QCM vérifie (écrit au CE2 ; à l'écoute
# au CP et au CE1, décision 2 du lot 3) : ce que l'élève reconnaît (un nombre, un jour, une date, un mot familier, une
# formule de salutation ou de politesse, la réponse à une question ritualisée). Jamais un geste ni une action
# (« comprendre et agir »), une production (parler, raconter, se décrire, prononcer, épeler, écrire), l'intonation, ce
# qui demande une image (associer un document oral à un document visuel, des affichages illustrés), ni la médiation (les
# repères culturels hors du QCM : décision 6). Par classe et par thème, le rang des attendus de fin d'année (« a ») et
# des objectifs (« o ») ; les classements discutables sont listés dans docs/Generateur-Procedural/lot-3-anglais.md §11.1.
QCM = {
    ("CP", "mots-familiers"): {"a1", "a2", "o1", "o2", "o4", "o6"},
    ("CE1", "mots-familiers"): {"a1", "a2", "o1", "o2", "o3", "o5", "o7"},
    ("CE2", "mots-familiers"): {"a1", "a2", "o1", "o2", "o3", "o5", "o7"},
    ("CP", "suivre-histoire"): {"a2", "o1", "o3"},     # des mots, des noms, des chiffres ; lettres et chiffres
    ("CE1", "suivre-histoire"): {"a2", "o1", "o3"},
    ("CE2", "suivre-histoire"): {"a2", "o1", "o3"},
    ("CP", "echanger-informations"): {"a2", "a3"},     # comprendre des expressions courantes, des nombres simples
    ("CE1", "echanger-informations"): {"a2", "a3"},
    ("CE2", "echanger-informations"): {"a2", "a3", "a5"},  # répondre à des questions ritualisées
    ("CP", "conversation"): {"a1", "a2", "o1", "o2", "o4"},  # saluer, remercier, prendre congé
    ("CE1", "conversation"): {"a1", "a2", "a4", "o1", "o2", "o5"},
    ("CE2", "conversation"): {"a1", "a2", "a4", "o1", "o2", "o5"},
    ("CE2", "mots-ecrits"): {"a1", "o1", "o2", "o3", "o4", "o5"},
    ("CE2", "informations-ecrits"): {"o2", "o3", "o4"},
}

SOURCE = {
    "texte": "Programme de langues vivantes étrangères et régionales pour le cycle 2 (annexe 1 de l’arrêté)",
    "arrete": "Arrêté du 26 février 2026 (JO du 7 mars 2026)",
    "nor": "MENE2602911A",
    "bo": "BO n° 12 du 19 mars 2026",
    "url": "https://www.education.gouv.fr/bo/2026/Hebdo12/MENE2602911A",
}
EN_VIGUEUR = {
    "CP": "au CP depuis la rentrée 2026-2027 (article 3 de l’arrêté)",
    "CE1": "au CE1 à la rentrée 2027-2028 (article 3 de l’arrêté) ; en 2026-2027, le CE1 suit encore le programme de "
           "langues vivantes de 2015 modifié (BO n° 31 du 30 juillet 2020)",
    "CE2": "au CE2 à la rentrée 2027-2028 (article 3 de l’arrêté) ; en 2026-2027, le CE2 suit encore le programme de "
           "langues vivantes de 2015 modifié (BO n° 31 du 30 juillet 2020)",
}
EXTRAIT = {"CP": "« Cours préparatoire »", "CE1": "« Cours élémentaire première année »",
           "CE2": "« Cours élémentaire deuxième année »"}
ENTETE = """# Référentiel des attendus — anglais, {classe} (générateur procédural du cycle 2, lot 3, étape 3.0). Libellés recopiés
# MOT POUR MOT des « Attendus de fin d’année » et de la colonne « Objectifs d’apprentissage » du programme officiel de
# 2026 (source ci-dessous ; le PDF du BO, pages 14 à 47 :
# https://www.education.gouv.fr/sites/default/files/document/Bulletin%20officiel%20n%C2%B0%2012%20du%2019%20mars%202026-481193.pdf).
# Le programme vaut pour toutes les langues vivantes ; ses marques de niveau, « (A1) » et « (pré-A1) », sont gardées
# dans les libellés. Seuls les identifiants, le code de la compétence (« code »), le champ « qcm » (se prête ou non à
# un QCM : classement du projet, pas du programme), la colonne d’origine (« colonne ») et le niveau du CECRL
# (« niveau_cecrl », lu dans la couleur du texte : bleu pour le A1) sont ajoutés. Méthode et corrections :
# docs/Generateur-Procedural/lot-3-anglais.md §11.1.
"""
COLONNES = {"attendus": "a", "objectifs": "o"}
NOM = "Programme de langues vivantes étrangères et régionales pour le cycle 2 (annexe 1)"


class Ligne(yaml.SafeDumper):
    pass


assert set(QCM) <= {(b["classe"], THEMES[b["competence"]]) for b in brouillon}, "un thème du classement inconnu"
for classe in ("CP", "CE1", "CE2"):
    segment, themes = classe.lower(), []
    for bloc in (b for b in brouillon if b["classe"] == classe):
        cle = THEMES[bloc["competence"]]
        ident = f"anglais.{segment}.{cle}"
        qcm = QCM.get((classe, cle), set())
        attendus = []
        for colonne, lettre in COLONNES.items():
            for rang, puce in enumerate(bloc[colonne], 1):
                attendus.append({"id": f"{ident}.{len(attendus) + 1:02d}", "libelle": puce["libelle"],
                                 "qcm": f"{lettre}{rang}" in qcm, "colonne": colonne,
                                 "niveau_cecrl": puce["niveau"]})
        inconnus = qcm - {f"{l}{r}" for c, l in COLONNES.items() for r in range(1, len(bloc[c]) + 1)}
        assert not inconnus, (classe, cle, inconnus)
        themes.append({"id": ident, "domaine": bloc["activite"], "theme": bloc["competence"], "code": bloc["code"],
                       "attendus": attendus})
    assert len({t["id"] for t in themes}) == len(themes), f"deux thèmes du même identifiant au {classe}"
    doc = {"matiere": "anglais", "niveau": classe, "cycle": 2,
           "source": SOURCE | {"en_vigueur": EN_VIGUEUR[classe], "extrait": f"{NOM}, {EXTRAIT[classe]}",
                               "releve": "2026-11-25"},
           "themes": themes}
    texte = ENTETE.format(classe=classe) + yaml.dump(doc, Dumper=Ligne, allow_unicode=True, sort_keys=False, width=120)
    (sortie / f"anglais-{segment}.yaml").write_text(texte, encoding="utf-8")
    tous = [a for t in themes for a in t["attendus"]]
    print(f"anglais-{segment}.yaml : {len(themes)} thèmes, {len(tous)} attendus "
          f"({sum(a['colonne'] == 'attendus' for a in tous)} de fin d’année, "
          f"{sum(a['colonne'] == 'objectifs' for a in tous)} objectifs), dont {sum(a['qcm'] for a in tous)} QCM ; "
          f"niveaux : {', '.join(f'{n} {sum(a['niveau_cecrl'] == n for a in tous)}' for n in ('pré-A1', 'A1', 'pré-A1 et A1'))}")
