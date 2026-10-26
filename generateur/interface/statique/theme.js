// Le thème de l'interface (Mon compte → Apparence), appliqué avant le premier affichage : pas d'éclair sombre
// quand le thème clair est choisi. Un réglage de cet ordinateur, gardé dans le navigateur (aucune donnée d'élève).
"use strict";
try {
  if (localStorage.getItem("theme") === "clair") document.documentElement.dataset.theme = "clair";
} catch (_) { /* stockage indisponible : le thème sombre, par défaut */ }
