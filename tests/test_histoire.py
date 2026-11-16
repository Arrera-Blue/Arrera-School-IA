"""Lot 2, étape 2.1 : le générateur du temps et de l'histoire, du CP au CE2 (generateur/procedural/histoire_geo/ ;
docs/Generateur-Procedural/lot-2-questionner-le-monde.md §4) — les tables, chaque genre juste par construction (la
réponse recalculée par un autre chemin), aucun fait discuté, l'aiguillage, un exercice de bout en bout."""

import random
import re
import shutil

import pytest

from generateur import procedural
from generateur.moteur import config, generation, registre
from generateur.moteur.validation.n2_schema import valider
from generateur.procedural import tables
from generateur.procedural.histoire_geo import histoire as h

TIRAGES = 300


def table(nom):
    return tables.charger("histoire-geo", nom).lignes


def nombre_de_mots(texte: str) -> int:
    return len([t for t in texte.split() if re.search(r"\w", t)])


def ordre(suite):
    return [l["nom"] for l in sorted((l for l in table("calendrier") if l["suite"] == suite), key=lambda l: l["rang"])]


@pytest.fixture
def relues(tmp_path, monkeypatch):
    copie = tmp_path / "donnees"
    shutil.copytree(tables.DOSSIER, copie)
    monkeypatch.setattr(tables, "DOSSIER", copie)
    for matiere, nom in tables.lister():
        tables.relire(matiere, nom, "Essai")
    return copie


@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    vrai_chemin = config.chemin
    monkeypatch.setattr(config, "chemin", lambda nom: vrai_chemin(nom) if nom == "types" else tmp_path / nom)
    return tmp_path


# --- les tables -------------------------------------------------------------------------------------

def test_les_tables_sont_coherentes():
    assert ordre("jour") == ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    assert len(ordre("mois")) == 12 and ordre("mois")[0] == "janvier" and ordre("mois")[-1] == "décembre"
    assert ordre("saison") == ["printemps", "été", "automne", "hiver"]
    durees = {l["unite"]: l["nombre"] for l in table("durees")}
    assert durees == {"année": 12, "semaine": 7, "journée": 24, "décennie": 10, "siècle": 100, "millénaire": 1000}
    periodes = sorted(table("periodes"), key=lambda l: l["rang"])
    assert [p["rang"] for p in periodes] == [1, 2, 3, 4, 5]
    for avant, apres in zip(periodes, periodes[1:]):  # les périodes se suivent sans trou
        assert avant["fin_annee"] == apres["debut_annee"] and avant["debut_annee"] < avant["fin_annee"]
    # le texte des limites dit la même chose que les nombres
    for p in periodes:
        for texte, annee in ((p["debut"], p["debut_annee"]), (p["fin"], p["fin_annee"])):
            if texte[0].isdigit():
                assert texte == (f"{-annee} av. J.-C." if annee < 0 else str(annee))
    for r in table("reperes"):
        assert r["marge"] >= 0 and ("av. J.-C." in r["date"]) == (r["annee"] < 0)
    pre = table("prehistoire")
    assert {l["periode"] for l in pre if l["sorte"] == "nouveaute"} == {"Néolithique"}
    assert {l["periode"] for l in pre if l["sorte"] == "activite"} == {"Paléolithique"}
    # écartés parce que discutés (des poteries et des villages plus anciens que le Néolithique)
    assert not {"la poterie", "les premiers villages"} & {l["texte"] for l in pre}


# --- chaque genre, juste par construction -------------------------------------------------------------

DECALAGES = {"demain": 1, "après-demain": 2, "hier": -1, "avant-hier": -2}


def attendu_jour_ou_mois(enonce: str, noms: list[str]) -> str:
    """La réponse, recalculée depuis l'énoncé seul."""
    if m := re.search(r"juste (après|avant) (\w+) \?", enonce):
        i, pas = noms.index(m[2]), (1 if m[1] == "après" else -1)
    elif m := re.search(r"le (\w+) mois de l'année", enonce):
        return noms[h.ORDINAUX.index(m[1])]
    else:
        depart = re.search(r"(?:c'est|en) (\w+)\.", enonce)[1]
        i = noms.index(depart)
        if m := re.search(r"dans (\d) (?:jours|mois)", enonce):
            pas = int(m[1])
        elif m := re.search(r"il y a (\d) jours", enonce):
            pas = -int(m[1])
        else:
            pas = DECALAGES[re.search(r"(après-demain|avant-hier|demain|hier) \?", enonce)[1]]
    return noms[(i + pas) % len(noms)]


@pytest.mark.parametrize("genre, niveau", [(g, n) for g in h.GENRES for n in h.CLASSES_DU_GENRE[g.__name__]],
                         ids=lambda x: getattr(x, "__name__", x))
def test_chaque_genre_est_juste_par_construction(genre, niveau):
    jours, mois = ordre("jour"), ordre("mois")
    saisons = [h.le(s) for s in ordre("saison")]
    durees = {l["unite"]: l for l in table("durees")}
    periodes = sorted(table("periodes"), key=lambda l: l["rang"])
    reperes = {r["evenement"]: r for r in table("reperes")}
    pre = table("prehistoire")
    rng, vus = random.Random(2026), set()
    for _ in range(TIRAGES):
        s = procedural.tirer_une(genre, rng, set(), niveau)
        vus.add(s.cle)
        options = [s.reponse, *s.distracteurs]
        assert nombre_de_mots(s.enonce) <= 12, s.enonce
        assert len(set(options)) == len(options) >= 3, s
        # jamais un fait discuté
        assert not re.search(r"premier jour de la semaine|combien de saisons|combien de continents|plus long fleuve",
                             s.enonce, re.I)
        nom = s.cle[0]
        if nom == "jour":
            assert s.reponse == attendu_jour_ou_mois(s.enonce, jours) and set(options) <= set(jours)
            if niveau == "CP":
                assert not re.search(r"dans \d|il y a \d", s.enonce)
            if "juste" in s.enonce:  # « juste après mardi » ne propose pas mardi
                assert s.enonce.split()[-2] not in options
        elif nom == "mois":
            assert s.reponse == attendu_jour_ou_mois(s.enonce, mois) and set(options) <= set(mois)
            if niveau == "CP":
                assert "juste" in s.enonce
        elif nom == "saison":
            assert set(options) <= set(saisons)
            if m := re.search(r"juste (après|avant) (.+) \?", s.enonce):
                i = saisons.index(m[2])
                assert s.reponse == saisons[(i + (1 if m[1] == "après" else -1)) % 4] and m[2] not in options
            elif "ensuite" in s.enonce:
                derniere = s.enonce.split("…")[0].split(", ")[-1]
                assert s.reponse == saisons[(saisons.index(derniere) + 1) % 4]
            else:
                avant = re.search(r"Dans l'ordre : (.+?), …", s.enonce)[1]
                assert s.reponse == saisons[(saisons.index(avant) + 1) % 4]
        elif nom == "calendrier":
            unite = re.search(r"(?:dans|Dans) (?:un|une) (\w+)", s.enonce)[1]
            l = durees[unite]
            assert l["depuis"] == "CP"
            assert s.reponse == (str(l["nombre"]) if s.enonce.startswith("Combien") else l["contient"])
            if s.enonce.startswith("Combien"):  # aucune mauvaise réponse n'est le bon nombre d'une autre écriture
                assert all(d.isdigit() and int(d) != l["nombre"] for d in s.distracteurs)
        elif nom == "duree":
            if m := re.search(r"Combien de (\w+)s y a-t-il dans (?:un|une) (\w+) \?", s.enonce):
                petite = m[1].removeprefix("d'") if m[1] != "année" else m[1]
                assert s.reponse == str(durees[m[2]]["nombre"] // durees[petite]["nombre"])
            elif m := re.search(r"d'années y a-t-il dans (?:un|une) (\w+) \?", s.enonce):
                assert s.reponse == str(durees[m[1]]["nombre"])
            else:
                m = re.search(r"dans (\d) (\w+)s \?", s.enonce)
                assert s.reponse == str(int(m[1]) * durees[m[2]]["nombre"])
            assert all(d.isdigit() and d != s.reponse for d in s.distracteurs)
        elif nom == "periode":
            noms = [p["nom"] for p in periodes]
            if m := re.search(r"juste (après|avant) (.+) \?", s.enonce):
                assert s.reponse == noms[noms.index(m[2]) + (1 if m[1] == "après" else -1)]
            elif m := re.search(r"la plus (ancienne|récente)", s.enonce):
                rangs = sorted(noms.index(o) for o in options)
                assert s.reponse == noms[rangs[0] if m[1] == "ancienne" else rangs[-1]]
            elif m := re.search(r"En quelle année (commence(?:nt)?|se termine(?:nt)?) (.+) \?", s.enonce):
                p = periodes[noms.index(m[2])]
                assert s.reponse == (p["debut"] if m[1].startswith("commence") else p["fin"])
                assert "environ" not in s.reponse and "av. J.-C." not in s.reponse
            else:  # « En 1200, dans quelle période… » : recalculée, et loin de toute limite (50 ans au moins)
                ecrite = re.search(r"^En (.+?), dans quelle période", s.enonce)[1]
                annee = -int(ecrite.split()[0]) if "av. J.-C." in ecrite else int(ecrite.removeprefix("l'an "))
                dedans = [p for p in periodes if p["debut_annee"] < annee < p["fin_annee"]]
                assert [p["nom"] for p in dedans] == [s.reponse]
                assert min(abs(annee - x) for p in periodes for x in (p["debut_annee"], p["fin_annee"])) >= 50
            assert set(options) <= set(noms) or s.enonce.startswith("En quelle année")
        elif nom == "repere":
            if "correspond" in s.enonce:
                date = re.search(r"« (.+) »", s.enonce)[1]
                assert reperes[s.reponse]["date"] == date
            elif "va avec" in s.enonce:
                assert s.reponse == reperes[re.search(r"« (.+) »", s.enonce)[1]]["date"]
            else:
                choisis = [reperes[o] for o in options]
                for i, a in enumerate(choisis):  # jamais deux repères trop proches pour leur incertitude
                    for b in choisis[i + 1:]:
                        assert abs(a["annee"] - b["annee"]) > a["marge"] + b["marge"]
                annees = sorted(choisis, key=lambda r: r["annee"])
                assert s.reponse == (annees[0] if "ancien" in s.enonce else annees[-1])["evenement"]
        elif nom == "prehistoire":
            if "Paléolithique, les êtres humains" in s.enonce:
                assert s.reponse == "nomades"
            elif "Néolithique, beaucoup" in s.enonce:
                assert s.reponse == "sédentaires"
            elif "apparaît au Néolithique" in s.enonce:
                assert {l["texte"]: l["sorte"] for l in pre}[s.reponse] == "nouveaute"
                assert all({l["texte"]: l["sorte"] for l in pre}[d] == "activite" for d in s.distracteurs)
            elif "déjà au Paléolithique" in s.enonce:
                assert {l["texte"]: l["sorte"] for l in pre}[s.reponse] == "activite"
                assert all({l["texte"]: l["sorte"] for l in pre}[d] == "nouveaute" for d in s.distracteurs)
            else:
                texte = re.search(r"(?:apparaît|apparaissent) (.+) \?", s.enonce)[1]
                ligne = next(l for l in pre if l["texte"] == texte)
                assert ligne["apparait"] == "oui" and s.reponse == f"au {ligne['periode']}"
    assert len(vus) >= (6 if genre is h.calendrier else 8)  # le calendrier du CP : 3 unités, 2 questions chacune


def test_rien_ne_compare_otzi_et_l_ecriture():
    """Vers 3200 et vers 3000 av. J.-C. : trop proches pour leurs incertitudes (le carbone 14 dit 3350 à 3100)."""
    r = {x["evenement"]: x for x in table("reperes")}
    assert not h._comparables(r["Ötzi, l'homme des glaces"], r["l'apparition de l'écriture"])
    assert h._comparables(r["le siège d'Alésia, défaite de Vercingétorix"], r["le règne de l'empereur Auguste"])


def test_les_annees_demandees_sont_loin_des_limites():
    for p in table("periodes"):
        annees = h._annees(p)
        assert annees and 0 not in annees
        assert all(p["debut_annee"] + h._marge(p["debut"]) <= a <= p["fin_annee"] - h._marge(p["fin"]) for a in annees)
    antiquite = next(p for p in table("periodes") if p["rang"] == 2)
    assert min(h._annees(antiquite)) >= -2500  # « environ 3000 av. J.-C. » : 500 ans de marge


def test_les_ecritures_de_l_histoire():
    assert [h.annee_texte(a) for a in (-52, 100, 1200)] == ["52 av. J.-C.", "l'an 100", "1200"]
    assert [h.le(s) for s in ("printemps", "été", "hiver")] == ["le printemps", "l'été", "l'hiver"]
    assert h.de("heures") == "d'heures" and h.de("mois") == "de mois"
    assert h.accord("les Temps modernes", "va", "vont") == "vont" and h.accord("le Moyen Âge", "va", "vont") == "va"


# --- l'aiguillage, et un exercice de bout en bout ------------------------------------------------------

@pytest.mark.parametrize("demande, generateur", [
    ({"notion": "les jours de la semaine", "matiere": "histoire-geo", "niveau": "CP"}, "histoire"),
    ({"notion": "les saisons", "matiere": "histoire-geo", "niveau": "CP"}, "histoire"),
    ({"notion": "les siècles et les millénaires", "matiere": "histoire-geo", "niveau": "CE1"}, "histoire"),
    ({"notion": "les grandes périodes de l'histoire", "matiere": "histoire-geo", "niveau": "CE1"}, "histoire"),
    ({"notion": "la Préhistoire", "matiere": "histoire-geo", "niveau": "CE2"}, "histoire"),
    ({"attendu": "histoire-geo.cp.manifestations-temps.03", "matiere": "histoire-geo", "niveau": "CP"}, "histoire"),
    ({"attendu": "histoire-geo.ce1.grandes-periodes", "matiere": "histoire-geo", "niveau": "CE1"}, "histoire"),
    ({"attendu": "histoire-geo.ce2.prehistoire", "matiere": "histoire-geo", "niveau": "CE2"}, "histoire"),
    # ce que le générateur ne fait pas : au modèle
    ({"notion": "les continents et les océans", "matiere": "histoire-geo", "niveau": "CP"}, None),
    ({"notion": "la vie à Rome", "matiere": "histoire-geo", "niveau": "CE2"}, None),
    ({"notion": "les rois de France", "matiere": "histoire-geo", "niveau": "CE2"}, None),
    ({"notion": "lire l'heure", "matiere": "histoire-geo", "niveau": "CP"}, None),
    ({"attendu": "histoire-geo.ce2.rome-gaule.01", "matiere": "histoire-geo", "niveau": "CE2"}, None),
    # une notion précise absente de la classe : au modèle (les siècles ne sont pas au CP)
    ({"notion": "les siècles", "matiere": "histoire-geo", "niveau": "CP"}, None),
    # au collège, rien
    ({"notion": "le Moyen Âge", "matiere": "histoire-geo", "niveau": "5e"}, None),
])
def test_l_aiguillage(relues, demande, generateur):
    assert procedural.aiguiller(demande) == generateur


def test_jamais_propose_tant_que_ses_tables_ne_sont_pas_relues(relues):
    (relues / "relectures.yaml").write_text("{}\n", encoding="utf-8")
    assert procedural.aiguiller({"notion": "les saisons", "matiere": "histoire-geo", "niveau": "CP"}) is None


@pytest.mark.parametrize("notion, genres", [("les saisons", {"saison"}), ("les jours de la semaine", {"jour"}),
                                           ("le calendrier", {"jour", "mois", "calendrier"})])
def test_les_notions_precises(relues, notion, genres):
    choix = procedural.selection(h, {"notion": notion}, "CP")
    assert {g.__name__ for g in choix.genres} == genres


@pytest.mark.parametrize("niveau", ["CP", "CE1", "CE2"])
def test_un_exercice_genere_de_bout_en_bout(relues, dossiers, niveau):
    demande = {"type": "qcm", "matiere": "histoire-geo", "niveau": niveau, "notion": "le temps et l'histoire",
               "nb_questions": 12}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=11)
    valider(instance, registre.charger("qcm").schema, meta_autorise=True)
    meta = instance["meta"]
    assert (meta["origine"], meta["generateur"]) == ("procedural", "histoire") and meta["validation"]["n3"]
    assert set(meta["tables"]) == {f"histoire-geo/{n}" for n in h.TABLES}
    assert instance["matiere"] == "histoire-geo" and len(instance["questions"]) == 12
    assert {q["genre"].split(".")[1] for q in meta["questions"]} <= {
        g for g, classes in h.CLASSES_DU_GENRE.items() if niveau in classes}


@pytest.mark.parametrize("attendu, niveau", [("histoire-geo.cp.manifestations-temps.03", "CP"),
                                             ("histoire-geo.ce1.grandes-periodes", "CE1"),
                                             ("histoire-geo.ce2.prehistoire", "CE2")])
def test_un_objectif_seul_donne_assez_de_questions_differentes(relues, dossiers, attendu, niveau):
    """10 questions, toutes différentes, pour un seul objectif (les saisons : 16 questions possibles)."""
    demande = {"type": "qcm", "matiere": "histoire-geo", "niveau": niveau, "notion": "le temps et l'histoire",
               "nb_questions": 10, "attendu": attendu}
    instance = generation.generer(demande, "qcm", "maquette", mode="procedural", graine=4)
    assert len({q["enonce"] for q in instance["questions"]}) == 10
