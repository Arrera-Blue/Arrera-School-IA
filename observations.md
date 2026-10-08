# Observations — recette 1.6

> Les défauts constatés à la relecture des exercices générés, pour la recette 1.6 (procédure :
> `docs/test/recette-1.6.md` dans le dossier du projet). Hors du paquet `generateur/` : ce fichier n'est pas
> copié dans le conteneur.
>
> **Gravité** : fond (réponse fausse, plusieurs réponses justes) · ambiguïté · niveau · forme.
> **Détecté** : réparé par reprise · à relire · non détecté.

## Synthèse

| # | Sujet | Chemin | Durée | Tentatives | Défauts (fond / ambiguïté / niveau / forme) | Fond non détecté |
|---|---|---|---|---|---|---|
| 1 | Fractions 6e | procédural (gabarits, sous le seuil d'habillage) | 0,0 s | 1 | 0 / 0 / 0 / 2 | 0 |
| 2 | Pythagore 4e | procédural + réécriture (4 énoncés sur 5) | 108,0 s | 1 | 0 / 0 / 0 / 2 | 0 |
| 3 | Conjugaison 6e | | | | | |
| 4 | Grammaire 5e | | | | | |
| 5 | Histoire 4e | | | | | |
| 6 | Maths mixtes 5e | | | | | |
| 7 | Rendu, 15 questions | | | | | |
| 8 | Rendu, 3 questions | | | | | |

**Jalon A** (aucun défaut de fond non détecté) : ☐

## Détail

<!-- Un bloc par exercice :

### n° — sujet (fichier.json)
| Q | Défaut | Gravité | Détecté |
|---|---|---|---|
| 3 | 3/4 ÷ 2/4 = 1/2 annoncé, 3/2 juste | fond | non |
-->

### 1 — Fractions 6e (`qcm-fractions-6e-20261008-081021.json`, graine 338952) — 08/10

5 questions vérifiées par N4, justes par construction. Une seule question réécrivable : pas d'appel au modèle.

| Q | Défaut | Gravité | Détecté |
|---|---|---|---|
| 3 | distracteur « 9/1 » (partie rapportée au reste) : juste comme erreur d'élève, mais étrange écrit ainsi | forme | — |
| 4 | distracteur « 4/4 » (seul le numérateur multiplié) : trop facile à écarter | forme | — |

### 2 — Pythagore 4e (`qcm-theoreme-de-pythagore-4e-20261008-081354.json`, graine 693358) — 08/10

5 réponses justes par construction ; 4 énoncés réécrits par Gemma, **sans changement de sens**. Objets
triangulaires (panneau, support, toit, morceau de bois) : la consigne du 07/10 fonctionne.

| Q | Défaut | Gravité | Détecté |
|---|---|---|---|
| 1 | réécriture refusée pour « deux » (sans doute « les deux côtés de l'angle droit ») : contrôle trop strict, l'énoncé reste le gabarit | outil | — |
| 2 | « un morceau de bois a des longueurs de 50 cm, 40 cm et 30 cm » : compréhensible, mais flou | forme | — |
| 5 | « un toit de forme triangulaire » de 40 cm : l'unité du tirage (cm) ne va pas avec l'objet choisi | forme | — |
