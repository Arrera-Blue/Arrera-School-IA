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
| `verifier_mot_pour_mot_c2.py` | les 182 libellés du cycle 2 retrouvés tels quels | `pyyaml` |

Méthode : `docs/etapes/etape-E2-programmes.md` (6e, 5e) ; `docs/Generateur-Procedural/cycle-2-cp-ce1-ce2.md` §11.4
(cycle 2). (`docs/` est à côté du dépôt, non versionné.)

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

## `essais/` : des essais ponctuels

| Script | Rôle |
|---|---|
| `banc_prompt.py` (+ `demandes.json`) | le banc du prompt principal (26/10) : `docs/etapes/etape-prompt-principal.md` |
| `contre_verification_essai.py` | l'essai de la contre-vérification (IA1.4) : `docs/etapes/etape-IA0-cadrage.md` |
| `criteres/lot-1-francais.json` | les 20 demandes réelles du critère de fin du lot 1 (et la graine de chaque exercice accepté), pour `python -m generateur.entrainement aveugle chemins --demandes …` : `docs/Generateur-Procedural/lot-1-francais.md` §11.5 |
