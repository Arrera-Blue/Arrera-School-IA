// Interface enseignant (phase 3 ; connexion et comptes : E1). Aucune dépendance : le PC enseignant peut être
// hors ligne. Règle de sécurité : tout texte venant du modèle est inséré avec textContent, jamais comme du HTML ;
// un mot de passe ne reste jamais dans la page après usage.
"use strict";

(() => {
  const MATIERES = {
    "maths": "Mathématiques", "francais": "Français", "histoire-geo": "Histoire-géographie", "svt": "SVT",
    "physique-chimie": "Physique-chimie", "anglais": "Anglais", "technologie": "Technologie",
  };
  const STATUTS = { genere: "À relire", accepte: "Accepté", rejete: "Rejeté" };
  const SOURCES = { modele: "proposé par le modèle : à vérifier", devine: "deviné dans la phrase : à vérifier" };
  const N4 = { verifie: "✔ calcul vérifié", a_relire: "? à relire", faux: "✘ calcul faux" };
  const ROLES = { admin: "Administrateur", enseignant: "Enseignant" };
  const EVENEMENTS = {
    connexion: "Connexion", deconnexion: "Déconnexion", echec_connexion: "Échec de connexion",
    echec_confirmation: "Mot de passe redemandé : erreur", verrouillage: "Compte verrouillé (15 min)",
    compte_cree: "Compte créé", compte_supprime: "Compte supprimé", compte_debloque: "Compte débloqué",
    mot_de_passe_change: "Mot de passe changé", mot_de_passe_reinitialise: "Mot de passe réinitialisé",
    suivi_consulte: "Suivi consulté", eleve_consulte: "Fiche de suivi consultée", simulation: "Réponses simulées",
    tentative_annulee: "Exercice d'un élève annulé", tentative_retablie: "Exercice d'un élève rétabli",
    groupe_cree: "Groupe créé", groupe_modifie: "Groupe modifié", groupe_supprime: "Groupe supprimé",
    propositions_validees: "Exercices à travailler validés", proposition_retiree: "Exercice à travailler retiré",
  };
  const INTERVALLE_MS = 1000;
  const ATTENTE_RECHERCHE_MS = 250;

  // origine : la vue d'où l'on a ouvert l'exercice, pour le lien « Retour »
  // statut, valide, occupe : ceux de l'exercice ouvert, pour l'état des boutons
  // donnees : la dernière réponse de /api/exercices/{id}, pour remplir le formulaire de modification
  // generation : l'identifiant de la génération suivie, pour pouvoir l'annuler
  // compte : le compte connecté (null : écran de connexion)
  // programmes : les attendus du programme officiel déjà chargés, par « matière|classe » (E2)
  // classe : la classe ouverte ; listeLue : les élèves lus dans une liste collée, avant de créer la classe ;
  // cartes : les cartes à imprimer (les codes en clair : effacées dès qu'on quitte la page des cartes) (E3)
  // tableau : le suivi de la classe ouverte ; fiche : celle de l'élève ouvert ; masquer : « Masquer les noms » (E4)
  const etat = { compte: null, programmes: {}, classe: null, listeLue: null, cartes: null, tableau: null, fiche: null,
    masquer: false, types: [], suivi: null, generation: null, exercice: null, regeneration: null, origine: "banque",
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
    if (!reponse.ok) {
      // 401 : plus de session (30 min sans activité, déconnexion ailleurs) ; sauf l'échec de la connexion elle-même
      if (reponse.status === 401 && !(methode === "POST" && chemin === "/api/session")) sessionPerdue(donnees);
      else if (reponse.status === 403 && donnees && donnees.doit_changer) imposerChangement();
      throw new Error(messageErreur(donnees, reponse.status));
    }
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

  const sansAccents = (texte) => (texte || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

  function remplirSelect(select, valeurs, libelles = {}, vide = null) {
    select.replaceChildren();
    if (vide !== null) select.append(el("option", { value: "", texte: vide }));
    for (const v of valeurs) select.append(el("option", { value: v, texte: libelles[v] || v }));
  }

  // --- navigation ---------------------------------------------------------------------------------

  function afficherVue(nom) {
    for (const vue of document.querySelectorAll(".vue")) vue.hidden = vue.id !== `vue-${nom}`;
    for (const lien of document.querySelectorAll("a[data-vue]")) {
      if (lien.dataset.vue === nom) lien.setAttribute("aria-current", "page");
      else lien.removeAttribute("aria-current");
    }
  }

  function router() {
    if (!etat.compte) {
      afficherVue("connexion");
      return;
    }
    if (etat.compte.doit_changer && location.hash !== "#/compte") {
      location.hash = "#/compte"; // le changement de hash rappelle router()
      return;
    }
    if (location.hash !== "#/cartes") oublierCartes(); // les codes en clair ne restent pas en mémoire
    const m = location.hash.match(/^#\/exercice\/([a-z0-9_-]+)$/);
    const c = location.hash.match(/^#\/classe\/(\d+)$/);
    const s = location.hash.match(/^#\/suivi\/(\d+)$/);
    const f = location.hash.match(/^#\/suivi-eleve\/(\d+)$/);
    if (location.hash === "#/classes") {
      afficherVue("classes");
      chargerClasses();
    } else if (c) {
      afficherVue("classe");
      ouvrirClasse(parseInt(c[1], 10));
    } else if (s) {
      afficherVue("suivi");
      ouvrirSuivi(parseInt(s[1], 10));
    } else if (f) {
      afficherVue("fiche");
      ouvrirFiche(parseInt(f[1], 10));
    } else if (location.hash === "#/cartes") {
      afficherVue("cartes");
      afficherCartes();
    } else if (location.hash === "#/compte") {
      afficherVue("compte");
      afficherCompte();
    } else if (location.hash === "#/comptes" && etat.compte.role === "admin") {
      afficherVue("comptes");
      chargerComptes();
    } else if (m) {
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

  // --- connexion (E1) ---------------------------------------------------------------------------

  function afficherConnexion(message = "", sansCompte = false) {
    $("#nav-principale").hidden = true;
    $("#entete-compte").hidden = true;
    $("#connexion-info").textContent = message;
    $("#connexion-info").hidden = !message;
    $("#form-connexion").hidden = sansCompte;
    $("#connexion-sans-compte").hidden = !sansCompte;
    afficherVue("connexion");
    if (!sansCompte) $("#connexion-identifiant").focus();
  }

  // ce que la page montre d'une session finie ne doit pas rester sous les yeux du suivant
  function viderVues() {
    clearTimeout(etat.suivi);
    oublierCartes();
    for (const id of ["#table-banque tbody", "#ex-questions", "#table-comptes tbody", "#table-journal tbody",
      "#table-classes tbody", "#table-eleves tbody", "#table-apercu tbody", "#table-suivi thead", "#table-suivi tbody",
      "#su-attendus", "#su-besoins", "#su-groupes", "#su-propositions", "#table-fiche tbody", "#table-tentatives tbody"]) {
      $(id).replaceChildren();
    }
    etat.tableau = null;
    etat.fiche = null;
    $("#ex-apercu").removeAttribute("src");
    $("#provisoire").hidden = true;
    $("#provisoire-valeur").textContent = "";
  }

  function sessionPerdue(donnees) {
    const avait = etat.compte !== null;
    etat.compte = null;
    viderVues();
    afficherConnexion(avait ? "Votre session a pris fin (30 minutes sans activité, ou déconnexion) : reconnectez-vous." : "",
      Boolean(donnees && donnees.sans_compte));
  }

  function imposerChangement() {
    if (etat.compte) etat.compte.doit_changer = true;
    location.hash = "#/compte";
  }

  async function chargerTypes() {
    const { types } = await api("/api/types");
    etat.types = types;
    remplirSelect($("#type"), types.map((t) => t.nom), Object.fromEntries(types.map((t) => [t.nom, t.titre])));
    choisirType();
    const premier = types[0] || { matieres: [], niveaux: [] };
    remplirSelect($("#filtre-matiere"), premier.matieres, MATIERES, "Toutes");
    remplirSelect($("#filtre-niveau"), premier.niveaux, {}, "Toutes");
  }

  async function ouvrirSession(compte) {
    etat.compte = compte;
    $("#entete-nom").textContent = compte.nom;
    $("#lien-comptes").hidden = compte.role !== "admin";
    $("#nav-principale").hidden = false;
    $("#entete-compte").hidden = false;
    $("#connexion-info").hidden = true;
    if (compte.doit_changer) {
      router();
      return;
    }
    try {
      if (!etat.types.length) await chargerTypes();
    } catch (e) {
      $("#analyse-etat").textContent = `Le serveur ne répond pas : ${e.message}`;
    }
    router();
    reprendreSuivi();
  }

  async function seConnecter(evenement) {
    evenement.preventDefault();
    const identifiant = $("#connexion-identifiant").value.trim();
    const motDePasse = $("#connexion-mot-de-passe");
    const erreur = $("#connexion-erreur");
    erreur.hidden = true;
    if (!identifiant || !motDePasse.value) {
      erreur.textContent = "Saisissez votre identifiant et votre mot de passe.";
      erreur.hidden = false;
      return;
    }
    $("#btn-connexion").disabled = true;
    try {
      const { compte } = await api("/api/session", { identifiant, mot_de_passe: motDePasse.value });
      motDePasse.value = "";
      await ouvrirSession(compte);
    } catch (e) {
      motDePasse.value = "";
      erreur.textContent = e.message.charAt(0).toUpperCase() + e.message.slice(1);
      erreur.hidden = false;
      motDePasse.focus();
    } finally {
      $("#btn-connexion").disabled = false;
    }
  }

  async function seDeconnecter() {
    try { await api("/api/session", undefined, "DELETE"); } catch (_) { /* déjà déconnecté */ }
    location.replace("/"); // page rechargée : plus rien de la session en mémoire
  }

  // --- mon compte ---------------------------------------------------------------------------------

  function afficherCompte() {
    const compte = etat.compte;
    $("#compte-infos").textContent = `${compte.nom} · identifiant « ${compte.identifiant} » · ${ROLES[compte.role] || compte.role}`;
    $("#compte-provisoire").hidden = !compte.doit_changer;
    $("#mdp-message").textContent = "";
  }

  async function changerMotDePasse(evenement) {
    evenement.preventDefault();
    const champs = ["#mdp-ancien", "#mdp-nouveau", "#mdp-confirmation"].map((id) => $(id));
    const [ancien, nouveau, confirmation] = champs.map((c) => c.value);
    const message = $("#mdp-message");
    if (nouveau.length < 12) {
      message.textContent = "Le nouveau mot de passe doit faire 12 caractères au moins.";
      return;
    }
    if (nouveau !== confirmation) {
      message.textContent = "Les deux saisies du nouveau mot de passe diffèrent.";
      return;
    }
    $("#btn-mot-de-passe").disabled = true;
    try {
      const { compte } = await api("/api/session/mot-de-passe", { ancien, nouveau });
      const etaitProvisoire = etat.compte.doit_changer;
      for (const c of champs) c.value = "";
      if (etaitProvisoire) {
        location.hash = "#/generer";
        await ouvrirSession(compte);
        return;
      }
      etat.compte = compte;
      afficherCompte();
      message.textContent = "Mot de passe changé. Vos autres sessions ont été fermées.";
    } catch (e) {
      $("#mdp-ancien").value = "";
      message.textContent = `Mot de passe non changé : ${e.message}`;
    } finally {
      $("#btn-mot-de-passe").disabled = false;
    }
  }

  // --- comptes (administrateurs) ------------------------------------------------------------------

  async function chargerComptes() {
    const etatComptes = $("#comptes-etat");
    etatComptes.textContent = "Chargement…";
    let comptes, journal;
    try {
      [{ comptes }, { journal }] = await Promise.all([api("/api/comptes"), api("/api/journal")]);
    } catch (e) {
      etatComptes.textContent = `Comptes illisibles : ${e.message}`;
      return;
    }
    etatComptes.textContent = `${comptes.length} compte${comptes.length > 1 ? "s" : ""}.`;
    $("#table-comptes tbody").replaceChildren(...comptes.map((c) => {
      const etats = [];
      if (c.verrouille) etats.push(el("span", { class: "badge statut-rejete", texte: "verrouillé" }));
      if (c.doit_changer) etats.push(el("span", { class: "badge statut-genere", texte: "mot de passe provisoire" }));
      if (!etats.length) etats.push(el("span", { class: "badge statut-accepte", texte: "actif" }));
      const soiMeme = c.identifiant === etat.compte.identifiant;
      const actions = el("div", { class: "question-actions" });
      if (soiMeme) actions.append(el("span", { class: "note", texte: "vous" }));
      else {
        if (c.verrouille) actions.append(el("button", { type: "button", class: "secondaire petit", "data-action": "debloquer",
          "data-identifiant": c.identifiant, texte: "Débloquer" }));
        actions.append(el("button", { type: "button", class: "secondaire petit", "data-action": "reinitialiser",
          "data-identifiant": c.identifiant, texte: "Réinitialiser le mot de passe…" }));
        actions.append(el("button", { type: "button", class: "secondaire petit danger", "data-action": "supprimer",
          "data-identifiant": c.identifiant, texte: "Supprimer…" }));
      }
      return el("tr", {}, el("td", { texte: c.identifiant }), el("td", { texte: c.nom }),
        el("td", { texte: ROLES[c.role] || c.role }), el("td", {}, el("div", { class: "badges" }, ...etats)),
        el("td", {}, actions));
    }));
    $("#table-journal tbody").replaceChildren(...journal.map((e) => el("tr", {},
      el("td", { texte: date(e.date) }), el("td", { texte: e.identifiant || "ligne de commande" }),
      el("td", { texte: EVENEMENTS[e.action] || e.action }), el("td", { texte: e.cible || "" }),
      el("td", { texte: e.detail || "" }))));
  }

  // le mot de passe de l'administrateur, redemandé avant une action sensible (⚖1) ; null si annulé
  function redemanderMotDePasse(titre, texte, ok) {
    return demander({ titre, texte, ok, champ: false, motDePasse: true });
  }

  function montrerProvisoire(titre, motDePasse) {
    $("#provisoire-titre").textContent = titre;
    $("#provisoire-valeur").textContent = motDePasse;
    $("#provisoire").hidden = false;
    $("#provisoire").scrollIntoView({ behavior: "smooth", block: "center" });
  }

  async function creerCompte(evenement) {
    evenement.preventDefault();
    const identifiant = $("#nouveau-identifiant").value.trim().toLowerCase();
    const nom = $("#nouveau-nom").value.trim();
    const role = $("#nouveau-role").value;
    const message = $("#nouveau-message");
    if (!identifiant || !nom) {
      message.textContent = "Indiquez l'identifiant et le nom affiché.";
      return;
    }
    const motDePasse = await redemanderMotDePasse(`Créer le compte « ${identifiant} »`,
      "Pour confirmer, saisissez votre mot de passe d'administrateur.", "Créer le compte");
    if (motDePasse === null) return;
    try {
      const reponse = await api("/api/comptes", { identifiant, nom, role, mot_de_passe: motDePasse });
      $("#form-nouveau-compte").reset();
      message.textContent = "";
      montrerProvisoire(`Compte « ${reponse.compte.identifiant} » créé`, reponse.mot_de_passe_provisoire);
    } catch (e) {
      message.textContent = `Compte non créé : ${e.message}`;
    }
    chargerComptes();
  }

  async function agirSurCompte(evenement) {
    const bouton = evenement.target.closest("button[data-action]");
    if (!bouton) return;
    const { action, identifiant } = bouton.dataset;
    const message = $("#comptes-etat");
    try {
      if (action === "debloquer") {
        await api(`/api/comptes/${encodeURIComponent(identifiant)}/debloquer`, {});
        message.textContent = `Compte « ${identifiant} » débloqué.`;
      } else if (action === "reinitialiser") {
        const motDePasse = await redemanderMotDePasse(`Réinitialiser le mot de passe de « ${identifiant} »`,
          "Ses sessions seront fermées, et il recevra un mot de passe provisoire. Pour confirmer, saisissez votre mot de passe.",
          "Réinitialiser");
        if (motDePasse === null) return;
        const reponse = await api(`/api/comptes/${encodeURIComponent(identifiant)}/reinitialiser`, { mot_de_passe: motDePasse });
        montrerProvisoire(`Nouveau mot de passe de « ${identifiant} »`, reponse.mot_de_passe_provisoire);
      } else if (action === "supprimer") {
        const motDePasse = await redemanderMotDePasse(`Supprimer le compte « ${identifiant} »`,
          "Le compte ne pourra plus se connecter ; ses actions restent dans le journal. Pour confirmer, saisissez votre mot de passe.",
          "Supprimer");
        if (motDePasse === null) return;
        await api(`/api/comptes/${encodeURIComponent(identifiant)}`, { mot_de_passe: motDePasse }, "DELETE");
        message.textContent = `Compte « ${identifiant} » supprimé.`;
      }
    } catch (e) {
      message.textContent = `Action refusée : ${e.message}`;
    }
    chargerComptes();
  }

  // --- classes et élèves (E3) -----------------------------------------------------------------------

  async function chargerClasses() {
    const message = $("#classes-etat");
    message.textContent = "Chargement…";
    let donnees;
    try {
      donnees = await api(`/api/classes?archivees=${$("#classes-archivees").checked}`);
    } catch (e) {
      message.textContent = `Classes illisibles : ${e.message}`;
      return;
    }
    $("#classes-rgpd").hidden = donnees.aipd_validee;
    $("#classe-annee").dataset.courante = donnees.annee_courante;
    $("#table-classes tbody").replaceChildren(...donnees.classes.map((c) => el("tr", {},
      el("td", {}, el("a", { href: `#/classe/${c.id}`, texte: c.nom })), el("td", { texte: c.niveau }),
      el("td", { texte: c.annee }), el("td", { class: "nombre", texte: String(c.eleves) }),
      el("td", {}, el("span", { class: `badge ${c.archivee ? "" : "statut-accepte"}`, texte: c.archivee ? "archivée" : "active" })))));
    message.textContent = donnees.classes.length ? `${donnees.classes.length} classe(s).`
      : "Aucune classe. Créez-en une, ou une classe de démonstration : python -m generateur.donnees.demo <identifiant>.";
  }

  function ouvrirFormulaireClasse() {
    const formulaire = $("#form-classe");
    formulaire.reset();
    $("#classe-annee").value = $("#classe-annee").dataset.courante || "";
    $("#classe-apercu").hidden = true;
    $("#classe-erreur").hidden = true;
    etat.listeLue = null;
    formulaire.hidden = false;
    $("#classe-nom").focus();
  }

  async function lireListe(texte) {
    return api("/api/classes/liste", { texte });
  }

  async function verifierListe(evenement) {
    evenement.preventDefault();
    const erreur = $("#classe-erreur");
    erreur.hidden = true;
    try {
      const { eleves, remarques } = await lireListe($("#classe-liste").value);
      etat.listeLue = eleves;
      $("#classe-remarques").replaceChildren(...remarques.map((r) => el("li", { texte: r })));
      $("#table-apercu tbody").replaceChildren(...eleves.map((e, i) => el("tr", {},
        el("td", { class: "nombre", texte: String(i + 1) }), el("td", { texte: e.nom }), el("td", { texte: e.prenom }))));
      $("#btn-creer-classe").textContent = `Créer la classe (${eleves.length} élève${eleves.length > 1 ? "s" : ""}) et ses cartes`;
      $("#classe-apercu").hidden = false;
    } catch (e) {
      erreur.textContent = `Liste illisible : ${e.message}`;
      erreur.hidden = false;
    }
  }

  async function creerClasse() {
    const erreur = $("#classe-erreur");
    erreur.hidden = true;
    const corps = { nom: $("#classe-nom").value.trim(), niveau: $("#classe-niveau").value,
      annee: $("#classe-annee").value.trim() || null, eleves: etat.listeLue || [] };
    if (!corps.nom) {
      erreur.textContent = "Donnez un nom à la classe (par exemple « 6e B »).";
      erreur.hidden = false;
      $("#classe-nom").focus();
      return;
    }
    $("#btn-creer-classe").disabled = true;
    try {
      const { classe, cartes } = await api("/api/classes", corps);
      $("#form-classe").hidden = true;
      montrerCartes(`Classe « ${classe.nom} » créée : ${cartes.length} carte(s)`, cartes, `#/classe/${classe.id}`);
    } catch (e) {
      erreur.textContent = `Classe non créée : ${e.message}`;
      erreur.hidden = false;
    } finally {
      $("#btn-creer-classe").disabled = false;
    }
  }

  async function ouvrirClasse(id, message = "") {
    $("#cl-message").textContent = message;
    $("#form-ajout").hidden = true;
    let classe;
    try {
      ({ classe } = await api(`/api/classes/${id}`));
    } catch (e) {
      $("#cl-titre").textContent = "Classe introuvable";
      $("#cl-infos").textContent = e.message;
      $("#table-eleves tbody").replaceChildren();
      return;
    }
    if (location.hash !== `#/classe/${id}`) return; // l'enseignant est allé ailleurs pendant le chargement
    etat.classe = classe;
    $("#cl-titre").textContent = classe.nom;
    $("#cl-infos").textContent = [classe.niveau, classe.annee, `${classe.eleves} élève(s)`,
      classe.archivee ? "classe archivée" : null].filter(Boolean).join(" · ");
    $("#btn-cl-archiver").textContent = classe.archivee ? "Désarchiver la classe" : "Archiver la classe";
    $("#btn-cl-suivi").href = `#/suivi/${classe.id}`;
    $("#table-eleves tbody").replaceChildren(...classe.liste.map(ligneEleve));
  }

  function ligneEleve(e) {
    const bouton = (action, texte, classeCss = "secondaire petit") =>
      el("button", { type: "button", class: classeCss, "data-action": action, texte });
    return el("tr", { "data-id": String(e.id), class: e.actif ? null : "eleve-inactif" },
      el("td", { class: "nombre", texte: String(e.numero) }), el("td", { texte: e.nom }), el("td", { texte: e.prenom }),
      el("td", {}, el("span", { class: `badge ${e.actif ? "statut-accepte" : "statut-genere"}`, texte: e.actif ? "actif" : "désactivé" })),
      el("td", {}, el("div", { class: "question-actions" }, bouton("modifier", "Corriger"), bouton("code", "Nouveau code"),
        bouton("actif", e.actif ? "Désactiver" : "Réactiver"), bouton("exporter", "Exporter…"),
        bouton("supprimer", "Supprimer…", "secondaire petit danger"))));
  }

  function eleveDe(ligne) {
    return etat.classe && etat.classe.liste.find((x) => String(x.id) === ligne.dataset.id);
  }

  async function agirSurEleve(evenement) {
    const bouton = evenement.target.closest("button[data-action]");
    if (!bouton) return;
    const ligne = bouton.closest("tr");
    const eleve = eleveDe(ligne);
    if (!eleve) return;
    const nom = `${eleve.prenom} ${eleve.nom}`;
    const message = $("#cl-message");
    try {
      if (bouton.dataset.action === "modifier") {
        corrigerEleve(ligne, eleve);
      } else if (bouton.dataset.action === "enregistrer") {
        const [nouveauNom, nouveauPrenom] = [...ligne.querySelectorAll("input")].map((i) => i.value.trim());
        await api(`/api/eleves/${eleve.id}`, { nom: nouveauNom, prenom: nouveauPrenom }, "PUT");
        await ouvrirClasse(etat.classe.id, "Nom corrigé.");
      } else if (bouton.dataset.action === "annuler") {
        ligne.replaceWith(ligneEleve(eleve));
      } else if (bouton.dataset.action === "code") {
        const { carte } = await api(`/api/eleves/${eleve.id}/code`, {});
        montrerCartes(`Nouveau code de ${nom}`, [carte], `#/classe/${etat.classe.id}`);
      } else if (bouton.dataset.action === "actif") {
        await api(`/api/eleves/${eleve.id}/actif`, { actif: !eleve.actif });
        await ouvrirClasse(etat.classe.id, eleve.actif ? `${nom} est désactivé : il ne pourra plus se connecter.` : `${nom} est réactivé.`);
      } else if (bouton.dataset.action === "exporter") {
        const motDePasse = await redemanderMotDePasse(`Exporter les données de ${nom}`,
          "Un fichier CSV, à remettre à l'établissement pour répondre à une demande d'accès (pas par e-mail). " +
          "Pour confirmer, saisissez votre mot de passe.", "Exporter");
        if (motDePasse === null) return;
        await telecharger(`/api/eleves/${eleve.id}/export`, { mot_de_passe: motDePasse });
        message.textContent = `Données de ${nom} exportées (fichier eleve-${eleve.id}.csv). Supprimez-le du PC une fois remis.`;
      } else if (bouton.dataset.action === "supprimer") {
        const motDePasse = await redemanderMotDePasse(`Supprimer ${nom}`,
          `${nom} et toutes ses réponses seront effacés, sans retour possible. Son numéro ne sera pas redonné. ` +
          "Pour confirmer, saisissez votre mot de passe.", "Supprimer");
        if (motDePasse === null) return;
        await api(`/api/eleves/${eleve.id}`, { mot_de_passe: motDePasse }, "DELETE");
        await ouvrirClasse(etat.classe.id, `${nom} est supprimé.`);
      }
    } catch (e) {
      message.textContent = `Action refusée : ${e.message}`;
    }
  }

  function corrigerEleve(ligne, eleve) {
    const champ = (valeur, libelle) => el("input", { type: "text", value: valeur, maxlength: "60", "aria-label": libelle });
    ligne.replaceChildren(el("td", { class: "nombre", texte: String(eleve.numero) }),
      el("td", { class: "edition-eleve" }, champ(eleve.nom, `Nom de l'élève n° ${eleve.numero}`)),
      el("td", { class: "edition-eleve" }, champ(eleve.prenom, `Prénom de l'élève n° ${eleve.numero}`)), el("td"),
      el("td", {}, el("div", { class: "question-actions" },
        el("button", { type: "button", class: "petit", "data-action": "enregistrer", texte: "Enregistrer" }),
        el("button", { type: "button", class: "secondaire petit", "data-action": "annuler", texte: "Annuler" }))));
    ligne.querySelector("input").focus();
  }

  // un fichier renvoyé par un POST (l'export CSV) : enregistré par le navigateur, jamais affiché dans la page
  async function telecharger(chemin, corps) {
    const reponse = await fetch(chemin, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corps) });
    if (!reponse.ok) {
      let donnees = null;
      try { donnees = await reponse.json(); } catch (_) { /* corps vide */ }
      if (reponse.status === 401) sessionPerdue(donnees);
      throw new Error(messageErreur(donnees, reponse.status));
    }
    const nom = (reponse.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/);
    const adresse = URL.createObjectURL(await reponse.blob());
    const lien = el("a", { href: adresse, download: nom ? nom[1] : "export.csv" });
    document.body.append(lien);
    lien.click();
    lien.remove();
    setTimeout(() => URL.revokeObjectURL(adresse), 1000);
  }

  async function ajouterEleves(evenement) {
    evenement.preventDefault();
    const message = $("#cl-message");
    try {
      const { eleves, remarques } = await lireListe($("#ajout-liste").value);
      if (!eleves.length) {
        message.textContent = `Aucun élève lu dans la liste. ${remarques.join(" ; ")}`;
        return;
      }
      const { cartes } = await api(`/api/classes/${etat.classe.id}/eleves`, { eleves });
      montrerCartes(`${cartes.length} élève(s) ajouté(s) à ${etat.classe.nom}`, cartes, `#/classe/${etat.classe.id}`);
    } catch (e) {
      message.textContent = `Élèves non ajoutés : ${e.message}`;
    }
  }

  async function nouveauxCodesClasse() {
    const motDePasse = await redemanderMotDePasse(`Nouveaux codes pour ${etat.classe.nom}`,
      "Chaque élève reçoit un nouveau code ; les cartes actuelles ne marcheront plus. Pour confirmer, saisissez votre mot de passe.",
      "Refaire les codes");
    if (motDePasse === null) return;
    try {
      const { cartes } = await api(`/api/classes/${etat.classe.id}/codes`, { mot_de_passe: motDePasse });
      montrerCartes(`Nouvelles cartes de ${etat.classe.nom}`, cartes, `#/classe/${etat.classe.id}`);
    } catch (e) {
      $("#cl-message").textContent = `Codes non refaits : ${e.message}`;
    }
  }

  async function archiverClasse() {
    const archivee = !etat.classe.archivee;
    try {
      await api(`/api/classes/${etat.classe.id}/archiver`, { archivee });
      if (archivee) location.hash = "#/classes";
      else await ouvrirClasse(etat.classe.id, "Classe désarchivée.");
    } catch (e) {
      $("#cl-message").textContent = `Action refusée : ${e.message}`;
    }
  }

  async function purgerAnnees() {
    const message = $("#classes-etat");
    try {
      const apercu = await api("/api/classes/purge");
      if (!apercu.classes.length) {
        message.textContent = `Rien à purger : aucune classe d'une année passée (avant ${apercu.annee_courante}).`;
        return;
      }
      const liste = apercu.classes.map((c) => `${c.nom} (${c.annee}, ${c.eleves} élève(s))`).join(", ");
      const motDePasse = await redemanderMotDePasse("Purger les années passées",
        `Seront effacés, sans retour possible : ${liste}, avec leurs élèves et leurs réponses. ` +
        "Pour confirmer, saisissez votre mot de passe.", "Purger");
      if (motDePasse === null) return;
      const fait = await api("/api/classes/purge", { mot_de_passe: motDePasse });
      await chargerClasses();
      message.textContent = `Purge faite : ${fait.classes} classe(s), ${fait.eleves} élève(s) effacés.`;
    } catch (e) {
      message.textContent = `Purge refusée : ${e.message}`;
    }
  }

  // --- suivi des élèves (E4) : des indicateurs, jamais une décision ----------------------------------------

  const SYMBOLES = { a_consolider: "!", en_cours: "·", en_reussite: "✓", pas_assez: "?" };
  const NATURES = { retravailler: "À retravailler", plus_loin: "Pour aller plus loin" };
  const ORIGINES = { simulation: "simulée (élève fictif)", classe: "en classe", import: "importée" };

  // « Masquer les noms » : le numéro dans la classe à la place du nom, pour projeter au tableau
  const nomEleve = (e) => (!e ? "?" : etat.masquer ? `Élève n° ${e.numero}` : `${e.prenom} ${e.nom}`);
  const pourcent = (taux) => (taux === null || taux === undefined ? "" : `${Math.round(taux * 100)} %`);
  const tronquer = (texte, n) => (texte.length <= n ? texte : `${texte.slice(0, n - 3).replace(/\s+\S*$/, "")}…`);

  function eleveDuSuivi(id) {
    return etat.tableau && etat.tableau.eleves.find((e) => e.id === id);
  }

  function nomsDesEleves(ids) {
    return ids.length ? ids.map((id) => nomEleve(eleveDuSuivi(id))).join(", ") : "aucun élève";
  }

  async function ouvrirSuivi(id) {
    const message = $("#su-message");
    message.textContent = "Chargement…";
    $("#su-retour").href = `#/classe/${id}`;
    let donnees;
    try {
      donnees = await api(`/api/classes/${id}/suivi`);
    } catch (e) {
      $("#su-titre").textContent = "Suivi introuvable";
      message.textContent = e.message;
      $("#su-contenu").hidden = true;
      return;
    }
    if (location.hash !== `#/suivi/${id}`) return; // l'enseignant est allé ailleurs pendant le chargement
    etat.tableau = { ...donnees, groupes: null, proposes: null, propositions: null, montrerProposees: false, ecartees: new Set() };
    $("#su-titre").textContent = `Suivi de ${donnees.classe.nom}`;
    $("#su-rappel").textContent = donnees.rappel;
    $("#su-contenu").hidden = !donnees.attendus.length;
    message.textContent = donnees.attendus.length ? "" : "Pas encore de réponses d'élèves pour cette classe. Pour essayer " +
      "avec des élèves fictifs : python -m generateur.donnees.simulation <identifiant> --classe \"<nom de la classe>\".";
    afficherSuivi();
    if (donnees.attendus.length) await Promise.all([chargerGroupes(), chargerPropositions()]);
  }

  function afficherSuivi() {
    const t = etat.tableau;
    if (!t) return;
    const p = (x) => Math.round(x * 100);
    $("#table-suivi thead").replaceChildren(el("tr", {}, el("th", { scope: "col", texte: "N°" }),
      el("th", { scope: "col", texte: "Élève" }),
      ...t.attendus.map((a) => el("th", { scope: "col", class: "case-suivi" }, el("abbr", { title: a.libelle, texte: a.code })))));
    $("#table-suivi tbody").replaceChildren(...t.eleves.map((e) => el("tr", { class: e.actif ? null : "eleve-inactif" },
      el("td", { class: "nombre", texte: String(e.numero) }),
      el("th", { scope: "row" }, el("a", { href: `#/suivi-eleve/${e.id}`, texte: nomEleve(e) })),
      ...t.attendus.map((a) => caseSuivi(e.cases[a.id], t.etats)))));
    const symbole = (etatCase) => el("span", { class: `case-suivi etat-${etatCase}`, "aria-hidden": "true", texte: SYMBOLES[etatCase] });
    $("#su-legende").replaceChildren(
      el("li", {}, symbole("a_consolider"), ` à consolider : moins de ${p(t.seuils.a_consolider)} % de réussite`),
      el("li", {}, symbole("en_cours"), " en cours"),
      el("li", {}, symbole("en_reussite"), ` en réussite : ${p(t.seuils.en_reussite)} % ou plus`),
      el("li", {}, symbole("pas_assez"), ` pas assez de réponses : moins de ${t.seuils.questions_min} questions`),
      el("li", { texte: "— aucune réponse sur cet attendu" }));
    $("#su-attendus").replaceChildren(...t.attendus.map((a) => el("li", {}, el("strong", { texte: a.code }), ` ${a.libelle}`)));
    afficherBesoins();
    if (t.groupes) afficherGroupes();
    if (t.propositions) afficherPropositions();
  }

  // la couleur n'est jamais seule : un symbole, le pourcentage, et l'état en toutes lettres pour les lecteurs d'écran
  function caseSuivi(c, etats) {
    if (!c) {
      return el("td", { class: "case-suivi" }, el("span", { "aria-hidden": "true", texte: "—" }),
        el("span", { class: "visuellement-cache", texte: "aucune réponse" }));
    }
    return el("td", { class: `case-suivi etat-${c.etat}`, title: `${etats[c.etat]} : ${c.explication}` },
      el("span", { "aria-hidden": "true", texte: `${SYMBOLES[c.etat]} ${pourcent(c.taux)}` }),
      el("span", { class: "visuellement-cache", texte: `${etats[c.etat]}, ${c.explication}` }));
  }

  function boutonGenerer(attendu, libelle, difficulte, texte, pour = "") {
    return el("button", { type: "button", class: "secondaire petit", "data-generer": attendu || "", "data-libelle": libelle || "",
      "data-difficulte": difficulte, "data-pour": pour, texte });
  }

  function afficherBesoins() {
    const t = etat.tableau;
    const items = [];
    t.besoins.forEach((b, i) => {
      const a = t.attendus[i];
      if (!b.a_consolider.length && !b.en_reussite.length) return;
      items.push(el("li", {}, el("p", {}, el("strong", { texte: `${a.code} · ` }), a.libelle),
        b.a_consolider.length ? el("p", {}, `À consolider (${b.a_consolider.length}) : ${nomsDesEleves(b.a_consolider)} `,
          boutonGenerer(a.id, a.libelle, "facile", "Générer un exercice pour les retravailler", `à consolider : ${a.code}`)) : null,
        b.en_reussite.length ? el("p", {}, `En réussite (${b.en_reussite.length}) : ${nomsDesEleves(b.en_reussite)} `,
          boutonGenerer(a.id, a.libelle, "difficile", "Générer un exercice pour aller plus loin", `en réussite : ${a.code}`)) : null));
    });
    $("#su-besoins").replaceChildren(...(items.length ? items
      : [el("li", { texte: "Aucun besoin repéré : personne n'est à consolider ni en réussite pour l'instant." })]));
  }

  // « Générer un exercice » : le formulaire de génération, pré-rempli ; l'enseignant vérifie, puis génère
  function genererDepuisSuivi(bouton) {
    const t = etat.tableau;
    const attendu = bouton.dataset.generer;
    const matiere = (attendu || (t.attendus[0] || { id: "" }).id).split(".")[0];
    location.hash = "#/generer";
    afficherVue("generer");
    remplirFormulaire({
      requete: { type: "qcm", matiere, niveau: t.classe.niveau, notion: tronquer(bouton.dataset.libelle, 120), nb_questions: 5,
        difficulte: bouton.dataset.difficulte, attendu },
      sources: {}, a_verifier: attendu ? [] : ["notion"], procedural: null,
      remarques: [`Préparé depuis le suivi de ${t.classe.nom}${bouton.dataset.pour ? ` (${bouton.dataset.pour})` : ""} : ` +
        "vérifiez la demande, puis générez."],
    });
    $("#chemin").hidden = true;
  }

  // --- les groupes de besoins

  async function chargerGroupes() {
    const t = etat.tableau;
    try {
      Object.assign(t, await api(`/api/classes/${t.classe.id}/groupes`));
      afficherGroupes();
    } catch (e) {
      $("#su-message").textContent = `Groupes illisibles : ${e.message}`;
    }
  }

  function afficherGroupes() {
    const t = etat.tableau;
    const bouton = (action, texte, classeCss = "secondaire petit") => el("button", { type: "button", class: classeCss, "data-action": action, texte });
    const deja = new Set(t.groupes.map((g) => `${g.nature}|${g.attendu || ""}`));
    const enregistres = t.groupes.map((g) => el("article", { class: "carte groupe", "data-groupe": String(g.id) },
      el("h3", { texte: g.nom }),
      el("p", { class: "infos", texte: g.attendu ? `${g.nature === "consolider" ? "À consolider" : "Pour aller plus loin"} : ${g.libelle_attendu}`
        : "Pour aller plus loin" }),
      el("p", { texte: `${g.eleves.length} élève(s) : ${nomsDesEleves(g.eleves)}` }),
      el("div", { class: "question-actions" },
        boutonGenerer(g.attendu, g.libelle_attendu, g.nature === "consolider" ? "facile" : "difficile",
          "Générer un exercice pour ce groupe", `groupe « ${g.nom} »`),
        bouton("modifier-groupe", "Modifier"), bouton("supprimer-groupe", "Supprimer…", "secondaire petit danger"))));
    const proposes = t.proposes.map((g, i) => [g, i]).filter(([g]) => !deja.has(`${g.nature}|${g.attendu || ""}`))
      .map(([g, i]) => el("article", { class: "carte groupe groupe-propose", "data-propose": String(i) },
        el("h3", {}, el("span", { class: "badge statut-genere", texte: "proposé" }), ` ${g.nom}`),
        el("p", { texte: `${g.eleves.length} élève(s) : ${nomsDesEleves(g.eleves)}` }),
        el("div", { class: "question-actions" }, bouton("enregistrer-groupe", "Enregistrer ce groupe", "petit"))));
    $("#su-groupes").replaceChildren(...(enregistres.length || proposes.length ? [...enregistres, ...proposes]
      : [el("p", { class: "note", texte: "Aucun groupe à proposer pour l'instant." })]));
  }

  function modifierGroupe(article, g) {
    const t = etat.tableau;
    article.replaceChildren(
      el("label", { for: `groupe-nom-${g.id}`, texte: "Nom du groupe" }),
      el("input", { id: `groupe-nom-${g.id}`, type: "text", maxlength: "120", value: g.nom }),
      el("fieldset", { class: "choix-eleves" }, el("legend", { texte: "Élèves du groupe" }),
        ...t.eleves.map((e) => el("label", { class: "case" },
          el("input", { type: "checkbox", value: String(e.id), checked: g.eleves.includes(e.id) }), ` ${nomEleve(e)}`))),
      el("div", { class: "question-actions" },
        el("button", { type: "button", class: "petit", "data-action": "enregistrer-modif", texte: "Enregistrer" }),
        el("button", { type: "button", class: "secondaire petit", "data-action": "annuler-modif", texte: "Annuler" })));
    article.querySelector("input").focus();
  }

  async function agirSurGroupe(evenement) {
    const bouton = evenement.target.closest("button");
    if (!bouton) return;
    if (bouton.dataset.generer !== undefined) { genererDepuisSuivi(bouton); return; }
    const t = etat.tableau;
    const article = bouton.closest("article");
    const g = article && article.dataset.groupe && t.groupes.find((x) => String(x.id) === article.dataset.groupe);
    const message = $("#su-message");
    try {
      if (bouton.dataset.action === "enregistrer-groupe") {
        const propose = t.proposes[parseInt(article.dataset.propose, 10)];
        await api(`/api/classes/${t.classe.id}/groupes`, propose);
        message.textContent = `Groupe « ${propose.nom} » enregistré.`;
      } else if (bouton.dataset.action === "modifier-groupe" && g) {
        modifierGroupe(article, g);
        return;
      } else if (bouton.dataset.action === "annuler-modif") {
        afficherGroupes();
        return;
      } else if (bouton.dataset.action === "enregistrer-modif" && g) {
        const nom = article.querySelector("input[type=text]").value.trim();
        const eleves = [...article.querySelectorAll("input[type=checkbox]:checked")].map((c) => parseInt(c.value, 10));
        await api(`/api/groupes/${g.id}`, { nom, eleves }, "PUT");
        message.textContent = `Groupe « ${nom} » modifié.`;
      } else if (bouton.dataset.action === "supprimer-groupe" && g) {
        const ok = await demander({ titre: `Supprimer le groupe « ${g.nom} »`, champ: false, ok: "Supprimer",
          texte: "Le groupe est effacé ; les élèves et leurs réponses ne changent pas." });
        if (ok === null) return;
        await api(`/api/groupes/${g.id}`, {}, "DELETE");
        message.textContent = `Groupe « ${g.nom} » supprimé.`;
      } else {
        return;
      }
      await chargerGroupes();
    } catch (e) {
      message.textContent = `Action refusée : ${e.message}`;
    }
  }

  // --- les exercices à travailler

  async function chargerPropositions() {
    const t = etat.tableau;
    try {
      t.propositions = await api(`/api/classes/${t.classe.id}/propositions`);
      afficherPropositions();
    } catch (e) {
      $("#su-message").textContent = `Exercices proposés illisibles : ${e.message}`;
    }
  }

  function tableau(titre, entetes, lignes) {
    return el("div", { class: "tableau-defilant" }, el("table", { class: "tableau" },
      el("caption", { class: "visuellement-cache", texte: titre }),
      el("thead", {}, el("tr", {}, ...entetes.map((h) => el("th", { scope: "col", texte: h })))), el("tbody", {}, ...lignes)));
  }

  function afficherPropositions() {
    const t = etat.tableau;
    const { validees, proposees } = t.propositions;
    const exercice = (p) => (p.exercice ? el("a", { href: `#/exercice/${p.exercice}`, texte: p.titre || p.exercice })
      : boutonGenerer(p.attendu, p.libelle_attendu, p.nature === "retravailler" ? "facile" : "difficile", "À générer…",
        `${NATURES[p.nature].toLowerCase()} : ${nomEleve(eleveDuSuivi(p.eleve_id))}`));
    const zone = [];
    if (validees.length) {
      zone.push(el("h3", { texte: `Validés (${validees.length})` }), tableau("Les exercices validés, par élève",
        ["Élève", "Pour", "Attendu du programme", "Exercice", "Actions"], validees.map((p) => el("tr", { "data-proposition": String(p.id) },
          el("td", { class: "sans-coupure", texte: nomEleve(eleveDuSuivi(p.eleve_id)) }), el("td", { texte: NATURES[p.nature] }),
          el("td", { texte: p.libelle_attendu }), el("td", {}, exercice(p)),
          el("td", {}, el("button", { type: "button", class: "secondaire petit", "data-action": "retirer", texte: "Retirer" }))))));
    } else {
      zone.push(el("p", { class: "note", texte: "Aucun exercice validé pour cette classe." }));
    }
    $("#btn-su-proposer").hidden = t.montrerProposees;
    if (t.montrerProposees) {
      if (!proposees.length) {
        zone.push(el("p", { class: "note", texte: "Rien à proposer : aucun élève n'est à consolider ni en réussite." }));
      } else {
        const gardees = proposees.length - t.ecartees.size;
        zone.push(el("h3", { texte: `Proposés (${proposees.length}) : décochez ceux que vous ne gardez pas` }),
          tableau("Les exercices proposés, à garder ou non", ["Garder", "Élève", "Pour", "Attendu du programme", "Exercice"],
            proposees.map((p, i) => el("tr", {},
              el("td", {}, el("input", { type: "checkbox", "data-index": String(i), checked: !t.ecartees.has(i),
                "aria-label": `Garder : ${NATURES[p.nature]}, ${nomEleve(eleveDuSuivi(p.eleve_id))}, ${p.libelle_attendu}` })),
              el("td", { class: "sans-coupure", texte: nomEleve(eleveDuSuivi(p.eleve_id)) }), el("td", { texte: NATURES[p.nature] }),
              el("td", { texte: p.libelle_attendu }), el("td", {}, exercice(p))))),
          el("div", { class: "actions" },
            el("button", { type: "button", "data-action": "valider", texte: `Valider la sélection (${gardees})` }),
            el("button", { type: "button", class: "lien", "data-action": "fermer", texte: "Annuler" })));
      }
    }
    $("#su-propositions").replaceChildren(...zone);
  }

  async function agirSurPropositions(evenement) {
    const t = etat.tableau;
    const caseGarder = evenement.target.closest("input[type=checkbox][data-index]");
    if (caseGarder) {
      const i = parseInt(caseGarder.dataset.index, 10);
      if (caseGarder.checked) t.ecartees.delete(i); else t.ecartees.add(i);
      const valider = $("#su-propositions button[data-action=valider]");
      if (valider) valider.textContent = `Valider la sélection (${t.propositions.proposees.length - t.ecartees.size})`;
      return;
    }
    const bouton = evenement.target.closest("button");
    if (!bouton) return;
    if (bouton.dataset.generer !== undefined) { genererDepuisSuivi(bouton); return; }
    const message = $("#su-message");
    try {
      if (bouton.dataset.action === "retirer") {
        await api(`/api/propositions/${bouton.closest("tr").dataset.proposition}`, {}, "DELETE");
        message.textContent = "Exercice retiré.";
      } else if (bouton.dataset.action === "fermer") {
        t.montrerProposees = false;
        afficherPropositions();
        return;
      } else if (bouton.dataset.action === "valider") {
        const gardees = t.propositions.proposees.filter((_, i) => !t.ecartees.has(i));
        const ok = await demander({ titre: "Valider les exercices à travailler", champ: false, ok: "Valider",
          texte: `${gardees.length} exercice(s) gardé(s) ; ils remplacent ceux déjà validés pour la classe.` });
        if (ok === null) return;
        const fait = await api(`/api/classes/${t.classe.id}/propositions`, { propositions: gardees.map((p) =>
          ({ eleve_id: p.eleve_id, nature: p.nature, attendu: p.attendu, exercice: p.exercice })) });
        t.montrerProposees = false;
        t.ecartees = new Set();
        message.textContent = `${fait.validees} exercice(s) validé(s).`;
      } else {
        return;
      }
      await chargerPropositions();
    } catch (e) {
      message.textContent = `Action refusée : ${e.message}`;
    }
  }

  // --- la fiche d'un élève

  async function ouvrirFiche(id, message = "") {
    $("#fi-message").textContent = message;
    let fiche;
    try {
      fiche = await api(`/api/eleves/${id}/suivi`);
    } catch (e) {
      $("#fi-titre").textContent = "Élève introuvable";
      $("#fi-infos").textContent = e.message;
      $("#table-fiche tbody").replaceChildren();
      $("#table-tentatives tbody").replaceChildren();
      return;
    }
    if (location.hash !== `#/suivi-eleve/${id}`) return;
    etat.fiche = fiche;
    const e = fiche.eleve;
    $("#fi-retour").href = `#/suivi/${e.classe_id}`;
    $("#fi-titre").textContent = nomEleve(e);
    $("#fi-infos").textContent = [e.classe, `n° ${e.numero}`, e.actif ? null : "désactivé"].filter(Boolean).join(" · ");
    $("#table-fiche tbody").replaceChildren(...(fiche.attendus.length ? fiche.attendus.map((a) => el("tr", {},
      el("td", { texte: a.libelle }),
      el("td", { class: "sans-coupure" }, el("span", { class: `case-suivi etat-${a.etat}`, "aria-hidden": "true", texte: SYMBOLES[a.etat] }),
        ` ${fiche.etats[a.etat]}`),
      el("td", { texte: `${a.explication}${a.taux === null ? "" : ` (${pourcent(a.taux)})`}` })))
      : [el("tr", {}, el("td", { colspan: "3", texte: "Pas encore de réponses." }))]));
    $("#table-tentatives tbody").replaceChildren(...fiche.tentatives.map((x) => el("tr", { "data-tentative": String(x.id),
      class: x.annulee ? "eleve-inactif" : null },
      el("td", { texte: date(x.date) }), el("td", { texte: x.titre || x.exercice }),
      el("td", { class: "nombre", texte: `${x.justes} / ${x.questions}` }),
      el("td", { texte: `${ORIGINES[x.origine] || x.origine}${x.annulee ? " · annulée" : ""}` }),
      el("td", {}, el("button", { type: "button", class: "secondaire petit", "data-annulee": x.annulee ? "0" : "1",
        texte: x.annulee ? "Rétablir" : "Annuler…" })))));
  }

  async function agirSurTentative(evenement) {
    const bouton = evenement.target.closest("button[data-annulee]");
    if (!bouton || !etat.fiche) return;
    const id = bouton.closest("tr").dataset.tentative;
    const annulee = bouton.dataset.annulee === "1";
    if (annulee) {
      const ok = await demander({ titre: "Annuler cet exercice", champ: false, ok: "Annuler l'exercice",
        texte: "Fait par erreur (un autre élève sur sa session, par exemple) : il ne comptera plus dans le suivi. " +
          "Vous pourrez le rétablir." });
      if (ok === null) return;
    }
    try {
      await api(`/api/tentatives/${id}/annuler`, { annulee });
      await ouvrirFiche(etat.fiche.eleve.id, annulee ? "Exercice annulé : il ne compte plus dans le suivi." : "Exercice rétabli.");
    } catch (e) {
      $("#fi-message").textContent = `Action refusée : ${e.message}`;
    }
  }

  // --- les cartes de connexion -------------------------------------------------------------------------

  function montrerCartes(titre, cartes, retour) {
    etat.cartes = { titre, cartes, retour };
    if (location.hash === "#/cartes") afficherCartes();
    else location.hash = "#/cartes";
  }

  function oublierCartes() {
    etat.cartes = null;
    $("#cartes").replaceChildren();
  }

  function afficherCartes() {
    const zone = $("#cartes");
    if (!etat.cartes) {
      $("#titre-cartes").textContent = "Cartes de connexion";
      $("#btn-imprimer").hidden = true;
      zone.replaceChildren(el("p", { class: "note", texte: "Plus de cartes à afficher : un code ne s'affiche qu'une " +
        "fois. Pour une nouvelle carte, ouvrez la classe et choisissez « Nouveau code »." }));
      return;
    }
    $("#titre-cartes").textContent = etat.cartes.titre;
    $("#cartes-retour").href = etat.cartes.retour;
    $("#btn-imprimer").hidden = false;
    zone.replaceChildren(...etat.cartes.cartes.map((c) => el("article", { class: "carte-eleve" },
      el("p", { class: "carte-classe", texte: `${c.classe} · ${c.annee} · n° ${c.numero}` }),
      el("p", { class: "carte-nom", texte: `${c.prenom} ${c.nom}` }),
      el("p", { class: "carte-consigne", texte: "Ton code secret, dans l'ordre :" }),
      el("ol", { class: "carte-code" }, ...c.code.map((image) => el("li", {},
        el("img", { src: `/statique/codes/${image.image}.svg`, alt: "" }), el("span", { texte: image.nom })))),
      el("p", { class: "carte-pied", texte: "Garde-le pour toi : ne le montre à personne." }))));
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
    $("#filtre-attendu").value = "";
    remplirAttendus(r.attendu || "");
    for (const champ of document.querySelectorAll("#form-requete .champ")) {
      const nom = champ.dataset.champ;
      const source = champ.querySelector(".source");
      const aVerifier = (resultat.a_verifier || []).includes(nom);
      champ.classList.toggle("a-verifier", aVerifier);
      const manque = nom === "notion" ? "à écrire" : "à choisir";
      const texte = nom === "attendu" ? "proposé d'après la notion : à vérifier" : SOURCES[resultat.sources[nom]];
      if (source) source.textContent = aVerifier ? (texte || manque) : "";
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

  // --- le programme officiel (E2) : la liste des attendus pour la matière et la classe ------------------

  async function chargerProgramme(matiere, niveau) {
    if (!matiere || !niveau) return null;
    const cle = `${matiere}|${niveau}`;
    if (!etat.programmes[cle]) {
      etat.programmes[cle] = await api(`/api/programmes?${new URLSearchParams({ matiere, niveau })}`);
    }
    return etat.programmes[cle];
  }

  // des groupes par thème : « Tout le thème », puis ses attendus ; `vide` : la première option
  function optionsDuProgramme(select, programme, vide) {
    select.replaceChildren(el("option", { value: "", texte: vide }));
    for (const t of programme.themes) {
      select.append(el("optgroup", { label: t.theme },
        el("option", { value: t.id, texte: `Tout le thème : ${t.theme}`, "data-cherche": sansAccents(t.theme) }),
        ...t.attendus.map((a) => el("option", { value: a.id, texte: a.libelle,
          "data-cherche": sansAccents(`${t.theme} ${a.sous_theme || ""} ${a.libelle}`) }))));
    }
  }

  async function remplirAttendus(choisi = "") {
    const select = $("#attendu");
    const matiere = $("#matiere").value;
    const niveau = $("#niveau").value;
    let programme = null;
    try {
      programme = await chargerProgramme(matiere, niveau);
    } catch (e) {
      $("#attendu-note").textContent = `Programme illisible : ${e.message}`;
    }
    // la matière ou la classe a changé pendant le chargement : une autre liste est en route
    if ($("#matiere").value !== matiere || $("#niveau").value !== niveau) return;
    const couvert = Boolean(programme && programme.couvert);
    if (couvert) optionsDuProgramme(select, programme, "Hors référentiel (notion libre)");
    else select.replaceChildren(el("option", { value: "", texte: "Hors référentiel (notion libre)" }));
    select.disabled = !couvert;
    $("#filtre-attendu").disabled = !couvert;
    select.value = [...select.options].some((o) => o.value === choisi) ? choisi : "";
    filtrerAttendus();
    noterAttendu(programme);
  }

  function filtrerAttendus() {
    const filtre = sansAccents($("#filtre-attendu").value.trim());
    const select = $("#attendu");
    for (const groupe of select.querySelectorAll("optgroup")) {
      let visibles = 0;
      for (const option of groupe.querySelectorAll("option")) {
        // l'attendu choisi reste toujours visible
        option.hidden = Boolean(filtre) && !option.dataset.cherche.includes(filtre) && option.value !== select.value;
        if (!option.hidden) visibles += 1;
      }
      groupe.hidden = visibles === 0;
    }
  }

  function noterAttendu(programme = etat.programmes[`${$("#matiere").value}|${$("#niveau").value}`]) {
    const note = $("#attendu-note");
    const select = $("#attendu");
    if (!$("#matiere").value || !$("#niveau").value) {
      note.textContent = "Choisissez la matière et la classe pour voir les attendus du programme.";
    } else if (!programme || !programme.couvert) {
      note.textContent = "Pas encore de référentiel pour cette matière à cette classe : la notion reste libre.";
    } else if (select.value) {
      note.textContent = `${select.selectedOptions[0].textContent} — ${programme.source.bo}.`;
    } else {
      note.textContent = `Hors référentiel : l'exercice ne sera rattaché à aucun attendu du programme (${programme.source.bo}).`;
    }
  }

  function choisirAttendu() {
    const select = $("#attendu");
    // sans notion écrite, le libellé de l'attendu en tient lieu
    if (select.value && !$("#notion").value.trim()) {
      const texte = select.selectedOptions[0].textContent.replace(/^Tout le thème : /, "");
      $("#notion").value = texte.length <= 120 ? texte : `${texte.slice(0, 117).replace(/\s+\S*$/, "")}…`;
    }
    const champ = select.closest(".champ");
    champ.classList.remove("a-verifier");
    champ.querySelector(".source").textContent = "";
    noterAttendu();
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
      attendu: $("#attendu").value || null,
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

  const enCours = (vue) => vue.etat === "en_attente" || vue.etat === "en_cours";

  async function annulerTache(ident) {
    try {
      return await api(`/api/generations/${ident}/annuler`, {});
    } catch (e) {
      return { erreurAnnulation: e.message };
    }
  }

  function suivreGeneration(tache) {
    clearTimeout(etat.suivi);
    etat.generation = tache.id;
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
    const bouton = $("#btn-annuler-generation");
    bouton.hidden = !enCours(vue);
    bouton.disabled = Boolean(vue.annulation);
    if (vue.annulation && enCours(vue)) {
      $("#prog-message").textContent = "Annulation demandée : le modèle s'arrête dès qu'il donne signe de vie " +
        "(pendant la lecture de la demande, il faut attendre qu'il ait fini de la lire).";
    }
    $("#prog-journal").replaceChildren(
      ...(vue.journal || []).map((j) => el("li", {}, el("span", { class: "temps", texte: duree(j.t) }), " ", j.message)));
  }

  function finGeneration(vue) {
    $("#btn-generer").disabled = false;
    $("#btn-annuler-generation").hidden = true;
    etat.generation = null;
    if (vue.etat === "annule") {
      $("#prog-message").textContent = "Génération annulée : rien n'a été enregistré.";
      $("#prog-erreur").hidden = true;
      return;
    }
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
      ["recherche", "#filtre-recherche"], ["attendu", "#filtre-programme"]]) {
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

  async function remplirFiltreProgramme() {
    const select = $("#filtre-programme");
    const matiere = $("#filtre-matiere").value;
    const niveau = $("#filtre-niveau").value;
    select.replaceChildren(el("option", { value: "", texte: matiere && niveau ? "Tous" : "Choisir matière et classe" }));
    select.disabled = true;
    let programme = null;
    try {
      programme = await chargerProgramme(matiere, niveau);
    } catch (_) { /* filtre indisponible : la banque reste lisible */ }
    if ($("#filtre-matiere").value !== matiere || $("#filtre-niveau").value !== niveau) return;
    if (programme && programme.couvert) {
      optionsDuProgramme(select, programme, "Tous");
      select.disabled = false;
    } else if (matiere && niveau) {
      select.replaceChildren(el("option", { value: "", texte: "Pas de référentiel" }));
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
    const programme = meta.programme;
    $("#ex-programme").hidden = !programme;
    if (programme) {
      const libelles = programme.libelles || programme.attendus;
      $("#ex-programme").textContent = `Programme officiel (${programme.source}) : ` +
        libelles.map((l) => `« ${l} »`).join(" ; ") + (programme.choisi ? "" : " (rattaché par le générateur)");
    }
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
    $("#ex-programme").hidden = true;
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
      let texte = vue.etat === "en_attente" && vue.devant
        ? `Question ${numero} : en attente (${vue.devant} tâche(s) avant).`
        : `Question ${numero} : ${p.message || "démarrage…"}`;
      if (vue.annulation) texte = `Question ${numero} : annulation demandée…`;
      const lignes = [el("p", { texte })];
      if (vue.ecoule_s !== undefined) lignes.push(el("p", { class: "note", texte: `Temps écoulé : ${duree(vue.ecoule_s)}` }));
      lignes.push(el("button", { type: "button", class: "secondaire petit annuler-tache", "data-tache": tache.id,
        disabled: Boolean(vue.annulation), texte: "Annuler la régénération" }));
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
      if (vue.etat === "annule") {
        bloc.replaceChildren(el("p", { texte: `Régénération de la question ${numero} annulée : la question d'origine est conservée.` }));
        occuper(false);
      } else if (vue.etat === "termine") {
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
  // motDePasse : true pour redemander le mot de passe (la promesse le donne ; il est effacé du champ aussitôt)
  function demander({ titre, texte, label = "", ok, champ = true, motDePasse = false }) {
    const dialogue = $("#dialogue");
    $("#dialogue-titre").textContent = titre;
    $("#dialogue-texte").textContent = texte;
    $("#dialogue-champ").hidden = !champ;
    $("#dialogue-champ-mdp").hidden = !motDePasse;
    $("#dialogue-label").textContent = label;
    $("#dialogue-ok").textContent = ok;
    $("#dialogue-motif").value = "";
    $("#dialogue-mdp").value = "";
    return new Promise((resoudre) => {
      const fermer = (valeur) => {
        $("#dialogue-form").onsubmit = null;
        $("#dialogue-annuler").onclick = null;
        dialogue.onclose = null;
        $("#dialogue-mdp").value = "";
        if (dialogue.open) dialogue.close();
        resoudre(valeur);
      };
      $("#dialogue-form").onsubmit = (e) => {
        e.preventDefault();
        if (motDePasse && !$("#dialogue-mdp").value) { $("#dialogue-mdp").focus(); return; }
        fermer(motDePasse ? $("#dialogue-mdp").value : $("#dialogue-motif").value.trim());
      };
      $("#dialogue-annuler").onclick = () => fermer(null);
      // l'évènement « close » arrive après coup : celui d'un dialogue précédent, déjà rouvert, est ignoré
      dialogue.onclose = () => { if (!dialogue.open) fermer(null); };
      dialogue.showModal();
      (motDePasse ? $("#dialogue-mdp") : champ ? $("#dialogue-motif") : $("#dialogue-ok")).focus();
    });
  }

  // --- démarrage --------------------------------------------------------------------------------

  async function demarrer() {
    $("#form-connexion").addEventListener("submit", seConnecter);
    $("#btn-deconnexion").addEventListener("click", seDeconnecter);
    $("#form-mot-de-passe").addEventListener("submit", changerMotDePasse);
    $("#form-nouveau-compte").addEventListener("submit", creerCompte);
    $("#table-comptes").addEventListener("click", agirSurCompte);
    $("#btn-provisoire-ok").addEventListener("click", () => {
      $("#provisoire").hidden = true;
      $("#provisoire-valeur").textContent = "";
    });
    $("#btn-nouvelle-classe").addEventListener("click", ouvrirFormulaireClasse);
    $("#btn-annuler-classe").addEventListener("click", () => { $("#form-classe").hidden = true; });
    $("#form-classe").addEventListener("submit", verifierListe);
    $("#classe-liste").addEventListener("input", () => { $("#classe-apercu").hidden = true; etat.listeLue = null; });
    $("#btn-creer-classe").addEventListener("click", creerClasse);
    $("#classes-archivees").addEventListener("change", chargerClasses);
    $("#btn-purge").addEventListener("click", purgerAnnees);
    $("#table-eleves").addEventListener("click", agirSurEleve);
    $("#btn-cl-ajouter").addEventListener("click", () => {
      $("#form-ajout").hidden = false;
      $("#ajout-liste").focus();
    });
    $("#btn-annuler-ajout").addEventListener("click", () => { $("#form-ajout").hidden = true; });
    $("#form-ajout").addEventListener("submit", ajouterEleves);
    $("#btn-cl-codes").addEventListener("click", nouveauxCodesClasse);
    $("#btn-cl-archiver").addEventListener("click", archiverClasse);
    $("#btn-imprimer").addEventListener("click", () => window.print());
    $("#su-masquer").addEventListener("change", (e) => { etat.masquer = e.target.checked; afficherSuivi(); });
    $("#su-besoins").addEventListener("click", (e) => {
      const bouton = e.target.closest("button[data-generer]");
      if (bouton) genererDepuisSuivi(bouton);
    });
    $("#su-groupes").addEventListener("click", agirSurGroupe);
    $("#su-propositions").addEventListener("click", agirSurPropositions);
    $("#btn-su-proposer").addEventListener("click", () => {
      if (!etat.tableau || !etat.tableau.propositions) return;
      etat.tableau.montrerProposees = true;
      etat.tableau.ecartees = new Set();
      afficherPropositions();
    });
    $("#table-tentatives").addEventListener("click", agirSurTentative);
    $("#form-phrase").addEventListener("submit", analyser);
    $("#btn-a-la-main").addEventListener("click", remplirALaMain);
    $("#form-requete").addEventListener("submit", generer);
    $("#type").addEventListener("change", choisirType);
    for (const id of ["#matiere", "#niveau"]) {
      // une autre matière ou une autre classe : un autre programme, l'attendu choisi ne vaut plus
      $(id).addEventListener("change", () => { $("#filtre-attendu").value = ""; remplirAttendus(""); });
    }
    $("#filtre-attendu").addEventListener("input", filtrerAttendus);
    $("#attendu").addEventListener("change", choisirAttendu);
    for (const id of ["#filtre-matiere", "#filtre-niveau"]) $(id).addEventListener("change", remplirFiltreProgramme);
    for (const id of ["#notion", "#matiere", "#precisions", "#attendu"]) {
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
    $("#btn-annuler-generation").addEventListener("click", async () => {
      if (!etat.generation) return;
      $("#btn-annuler-generation").disabled = true;
      const vue = await annulerTache(etat.generation);
      if (vue.erreurAnnulation) $("#prog-message").textContent = `Annulation impossible : ${vue.erreurAnnulation}`;
      else afficherProgression(vue);
    });
    $("#ex-regeneration").addEventListener("click", async (e) => {
      const bouton = e.target.closest(".annuler-tache");
      if (!bouton || bouton.disabled) return;
      bouton.disabled = true;
      const vue = await annulerTache(bouton.dataset.tache);
      if (vue.erreurAnnulation) $("#ex-message").textContent = `Annulation impossible : ${vue.erreurAnnulation}`;
    });
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

    // déjà connecté (page rechargée) ? sinon, l'écran de connexion (affiché par api() sur le 401)
    try {
      const { compte } = await api("/api/session");
      await ouvrirSession(compte);
    } catch (e) {
      if ($("#vue-connexion").hidden) afficherConnexion(`Le serveur ne répond pas : ${e.message}`);
    }
  }

  document.addEventListener("DOMContentLoaded", demarrer);
})();
