"""Le référentiel du français du cycle 2 (lot 0, étape 0.4) : du brouillon (extraire_objectifs_c2.py) aux fichiers
`generateur/programmes/francais-cp.yaml`, `-ce1.yaml`, `-ce2.yaml`, au format d'E2. Les libellés sont ceux du
brouillon, mot pour mot ; seuls les identifiants des thèmes et le champ « qcm » (un classement du projet, pas du
programme) sont ajoutés ici.

Usage : python -I construire_referentiel_c2.py <brouillon.json> <dossier generateur/programmes>"""
import json
import sys
from pathlib import Path

import yaml

brouillon, sortie = json.load(open(sys.argv[1], encoding="utf-8")), Path(sys.argv[2])

# les identifiants des thèmes, repris de ceux de 6e et 5e quand le thème est le même (relations-mots, reemployer…)
THEMES = {
    "Identifier les mots de manière de plus en plus aisée": "identifier-mots",
    "Lire à voix haute": "lire-voix-haute",
    "Comprendre un texte": "comprendre-textes",
    "Devenir lecteur": "devenir-lecteur",
    "Apprendre à écrire en écriture cursive": "ecrire-cursive",
    "Encoder puis écrire sous dictée": "encoder-dictee",
    "Copier et acquérir des stratégies de copie": "copier",
    "Produire des écrits": "produire-ecrits",
    "Écouter pour comprendre": "ecouter",
    "Dire pour être compris": "dire",
    "Participer à des échanges": "echanges",
    "Enrichir son vocabulaire dans tous les enseignements": "vocabulaire",
    "Enrichir son vocabulaire dans toutes les disciplines": "vocabulaire",
    "Établir des relations entre les mots": "relations-mots",
    "Réemployer le vocabulaire étudié": "reemployer",
    "Mémoriser l’orthographe lexicale": "orthographe-lexicale",
    "Mémoriser l’orthographe des mots": "orthographe-lexicale",
    "Se repérer dans la phrase simple": "phrase-simple",
    "Découvrir, comprendre et mettre en œuvre l’orthographe grammaticale": "orthographe-grammaticale",
}

# le champ « qcm », la règle d'E2 : en français, seuls le vocabulaire et la grammaire se travaillent par QCM ; jamais
# la lecture, l'écriture, l'oral, ni ce qui demande une production ou un geste (consulter un dictionnaire, se
# constituer un répertoire, réemployer à l'oral ou à l'écrit). Les attendus de vocabulaire qui n'en relèvent pas, par
# classe et par thème, rang dans le thème :
PAS_QCM = {
    ("CP", "reemployer"): {1, 2},            # réemployer et mémoriser (production)
    ("CE1", "vocabulaire"): {2, 4},          # automatiser des formulations ; consulter un dictionnaire
    ("CE1", "reemployer"): {1, 2},           # mobiliser, utiliser pour s'exprimer (production)
    ("CE2", "vocabulaire"): {2, 5},          # automatiser des formulations ; consulter un dictionnaire
    ("CE2", "relations-mots"): {4},          # se constituer un répertoire lexical personnel
    ("CE2", "reemployer"): {4},              # la fluence verbale (oral)
}
QCM_POSSIBLE = ("Vocabulaire", "Grammaire et orthographe")

SOURCE = {
    "texte": "Programme de français du cycle 2 (annexe 3 de l’arrêté)",
    "arrete": "Arrêté du 22 octobre 2024 (JO du 25 octobre 2024)",
    "nor": "MENE2415135A",
    "bo": "BO n° 41 du 31 octobre 2024",
    "url": "https://www.education.gouv.fr/bo/2024/Hebdo41/MENE2415135A",
    "en_vigueur": "en CP, CE1 et CE2 depuis la rentrée 2025-2026 (article 3 de l’arrêté)",
}
EXTRAIT = {"CP": "« Cours préparatoire »", "CE1": "« Cours élémentaire première année »",
           "CE2": "« Cours élémentaire deuxième année »"}
ENTETE = """# Référentiel des attendus — francais, {classe} (générateur procédural du cycle 2, lot 0, étape 0.4). Libellés recopiés
# MOT POUR MOT des « Objectifs d’apprentissage » du programme officiel (source ci-dessous ; le PDF de l’annexe :
# https://www.education.gouv.fr/sites/default/files/ensel135_annexe3.pdf) ; seuls les identifiants et le champ « qcm »
# (se prête ou non à un QCM : classement du projet, pas du programme) sont ajoutés. Les repères de période du
# programme (« Dès le début de l’année »…) ne sont pas repris, comme en E2. Méthode et corrections :
# docs/Generateur-Procedural/cycle-2-cp-ce1-ce2.md §11.4.
"""


class Ligne(yaml.SafeDumper):
    pass


for classe in ("CP", "CE1", "CE2"):
    segment = classe.lower()
    themes = []
    for bloc in (b for b in brouillon if b["classe"] == classe):
        cle = THEMES[bloc["theme"]]
        ident = f"francais.{segment}.{cle}"
        attendus = []
        for rang, objectif in enumerate(bloc["objectifs"], 1):
            qcm = bloc["domaine"] in QCM_POSSIBLE and rang not in PAS_QCM.get((classe, cle), set())
            attendus.append({"id": f"{ident}.{rang:02d}", "libelle": objectif["libelle"], "qcm": qcm})
        themes.append({"id": ident, "domaine": bloc["domaine"], "theme": bloc["theme"], "attendus": attendus})
    doc = {"matiere": "francais", "niveau": classe, "cycle": 2,
           "source": SOURCE | {"extrait": f"Programme de français du cycle 2 (annexe 3), {EXTRAIT[classe]}",
                               "releve": "2026-11-10"},
           "themes": themes}
    texte = ENTETE.format(classe=classe) + yaml.dump(doc, Dumper=Ligne, allow_unicode=True, sort_keys=False, width=120)
    (sortie / f"francais-{segment}.yaml").write_text(texte, encoding="utf-8")
    n = sum(len(t["attendus"]) for t in themes)
    print(f"francais-{segment}.yaml : {len(themes)} thèmes, {n} attendus, dont {sum(a['qcm'] for t in themes for a in t['attendus'])} QCM")
