// Interface enseignant (phase 3). Aucune dépendance : le PC enseignant peut être hors ligne.
// Règle de sécurité : tout texte venant du modèle est inséré avec textContent, jamais comme du HTML.
"use strict";

(() => {
  const MATIERES = {
    "maths": "Mathématiques", "francais": "Français", "histoire-geo": "Histoire-géographie", "svt": "SVT",
    "physique-chimie": "Physique-chimie", "anglais": "Anglais", "technologie": "Technologie",
  };
  const STATUTS = { genere: "À relire", accepte: "Accepté", rejete: "Rejeté" };
  const SOURCES = { modele: "proposé par le modèle : à vérifier", devine: "deviné dans la phrase : à vérifier" };
  const N4 = { verifie: "✔ calcul vérifié", a_relire: "? à relire", faux: "✘ calcul faux" };
  const INTERVALLE_MS = 1000;
  const ATTENTE_RECHERCHE_MS = 250;

  // origine : la vue d'où l'on a ouvert l'exercice, pour le lien « Retour »
  // statut, valide, occupe : ceux de l'exercice ouvert, pour l'état des boutons
  // donnees : la dernière réponse de /api/exercices/{id}, pour remplir le formulaire de modification
  const etat = { types: [], suivi: null, exercice: null, regeneration: null, origine: "banque",
    statut: null, valide: true, occupe: false, donnees: null, recherche: null, annonce: null };
  const $ = (selecteur) => document.querySelector(selecteur);

  // --- outils -----------------------------------------------------------------------------------

  function el(balise, attributs = {}, ...enfants) {
    const e = document.createElement(balise);
    for (const [cle, valeur] of Object.entries(attributs)) {
      if (valeur === undefined || valeur === null || valeur === false) continue;
      if (cle === "class") e.className = valeur;
      else if (cle === "texte") e.textContent = valeur;
      else e.setAttribute(cle, valeur === true ? "" : valeur);
    }
    for (const enfant of enfants) if (enfant !== null && enfant !== undefined) e.append(enfant);
    return e;
  }

  async function api(chemin, corps, methode = corps === undefined ? "GET" : "POST") {
    const init = { method: methode, headers: { Accept: "application/json" } };
    if (methode !== "GET") init.headers["Content-Type"] = "application/json"; // exigé par le serveur (requêtes intersites)
    if (corps !== undefined) init.body = JSON.stringify(corps);
    let reponse;
    try {
      reponse = await fetch(chemin, init);
    } catch (_) {
      throw new Error("le serveur ne répond pas : est-il toujours lancé ?");
    }
    let donnees = null;
    try { donnees = await reponse.json(); } catch (_) { /* corps vide ou non JSON */ }
    if (!reponse.ok) throw new Error(messageErreur(donnees, reponse.status));
    return donnees;
  }

  function messageErreur(donnees, statut) {
    const detail = donnees && donnees.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((e) => `${(e.loc || []).slice(1).join(".") || "requête"} : ${e.msg}`).join(" ; ");
    }
    return `erreur ${statut}`;
  }

  function date(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString("fr-FR") + " " + d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  }

  function duree(secondes) {
    if (secondes === undefined || secondes === null) return "";
    if (secondes < 60) return `${Math.round(secondes)} s`;
    return `${Math.floor(secondes / 60)} min ${String(Math.round(secondes % 60)).padStart(2, "0")} s`;
  }

  function remplirSelect(select, valeurs, libelles = {}, vide = null) {
    select.replaceChildren();
    if (vide !== null) select.append(el("option", { value: "", texte: vide }));
    for (const v of valeurs) select.append(el("option", { value: v, texte: libelles[v] || v }));
  }

  // --- navigation ---------------------------------------------------------------------------------

  function afficherVue(nom) {
    for (const vue of document.querySelectorAll(".vue")) vue.hidden = vue.id !== `vue-${nom}`;
    for (const lien of document.querySelectorAll("nav a")) {
      if (lien.dataset.vue === nom) lien.setAttribute("aria-current", "page");
      else lien.removeAttribute("aria-current");
    }
  }

  function router() {
    const m = location.hash.match(/^#\/exercice\/([a-z0-9_-]+)$/);
    if (m) {
      afficherVue("exercice");
      ouvrirExercice(m[1]);
    } else if (location.hash === "#/banque") {
      etat.origine = "banque";
      afficherVue("banque");
      chargerBanque();
    } else {
      etat.origine = "generer";
      afficherVue("generer");
    }
  }

  // --- 1. analyser la demande -------------------------------------------------------------------

  async function analyser(evenement) {
    evenement.preventDefault();
    const phrase = $("#phrase").value.trim();
    const message = $("#analyse-etat");
    if (!phrase) {
      message.textContent = "Écrivez d'abord votre demande.";
      $("#phrase").focus();
      return;
    }
    $("#btn-analyser").disabled = true;
    message.textContent = "Analyse en cours…";
    try {
      const resultat = await api("/api/analyser", { phrase });
      remplirFormulaire(resultat);
      message.textContent = resultat.duree_modele_s
        ? `Analyse terminée (le modèle a complété en ${duree(resultat.duree_modele_s)}).`
        : "Analyse terminée.";
    } catch (e) {
      message.textContent = `Analyse impossible : ${e.message}`;
    } finally {
      $("#btn-analyser").disabled = false;
    }
  }

  function remplirFormulaire(resultat) {
    const r = resultat.requete;
    $("#type").value = r.type || "qcm";
    choisirType();
    $("#matiere").value = r.matiere || "";
    $("#niveau").value = r.niveau || "";
    $("#notion").value = r.notion || "";
    $("#nb_questions").value = r.nb_questions || 5;
    $("#difficulte").value = r.difficulte || "";
    $("#precisions").value = r.demande_enseignant || "";
    for (const champ of document.querySelectorAll("#form-requete .champ")) {
      const nom = champ.dataset.champ;
      const source = champ.querySelector(".source");
      const aVerifier = (resultat.a_verifier || []).includes(nom);
      champ.classList.toggle("a-verifier", aVerifier);
      const manque = nom === "notion" ? "à écrire" : "à choisir";
      if (source) source.textContent = aVerifier ? (SOURCES[resultat.sources[nom]] || manque) : "";
    }
    const remarques = $("#remarques");
    remarques.replaceChildren(...(resultat.remarques || []).map((t) => el("li", { texte: t })));
    const chemin = $("#chemin");
    if (resultat.procedural) {
      chemin.textContent = `Calculs faits par le programme (${resultat.procedural.notion}) : réponses justes par ` +
        "construction. Le modèle ne fait que réécrire certains énoncés.";
    } else {
      chemin.textContent = "Exercice rédigé par le modèle, puis contrôlé automatiquement (N1 → N4). " +
        "Hors mathématiques, le fond reste à relire par vous.";
    }
    chemin.hidden = false;
    montrerFormulaire();
  }

  function remplirALaMain() {
    remplirFormulaire({
      requete: { type: "qcm", nb_questions: 5, demande_enseignant: $("#phrase").value.trim() || null },
      sources: {}, a_verifier: [], remarques: [], procedural: null,
    });
    $("#chemin").hidden = true;
    $("#matiere").focus();
  }

  function montrerFormulaire() {
    const formulaire = $("#form-requete");
    formulaire.hidden = false;
    $("#requete-erreur").hidden = true;
    formulaire.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function choisirType() {
    const type = etat.types.find((t) => t.nom === $("#type").value) || etat.types[0];
    if (!type) return;
    const matiere = $("#matiere").value;
    const niveau = $("#niveau").value;
    remplirSelect($("#matiere"), type.matieres, MATIERES, "— choisir —");
    remplirSelect($("#niveau"), type.niveaux, {}, "— choisir —");
    $("#matiere").value = matiere;
    $("#niveau").value = niveau;
    $("#nb_questions").min = type.questions_min;
    $("#nb_questions").max = type.questions_max;
  }

  // --- 2. générer -------------------------------------------------------------------------------

  async function generer(evenement) {
    evenement.preventDefault();
    const erreur = $("#requete-erreur");
    const formulaire = $("#form-requete");
    if (!formulaire.checkValidity()) {
      const invalide = formulaire.querySelector(":invalid");
      const libelle = invalide && formulaire.querySelector(`label[for="${invalide.id}"]`);
      erreur.textContent = `À compléter : ${libelle ? libelle.textContent : "un champ"}.`;
      erreur.hidden = false;
      if (invalide) invalide.focus();
      return;
    }
    erreur.hidden = true;
    const nombre = parseInt($("#nb_questions").value, 10);
    const corps = {
      type: $("#type").value,
      matiere: $("#matiere").value || null,
      niveau: $("#niveau").value || null,
      notion: $("#notion").value.trim() || null,
      nb_questions: Number.isNaN(nombre) ? null : nombre,
      difficulte: $("#difficulte").value || null,
      demande_enseignant: $("#precisions").value.trim() || null,
    };
    $("#btn-generer").disabled = true;
    try {
      const tache = await api("/api/generations", corps);
      suivreGeneration(tache);
    } catch (e) {
      erreur.textContent = `Génération impossible : ${e.message}`;
      erreur.hidden = false;
      $("#btn-generer").disabled = false;
    }
  }

  function suivreGeneration(tache) {
    clearTimeout(etat.suivi);
    $("#progression").hidden = false;
    $("#prog-erreur").hidden = true;
    $("#btn-generer").disabled = true;
    afficherProgression(tache);
    if (tache.etat === "en_attente" || tache.etat === "en_cours") {
      const relire = async () => {
        try {
          const vue = await api(`/api/generations/${tache.id}`);
          afficherProgression(vue);
          if (vue.etat === "en_attente" || vue.etat === "en_cours") etat.suivi = setTimeout(relire, INTERVALLE_MS);
          else finGeneration(vue);
        } catch (e) {
          $("#prog-message").textContent = `Suivi interrompu : ${e.message}`;
          $("#btn-generer").disabled = false;
        }
      };
      etat.suivi = setTimeout(relire, INTERVALLE_MS);
    } else {
      finGeneration(tache);
    }
  }

  function afficherProgression(vue) {
    const p = vue.progression || {};
    const barre = $("#prog-barre");
    let message = p.message || "Démarrage…";
    if (vue.etat === "en_attente") {
      message = vue.devant ? `En attente : ${vue.devant} génération(s) avant celle-ci.` : "En attente…";
    }
    $("#prog-message").textContent = message;
    if (p.sur && p.question) {
      barre.max = p.sur;
      barre.value = Math.min(p.question, p.sur);
      barre.textContent = `question ${p.question} sur ${p.sur}`;
    } else if (vue.etat === "termine") {
      barre.max = 1;
      barre.value = 1;
    } else {
      barre.removeAttribute("value"); // barre indéterminée : lecture de la demande, vérification…
    }
    $("#prog-temps").textContent = vue.ecoule_s !== undefined ? `Temps écoulé : ${duree(vue.ecoule_s)}` : "";
    $("#prog-journal").replaceChildren(
      ...(vue.journal || []).map((j) => el("li", {}, el("span", { class: "temps", texte: duree(j.t) }), " ", j.message)));
  }

  function finGeneration(vue) {
    $("#btn-generer").disabled = false;
    if (vue.etat === "termine" && vue.exercice) {
      const lien = el("a", { href: `#/exercice/${vue.exercice}`, texte: "ouvrir la relecture" });
      $("#prog-message").replaceChildren("Exercice prêt : ", lien, ".");
      if (!$("#vue-generer").hidden) location.hash = `#/exercice/${vue.exercice}`;
      return;
    }
    const bloc = $("#prog-erreur");
    const erreur = vue.erreur || { message: "échec inconnu" };
    bloc.replaceChildren(el("p", { texte: erreur.message }));
    if (erreur.erreurs && erreur.erreurs.length) {
      bloc.append(el("ul", {}, ...erreur.erreurs.map((m) => el("li", { texte: m }))));
    }
    bloc.append(el("p", { texte: "Vous pouvez modifier la demande ci-dessus et relancer la génération." }));
    bloc.hidden = false;
  }

  async function reprendreSuivi() {
    // la page a été rechargée pendant une génération : on la retrouve
    try {
      const { taches } = await api("/api/generations");
      const encours = taches.find((t) => t.nature === "generation" && (t.etat === "en_cours" || t.etat === "en_attente"));
      if (encours) suivreGeneration(encours);
    } catch (_) { /* rien à reprendre */ }
  }

  // --- banque -----------------------------------------------------------------------------------

  async function chargerBanque() {
    const parametres = new URLSearchParams();
    for (const [cle, id] of [["matiere", "#filtre-matiere"], ["niveau", "#filtre-niveau"], ["statut", "#filtre-statut"],
      ["recherche", "#filtre-recherche"]]) {
      if ($(id).value.trim()) parametres.set(cle, $(id).value.trim());
    }
    const message = $("#banque-etat");
    message.textContent = "Chargement…";
    try {
      const { exercices } = await api(`/api/exercices?${parametres}`);
      const lignes = exercices.map((x) => el("tr", {},
        el("td", { texte: date(x.date) }),
        el("td", {}, el("a", { href: `#/exercice/${x.id}`, texte: x.titre || x.id }),
          x.notion ? el("span", { class: "sous-titre", texte: x.notion }) : null),
        el("td", { texte: MATIERES[x.matiere] || x.matiere || "—" }),
        el("td", { texte: x.niveau || "—" }),
        el("td", { class: "nombre", texte: String(x.questions) }),
        el("td", { texte: x.origine === "procedural" ? "programme" : "modèle" }),
        el("td", {}, controles(x)),
        el("td", {}, badgeStatut(x.statut))));
      $("#table-banque tbody").replaceChildren(...lignes);
      const compte = exercices.length ? `${exercices.length} exercice(s).` : "Aucun exercice ne correspond.";
      message.textContent = etat.annonce ? `${etat.annonce} ${compte}` : compte;
      etat.annonce = null;
    } catch (e) {
      message.textContent = `Banque illisible : ${e.message}`;
    }
  }

  function controles(x) {
    if (x.a_corriger) return el("span", { class: "badge n4-faux", texte: `✘ ${x.a_corriger} à corriger` });
    if (x.a_relire) return el("span", { class: "badge n4-a_relire", texte: `? ${x.a_relire} à relire` });
    return el("span", { class: "badge n4-verifie", texte: "✔" });
  }

  function badgeStatut(statut) {
    return el("span", { class: `badge statut-${statut}`, texte: STATUTS[statut] || statut });
  }

  // --- exercice : relecture, aperçu, décision ---------------------------------------------------

  async function ouvrirExercice(ident, garderMessage = false) {
    if (!garderMessage) $("#ex-message").textContent = "";
    let donnees;
    try {
      donnees = await api(`/api/exercices/${ident}`);
    } catch (e) {
      if (location.hash !== `#/exercice/${ident}`) return;
      viderExercice();
      $("#ex-titre").textContent = "Exercice introuvable";
      $("#ex-message").textContent = e.message;
      return;
    }
    // l'enseignant a ouvert un autre exercice pendant le chargement : la réponse arrivée en retard est ignorée
    if (location.hash !== `#/exercice/${ident}`) return;
    etat.exercice = ident;
    etat.donnees = donnees;
    $("#ex-actions").hidden = false;
    const { exercice: x, resume, relecture } = donnees;
    const meta = x.meta || {};
    $("#ex-titre").textContent = x.titre || ident;
    $("#ex-statut").replaceWith(Object.assign(badgeStatut(resume.statut), { id: "ex-statut" }));
    const origine = meta.origine === "procedural"
      ? `générateur procédural (${meta.generateur})` + (meta.modele ? `, énoncés réécrits par ${meta.modele}` : "")
      : `modèle ${meta.modele || "?"}`;
    $("#ex-infos").textContent = [MATIERES[x.matiere] || x.matiere, x.niveau, x.notion,
      `${x.questions.length} questions`, origine, meta.duree_s !== undefined ? `généré en ${duree(meta.duree_s)}` : null,
      meta.tentatives > 1 ? `${meta.tentatives} tentatives` : null, date(meta.date)].filter(Boolean).join(" · ");
    afficherValidation(x, relecture);
    afficherQuestions(x, relecture);
    $("#ex-apercu").src = `/api/exercices/${ident}/apercu?v=${Date.now()}`;
    $("#btn-telecharger").href = `/api/exercices/${ident}/telecharger`;
    $("#btn-telecharger").setAttribute("download", `${ident}.html`);
    $("#ex-retour").href = `#/${etat.origine}`;
    $("#ex-retour").textContent = etat.origine === "generer" ? "← Retour à la demande" : "← Retour à la banque";
    etat.statut = resume.statut;
    etat.valide = relecture.valide;
    occuper(donnees.occupe);
    if (!garderMessage) $("#ex-titre").focus();
    if (donnees.occupe && !etat.regeneration) reprendreRegeneration(ident);
  }

  function viderExercice() {
    etat.exercice = null;
    etat.donnees = null;
    for (const id of ["#ex-infos", "#ex-validation", "#ex-avertissements", "#ex-questions"]) $(id).replaceChildren();
    $("#ex-erreurs").hidden = true;
    $("#ex-actions").hidden = true;
    $("#ex-regeneration").hidden = true;
    $("#ex-statut").replaceWith(el("span", { id: "ex-statut", class: "badge", hidden: true }));
    $("#ex-apercu").removeAttribute("src");
  }

  function afficherValidation(x, relecture) {
    // contrôles refaits par le serveur avec les règles du jour : un exercice ancien peut contenir une erreur
    // que son verdict d'origine ignorait
    const bloc = $("#ex-erreurs");
    if (relecture.valide) {
      bloc.hidden = true;
    } else {
      bloc.replaceChildren(
        el("p", {}, el("strong", { texte: "Cet exercice contient une erreur détectée par les contrôles actuels." })),
        el("ul", {}, ...relecture.questions.flatMap((q) => q.erreurs).concat(relecture.erreurs)
          .map((m) => el("li", { texte: m }))),
        el("p", { texte: "Modifiez ou régénérez la question concernée ; l'exercice ne peut pas être accepté en l'état." }));
      bloc.hidden = false;
    }
    const verifiees = relecture.questions.filter((q) => q.n4 === "verifie").length;
    const faux = relecture.questions.filter((q) => q.n4 === "faux").length;
    let n4;
    if (faux) n4 = `N4 : ${faux} calcul(s) faux`;
    else if (relecture.procedural) n4 = "N4 : calculs faits par le programme, justes par construction";
    else if (x.matiere !== "maths") n4 = "N4 : hors mathématiques, aucun calcul à recalculer — le fond est à relire par vous";
    else if (relecture.a_relire) n4 = `N4 : ${verifiees} calcul(s) vérifié(s), ${relecture.a_relire} question(s) à relire`;
    else n4 = `N4 : ${verifiees} calcul(s) recalculé(s) et juste(s)`;
    const n3 = !(relecture.niveau || "").includes("N3");
    const n4ok = relecture.procedural || (x.matiere === "maths" && !relecture.a_relire);
    const lignes = [
      ["ok", "N1 : réponse lisible (JSON)"],
      ["ok", "N2 : conforme au format de l'exercice"],
      [n3 ? "ok" : "faux", "N3 : cohérence pédagogique (pas de doublon, une seule bonne réponse…)"],
      [faux ? "faux" : (n4ok ? "ok" : "a-relire"), n4],
    ];
    const symboles = { ok: "✔ ", faux: "✘ ", "a-relire": "? " };
    $("#ex-validation").replaceChildren(...lignes.map(([classe, texte]) =>
      el("li", { class: classe }, el("span", { "aria-hidden": "true", texte: symboles[classe] }), texte)));
    const avertissements = relecture.avertissements || [];
    $("#ex-avertissements").replaceChildren(...avertissements.map((a) => el("p", { class: "avertissement", texte: `⚠ ${a}` })));
  }

  function afficherQuestions(x, relecture) {
    const items = x.questions.map((q, i) => {
      const info = relecture.questions[i] || {};
      const badges = el("span", { class: "badges" });
      if (info.erreurs && info.erreurs.length) badges.append(el("span", { class: "badge n4-faux", texte: "✘ à corriger" }));
      if (info.calcul === "programme" && info.n4 !== "faux") {
        badges.append(el("span", { class: "badge n4-verifie", texte: "✔ calcul fait par le programme" }));
      } else if (info.calcul === "enseignant" && info.n4 === "a_relire") {
        // écrite par l'enseignant : rien à relire de plus ; seul un calcul faux ou vérifié par N4 est signalé
      } else if (info.n4) {
        badges.append(el("span", { class: `badge n4-${info.n4}`, texte: N4[info.n4] || info.n4 }));
      }
      if (info.calcul === "programme" && info.enonce === "modele") {
        badges.append(el("span", { class: "badge", texte: "énoncé réécrit par le modèle" }));
      }
      if (info.regeneree) badges.append(el("span", { class: "badge", texte: "régénérée" }));
      if (info.modifiee) badges.append(el("span", { class: "badge", texte: "modifiée à la main" }));
      const propositions = el("ul", { class: "propositions" }, ...q.propositions.map((p, j) => {
        const juste = j === q.index_correct;
        return el("li", { class: juste ? "juste" : null },
          el("span", { class: "marque", "aria-hidden": "true", texte: juste ? "✔" : "" }),
          el("span", { texte: p }),
          juste ? el("span", { class: "visuellement-cache", texte: " (bonne réponse)" }) : null);
      }));
      const boutons = el("div", { class: "question-actions" },
        el("button", { type: "button", class: "secondaire petit modifier", "data-numero": String(i + 1),
          texte: "Modifier" }),
        el("button", { type: "button", class: "secondaire petit regenerer", "data-numero": String(i + 1),
          texte: "Régénérer cette question" }));
      return el("li", { class: "question", id: `question-${i + 1}`, tabindex: "-1" },
        el("div", { class: "question-entete" }, el("h3", { texte: `Question ${i + 1}` }), badges),
        el("p", { class: "enonce", texte: q.enonce }),
        propositions,
        el("p", { class: "explication" }, el("strong", { texte: "Explication : " }), q.explication),
        ...(info.erreurs || []).map((a) => el("p", { class: "erreur", texte: `✘ ${a}` })),
        ...(info.avertissements || []).map((a) => el("p", { class: "avertissement", texte: `⚠ ${a}` })),
        boutons);
    });
    $("#ex-questions").replaceChildren(...items);
  }

  // --- modifier une question à la main ----------------------------------------------------------

  const PROPOSITIONS_MAX = 4;

  function ouvrirEdition(numero) {
    const q = etat.donnees && etat.donnees.exercice.questions[numero - 1];
    const item = document.getElementById(`question-${numero}`);
    if (!q || !item) return;
    const ouverte = document.querySelector("form.edition");
    if (ouverte) fermerEdition(ouverte);
    const lignes = [];
    for (let j = 0; j < PROPOSITIONS_MAX; j++) {
      const id = `edit-prop-${numero}-${j}`;
      lignes.push(el("div", { class: "proposition-edit" },
        el("input", { type: "radio", name: `juste-${numero}`, value: String(j), checked: j === q.index_correct,
          "aria-label": `Proposition ${j + 1} : bonne réponse` }),
        el("input", { type: "text", id, maxlength: "150", value: q.propositions[j] || "",
          "aria-label": `Proposition ${j + 1}` + (j >= 3 ? " (facultative)" : "") })));
    }
    const formulaire = el("form", { class: "edition", "data-numero": String(numero), novalidate: true },
      el("div", {}, el("label", { for: `edit-enonce-${numero}`, texte: "Énoncé" }),
        el("textarea", { id: `edit-enonce-${numero}`, rows: "3", maxlength: "300", texte: q.enonce })),
      el("fieldset", {}, el("legend", { texte: "Propositions" }),
        el("p", { class: "aide", texte: "Cochez la bonne réponse. 3 ou 4 propositions : laissez la 4e vide pour n'en garder que 3." }),
        ...lignes),
      el("div", {}, el("label", { for: `edit-explication-${numero}`, texte: "Explication" }),
        el("textarea", { id: `edit-explication-${numero}`, rows: "3", maxlength: "400", texte: q.explication })),
      el("p", { class: "erreur", role: "alert", hidden: true }),
      el("div", { class: "actions" },
        el("button", { type: "submit", texte: "Enregistrer" }),
        el("button", { type: "button", class: "secondaire annuler-edition", texte: "Annuler" })),
      el("p", { class: "note", texte: "La question est revérifiée (N2 → N4) avant d'être enregistrée ; l'exercice sera à accepter de nouveau." }));
    for (const enfant of item.children) if (!enfant.matches(".question-entete")) enfant.hidden = true;
    item.append(formulaire);
    formulaire.querySelector("textarea").focus();
  }

  function fermerEdition(formulaire) {
    const item = formulaire.closest(".question");
    formulaire.remove();
    for (const enfant of item.children) enfant.hidden = false;
  }

  async function enregistrerEdition(formulaire) {
    const numero = parseInt(formulaire.dataset.numero, 10);
    const erreur = formulaire.querySelector(".erreur");
    const montrer = (texte) => { erreur.textContent = texte; erreur.hidden = false; };
    const textes = [...formulaire.querySelectorAll(".proposition-edit input[type=text]")].map((i) => i.value.trim());
    const cochee = formulaire.querySelector(".proposition-edit input[type=radio]:checked");
    if (!cochee) return montrer("Cochez la bonne réponse.");
    if (!textes[parseInt(cochee.value, 10)]) return montrer("La bonne réponse cochée est vide.");
    // les propositions vides sont retirées ; l'indice de la bonne réponse suit
    const propositions = [];
    let indexCorrect = 0;
    textes.forEach((texte, j) => {
      if (!texte) return;
      if (j === parseInt(cochee.value, 10)) indexCorrect = propositions.length;
      propositions.push(texte);
    });
    const corps = {
      enonce: formulaire.querySelector(`#edit-enonce-${numero}`).value.trim(),
      propositions, index_correct: indexCorrect,
      explication: formulaire.querySelector(`#edit-explication-${numero}`).value.trim(),
    };
    const bouton = formulaire.querySelector("button[type=submit]");
    bouton.disabled = true;
    try {
      await api(`/api/exercices/${etat.exercice}/questions/${numero}`, corps, "PUT");
    } catch (e) {
      montrer(e.message.charAt(0).toUpperCase() + e.message.slice(1));
      bouton.disabled = false;
      return;
    }
    $("#ex-message").textContent = `Question ${numero} modifiée. L'exercice est à accepter de nouveau.`;
    await ouvrirExercice(etat.exercice, true);
    const question = document.getElementById(`question-${numero}`);
    if (question) {
      question.classList.add("nouvelle");
      question.focus({ preventScroll: true });
    }
  }

  function occuper(occupe) {
    etat.occupe = Boolean(occupe);
    for (const b of document.querySelectorAll(".regenerer, .modifier")) b.disabled = etat.occupe;
    $("#btn-accepter").disabled = etat.occupe || !etat.valide || etat.statut === "accepte";
    $("#btn-rejeter").disabled = etat.occupe || etat.statut === "rejete";
    $("#btn-supprimer").disabled = etat.occupe || etat.statut === "accepte";
    $("#btn-accepter").title = etat.valide ? "" : "L'exercice contient une erreur : modifiez ou régénérez la question concernée";
    $("#btn-supprimer").title = etat.statut === "accepte" ? "Un exercice accepté doit d'abord être rejeté" : "";
  }

  async function decider(decision, motif = null) {
    const message = $("#ex-message");
    try {
      const { resume } = await api(`/api/exercices/${etat.exercice}/decision`, { decision, motif });
      $("#ex-statut").replaceWith(Object.assign(badgeStatut(resume.statut), { id: "ex-statut" }));
      etat.statut = resume.statut;
      occuper(etat.occupe);
      message.textContent = decision === "accepter"
        ? "Exercice accepté : il pourra être publié vers les postes élèves."
        : "Exercice rejeté. Il reste dans la banque, avec votre motif.";
    } catch (e) {
      message.textContent = `Décision non enregistrée : ${e.message}`;
    }
  }

  async function supprimer() {
    const ident = etat.exercice;
    const titre = $("#ex-titre").textContent;
    const ok = await demander({ titre: "Supprimer l'exercice", ok: "Supprimer", champ: false,
      texte: `« ${titre} » sera retiré de la banque. Il reste récupérable dans le dossier banque/supprimes/ du serveur.` });
    if (ok === null) return;
    try {
      await api(`/api/exercices/${ident}`, undefined, "DELETE");
    } catch (e) {
      $("#ex-message").textContent = `Suppression impossible : ${e.message}`;
      return;
    }
    etat.annonce = `« ${titre} » supprimé.`; // affiché par la banque, qui s'ouvre
    location.hash = "#/banque";
  }

  async function regenerer(numero, motif) {
    const message = $("#ex-message");
    try {
      const tache = await api(`/api/exercices/${etat.exercice}/questions/${numero}/regenerer`, { motif });
      suivreRegeneration(tache, numero);
    } catch (e) {
      message.textContent = `Régénération impossible : ${e.message}`;
    }
  }

  function suivreRegeneration(tache, numero) {
    const ident = etat.exercice;
    etat.regeneration = tache.id;
    occuper(true);
    const bloc = $("#ex-regeneration");
    bloc.hidden = false;
    const afficher = (vue) => {
      const p = vue.progression || {};
      const texte = vue.etat === "en_attente" && vue.devant
        ? `Question ${numero} : en attente (${vue.devant} tâche(s) avant).`
        : `Question ${numero} : ${p.message || "démarrage…"}`;
      const lignes = [el("p", { texte })];
      if (vue.ecoule_s !== undefined) lignes.push(el("p", { class: "note", texte: `Temps écoulé : ${duree(vue.ecoule_s)}` }));
      bloc.replaceChildren(...lignes);
    };
    afficher(tache);
    const relire = async () => {
      let vue;
      try {
        vue = await api(`/api/generations/${tache.id}`);
      } catch (e) {
        bloc.replaceChildren(el("p", { class: "erreur", texte: `Suivi interrompu : ${e.message}` }));
        etat.regeneration = null;
        occuper(false);
        return;
      }
      if (etat.exercice !== ident) { etat.regeneration = null; return; } // l'enseignant est allé ailleurs
      afficher(vue);
      if (vue.etat === "en_attente" || vue.etat === "en_cours") {
        setTimeout(relire, INTERVALLE_MS);
        return;
      }
      etat.regeneration = null;
      if (vue.etat === "termine") {
        bloc.hidden = true;
        $("#ex-message").textContent = `Question ${numero} remplacée. L'exercice est à accepter de nouveau.`;
        await ouvrirExercice(ident, true);
        const question = document.getElementById(`question-${numero}`);
        if (question) {
          question.classList.add("nouvelle");
          question.scrollIntoView({ behavior: "smooth", block: "center" });
          question.focus({ preventScroll: true });
        }
      } else {
        const erreur = vue.erreur || { message: "échec" };
        bloc.replaceChildren(el("p", { class: "erreur", texte: erreur.message }),
          ...(erreur.erreurs || []).map((m) => el("p", { class: "note", texte: m })),
          el("p", { texte: "La question d'origine est conservée." }));
        occuper(false);
      }
    };
    setTimeout(relire, INTERVALLE_MS);
  }

  async function reprendreRegeneration(ident) {
    try {
      const { taches } = await api("/api/generations");
      const t = taches.find((x) => x.nature === "regeneration" && x.exercice === ident &&
        (x.etat === "en_cours" || x.etat === "en_attente"));
      if (t) suivreRegeneration(t, (t.description.match(/Question (\d+)/) || [])[1] || "?");
    } catch (_) { /* rien à reprendre */ }
  }

  // --- boîte de dialogue (motif d'un rejet, d'une régénération) -----------------------------------

  // champ : false pour une simple confirmation (la promesse donne alors "" si confirmé, null si annulé)
  function demander({ titre, texte, label = "", ok, champ = true }) {
    const dialogue = $("#dialogue");
    $("#dialogue-titre").textContent = titre;
    $("#dialogue-texte").textContent = texte;
    $("#dialogue-champ").hidden = !champ;
    $("#dialogue-label").textContent = label;
    $("#dialogue-ok").textContent = ok;
    $("#dialogue-motif").value = "";
    return new Promise((resoudre) => {
      const fermer = (valeur) => {
        $("#dialogue-form").onsubmit = null;
        $("#dialogue-annuler").onclick = null;
        dialogue.onclose = null;
        if (dialogue.open) dialogue.close();
        resoudre(valeur);
      };
      $("#dialogue-form").onsubmit = (e) => { e.preventDefault(); fermer($("#dialogue-motif").value.trim()); };
      $("#dialogue-annuler").onclick = () => fermer(null);
      dialogue.onclose = () => fermer(null);
      dialogue.showModal();
      (champ ? $("#dialogue-motif") : $("#dialogue-ok")).focus();
    });
  }

  // --- démarrage --------------------------------------------------------------------------------

  async function demarrer() {
    $("#form-phrase").addEventListener("submit", analyser);
    $("#btn-a-la-main").addEventListener("click", remplirALaMain);
    $("#form-requete").addEventListener("submit", generer);
    $("#type").addEventListener("change", choisirType);
    for (const id of ["#notion", "#matiere", "#precisions"]) {
      // le chemin annoncé (programme ou modèle) dépend de la demande : il n'est plus sûr si elle change
      $(id).addEventListener("input", () => { $("#chemin").hidden = true; });
    }
    $("#filtres").addEventListener("change", chargerBanque);
    $("#filtres").addEventListener("submit", (e) => { e.preventDefault(); chargerBanque(); });
    $("#filtre-recherche").addEventListener("input", () => {
      clearTimeout(etat.recherche);
      etat.recherche = setTimeout(chargerBanque, ATTENTE_RECHERCHE_MS);
    });
    $("#btn-accepter").addEventListener("click", () => decider("accepter"));
    $("#btn-rejeter").addEventListener("click", async () => {
      const motif = await demander({ titre: "Rejeter l'exercice", label: "Motif (facultatif)", ok: "Rejeter",
        texte: "L'exercice restera dans la banque, marqué « rejeté ». Votre motif aide à améliorer le générateur." });
      if (motif !== null) decider("rejeter", motif || null);
    });
    $("#btn-supprimer").addEventListener("click", supprimer);
    $("#ex-questions").addEventListener("submit", (e) => {
      if (!e.target.matches("form.edition")) return;
      e.preventDefault();
      enregistrerEdition(e.target);
    });
    $("#ex-questions").addEventListener("click", async (e) => {
      const annuler = e.target.closest(".annuler-edition");
      if (annuler) { fermerEdition(annuler.closest("form.edition")); return; }
      const modifier = e.target.closest(".modifier");
      if (modifier && !modifier.disabled) { ouvrirEdition(parseInt(modifier.dataset.numero, 10)); return; }
      const bouton = e.target.closest(".regenerer");
      if (!bouton || bouton.disabled) return;
      const numero = bouton.dataset.numero;
      const motif = await demander({ titre: `Régénérer la question ${numero}`, label: "Ce qui ne va pas (facultatif)",
        ok: "Régénérer", texte: "Seule cette question sera remplacée ; les autres ne changent pas." });
      if (motif !== null) regenerer(numero, motif || null);
    });
    window.addEventListener("hashchange", router);

    try {
      const { types } = await api("/api/types");
      etat.types = types;
      remplirSelect($("#type"), types.map((t) => t.nom), Object.fromEntries(types.map((t) => [t.nom, t.titre])));
      choisirType();
      const premier = types[0] || { matieres: [], niveaux: [] };
      remplirSelect($("#filtre-matiere"), premier.matieres, MATIERES, "Toutes");
      remplirSelect($("#filtre-niveau"), premier.niveaux, {}, "Toutes");
    } catch (e) {
      $("#analyse-etat").textContent = `Le serveur ne répond pas : ${e.message}`;
    }
    router();
    reprendreSuivi();
  }

  document.addEventListener("DOMContentLoaded", demarrer);
})();
