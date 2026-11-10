"""Générateur procédural du cycle 2, lot 0, étape 0.3 : les tables de référence (generateur/procedural/tables.py) —
format, monde fermé, sources, relecture, et la règle : un générateur dont une table n'est pas relue n'est jamais
proposé (docs/Generateur-Procedural/cycle-2-cp-ce1-ce2.md §2, §11.3)."""

import copy
import random
from datetime import date
from types import SimpleNamespace

import pytest
import yaml

from generateur import procedural
from generateur.procedural import tables

TABLE = {
    "description": "Quelques formes conjuguées, pour les tests.",
    "sources": {"wikt": {"nom": "Wiktionnaire", "url": "https://fr.wiktionary.org/", "consulte": "2026-11-10",
                         "licence": "CC BY-SA 4.0"}},
    "proprietes": {"infinitif": "texte", "groupe": [1, 2, 3], "temps": ["present", "futur"],
                   "personne": ["je", "tu", "il", "nous", "vous", "ils"], "forme": "texte", "syllabes": "nombre"},
    "cle": ["infinitif", "temps", "personne"],
    "lignes": [
        {"infinitif": "chanter", "groupe": 1, "temps": "present", "personne": "ils", "forme": "chantent",
         "syllabes": 2, "source": "wikt"},
        {"infinitif": "chanter", "groupe": 1, "temps": "present", "personne": "nous", "forme": "chantons",
         "syllabes": 2, "source": "wikt", "note": "-ons avec nous"},
        {"infinitif": "finir", "groupe": 2, "temps": "futur", "personne": "ils", "forme": "finiront",
         "syllabes": 3, "source": "wikt"},
    ],
}


def ecrire(dossier, donnees, matiere="francais", nom="conjugaisons"):
    (dossier / matiere).mkdir(parents=True, exist_ok=True)
    (dossier / matiere / f"{nom}.yaml").write_text(yaml.safe_dump(donnees, allow_unicode=True, sort_keys=False),
                                                   encoding="utf-8")


@pytest.fixture
def dossier(tmp_path, monkeypatch):
    monkeypatch.setattr(tables, "DOSSIER", tmp_path)
    ecrire(tmp_path, TABLE)
    return tmp_path


def test_une_table_se_lit_et_se_consulte(dossier):
    t = tables.charger("francais", "conjugaisons")
    assert (t.ident, len(t.lignes), t.cle, t.relue, t.relecture) == ("francais/conjugaisons", 3,
                                                                       ("infinitif", "temps", "personne"), False, None)
    assert [l["forme"] for l in t.filtrer(temps="present")] == ["chantent", "chantons"]
    assert t.valeurs("infinitif") == ["chanter", "finir"] and t.valeurs("forme", personne="ils", groupe=2) == ["finiront"]
    assert t.une(random.Random(0), infinitif="finir")["forme"] == "finiront"
    with pytest.raises(KeyError):
        t.filtrer(mode="indicatif")
    with pytest.raises(LookupError):
        t.une(random.Random(0), temps="futur", personne="je")
    assert tables.lister() == [("francais", "conjugaisons")]


def modifie(chemin_cle: str, valeur):
    """La table de référence, avec une valeur changée (`lignes.0.forme`) ; None supprime la clé."""
    donnees = copy.deepcopy(TABLE)
    *chemin, dernier = chemin_cle.split(".")
    cible = donnees
    for morceau in chemin:
        cible = cible[int(morceau)] if morceau.isdigit() else cible[morceau]
    if valeur is None:
        del cible[int(dernier) if dernier.isdigit() else dernier]
    else:
        cible[int(dernier) if dernier.isdigit() else dernier] = valeur
    return donnees


@pytest.mark.parametrize("donnees, defaut", [
    (modifie("description", ""), "description absente"),
    (modifie("sources.wikt.url", None), "source wikt : url manquant"),
    (modifie("lignes.0.forme", None), "ligne 1 : forme vide (monde fermé"),             # le monde fermé
    (modifie("lignes.0.forme", "  "), "ligne 1 : forme vide"),
    (modifie("lignes.1.temps", "passe_simple"), "ligne 2 : temps = 'passe_simple', hors des valeurs permises"),
    (modifie("lignes.2.syllabes", "trois"), "ligne 3 : syllabes n'est pas un nombre entier"),
    (modifie("lignes.0.mode", "indicatif"), "ligne 1 : colonne inconnue 'mode'"),
    (modifie("lignes.0.source", "manuel"), "ligne 1 : source 'manuel' inconnue"),
    (modifie("lignes.1.personne", "ils"), "ligne 2 : même clé que la ligne 1"),
    (modifie("cle", ["infinitif", "mode"]), "clé absente, ou qui cite une propriété inconnue"),
    (modifie("lignes", []), "aucune ligne"),
    (modifie("proprietes.temps", ["present", "present"]), "propriété temps"),
    (modifie("proprietes.source", "texte"), "propriété 'source' : nom réservé"),
])
def test_les_defauts_d_une_table(dossier, donnees, defaut):
    assert any(defaut in d for d in tables.defauts(donnees)), tables.defauts(donnees)
    ecrire(dossier, donnees)
    with pytest.raises(tables.TableInvalide, match="francais/conjugaisons"):
        tables.charger("francais", "conjugaisons")


def test_la_table_de_reference_n_a_aucun_defaut():
    assert tables.defauts(TABLE) == []


@pytest.mark.parametrize("matiere, nom", [("..", "conjugaisons"), ("francais", "../../config"), ("Francais", "x"),
                                          ("francais", "absente")])
def test_une_table_mal_nommee_ou_absente(dossier, matiere, nom):
    with pytest.raises(tables.TableInconnue):
        tables.charger(matiere, nom)


def test_la_relecture_et_une_table_modifiee_ensuite(dossier):
    note = tables.relire("francais", "conjugaisons", "  Lois  ", le=date(2026, 11, 12))
    assert note["par"] == "Lois" and note["le"] == "2026-11-12"
    t = tables.charger("francais", "conjugaisons")
    assert t.relue and t.relecture["par"] == "Lois" and tables.relues("francais", ["conjugaisons"])
    assert (dossier / "relectures.yaml").read_text(encoding="utf-8").startswith("# Les relectures")
    # une table modifiée après sa relecture n'est plus relue
    ecrire(dossier, modifie("lignes.0.forme", "chante"))
    assert not tables.charger("francais", "conjugaisons").relue
    assert not tables.relues("francais", ["conjugaisons"])
    # revenue à l'identique (même empreinte) : de nouveau relue ; une note compte aussi, elle fait partie de la ligne
    ecrire(dossier, TABLE)
    assert tables.charger("francais", "conjugaisons").relue
    ecrire(dossier, modifie("lignes.0.note", "une remarque"))
    assert not tables.charger("francais", "conjugaisons").relue


def test_on_ne_relit_ni_une_table_fautive_ni_sans_dire_qui(dossier):
    with pytest.raises(ValueError):
        tables.relire("francais", "conjugaisons", "  ")
    ecrire(dossier, modifie("lignes.0.forme", None))
    with pytest.raises(tables.TableInvalide):
        tables.relire("francais", "conjugaisons", "Lois")
    assert not (dossier / "relectures.yaml").exists()
    assert not tables.relues("francais", ["conjugaisons"]) and not tables.relues("francais", ["absente"])
    assert tables.relues("francais", [])  # un générateur sans table : rien à relire


def test_la_commande(dossier, capsys):
    assert tables.main([]) == 0
    assert "· francais/conjugaisons : 3 lignes, pas encore relue" in capsys.readouterr().out
    assert tables.main(["relire", "francais/conjugaisons", "--par", "Lois"]) == 0
    assert "relue par Lois" in capsys.readouterr().out
    assert tables.main([]) == 0 and "✓ francais/conjugaisons : 3 lignes, relue par Lois" in capsys.readouterr().out
    ecrire(dossier, modifie("lignes.0.forme", "chante"))
    assert tables.main([]) == 0 and "modifiée depuis sa relecture : à relire" in capsys.readouterr().out
    ecrire(dossier, modifie("lignes.0.forme", None), nom="fautive")
    assert tables.main([]) == 1 and "✗ francais/fautive" in capsys.readouterr().out
    assert tables.main(["relire", "francais/fautive", "--par", "Lois"]) == 1


def test_un_generateur_dont_une_table_n_est_pas_relue_n_est_jamais_propose(dossier, monkeypatch):
    def accord(rng):
        ligne = tables.charger("francais", "conjugaisons").une(rng, personne="ils")
        return procedural.Squelette(genre="conjugaison_essai.accord", enonce=f"Ils ({ligne['infinitif']}) : ils …",
                                    reponse=ligne["forme"], distracteurs=("x", "y", "z"), explication="-ent",
                                    cle=(ligne["infinitif"],))
    faux = SimpleNamespace(NOM="conjugaison_essai", TITRE="Conjugaison", NOTION="conjugaison", MATIERE="francais",
                           NIVEAU="CE1", NIVEAUX=("CE1",), MOTS_CLES=("conjugaison",), GENRES=(accord,), ATTENDUS={},
                           TABLES=("conjugaisons",))
    francais = SimpleNamespace(MATIERE="francais", AUTRES_NOTIONS=procedural.matieres()["maths"].AUTRES_NOTIONS,
                               generateurs=lambda: (faux,))
    vraies = procedural.matieres()
    monkeypatch.setattr(procedural, "matieres", lambda: {**vraies, "francais": francais})
    demande = {"notion": "la conjugaison", "matiere": "francais", "niveau": "CE1"}

    assert procedural.aiguiller(demande) is None                  # pas encore relue : jamais proposé
    tables.relire("francais", "conjugaisons", "Lois")
    assert procedural.aiguiller(demande) == "conjugaison_essai"   # relue : proposé
    assert procedural.tirer("conjugaison_essai", 1, random.Random(0))[0].reponse in ("chantent", "finiront")
    ecrire(dossier, modifie("lignes.0.forme", "chante"))
    assert procedural.aiguiller(demande) is None                  # modifiée depuis : plus proposé
    assert procedural.aiguiller({"notion": "les fractions", "niveau": "6e"}) == "fractions"  # les maths, sans table


def test_les_tables_du_depot_sont_saines():
    """Chaque table rangée dans generateur/procedural/donnees/ se charge sans défaut (aucune pour l'instant)."""
    for matiere, nom in tables.lister():
        tables.charger(matiere, nom)
