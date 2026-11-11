"""Les tables de conjugaison du lot 1 (étape 1.1) : `francais/conjugaisons.yaml` et `francais/terminaisons.yaml`.

Écrites par Claude : être, avoir et les 8 verbes irréguliers du CE2 forme par forme ; les verbes en -er par la règle,
avec les particularités d'orthographe de manger (nous mangeons) et de commencer (nous commençons). Le contenu suit le
programme (lot-1-francais.md §1, §3) : CP, être et avoir au présent ; CE1, 4 temps, être, avoir et les verbes en -er ;
CE2, les 8 verbes irréguliers en plus. Au passé composé avec être (aller, venir, arriver), seulement il et ils :
« je suis allé » et « je suis allée » sont justes tous les deux.

Usage : python -I construire_conjugaisons.py <dossier generateur/procedural/donnees>
Puis : verifier_conjugaisons.py (chaque forme comparée à Verbiste, par verbecc)."""
import sys
from pathlib import Path

import yaml

PERSONNES = ("je", "tu", "il", "nous", "vous", "ils")
TEMPS = ("present", "imparfait", "futur", "passe_compose")
AVOIR_PRESENT = ("ai", "as", "a", "avons", "avez", "ont")
ETRE_PRESENT = ("suis", "es", "est", "sommes", "êtes", "sont")

IRREGULIERS = {  # infinitif : (groupe, depuis, {temps: formes}, participe passé, auxiliaire)
    "être": ("aux", None, {
        "present": ETRE_PRESENT,
        "imparfait": ("étais", "étais", "était", "étions", "étiez", "étaient"),
        "futur": ("serai", "seras", "sera", "serons", "serez", "seront")}, "été", "avoir"),
    "avoir": ("aux", None, {
        "present": AVOIR_PRESENT,
        "imparfait": ("avais", "avais", "avait", "avions", "aviez", "avaient"),
        "futur": ("aurai", "auras", "aura", "aurons", "aurez", "auront")}, "eu", "avoir"),
    "faire": ("3", "CE2", {
        "present": ("fais", "fais", "fait", "faisons", "faites", "font"),
        "imparfait": ("faisais", "faisais", "faisait", "faisions", "faisiez", "faisaient"),
        "futur": ("ferai", "feras", "fera", "ferons", "ferez", "feront")}, "fait", "avoir"),
    "aller": ("3", "CE2", {
        "present": ("vais", "vas", "va", "allons", "allez", "vont"),
        "imparfait": ("allais", "allais", "allait", "allions", "alliez", "allaient"),
        "futur": ("irai", "iras", "ira", "irons", "irez", "iront")}, "allé", "être"),
    "dire": ("3", "CE2", {
        "present": ("dis", "dis", "dit", "disons", "dites", "disent"),
        "imparfait": ("disais", "disais", "disait", "disions", "disiez", "disaient"),
        "futur": ("dirai", "diras", "dira", "dirons", "direz", "diront")}, "dit", "avoir"),
    "venir": ("3", "CE2", {
        "present": ("viens", "viens", "vient", "venons", "venez", "viennent"),
        "imparfait": ("venais", "venais", "venait", "venions", "veniez", "venaient"),
        "futur": ("viendrai", "viendras", "viendra", "viendrons", "viendrez", "viendront")}, "venu", "être"),
    "pouvoir": ("3", "CE2", {
        "present": ("peux", "peux", "peut", "pouvons", "pouvez", "peuvent"),
        "imparfait": ("pouvais", "pouvais", "pouvait", "pouvions", "pouviez", "pouvaient"),
        "futur": ("pourrai", "pourras", "pourra", "pourrons", "pourrez", "pourront")}, "pu", "avoir"),
    "voir": ("3", "CE2", {
        "present": ("vois", "vois", "voit", "voyons", "voyez", "voient"),
        "imparfait": ("voyais", "voyais", "voyait", "voyions", "voyiez", "voyaient"),
        "futur": ("verrai", "verras", "verra", "verrons", "verrez", "verront")}, "vu", "avoir"),
    "vouloir": ("3", "CE2", {
        "present": ("veux", "veux", "veut", "voulons", "voulez", "veulent"),
        "imparfait": ("voulais", "voulais", "voulait", "voulions", "vouliez", "voulaient"),
        "futur": ("voudrai", "voudras", "voudra", "voudrons", "voudrez", "voudront")}, "voulu", "avoir"),
    "prendre": ("3", "CE2", {
        "present": ("prends", "prends", "prend", "prenons", "prenez", "prennent"),
        "imparfait": ("prenais", "prenais", "prenait", "prenions", "preniez", "prenaient"),
        "futur": ("prendrai", "prendras", "prendra", "prendrons", "prendrez", "prendront")}, "pris", "avoir"),
}
PREMIER_GROUPE = ("chanter", "jouer", "parler", "aimer", "danser", "marcher", "regarder", "écouter", "donner",
                  "arriver", "manger", "commencer")
AUXILIAIRE_ETRE = {"arriver"}
TERMINAISONS = {"present": ("e", "es", "e", "ons", "ez", "ent"),
                "imparfait": ("ais", "ais", "ait", "ions", "iez", "aient"),
                "futur": ("erai", "eras", "era", "erons", "erez", "eront")}


def premier_groupe(infinitif: str) -> dict:
    radical = infinitif[:-2]
    formes = {}
    for temps, fins in TERMINAISONS.items():
        liste = []
        for fin in fins:
            r = radical
            # devant a ou o, le g garde le son « je » (mangeons) et le c le son « se » (commençons)
            if fin[0] in "ao" and r.endswith("g"):
                r += "e"
            if fin[0] in "ao" and r.endswith("c"):
                r = r[:-1] + "ç"
            liste.append(r + fin)
        formes[temps] = tuple(liste)
    return formes


def passe_compose(participe: str, auxiliaire: str) -> dict:
    if auxiliaire == "avoir":
        return {p: f"{a} {participe}" for p, a in zip(PERSONNES, AVOIR_PRESENT)}
    return {"il": f"est {participe}", "ils": f"sont {participe}s"}  # seulement il et ils (pas d'ambiguïté de genre)


def lignes() -> list[dict]:
    resultat = []

    def ajouter(infinitif, groupe, temps, formes_par_personne, depuis):
        for personne, forme in formes_par_personne.items():
            resultat.append({"infinitif": infinitif, "groupe": groupe, "temps": temps, "personne": personne,
                             "forme": forme, "depuis": depuis, "source": "verbiste"})

    for infinitif, (groupe, depuis, temps_formes, participe, aux) in IRREGULIERS.items():
        for temps, formes in temps_formes.items():
            # être et avoir : le présent dès le CP, le reste au CE1
            d = depuis or ("CP" if temps == "present" else "CE1")
            ajouter(infinitif, groupe, temps, dict(zip(PERSONNES, formes)), d)
        ajouter(infinitif, groupe, "passe_compose", passe_compose(participe, aux), depuis or "CE1")
    for infinitif in PREMIER_GROUPE:
        for temps, formes in premier_groupe(infinitif).items():
            ajouter(infinitif, "1", temps, dict(zip(PERSONNES, formes)), "CE1")
        ajouter(infinitif, "1", "passe_compose",
                passe_compose(infinitif[:-2] + "é", "être" if infinitif in AUXILIAIRE_ETRE else "avoir"), "CE1")
    return resultat


SOURCE = {"verbiste": {"nom": "Verbiste (par verbecc 2.1.0) : chaque forme comparée, identique",
                       "url": "https://github.com/bretttolbert/verbecc", "consulte": "2026-11-11",
                       "licence": "LGPL (données de Verbiste) ; seules des formes de la langue sont reprises"}}


def ecrire(dossier: Path) -> None:
    (dossier / "francais").mkdir(parents=True, exist_ok=True)
    conj = {
        "description": "Les formes conjuguées des verbes du programme du cycle 2, à l'indicatif (présent, imparfait, "
                       "futur, passé composé), sans le pronom. « depuis » : la première classe où la ligne sert (CP : "
                       "être et avoir au présent ; CE1 : 4 temps, être, avoir, verbes en -er ; CE2 : faire, aller, "
                       "dire, venir, pouvoir, voir, vouloir, prendre). Au passé composé avec être, seulement il et ils.",
        "sources": SOURCE,
        "proprietes": {"infinitif": "texte", "groupe": ["aux", "1", "3"], "temps": list(TEMPS),
                       "personne": list(PERSONNES), "forme": "texte", "depuis": ["CP", "CE1", "CE2"]},
        "cle": ["infinitif", "temps", "personne"],
        "lignes": lignes(),
    }
    term = {
        "description": "Les terminaisons des verbes en -er (ce par quoi la forme se termine), pour les explications "
                       "et les questions de terminaison. Le passé composé n'en a pas : l'auxiliaire et le participe "
                       "passé en -é.",
        "sources": SOURCE,
        "proprietes": {"temps": ["present", "imparfait", "futur"], "personne": list(PERSONNES), "terminaison": "texte"},
        "cle": ["temps", "personne"],
        "lignes": [{"temps": t, "personne": p, "terminaison": f"-{fin}", "source": "verbiste"}
                   for t, fins in TERMINAISONS.items() for p, fin in zip(PERSONNES, fins)],
    }
    entete = ("# Table de référence (générateur procédural du français, lot 1, étape 1.1), écrite par Claude avec\n"
              "# scripts/conjugaison/construire_conjugaisons.py, chaque forme comparée à Verbiste.\n"
              "# À relire par l'utilisateur : python -m generateur.procedural.tables relire francais/{nom} --par \"…\"\n")
    for nom, donnees in (("conjugaisons", conj), ("terminaisons", term)):
        texte = entete.format(nom=nom) + yaml.safe_dump(donnees, allow_unicode=True, sort_keys=False, width=120)
        (dossier / "francais" / f"{nom}.yaml").write_text(texte, encoding="utf-8")
        print(f"francais/{nom}.yaml : {len(donnees['lignes'])} lignes")


if __name__ == "__main__":
    ecrire(Path(sys.argv[1]))
