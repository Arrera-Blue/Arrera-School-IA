// Les écrans de l'élève sur le serveur de classe (E8) : choisir sa classe, son nom, taper son code, puis son accueil.
// Rien dans le stockage du navigateur (postes partagés) : l'état vit dans la page, la session dans un cookie HttpOnly.
"use strict";
(() => {
  const $ = (s) => document.querySelector(s);
  const ECRANS = ["classes", "noms", "code", "accueil"];
  const MATIERES = { maths: "Mathématiques", francais: "Français", "histoire-geo": "Histoire-géographie", svt: "SVT",
    "physique-chimie": "Physique-chimie", anglais: "Anglais", technologie: "Technologie" };
  const etat = { classe: null, eleve: null, images: [], saisi: [], bloque: false };

  function el(balise, attributs = {}, ...enfants) {
    const e = document.createElement(balise);
    for (const [cle, valeur] of Object.entries(attributs)) {
      if (valeur === null || valeur === undefined || valeur === false) continue;
      if (cle === "texte") e.textContent = valeur;
      else e.setAttribute(cle, valeur === true ? "" : valeur);
    }
    e.append(...enfants.filter((x) => x !== null && x !== undefined));
    return e;
  }

  async function api(chemin, corps, methode = corps === undefined ? "GET" : "POST") {
    const options = { method: methode, credentials: "same-origin", headers: {} };
    if (methode !== "GET") {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(corps === undefined ? {} : corps);
    }
    const reponse = await fetch(chemin, options);
    const donnees = await reponse.json().catch(() => ({}));
    return { statut: reponse.status, donnees };
  }

  function style(niveau) { document.body.dataset.style = niveau === "6e" ? "enfant" : "college"; }

  function afficher(ecran, focus) {
    for (const nom of ECRANS) $(`#ecran-${nom}`).hidden = nom !== ecran;
    window.scrollTo(0, 0);
    if (focus) $(focus).focus({ preventScroll: true });
  }

  function informer(texte) {
    $("#message").textContent = texte;
    $("#message").hidden = !texte;
  }

  function secouer(element) {
    element.classList.remove("secoue");
    void element.offsetWidth;
    element.classList.add("secoue");
  }

  // --- 1. la classe ---
  async function classes(message = "") {
    etat.classe = null;
    etat.eleve = null;
    style(null);
    informer(message);
    const { statut, donnees } = await api("/api/classes");
    const liste = statut === 200 ? donnees.classes : [];
    $("#classes").replaceChildren(...liste.map((c) => {
      const b = el("button", { type: "button", class: "tuile" }, el("span", { class: "pastille", texte: c.niveau }), el("b", { texte: c.nom }));
      b.addEventListener("click", () => noms(c));
      return b;
    }));
    $("#classes-vide").hidden = liste.length > 0;
    afficher("classes");
  }

  // --- 2. le nom ---
  async function noms(classe) {
    const { statut, donnees } = await api(`/api/classes/${classe.id}/eleves`);
    if (statut !== 200) { classes("Cette classe n'est plus ouverte."); return; }
    etat.classe = donnees.classe;
    etat.images = donnees.images;
    style(etat.classe.niveau);
    informer("");
    $("#noms-classe").textContent = `${etat.classe.nom} : touche ton prénom.`;
    $("#noms").replaceChildren(...donnees.eleves.map((e) => {
      const b = el("button", { type: "button", class: "tuile", texte: e.nom });
      b.addEventListener("click", () => code(e));
      return b;
    }));
    afficher("noms");
  }

  // --- 3. le code ---
  function code(eleve) {
    etat.eleve = eleve;
    etat.saisi = [];
    etat.bloque = false;
    const images = etat.classe.connexion === "images";
    $("#code-bonjour").textContent = `Bonjour ${eleve.nom.split(" ")[0]} !`;
    $("#code-consigne").textContent = images ? "Touche les 4 images de ta carte, dans l'ordre." : "Tape le mot de passe écrit sur ta carte.";
    $("#code-images").hidden = !images;
    $("#code-mdp").hidden = images;
    $("#code-erreur").hidden = true;
    $("#code-bloque").hidden = true;
    $("#mdp").value = "";
    $("#mdp").disabled = false;
    $("#se-connecter").disabled = false;
    if (images) {
      $("#images").replaceChildren(...etat.images.map((i) => {
        const b = el("button", { type: "button", class: "image", "aria-label": i.nom },
          el("img", { src: `/codes/${i.image}.svg`, alt: "" }), el("span", { texte: i.nom }));
        b.addEventListener("click", () => toucher(i));
        return b;
      }));
      cases();
    }
    afficher("code", images ? "#code-bonjour" : "#mdp");
  }

  function cases() {
    $("#cases").replaceChildren(...[0, 1, 2, 3].map((i) => {
      const image = etat.saisi[i];
      return el("span", { class: `case${i === etat.saisi.length ? " suivante" : ""}` },
        image ? el("img", { src: `/codes/${image.image}.svg`, alt: image.nom }) : null);
    }));
  }

  function toucher(image) {
    if (etat.bloque || etat.saisi.length >= 4) return;
    etat.saisi.push(image);
    cases();
    if (etat.saisi.length === 4) envoyerCode(etat.saisi.map((i) => i.image));
  }

  async function envoyerCode(saisie) {
    $("#se-connecter").disabled = true;
    const { statut, donnees } = await api("/api/session", { eleve: etat.eleve.id, code: saisie });
    $("#se-connecter").disabled = false;
    if (statut === 200) { accueil(); return; }
    const images = etat.classe.connexion === "images";
    if (statut === 423) {
      etat.bloque = true;
      $("#code-erreur").hidden = true;
      $("#code-bloque").textContent = "Trop d'essais : ta connexion est bloquée. Demande à ton professeur de la débloquer.";
      $("#code-bloque").hidden = false;
      $("#mdp").disabled = true;
      $("#se-connecter").disabled = true;
    } else if (statut === 401) {
      const restants = donnees.restants;
      $("#code-erreur").textContent = (images ? "Ce n'est pas le bon code. Regarde bien ta carte" : "Mot de passe incorrect. Vérifie ta carte")
        + ` : il te reste ${restants} essai${restants > 1 ? "s" : ""}.`;
      $("#code-erreur").hidden = false;
    } else {
      $("#code-erreur").textContent = "La connexion n'a pas marché : réessaie.";
      $("#code-erreur").hidden = false;
    }
    if (images) {
      secouer($("#cases"));
      etat.saisi = [];
      setTimeout(cases, 450);
    } else {
      secouer($("#champ-mdp"));
      $("#mdp").value = "";
      if (!etat.bloque) $("#mdp").focus();
    }
  }

  // --- 4. l'accueil ---
  function etoiles(fait) {
    const ratio = fait.justes / fait.questions;
    return "★".repeat(ratio >= 0.9 ? 3 : ratio >= 0.6 ? 2 : 1);
  }

  function dateCourte(iso) {
    return new Date(iso).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
  }

  function carteExercice(x, section) {
    const enfant = document.body.dataset.style === "enfant";
    const details = [MATIERES[x.matiere] || x.matiere];
    if (x.difficulte) details.push(x.difficulte);
    let detail = details.join(", ") + ".";
    if (x.fait) detail += ` Fait le ${new Date(x.fait.date).toLocaleDateString("fr-FR", { day: "numeric", month: "long" })} : ${x.fait.justes} sur ${x.fait.questions}.`;
    else if (x.fin) detail += ` Jusqu'au ${dateCourte(x.fin)}.`;
    const etiquette = x.fait
      ? el("span", { class: "etat fait" }, enfant ? el("span", { class: "etoiles", texte: etoiles(x.fait) }) : `${x.fait.justes}/${x.fait.questions}`, " Rejouer")
      : el("span", { class: "etat a-faire", texte: "À faire" });
    const b = el("button", { type: "button", class: "exo" },
      el("span", { class: "icone", "aria-hidden": "true", texte: section === "a_retravailler" ? "!" : section === "plus_loin" ? "↗" : "QCM" }),
      el("span", {}, el("h3", { texte: x.titre || x.exercice }), el("p", { texte: detail })), etiquette);
    b.addEventListener("click", () => { location.href = `/exercice/${encodeURIComponent(x.exercice)}`; });
    return b;
  }

  async function accueil() {
    const { statut, donnees } = await api("/api/accueil");
    if (statut !== 200) { classes("Tu as été déconnecté (10 minutes sans rien faire). Reconnecte-toi."); return; }
    etat.eleve = donnees.eleve;
    style(donnees.eleve.niveau);
    informer("");
    $("#accueil-bonjour").textContent = `Bonjour ${donnees.eleve.prenom} !`;
    $("#accueil-classe").textContent = `${donnees.eleve.classe}. Voici tes exercices.`;
    let total = 0;
    for (const section of ["a_retravailler", "plus_loin", "exercices"]) {
      const liste = donnees[section] || [];
      total += liste.length;
      const bloc = $(`#sec-${section}`);
      bloc.hidden = liste.length === 0;
      bloc.querySelector(".compte").textContent = String(liste.length);
      bloc.querySelector(".exos").replaceChildren(...liste.map((x) => carteExercice(x, section)));
    }
    $("#accueil-vide").hidden = total > 0;
    afficher("accueil", "#accueil-bonjour");
  }

  async function seDeconnecter(puis) {
    await api("/api/session", {}, "DELETE");
    puis();
  }

  // --- démarrage ---
  document.addEventListener("DOMContentLoaded", async () => {
    $("#noms-retour").addEventListener("click", () => classes());
    $("#code-retour").addEventListener("click", () => noms(etat.classe));
    $("#effacer").addEventListener("click", () => { etat.saisi.pop(); cases(); });
    $("#code-mdp").addEventListener("submit", (e) => {
      e.preventDefault();
      if (!etat.bloque && $("#mdp").value.trim()) envoyerCode($("#mdp").value);
    });
    $("#afficher").addEventListener("click", () => {
      const voir = $("#mdp").type === "password";
      $("#mdp").type = voir ? "text" : "password";
      $("#afficher").textContent = voir ? "Masquer" : "Afficher";
      $("#afficher").setAttribute("aria-pressed", String(voir));
    });
    $("#fini").addEventListener("click", () => seDeconnecter(() => classes("À bientôt !")));
    $("#pas-moi").addEventListener("click", () => {
      const classe = etat.classe || (etat.eleve && { id: etat.eleve.classe_id });
      seDeconnecter(() => (classe ? noms(classe) : classes()));
    });
    const { statut } = await api("/api/session");
    if (statut === 200) accueil(); else classes();
  });
})();
