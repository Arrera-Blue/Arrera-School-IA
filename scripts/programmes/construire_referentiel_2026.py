"""Le référentiel des programmes de 2026 du cycle 2 (lot 2, étape 2.0) : des brouillons (extraire_objectifs_2026.py)
aux fichiers `generateur/programmes/sciences-et-technologie-cp.yaml`…, `histoire-geo-cp.yaml`…, au format d'E2. Les
libellés et les titres des thèmes sont ceux des brouillons, mot pour mot ; seuls les identifiants des thèmes, le champ
« qcm » (un classement du projet, pas du programme) et, en histoire-géographie, la colonne d'origine (`colonne`) sont
ajoutés ici.

Usage : python -I construire_referentiel_2026.py <sciences.json> <histoire-geo.json> <dossier generateur/programmes>"""
import json
import sys
from pathlib import Path

import yaml

sciences, histoire_geo = (json.load(open(c, encoding="utf-8")) for c in sys.argv[1:3])
sortie = Path(sys.argv[3])

THEMES = {
    # sciences et technologie
    "Masse, volumes et mesure de température": "masse-temperature",
    "Masse et volumes": "masse-volumes",
    "Masse, volumes et mesure du temps": "masse-volumes-temps",
    "États physiques de la matière": "etats-matiere",
    "L’électricité": "electricite",
    "Unité et diversité du vivant": "diversite-vivant",
    "Observer et décrire son environnement proche": "environnement-proche",
    "Agir pour protéger l’environnement": "proteger-environnement",
    "Nutrition des êtres vivants": "nutrition",
    "Sens et perception chez les animaux": "sens-perception",
    "Reproduction, croissance et développement": "reproduction-croissance",
    "Locomotion chez les animaux": "locomotion",
    "Alimentation": "alimentation",
    "Croissance et mouvement": "croissance-mouvement",
    "Santé et hygiène de vie": "sante-hygiene",
    "Les objets techniques au cœur de la société": "objets-techniques",
    # histoire-géographie
    "Les manifestations naturelles du temps": "manifestations-temps",
    "Les représentations humaines du temps": "representations-temps",
    "Situer des évènements dans le temps": "situer-evenements",
    "Du passé proche au passé lointain": "passe-proche-lointain",
    "Les grandes périodes de l’histoire": "grandes-periodes",
    "Les traces du passé": "traces-passe",
    "La vie des femmes et des hommes au Paléolithique et au Néolithique (environ 3 millions d'années à 3000 av. J.-C.)":
        "prehistoire",
    "Vivre à Rome et en Gaule romaine du Ier siècle avant J.-C. au IIe siècle après J.-C.": "rome-gaule",
    "La construction du royaume de France (Xe – XVe siècles)": "royaume-france",
    "Autour de l’école": "autour-ecole",
    "Des représentations du monde": "representations-monde",
    "La Terre est peuplée": "terre-peuplee",
    "Découvrir les lieux où vivent les êtres humains": "lieux-de-vie",
    "L’inégale répartition de la population en France": "repartition-population",
    "Se loger en France": "se-loger",
    "Travailler en France": "travailler",
}

# le champ « qcm », la règle d'E2 et du lot 1 : une connaissance qu'un QCM écrit vérifie ; jamais un geste (observer,
# mesurer, réaliser, utiliser), une production (décrire, expliquer à l'oral, faire un plan), une attitude (un rapport
# sensible à la nature, s'impliquer), l'hygiène et la santé (décision 5 du lot 2), ni ce qui demande une carte ou une
# image (localiser, reconnaître un paysage : décision 10 du 10/11). Ce qui se prête à un QCM, par classe et par thème :
# le rang des objectifs (« o ») et, en histoire-géographie, des attendus (« a ») ; les classements discutables sont
# listés dans docs/Generateur-Procedural/lot-2-questionner-le-monde.md §11.1.
QCM = {
    # sciences et technologie
    ("CP", "masse-temperature"): {"o2"},            # le vocabulaire des masses (lourd, léger)
    ("CP", "etats-matiere"): {"o1"},
    ("CE1", "etats-matiere"): {"o2", "o3", "o4"},   # nommer le changement d'état ; la masse, le volume
    ("CE1", "electricite"): {"o1", "o2"},           # le circuit ouvert ou fermé ; conducteur ou isolant
    ("CE2", "masse-volumes-temps"): {"o1"},         # convertir des unités de masse
    ("CE2", "etats-matiere"): {"o1"},
    ("CP", "diversite-vivant"): {"o1"},
    ("CE1", "nutrition"): {"o1", "o2", "o3"},       # l'eau et la lumière ; racine, tige, feuille ; le régime
    ("CE1", "sens-perception"): {"o1"},
    ("CE2", "diversite-vivant"): {"o1"},            # la classification
    ("CE2", "reproduction-croissance"): {"o1", "o3"},
    ("CE2", "locomotion"): {"o1", "o2"},
    ("CE2", "environnement-proche"): {"o2"},        # la chaine alimentaire
    ("CP", "alimentation"): {"o1"},
    ("CP", "croissance-mouvement"): {"o1"},         # les articulations, quelques os
    ("CE1", "alimentation"): {"o1"},                # les apports des aliments (pas l'équilibre alimentaire)
    ("CE1", "croissance-mouvement"): {"o3"},        # la dentition
    ("CE2", "croissance-mouvement"): {"o1", "o3"},  # muscles et articulations ; pouls et respiration
    ("CP", "objets-techniques"): {"o1", "o2"},
    ("CE1", "objets-techniques"): {"o1", "o2"},     # les parties d'un objet ; électrique ou non
    ("CE2", "objets-techniques"): {"o1"},           # saisir, traiter, restituer
    # histoire-géographie
    ("CP", "manifestations-temps"): {"a1", "a2"},   # le jour et la nuit ; les saisons
    ("CP", "representations-temps"): {"o1", "o3", "a1", "a2"},
    ("CP", "situer-evenements"): {"o1", "a1", "a2"},  # avant, après ; hier, demain ; les générations
    ("CE1", "passe-proche-lointain"): {"o1", "a1"},
    ("CE1", "grandes-periodes"): {"o1", "o2", "a2"},
    ("CE1", "traces-passe"): {"o1", "o3", "a1"},
    ("CE2", "prehistoire"): {"o1", "o2"},
    ("CE2", "rome-gaule"): {"o1", "o2", "o4", "a1"},
    ("CE2", "royaume-france"): {"o1", "o2", "a3", "a4"},
    ("CP", "representations-monde"): {"o1"},        # continents et océans
    ("CE1", "terre-peuplee"): {"o1", "o2", "a3"},   # foyers de peuplement, grandes villes ; ville et village
    ("CE1", "lieux-de-vie"): {"o1", "o2", "o3", "o4", "a1"},
    ("CE2", "repartition-population"): {"a3"},      # nommer les massifs et les fleuves (sans carte)
}

ARRETE_SCIENCES = {
    "texte": "Programme de sciences et technologie du cycle 2 (annexe 1 de l’arrêté)",
    "arrete": "Arrêté du 5 juin 2026 (JO du 9 juin 2026)",
    "nor": "MENE2611650A",
    "bo": "BO n° 24 du 11 juin 2026",
    "url": "https://www.education.gouv.fr/bo/2026/Hebdo24/MENE2611650A",
}
ARRETE_HG = {
    "texte": "Programme d’histoire-géographie pour le cycle 2 (annexe 3 de l’arrêté)",
    "arrete": "Arrêté du 22 avril 2026 (JO du 8 mai 2026)",
    "nor": "MENE2608631A",
    "bo": "BO n° 22 du 28 mai 2026",
    "url": "https://www.education.gouv.fr/bo/2026/Hebdo22/MENE2608631A",
}
EN_VIGUEUR = {
    "CP": "au CP depuis la rentrée 2026-2027 (article 3 de l’arrêté)",
    "CE1": "au CE1 à la rentrée 2027-2028 (article 3 de l’arrêté) ; en 2026-2027, le CE1 suit encore « Questionner le "
           "monde » (BO n° 31 du 30 juillet 2020)",
    "CE2": "au CE2 à la rentrée 2027-2028 (article 3 de l’arrêté) ; en 2026-2027, le CE2 suit encore « Questionner le "
           "monde » (BO n° 31 du 30 juillet 2020)",
}
EXTRAIT = {"CP": "« Cours préparatoire »", "CE1": "« Cours élémentaire première année »",
           "CE2": "« Cours élémentaire deuxième année »"}
COLONNES = {"Objectifs d’apprentissage": ("o", "objectifs"),
            "Attendus (connaissances et compétences)": ("a", "attendus")}
ENTETE = {
    "sciences-et-technologie": """# Référentiel des attendus — sciences-et-technologie, {classe} (générateur procédural du cycle 2, lot 2, étape 2.0).
# Libellés recopiés MOT POUR MOT de la colonne « Objectifs d’apprentissage » du programme officiel de 2026 (source
# ci-dessous ; le PDF du BO, pages 4 à 15 :
# https://www.education.gouv.fr/sites/default/files/document/bulletin-officiel-ndeg-24-du-11-juin-2026-519026.pdf) ;
# seuls les identifiants et le champ « qcm » (se prête ou non à un QCM : classement du projet, pas du programme) sont
# ajoutés. Méthode et corrections : docs/Generateur-Procedural/lot-2-questionner-le-monde.md §11.1.
""",
    "histoire-geo": """# Référentiel des attendus — histoire-geo, {classe} (générateur procédural du cycle 2, lot 2, étape 2.0). Libellés
# recopiés MOT POUR MOT des colonnes « Objectifs d’apprentissage » et « Attendus (connaissances et compétences) » du
# programme officiel de 2026 (source ci-dessous ; le PDF de l’annexe :
# https://www.education.gouv.fr/sites/default/files/document/annexe-3-programme-d-histoire-geographie-cycle-2-516776.pdf) ;
# seuls les identifiants, le champ « qcm » (se prête ou non à un QCM : classement du projet, pas du programme) et la
# colonne d’origine (« colonne ») sont ajoutés. Méthode et corrections :
# docs/Generateur-Procedural/lot-2-questionner-le-monde.md §11.1.
""",
}


class Ligne(yaml.SafeDumper):
    pass


def ecrire(matiere: str, brouillon: list[dict], arrete: dict, nom_texte: str) -> None:
    hg = matiere == "histoire-geo"
    for classe in ("CP", "CE1", "CE2"):
        segment, themes = classe.lower(), []
        for bloc in (b for b in brouillon if b["classe"] == classe):
            cle = THEMES[bloc["theme"]]
            ident = f"{matiere}.{segment}.{cle}"
            qcm = QCM.get((classe, cle), set())
            attendus = []
            for colonne, puces in bloc["colonnes"].items():
                lettre, nom = COLONNES[colonne]
                for rang, libelle in enumerate(puces, 1):
                    attendu = {"id": f"{ident}.{len(attendus) + 1:02d}", "libelle": libelle,
                               "qcm": f"{lettre}{rang}" in qcm}
                    if hg:
                        attendu["colonne"] = nom
                    attendus.append(attendu)
            inconnus = qcm - {f"{COLONNES[c][0]}{r}" for c, p in bloc["colonnes"].items() for r in range(1, len(p) + 1)}
            assert not inconnus, (classe, cle, inconnus)
            themes.append({"id": ident, "domaine": bloc["domaine"], "theme": bloc["theme"], "attendus": attendus})
        doc = {"matiere": matiere, "niveau": classe, "cycle": 2,
               "source": arrete | {"en_vigueur": EN_VIGUEUR[classe],
                                   "extrait": f"{nom_texte}, {EXTRAIT[classe]}", "releve": "2026-11-16"},
               "themes": themes}
        entete = ENTETE[matiere].format(classe=classe)
        texte = entete + yaml.dump(doc, Dumper=Ligne, allow_unicode=True, sort_keys=False, width=120)
        (sortie / f"{matiere}-{segment}.yaml").write_text(texte, encoding="utf-8")
        n = sum(len(t["attendus"]) for t in themes)
        print(f"{matiere}-{segment}.yaml : {len(themes)} thèmes, {n} attendus, dont "
              f"{sum(a['qcm'] for t in themes for a in t['attendus'])} QCM")


assert set(QCM) <= {(b["classe"], THEMES[b["theme"]]) for b in sciences + histoire_geo}, "un thème du classement inconnu"
ecrire("sciences-et-technologie", sciences, ARRETE_SCIENCES, "Programme de sciences et technologie du cycle 2 (annexe 1)")
ecrire("histoire-geo", histoire_geo, ARRETE_HG, "Programme d’histoire-géographie pour le cycle 2 (annexe 3)")
