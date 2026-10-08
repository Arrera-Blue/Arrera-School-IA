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
| 3 | Conjugaison 6e | modèle | 418,2 s | 2 | 0 / 0 / 1 / 4 | 0 |
| 4 | Grammaire 5e | modèle | 339,8 s | 1 | 0 / 1 / 1 / 2 | 0 |
| 5 | Histoire 4e | modèle | 347,7 s | 1 | 0 / 1 / 0 / 3 | 0 |
| 6 | Maths mixtes 5e | modèle, contrôlé par N4 | 137,9 s (modèle déjà chargé) | 1 | 0 / 0 / 0 / 1 | 0 |
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

### 3 — Conjugaison 6e (`qcm-le-present-de-l-indicatif-des-verbes-du--6e-20261008-083441.json`) — 08/10

5 réponses justes, une seule bonne réponse par question (relu à la main ; N4 ne vérifie rien hors maths).
Version refusée à la tentative 1 : 4 propositions identiques (« Nous mangeons une pomme. ») → N3, puis
réparée par la reprise.

| Q | Défaut | Gravité | Détecté |
|---|---|---|---|
| 1 | explication : « suffixel » (faute de frappe), « forme de base » au lieu de « radical » | forme | non |
| 3 | distracteur « jouonsent » : forme inventée, absurde | forme | non |
| 4 | distracteur « parleznt » : forme inventée, absurde | forme | non |
| 5 | avertissement N3 sur « souvent » : faux positif (le mot appartient à la phrase, pas à la consigne) | outil | — |
| toutes | 5 verbes du 1er groupe, même question 5 fois : aucun verbe en -ir, aucun irrégulier (être, avoir, aller, faire) ; trop facile et répétitif | niveau | non |

### 4 — Grammaire 5e (`qcm-nature-des-mots-classes-de-mots-5e-20261008-110412.json`) — 08/10

5 réponses justes (relu à la main), en une tentative.

| Q | Défaut | Gravité | Détecté |
|---|---|---|---|
| 1 | « quel est la nature » : faute d'accord dans l'énoncé | forme | non |
| 4 | « quel est le rôle du mot » pour demander sa nature : en grammaire, le rôle est la fonction (sujet, COD…), confusion que la 5e travaille justement | ambiguïté | non |
| toutes | trop facile pour la 5e (« chat » est un nom) ; seulement nom, verbe, adjectif, adverbe : aucun déterminant, pronom, préposition, conjonction | niveau | non |
| toutes | bonne réponse toujours en position 3 (mélangée à l'affichage) | forme | avertissement N3 |

### 5 — Histoire 4e (`qcm-la-revolution-francaise-4e-20261008-112203.json`) — 08/10

5 réponses justes, dates et faits exacts (relu à la main), en une tentative.

| Q | Défaut | Gravité | Détecté |
|---|---|---|---|
| 1 | « Quelle monarchie… » : seule la bonne réponse est une monarchie (république, oligarchie, régime parlementaire) : la question donne la réponse | forme | non |
| 3 | « la bourgeoisie » se défend aussi (elle mène le Tiers État aux débuts de la Révolution) ; le Tiers État n'est pas « composé de paysans et de petits artisans » seulement ; « les début » | ambiguïté | **non** |
| 4 | bonne réponse nettement plus longue que les autres | forme | avertissement N3 |
| 2 | avertissement N3 sur « souvent » : ici justifié (« souvent considéré comme le début ») | — | avertissement N3 |

### 6 — Maths mixtes 5e (`qcm-fractions-et-pourcentages-5e-20261008-112814.json`) — 08/10

5 réponses justes (calculs refaits à la main), en une tentative. N4 : 1 vérifiée, **4 à relire** : sur une
demande mixte, l'enseignant doit encore refaire 4 calculs sur 5.

| Q | Défaut | Gravité | Détecté |
|---|---|---|---|
| 2 | 1 − 3/5 = 2/5 (juste) : « ce qui reste » n'est pas lu par N4 | outil | à relire |
| 3 | 40 % = 2/5 (juste) : « quelle fraction représente 40 % » n'est pas lu par N4 | outil | à relire |
| 4 | 20 % de 50 € = 10 € (juste) : « le montant de la réduction » n'est pas lu par N4 | outil | à relire |
| 5 | dénominateur commun de 1/3 et 1/6 → 6 (juste) ; distracteurs « 1/9 » et « 1/18 » : des fractions quand un nombre est demandé | forme | à relire |
