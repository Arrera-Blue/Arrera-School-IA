"""Brouillon du référentiel du programme de langues vivantes du cycle 2 (lot 3, étape 3.0) : l'annexe 1 du BO n° 12 du
19 mars 2026 (« Programme de langues vivantes étrangères et régionales pour le cycle 2 », pages 14 à 47 du PDF du BO).
Les attendus de fin d'année et la colonne « Objectifs d'apprentissage », mot pour mot, avec leur activité langagière,
leur classe et leur compétence (« Comprendre quelques mots familiers et expressions très courantes (CO-CP) »).

Le format : six activités langagières (compréhension de l'oral, CO ; expression orale en continu, EOC ; en
interaction, EOI ; compréhension de l'écrit, CE ; expression écrite, EE ; médiation, M), chacune classe par classe ;
dans chaque classe, des compétences dont le titre finit par leur code (« (CO-CP) ») ; sous chacune, « Attendus de fin
d'année : » (des puces « − », sur toute la largeur), puis un tableau à deux colonnes « Objectifs d'apprentissage |
Exemples de réussite », chaque case faite de puces « - ». Comme pour les programmes de 2026 du lot 2
(extraire_objectifs_2026.py), le texte brut de pypdf mêle les colonnes sur une même ligne, et son mode « mise en page »
rend des pages vides : chaque morceau de texte est rangé dans sa colonne **par sa position sur la page** (les puces de
la 1re colonne à 37,7 points du bord, celles de la 2e à 299,1, ou 293,7 aux pages 32 et 33 : limite à 290 ; une
ponctuation qui finit une ligne de la 1re colonne et tombe au-delà y reste), puis la 1re colonne relue de haut en bas. Les exemples de réussite (2e colonne) ne sont pas relevés : ils serviront de source aux tables du générateur.

- un tableau commence à sa ligne d'en-tête (« Objectifs d'apprentissage Exemples de réussite ») et finit à la première
  ligne écrite dans la marge de gauche (un titre, un paragraphe) ; il peut passer d'une page à la suivante ;
- les titres des activités et des compétences sont ceux du sommaire, au début de l'annexe ; un titre de compétence
  peut tenir sur deux lignes, et son code être coupé (« (EOI- » / « CP) ») ou espacé (« (M - CE1) ») ;
- mise en page : un mot coupé en fin de ligne après un trait d'union est recollé sans espace (« pré- » / « A1) ») ;
  le pied de page (« education.gouv.fr BO n° 12 17 ») est ignoré ;
- une sous-liste (puce U+F09F de la police Symbol dans les objectifs, « • » dans les attendus) reste dans son libellé,
  sans sa puce, comme au lot 2 (« … de différentes natures : fossiles ; ossements ; … ») ;
- les marques de niveau du texte, « (A1) » et « (pré-A1) », sont gardées telles quelles, à leur place : elles font
  partie du libellé. Le programme marque aussi le niveau A1 par la couleur (bleu foncé, RVB 0 ; 0 ; 0,569 ; le
  pré-A1 en noir) : la couleur de chaque caractère est lue dans le PDF, le niveau de chaque libellé en est tiré
  (« pré-A1 », « A1 », ou « pré-A1 et A1 » quand le libellé mêle les deux), et chaque marque est confrontée à la
  couleur du texte qui la suit (sur la sortie d'erreur, chaque écart) ;
- les coquilles du texte officiel sont gardées (« (pré-A1)avoir recours », « journée; », « bloc lexicalisé). »).

Usage : python -I extraire_objectifs_lv.py <bo12.pdf> <première page> <dernière page> [--lignes]
-> JSON sur la sortie standard (avec --lignes : les lignes du PDF de chaque libellé, pour la vérification) ; sur la
sortie d'erreur, chaque correction de mise en page."""
import json
import re
import sys

from pypdf import PdfReader

# entre les deux colonnes du tableau, en points depuis le bord gauche : les puces de la 2e colonne sont à 299,1 (à
# 293,7 aux pages 32 et 33) ; une ponctuation qui finit une ligne de la 1re colonne peut tomber au-delà (« , » à 293,7,
# page 18) : elle suit alors, sur la même ligne, un morceau de la 1re colonne
LIMITE = 290
LIMITE_PONCTUATION = 299
MARGE = 37.5      # les titres et les paragraphes sont à 36 ; les puces de la 1re colonne à 37,7
CLASSES = {"Cours préparatoire": "CP", "Cours élémentaire première année": "CE1",
           "Cours élémentaire deuxième année": "CE2"}
CODE = re.compile(r"\s*\(\s*(CO|EOC|EOI|CE|EE|M)\s*-\s*(CP|CE1|CE2)\s*\)$")
PIED = re.compile(r"^education\.gouv\.fr BO n° 12 \d+$")
ENTETE = "Objectifs d’apprentissage Exemples de réussite"
BLEU, NOIR = ("rg", (0.0, 0.0, 0.569)), ("g", (0.0,))  # le niveau A1 ; le pré-A1 (et le texte courant)
SOUS_PUCE = re.compile(r"\s*[\uf09f•]\s*")
MARQUE = re.compile(r"\((pré-)?A1\)")

chemin, premiere, derniere = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
avec_lignes = "--lignes" in sys.argv


def propre(texte: str) -> str:
    return re.sub(r"\s+", " ", texte).strip()


# --- les lignes de chaque page : (y, x du premier morceau, {colonne: texte}, texte de toute la ligne, morceaux près
# de la limite, {colonne: couleurs}, couleurs de toute la ligne) ; les couleurs : un caractère par caractère du texte
# (« B » : bleu, A1 ; « N » : noir ; « . » : autre)
def lignes_de(page) -> list[tuple]:
    morceaux = []
    etat = {"couleur": None, "pile": []}

    def operateur(op, args, cm, tm):  # la couleur de remplissage, avec la pile de l'état graphique (q, Q)
        if op == b"q":
            etat["pile"].append(etat["couleur"])
        elif op == b"Q":
            etat["couleur"] = etat["pile"].pop() if etat["pile"] else None
        elif op in (b"rg", b"g", b"k", b"sc", b"scn"):
            etat["couleur"] = (op.decode(), tuple(round(float(a), 3) for a in args))

    def visiteur(texte, cm, tm, police, taille):
        code = "B" if etat["couleur"] == BLEU else "N" if etat["couleur"] == NOIR else "."
        morceaux.append((texte, tm[4] * cm[0] + cm[4], tm[5] * cm[3] + cm[5], code))

    brut = page.extract_text(visitor_text=visiteur, visitor_operand_before=operateur)
    assert "".join(m[0] for m in morceaux) == brut, "les morceaux ne redonnent pas le texte de la page"
    lignes: list[dict] = []
    derniere_ligne, position = None, None  # la ligne du dernier morceau écrit, et sa colonne : les espaces y vont
    for texte, x, y, code in morceaux:
        texte = texte.replace("\n", " ")
        if not texte.strip():
            if derniere_ligne:
                derniere_ligne["colonnes"][position] += texte
                derniere_ligne["couleurs"][position] += code * len(texte)
                derniere_ligne["texte"] += texte
                derniere_ligne["couleur"] += code * len(texte)
            continue
        ligne = next((l for l in lignes if abs(y - l["y"]) <= 1), None)
        if ligne is None:
            ligne = {"y": y, "x": x, "colonnes": {}, "couleurs": {}, "texte": "", "couleur": "", "douteux": []}
            lignes.append(ligne)
        ligne["x"] = min(ligne["x"], x)
        c = int(x >= LIMITE)
        if c and ligne is derniere_ligne and position == 0 and re.match(r"^[,;:.)]", texte) and x < LIMITE_PONCTUATION:
            c = 0  # une ponctuation qui finit une ligne de la 1re colonne (« gestes » + « , » à 293,7)
        elif LIMITE <= x < LIMITE_PONCTUATION and texte.strip() != "-":
            ligne["douteux"].append(texte)  # près de la limite : à regarder, si c'est dans un tableau
        ligne["colonnes"][c] = ligne["colonnes"].get(c, "") + texte
        ligne["couleurs"][c] = ligne["couleurs"].get(c, "") + code * len(texte)
        ligne["texte"] += texte
        ligne["couleur"] += code * len(texte)
        derniere_ligne, position = ligne, c
    return [(l["y"], l["x"], {c: propre(t) for c, t in l["colonnes"].items()}, propre(l["texte"]), l["douteux"],
             {c: (t, l["couleurs"][c]) for c, t in l["colonnes"].items()}, (l["texte"], l["couleur"]))
            for l in sorted(lignes, key=lambda l: -l["y"])]


def niveau(brut: list[tuple[str, str]], libelle: str) -> str:
    """Le niveau d'un libellé, tiré de la couleur de ses lettres. Les marques confrontées à la couleur : « (A1) » ouvre
    un passage bleu, « (pré-A1) » un passage noir ; tout passage bleu commence par « (A1) » ; le retour au noir n'est
    pas toujours marqué (« (je, tu, (A1) il/elle/on), compléments (moi, toi… ») : il est admis. Les écarts sur la
    sortie d'erreur."""
    texte = "".join(t for t, _ in brut)
    couleurs = "".join(c for _, c in brut)
    garde = [i for i, ch in enumerate(texte) if not ch.isspace()]
    texte, couleurs = "".join(texte[i] for i in garde), "".join(couleurs[i] for i in garde)
    vues, ecarts, marque, precedente, i = set(), [], None, "N", 0
    while i < len(texte):
        if m := MARQUE.match(texte, i):
            marque, i = ("N" if m[1] else "B"), m.end()
            continue
        if texte[i].isalpha():
            c = couleurs[i]
            vues.add(c)
            if marque and c != marque:
                ecarts.append(f"« {m_texte(texte, i)} » en {'bleu' if c == 'B' else 'noir'} après une marque")
            elif not marque and c == "B" and precedente == "N":
                ecarts.append(f"« {m_texte(texte, i)} » en bleu sans « (A1) »")
            marque, precedente = None, c
        i += 1
    for ecart in ecarts:
        print(f"! {ecart} : {libelle[:70]}", file=sys.stderr)
    assert vues <= {"B", "N"}, (vues, libelle)
    return {frozenset("N"): "pré-A1", frozenset("B"): "A1"}.get(frozenset(vues), "pré-A1 et A1")


def m_texte(texte: str, i: int) -> str:
    return f"…{texte[max(0, i - 12):i]}[{texte[i:i + 12]}]…"


def ajouter(puces: list[dict], texte: str, brut: tuple[str, str]) -> None:
    """La suite d'une puce : recollée sans espace après un trait d'union en fin de ligne (« pré- » / « A1) »)."""
    if re.search(r"\w-$", puces[-1]["lignes"][-1]):
        print(f"~ recollé : …{puces[-1]['lignes'][-1][-20:]}|{texte[:20]}…", file=sys.stderr)
    puces[-1]["lignes"].append(texte)
    puces[-1]["brut"].append(brut)


def joindre(lignes: list[str]) -> str:
    texte = lignes[0]
    for suite in lignes[1:]:
        texte += suite if re.search(r"\w-$", texte) else " " + suite
    return propre(texte)


def libelle(puce: dict) -> str:
    texte = joindre(puce["lignes"])
    sans = SOUS_PUCE.sub(" ", texte).strip()
    if sans != texte:
        print(f"~ puces de sous-liste retirées : {texte[:60]}…", file=sys.stderr)
    return sans


lecteur = PdfReader(chemin)
lignes = []
for numero in range(premiere, derniere + 1):
    lignes += [l for l in lignes_de(lecteur.pages[numero - 1]) if not PIED.match(l[3])]

# --- le sommaire : les activités (« … (CO) ») et les compétences (« … ____ CP CE1 CE2 »), jusqu'à « Préambule » ---
textes = [l[3] for l in lignes]
debut, fin = textes.index("Sommaire"), [i for i, t in enumerate(textes) if t == "Préambule"][1]
activites, competences, en_cours = {}, [], []
for texte in textes[debut + 1:fin]:
    if m := re.match(r"^(.+) \((CO|EOC|EOI|CE|EE|M)\)$", texte):
        activites[m[1]] = m[2]
    elif activites:  # les compétences, après la première activité
        en_cours.append(texte)
        if "_" in texte:
            titre, _, classes = joindre(en_cours).partition("_")
            competences.append((propre(titre), classes.strip("_ ").split()))
            en_cours = []
assert list(activites.values()) == ["CO", "EOC", "EOI", "CE", "EE", "M"], activites
assert not en_cours, en_cours
titres = {t for t, _ in competences}

# --- le corps de l'annexe ---------------------------------------------------------------------------------------
blocs, activite, classe, tampon, etat, courant = [], None, None, [], "texte", None
for y, x, cols, texte, douteux, bruts, brut in lignes[fin + 1:]:
    if etat == "tableau" and x < MARGE and texte != ENTETE:
        etat = "texte"  # une ligne dans la marge : le tableau est fini
    if etat == "tableau":
        if texte == ENTETE:
            continue  # l'en-tête répété en haut d'une page
        assert not douteux, f"un morceau près de la limite des colonnes : {douteux} dans « {texte} »"
        gauche = cols.get(0)
        if not gauche:
            continue
        puces = courant["objectifs"]
        if gauche.startswith("- "):
            puces.append({"lignes": [gauche[2:]], "brut": [bruts[0]]})
        else:
            assert puces, f"une suite sans puce : {gauche}"
            ajouter(puces, gauche, bruts[0])
        continue
    if etat == "attendus":
        if texte == ENTETE:
            etat = "tableau"
            continue
        puces = courant["attendus"]
        if texte.startswith("− "):
            puces.append({"lignes": [texte[2:]], "brut": [brut]})
        else:
            assert puces, f"une suite sans puce : {texte}"
            ajouter(puces, texte, brut)
        continue
    # hors d'un tableau : les titres
    if texte in activites:
        activite, classe, tampon = texte, None, []
    elif texte in CLASSES:
        classe, tampon = CLASSES[texte], []
    elif re.match(r"^Attendus (de )?fin d’année :$", texte):
        assert courant and not courant["attendus"], texte
        etat = "attendus"
    elif texte == ENTETE:  # une compétence sans attendus de fin d'année
        assert courant and not courant["objectifs"], texte
        etat = "tableau"
    else:
        tampon.append(texte)
        joint = joindre(tampon[-2:])
        if m := CODE.search(joint):
            titre = joint[:m.start()]
            if titre not in titres:
                titre = next(t for t in titres if joint.endswith(t + joint[m.start():]) or titre.endswith(t))
            code = f"{m[1]}-{m[2]}"
            assert m[1] == activites[activite] and m[2] == classe, (code, activite, classe)
            if propre(joint[m.start():]) != f"({code})":
                print(f"~ code d’une compétence remis en forme : {propre(joint[m.start():])} → ({code})", file=sys.stderr)
            assert classe in dict(competences)[titre], (titre, classe)
            courant = {"activite": activite, "code_activite": m[1], "classe": classe, "competence": titre,
                       "code": code, "attendus": [], "objectifs": []}
            blocs.append(courant)
            tampon = []

sortie = []
for b in blocs:
    bloc = {k: v for k, v in b.items() if k not in ("attendus", "objectifs")}
    for cle in ("attendus", "objectifs"):
        bloc[cle] = [{"libelle": (l := libelle(p)), "niveau": niveau(p["brut"], l)} for p in b[cle]]
        if avec_lignes:
            bloc[f"lignes_{cle}"] = [p["lignes"] for p in b[cle]]
    sortie.append(bloc)
attendues = {(t, c) for t, classes in competences for c in classes}
trouvees = {(b["competence"], b["classe"]) for b in sortie}
assert attendues == trouvees, (attendues - trouvees, trouvees - attendues)
assert all(b["objectifs"] for b in sortie), "une compétence sans objectifs"
json.dump(sortie, sys.stdout, ensure_ascii=False, indent=1)
print(f"{len(sortie)} compétences, {sum(len(b['attendus']) for b in sortie)} attendus de fin d’année, "
      f"{sum(len(b['objectifs']) for b in sortie)} objectifs", file=sys.stderr)
