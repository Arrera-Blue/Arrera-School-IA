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

## `essais/` : des essais ponctuels

| Script | Rôle |
|---|---|
| `banc_prompt.py` (+ `demandes.json`) | le banc du prompt principal (26/10) : `docs/etapes/etape-prompt-principal.md` |
| `contre_verification_essai.py` | l'essai de la contre-vérification (IA1.4) : `docs/etapes/etape-IA0-cadrage.md` |
