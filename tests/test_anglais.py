"""Lot 3 du cycle 2, l'anglais (docs/Generateur-Procedural/lot-3-anglais.md), étape 3.0 : le programme de langues
vivantes de 2026 relevé mot pour mot (annexe 1 du BO n° 12 du 19 mars 2026), « anglais » au cycle 2 dans l'analyse, et
N2 à N4 sur des questions d'anglais (aucun contrôle du français ne refuse un mot anglais)."""

import pytest
import yaml

from generateur import programmes
from generateur.moteur import analyse, registre
from generateur.moteur.validation import fond, n3_pedagogie, n4_calcul
from generateur.moteur.validation.n2_schema import valider


def document(niveau: str) -> dict:
    return next(d for d in programmes.documents() if (d["matiere"], d["niveau"]) == ("anglais", niveau))


# --- le programme relevé ---------------------------------------------------------------------------

def test_le_programme_de_langues_vivantes_de_2026():
    for niveau, themes, attendus, qcm in (("CP", 13, 62, 16), ("CE1", 14, 87, 18), ("CE2", 17, 110, 28)):
        doc = document(niveau)
        assert doc["cycle"] == 2 and doc["source"]["nor"] == "MENE2602911A"
        assert doc["source"]["bo"] == "BO n° 12 du 19 mars 2026"
        assert ("depuis la rentrée 2026" if niveau == "CP" else "rentrée 2027-2028") in doc["source"]["en_vigueur"]
        assert len(doc["themes"]) == themes
        assert len(programmes.lister("anglais", niveau)) == attendus
        assert len(programmes.lister("anglais", niveau, qcm=True)) == qcm
    # la compréhension de l'écrit et l'expression écrite ne commencent qu'au CE2
    assert {t["code"].split("-")[0] for t in document("CP")["themes"]} == {"CO", "EOC", "EOI", "M"}
    assert {t["code"].split("-")[0] for t in document("CE2")["themes"]} == {"CO", "EOC", "EOI", "CE", "EE", "M"}
    t = programmes.theme("anglais.cp.mots-familiers")
    assert t["theme"] == "Comprendre quelques mots familiers et expressions très courantes"
    assert t["domaine"] == "Compréhension de l’oral : écouter et comprendre"
    # le titre du CE2 diffère, l'identifiant non
    assert programmes.theme("anglais.ce2.se-decrire")["theme"].startswith("Décrire ou se décrire")


def test_les_attendus_de_fin_d_annee_puis_les_objectifs():
    doc = document("CE1")
    t = next(t for t in doc["themes"] if t["id"] == "anglais.ce1.suivre-histoire")
    assert t["code"] == "CO-CE1"
    assert [a["colonne"] for a in t["attendus"]] == ["attendus"] * 3 + ["objectifs"] * 4
    assert programmes.attendu("anglais.ce1.suivre-histoire.04").libelle == \
        "Reconnaitre certaines lettres de l’alphabet et les nombres (A1) jusqu’à 31 environ."


def test_le_niveau_du_cecrl_lu_dans_la_couleur():
    """Le CP est tout en pré-A1 ; « (A1) » ouvre un passage bleu, le retour au noir n'est pas toujours marqué."""
    assert {a["niveau_cecrl"] for t in document("CP")["themes"] for a in t["attendus"]} == {"pré-A1"}
    niveaux = {a["id"]: a["niveau_cecrl"] for n in ("CE1", "CE2") for t in document(n)["themes"] for a in t["attendus"]}
    assert niveaux["anglais.ce1.suivre-histoire.04"] == "pré-A1 et A1"      # « … et les nombres (A1) jusqu’à 31 »
    assert niveaux["anglais.ce1.comprendre-agir.04"] == "A1"                # « (A1) Identifier les modaux… »
    assert niveaux["anglais.ce1.suivre-histoire.05"] == "pré-A1"
    assert set(niveaux.values()) == {"pré-A1", "A1", "pré-A1 et A1"}


def test_la_mise_en_page_mise_a_part_le_texte_garde():
    # une sous-liste reste dans son libellé, sans sa puce (U+F09F de la police Symbol, « • »)
    a = programmes.attendu("anglais.cp.raconter.02").libelle
    assert a.startswith("Nommer, caractériser, dénombrer très simplement des personnes, des objets, des lieux : "
                        "mobiliser quelques mots connus") and "\uf09f" not in a
    assert "•" not in programmes.attendu("anglais.ce1.emotions-souhaits.01").libelle
    # une case coupée par un changement de page : entière
    assert programmes.attendu("anglais.cp.reproduire-modele.03").libelle.endswith("ritualisées et mémorisées.")
    assert programmes.attendu("anglais.cp.clarifier.03").libelle.endswith("(prononciation des lettres d’un prénom, "
                                                                           "par exemple).")
    # les coquilles du texte officiel sont gardées
    assert "nommer les différents moments de la journée;" in programmes.attendu("anglais.ce2.se-decrire.05").libelle


def test_ce_qui_se_prete_a_un_qcm():
    # reconnaître des nombres, des jours, des dates ; des formules de politesse ; lire des nombres en lettres au CE2
    for ident in ("anglais.cp.mots-familiers.01", "anglais.ce1.suivre-histoire.04", "anglais.cp.conversation.01",
                  "anglais.ce2.mots-ecrits.05"):
        assert programmes.attendu(ident).qcm, ident
    # un geste, une action, l'intonation, la prononciation, une production, la médiation (décision 6) : non
    assert not any(a.qcm for a in programmes.lister("anglais") if a.theme_id.split(".")[2] in (
        "comprendre-agir", "reperes-phonologiques", "reproduire-modele", "raconter", "se-decrire",
        "emotions-souhaits", "clarifier", "epeler-recopier", "reperes-culturels", "expliciter", "animer-cooperer"))
    assert not programmes.attendu("anglais.ce1.mots-familiers.06").qcm  # les pronoms, « accompagnés de gestes »
    # les thèmes du formulaire : seulement ceux qui ont des QCM
    assert {t["id"].split(".")[2] for t in programmes.arbre("anglais", "CP")["themes"]} == {
        "mots-familiers", "suivre-histoire", "echanger-informations", "conversation"}


# --- l'analyse de la phrase de l'enseignant -----------------------------------------------------------

@pytest.mark.parametrize("phrase, matiere, niveau, notion", [
    ("les couleurs en anglais pour des CP", "anglais", "CP", "couleurs en anglais"),
    ("les jours de la semaine en anglais, CE2", "anglais", "CE2", "jours de la semaine en anglais"),
    # sans « anglais », les jours de la semaine restent à l'histoire (lot 2)
    ("les jours de la semaine au CP", "histoire-geo", "CP", "jours de la semaine"),
    # « en anglais » ne compte pas dans la limite de mots d'une notion devinée
    ("les nombres de 1 à 20 en anglais CE2", "anglais", "CE2", "nombres de 1 à 20 en anglais"),
    ("english numbers CE1", "anglais", "CE1", "english numbers"),
    # le collège ne change pas
    ("les verbes irréguliers anglais en 3e", "anglais", "3e", "verbes irréguliers anglais"),
])
def test_l_anglais_au_cycle_2(phrase, matiere, niveau, notion):
    requete = analyse.analyser(phrase).requete
    assert (requete["matiere"], requete["niveau"], requete["notion"]) == (matiere, niveau, notion)


@pytest.mark.parametrize("phrase, attendu", [
    ("les jours de la semaine en anglais, CE2", "anglais.ce2.mots-familiers.01"),
    ("saluer et remercier en anglais au CP", "anglais.cp.conversation.02"),
    ("reconnaitre les nombres jusqu'à 100 en anglais au CE2", "anglais.ce2.suivre-histoire.04"),
])
def test_l_objectif_d_anglais_est_propose(phrase, attendu):
    """« anglais » ne compte pas pour choisir l'objectif : aucun libellé ne le dit (le programme vaut pour toutes les
    langues)."""
    resultat = analyse.analyser(phrase)
    assert resultat.requete["attendu"] == attendu and resultat.sources["attendu"] == "devine"


def test_plusieurs_objectifs_a_choisir():
    resultat = analyse.analyser("les nombres en anglais au CE1")
    assert resultat.requete.get("attendu") is None
    assert any("attendus du programme correspondent à la notion" in r for r in resultat.remarques)


# --- N2 à N4 sur des questions d'anglais ------------------------------------------------------------

def q(enonce: str, propositions: list[str], explication: str) -> dict:
    return {"enonce": enonce, "propositions": propositions, "index_correct": 0, "explication": explication}


# les formes de questions prévues par la conception (§4 à §6), la bonne réponse en premier
QUESTIONS = [
    q("Que veut dire « Monday » ?", ["lundi", "mardi", "mercredi", "jeudi"],
      "« Monday » veut dire lundi. En anglais, les jours prennent une majuscule."),
    q("Comment dit-on « rouge » en anglais ?", ["red", "blue", "green", "yellow"], "« Rouge » se dit « red »."),
    q("Quel nombre s'écrit « fourteen » ?", ["14", "40", "41", "15"],
      "fourteen : 14 ; forty : 40. -teen : de 13 à 19 ; -ty : les dizaines."),
    q("Comment écrit-on 40 en anglais ?", ["forty", "fourteen", "fifty", "four"],
      "40 se dit « forty » ; « fourteen », c'est 14."),
    q("On te demande « How old are you? ». Que réponds-tu ?",
      ["I'm seven.", "I'm fine, thank you.", "My name is Tom.", "It's sunny."],
      "« How old are you? » demande ton âge : « I'm seven. »"),
    q("Que veut dire « the third of December » ?", ["le 3 décembre", "le 13 décembre", "le 3 novembre", "le 30 décembre"],
      "« third » : troisième, le 3 ; « December » : décembre."),
    q("Que veut dire « It's eight o'clock » ?", ["Il est 8 heures.", "Il est 9 heures.", "Il est 7 heures.",
                                                  "Il est 8 heures et demie."],
      "« eight » : 8 ; « o'clock » : l'heure pile."),
    q("Que dit-on pour remercier ?", ["Thank you!", "Hello!", "Goodbye!", "Please!"],
      "On remercie en disant « Thank you! »."),
    q("Comment dit-on « chien » en anglais ?", ["dog", "cat", "rabbit", "horse"], "« Chien » se dit « dog »."),
]


@pytest.mark.parametrize("niveau", ["CP", "CE1", "CE2"])
def test_n2_a_n4_acceptent_l_anglais(niveau):
    instance = {"type": "qcm", "titre": "Les mots familiers en anglais", "matiere": "anglais", "niveau": niveau,
                "notion": "les mots familiers en anglais", "questions": QUESTIONS}
    valider(instance, registre.charger("qcm").schema)
    assert [c.message for c in n3_pedagogie.verifier(instance) if c.bloquant] == []
    avertissements, bilan = fond.valider_le_fond(instance)
    # rien n'est recalculé en anglais : tout est « à relire », jamais « faux » (N4 du français ne s'y applique pas)
    assert bilan["n4_questions"] == [n4_calcul.A_RELIRE] * len(QUESTIONS)
    assert not any("forme verbale" in a for a in avertissements)


def test_le_programme_a_les_libelles_du_fichier():
    """Le référentiel lu par l'application est celui des fichiers, sans perte (les marques de niveau comprises)."""
    brut = yaml.safe_load(open(programmes.DOSSIER / "anglais-ce2.yaml", encoding="utf-8"))
    for t in brut["themes"]:
        for a in t["attendus"]:
            assert programmes.attendu(a["id"]).libelle == a["libelle"]
