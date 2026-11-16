# Scripts

Des outils lancés à la main pour **fabriquer ou vérifier des données** du dépôt, et quelques essais. L'application ne les
importe jamais (`generateur/` n'en dépend pas) ; pytest ne les parcourt pas (`testpaths = tests`). Certains demandent
des bibliothèques **hors des dépendances du projet**, à installer à part (dans un environnement séparé) : elles ne
servent qu'ici.

## `programmes/` : les programmes officiels (`generateur/programmes/*.yaml`)

| Script | Rôle | Demande |
|---|---|---|
| `extraire_pdf.py` | le texte des PDF du Bulletin officiel, page par page | `pypdf` |
| `extraire_objectifs.py` | les objectifs d'une classe du cycle 3 ou 4 (6e, 5e), avec `entetes-*.json` | — |
| `construire_referentiel.py` | les fichiers `maths-6e.yaml`… (corrections à la main listées dans le script) | `pyyaml` |
| `verifier_mot_pour_mot.py` | chaque libellé retrouvé tel quel dans le texte officiel | — |
| `extraire_objectifs_c2.py` | les objectifs du français du cycle 2 (CP, CE1, CE2 : un tableau à deux colonnes) | — |
| `construire_referentiel_c2.py` | `francais-cp.yaml`, `-ce1.yaml`, `-ce2.yaml` (identifiants, champ « qcm ») | `pyyaml` |
| `verifier_mot_pour_mot_c2.py` | les libellés du cycle 2 (et les titres des thèmes de 2026) retrouvés tels quels dans le texte officiel | `pyyaml` |
| `extraire_objectifs_2026.py` | les programmes de 2026 du cycle 2 : sciences et technologie, histoire-géographie ; chaque morceau de texte rangé dans sa colonne par sa position sur la page | `pypdf` |
| `construire_referentiel_2026.py` | `sciences-et-technologie-cp.yaml`…, `histoire-geo-cp.yaml`… (identifiants, champ « qcm », colonne d'origine) | `pyyaml` |

Méthode : `docs/etapes/etape-E2-programmes.md` (6e, 5e) ; `docs/Generateur-Procedural/cycle-2-cp-ce1-ce2.md` §11.4
(français du cycle 2) ; `docs/Generateur-Procedural/lot-2-questionner-le-monde.md` §11.1 (sciences et
histoire-géographie du cycle 2). (`docs/` est à côté du dépôt, non versionné.)

Les programmes de 2026, de bout en bout (les PDF téléchargés à part, dans un dossier vide) :

```bash
python -I scripts/programmes/extraire_objectifs_2026.py sciences bo24.pdf 4 15 > sciences.json
python -I scripts/programmes/extraire_objectifs_2026.py histoire-geo annexe-3-hg-c2.pdf 1 8 > histoire-geo.json
python -I scripts/programmes/construire_referentiel_2026.py sciences.json histoire-geo.json generateur/programmes
python -I scripts/programmes/verifier_mot_pour_mot_c2.py <texte officiel.txt> generateur/programmes/histoire-geo-cp.yaml
```

## `conjugaison/` : les tables de conjugaison (`generateur/procedural/donnees/francais/`)

| Script | Rôle | Demande |
|---|---|---|
| `construire_conjugaisons.py` | `conjugaisons.yaml` et `terminaisons.yaml` ; **la source de ces tables** : pour ajouter un verbe, le modifier et le relancer | `pyyaml` |
| `verifier_conjugaisons.py` | le second contrôle : chaque forme comparée à Verbiste | `verbecc` (LGPL, environnement séparé) |
| `page_relecture_conjugaisons.py` | la page de relecture en grilles, pour l'enseignant | `pyyaml` |

Après une modification, la table n'est plus relue : la faire relire et valider
(`python -m generateur.procedural.tables relire francais/conjugaisons --par "…"`). Méthode :
`docs/Generateur-Procedural/lot-1-francais.md` §11.

## `accords/` : les tables des accords (`generateur/procedural/donnees/francais/`)

| Script | Rôle | Demande |
|---|---|---|
| `construire_accords.py` | `noms.yaml`, `adjectifs.yaml`, `pluriels_irreguliers.yaml`, `feminins.yaml` ; **la source de ces tables** | `pyyaml` |
| `verifier_accords.py` | le second contrôle : genres, pluriels, formes et erreurs typiques comparés à Lexique 3.83 | `Lexique383.tsv` (lexique.org, CC BY-SA 4.0, téléchargé à part) |
| `page_relecture_accords.py` | la page de relecture des quatre tables, pour l'enseignant | `pyyaml` |

Méthode : `docs/Generateur-Procedural/lot-1-francais.md` §11.2.

## `phrase/` : la table des phrases (`generateur/procedural/donnees/francais/phrases.yaml`)

| Script | Rôle | Demande |
|---|---|---|
| `construire_phrases.py` | `phrases.yaml` : 62 phrases, leur type, leurs formes, la nature de chaque mot ; **la source de la table** | `pyyaml` |
| `verifier_phrases.py` | le second contrôle : la nature de chaque mot parmi les catégories que Lexique 3.83 lui donne | `Lexique383.tsv` (à part) |
| `page_relecture_phrases.py` | la page de relecture de la table, pour l'enseignant | `pyyaml` |

Méthode : `docs/Generateur-Procedural/lot-1-francais.md` §11.3.

## `vocabulaire/` : les tables du vocabulaire (`generateur/procedural/donnees/francais/`)

| Script | Rôle | Demande |
|---|---|---|
| `construire_vocabulaire.py` | `contraires`, `prefixes`, `familles`, `lettres_muettes`, `categories`, `niveaux_de_langue` ; **la source de ces tables** ; Lexique 3.83 y choisit les pièges qui ne sont pas de vrais mots | `pyyaml`, `Lexique383.tsv` (à part) |
| `verifier_vocabulaire.py` | le second contrôle : mots, classes, pièges, un seul rangement par mot, comparés à Lexique 3.83 | `Lexique383.tsv` (à part) |
| `page_relecture_vocabulaire.py` | la page de relecture des six tables, pour l'enseignant | `pyyaml` |

Méthode : `docs/Generateur-Procedural/lot-1-francais.md` §11.4.

## `histoire_geo/` : les tables de l'histoire (`generateur/procedural/donnees/histoire-geo/`)

| Script | Rôle | Demande |
|---|---|---|
| `page_relecture_histoire.py` | la page de relecture des 5 tables (calendrier, durées, périodes, repères, Préhistoire), avec leurs sources et ce qui n'est jamais demandé | `pyyaml` |

Les tables sont écrites à la main (petites, chaque ligne avec sa source : le programme d'abord, sinon Wikipédia ou le
Wiktionnaire) : `docs/Generateur-Procedural/lot-2-questionner-le-monde.md` §11.2.

## `sciences_et_technologie/` : les tables du vivant (`generateur/procedural/donnees/sciences-et-technologie/`)

| Script | Rôle | Demande |
|---|---|---|
| `page_relecture_vivant.py` | la page de relecture des 9 tables (vivant ou non, animaux, régimes, sens, plante, vie d'une plante, petits, locomotion, chaînes), avec leurs sources et ce qui n'est jamais demandé | `pyyaml` |

Les tables sont écrites à la main, chaque ligne avec sa source (le programme, sinon la page Wikipédia ou Wiktionnaire
lue) : `docs/Generateur-Procedural/lot-2-questionner-le-monde.md` §11.3.

## `lexique/` : la liste des mots de Lexique 3.83 (`generateur/moteur/validation/lexique/`)

| Script | Rôle | Demande |
|---|---|---|
| `construire_lexique.py` | `mots.txt.gz` (l'orthographe de chaque mot, compressée : 324 Ko ; le même fichier à chaque construction) et `LISEZMOI.md` (source, licence CC BY-SA 4.0) : N4 du français y reconnaît une forme verbale inventée par le modèle | `Lexique383.tsv` (lexique.org, téléchargé à part) |

Méthode et mesure : `docs/Generateur-Procedural/controle-du-modele.md`.

## `essais/` : des essais ponctuels

| Script | Rôle |
|---|---|
| `banc_prompt.py` (+ `demandes.json`) | le banc du prompt principal (26/10) : `docs/etapes/etape-prompt-principal.md` |
| `contre_verification_essai.py` | l'essai de la contre-vérification (IA1.4) : `docs/etapes/etape-IA0-cadrage.md` |
| `criteres/lot-1-francais.json` | les 20 demandes réelles du critère de fin du lot 1 (et la graine de chaque exercice accepté), pour `python -m generateur.entrainement aveugle chemins --demandes …` : `docs/Generateur-Procedural/lot-1-francais.md` §11.5 |
