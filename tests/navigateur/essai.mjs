// Essai de l'interface enseignant dans Chrome, piloté par le protocole DevTools (3.3, C6). Sans dépendance.
//
//     node tests/navigateur/essai.mjs                 (depuis Arrera-School-IA ; Node 22 ou plus, Google Chrome)
//     node tests/navigateur/essai.mjs --avec-modele   (en plus : annuler une vraie génération, ~15 s)
//
// Lance l'interface sur une copie de la banque (serveur_copie.py), puis Chrome sans fenêtre, et refait le
// parcours de l'enseignant : analyser une demande, générer (calcul mental : le programme seul, sans le modèle),
// relire, modifier une question, accepter, rechercher, supprimer, affichage sur téléphone ; aucune erreur
// JavaScript ni violation de CSP. Captures d'écran et copie de la banque : dans le dossier affiché à la fin.
// Code de sortie : 0 si tous les contrôles passent, 1 sinon.
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROMES = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome",
  "/usr/bin/chromium", "/usr/bin/chromium-browser"];
const AVEC_MODELE = process.argv.includes("--avec-modele");
const PORT = 8012, DEBOGAGE = 9333, BASE = `http://127.0.0.1:${PORT}/`;
const dossier = mkdtempSync(join(tmpdir(), "essai-interface-"));
const python = existsSync(".venv/bin/python") ? ".venv/bin/python" : "python3";
const attendre = (ms) => new Promise((r) => setTimeout(r, ms));

const serveur = spawn(python, ["tests/navigateur/serveur_copie.py", dossier, String(PORT)], { stdio: "inherit" });
const chrome = spawn(CHROMES.find(existsSync), ["--headless=new", `--remote-debugging-port=${DEBOGAGE}`,
  `--user-data-dir=${join(dossier, "profil")}`, "--window-size=1280,1600", "about:blank"], { stdio: "ignore" });
const arreter = () => { chrome.kill(); serveur.kill(); };
process.on("exit", arreter);

async function prete(url) {
  for (let i = 0; i < 100; i++) { try { return await (await fetch(url)).json(); } catch { await attendre(200); } }
  throw new Error(`${url} ne répond pas`);
}
await prete(BASE + "api/types");
const page = (await prete(`http://127.0.0.1:${DEBOGAGE}/json`)).find((c) => c.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));

let numero = 0;
const enAttente = new Map(), problemes = [];
ws.addEventListener("message", (m) => {
  const d = JSON.parse(m.data);
  if (d.id && enAttente.has(d.id)) { enAttente.get(d.id)(d); enAttente.delete(d.id); }
  if (d.method === "Runtime.exceptionThrown") problemes.push(`exception : ${d.params.exceptionDetails.exception?.description}`);
  if (d.method === "Log.entryAdded" && d.params.entry.level === "error" && !/status of 4(09|22)/.test(d.params.entry.text)) {
    problemes.push(`console : ${d.params.entry.text}`); // 409, 422 : refus attendus, provoqués par l'essai
  }
});
const cdp = (method, params = {}) => new Promise((r) => {
  const id = ++numero; enAttente.set(id, r); ws.send(JSON.stringify({ id, method, params }));
});
async function js(expression) {
  const r = await cdp("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.result.exceptionDetails) throw new Error(`${expression} → ${r.result.exceptionDetails.text}`);
  return r.result.result.value;
}
async function jusqua(expression, ms = 15000) {
  for (let t = 0; t < ms; t += 100) { if (await js(expression)) return; await attendre(100); }
  throw new Error(`délai dépassé : ${expression}`);
}
async function capture(nom) {
  const r = await cdp("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(dossier, `${nom}.png`), Buffer.from(r.result.data, "base64"));
}
const aller = (chemin) => cdp("Page.navigate", { url: BASE + chemin });
const resultats = [];
const verifier = (nom, ok, detail = "") => resultats.push({ nom, ok: Boolean(ok), detail });
const saisir = (selecteur, valeur) => js(`(() => { const e = document.querySelector(${JSON.stringify(selecteur)});
  e.value = ${JSON.stringify(valeur)}; e.dispatchEvent(new Event("input", { bubbles: true })); })()`);

await cdp("Runtime.enable"); await cdp("Log.enable"); await cdp("Page.enable");
try {
  // 1. analyser et générer, sans le modèle : le calcul mental est fait par le programme seul
  await aller("#/generer");
  await jusqua(`document.querySelector("#type").options.length > 0`);
  await saisir("#phrase", "un QCM de 5 questions de calcul mental pour des 6e");
  await js(`document.querySelector("#btn-analyser").click()`);
  await jusqua(`!document.querySelector("#form-requete").hidden`);
  verifier("analyse : formulaire pré-rempli", await js(`document.querySelector("#matiere").value === "maths" &&
    document.querySelector("#niveau").value === "6e" && document.querySelector("#nb_questions").value === "5"`));
  await js(`document.querySelector("#btn-generer").click()`);
  await jusqua(`location.hash.startsWith("#/exercice/") && document.querySelectorAll("#ex-questions .question").length === 5`, 60000);
  const ident = await js(`location.hash.slice("#/exercice/".length)`);
  verifier("génération puis relecture", true, ident);
  verifier("calculs faits par le programme", await js(`document.querySelector("#ex-validation").textContent.includes("justes par construction")`));
  await capture("1-relecture");

  // 2. modifier une question à la main : refus de la page, refus du serveur, puis enregistrement
  await js(`document.querySelector("#question-2 .modifier").click()`);
  await jusqua(`document.querySelector("#question-2 form.edition")`);
  verifier("modifier : formulaire seul à l'écran", await js(`getComputedStyle(document.querySelector("#question-2 .propositions")).display === "none"`));
  await js(`(() => { const f = document.querySelector("#question-2 form.edition");
    f.querySelector("input[type=radio]:checked").parentElement.querySelector("input[type=text]").value = ""; f.requestSubmit(); })()`);
  verifier("modifier : bonne réponse vide refusée", await js(`document.querySelector("#question-2 .edition .erreur").textContent === "La bonne réponse cochée est vide."`));
  await js(`document.querySelector("#question-2 .annuler-edition").click()`);
  await js(`document.querySelector("#question-2 .modifier").click()`);
  await js(`(() => { const f = document.querySelector("#question-2 form.edition");
    const champs = [...f.querySelectorAll(".proposition-edit")]; const coche = champs.findIndex((c) => c.querySelector("input[type=radio]").checked);
    let gardes = 0; champs.forEach((c, j) => { if (j !== coche && gardes++ >= 1) c.querySelector("input[type=text]").value = ""; }); f.requestSubmit(); })()`);
  await jusqua(`!document.querySelector("#question-2 .edition .erreur").hidden`);
  verifier("modifier : 2 propositions refusées par le serveur", /au moins 3/.test(await js(`document.querySelector("#question-2 .edition .erreur").textContent`)));
  await js(`document.querySelector("#question-2 .annuler-edition").click()`);
  await js(`document.querySelector("#question-2 .modifier").click()`);
  await js(`(() => { const f = document.querySelector("#question-2 form.edition");
    f.querySelector("textarea[id^=edit-explication]").value += " Relu."; f.requestSubmit(); })()`);
  await jusqua(`document.querySelector("#ex-message").textContent.includes("modifiée")`);
  verifier("modifier : enregistrée, badge « modifiée à la main »", await js(`(() => { const b = document.querySelector("#question-2 .badges").textContent;
    return b.includes("modifiée à la main") && !b.includes("à relire"); })()`));
  await capture("2-modification");

  // 3. accepter ; un exercice accepté ne se supprime pas
  await js(`document.querySelector("#btn-accepter").click()`);
  await jusqua(`document.querySelector("#ex-statut").textContent === "Accepté"`);
  verifier("accepter", true);
  verifier("supprimer : désactivé sur un exercice accepté", await js(`document.querySelector("#btn-supprimer").disabled`));

  // 4. rechercher dans la banque
  await aller("#/banque");
  await jusqua(`document.querySelectorAll("#table-banque tbody tr").length > 0`);
  const total = await js(`document.querySelectorAll("#table-banque tbody tr").length`);
  await saisir("#filtre-recherche", "CALCUL MENTAL");
  await jusqua(`document.querySelectorAll("#table-banque tbody tr").length <= ${total} && !document.querySelector("#banque-etat").textContent.startsWith("Chargement")`);
  await attendre(600);
  const titres = await js(`[...document.querySelectorAll("#table-banque tbody tr td:nth-child(2)")].map((t) => t.textContent)`);
  verifier("rechercher (majuscules)", titres.length > 0 && titres.every((t) => /calcul mental/i.test(t)), `${titres.length} sur ${total}`);
  await saisir("#filtre-recherche", "zzzz");
  await jusqua(`document.querySelector("#banque-etat").textContent.includes("Aucun")`);
  verifier("rechercher : aucun résultat annoncé", true);

  // 5. supprimer un exercice à relire (annuler, puis confirmer)
  await js(`(() => { document.querySelector("#filtre-recherche").value = ""; document.querySelector("#filtre-statut").value = "genere";
    document.querySelector("#filtre-statut").dispatchEvent(new Event("change", { bubbles: true })); })()`);
  await jusqua(`document.querySelectorAll("#table-banque tbody tr a").length > 0`);
  const aSupprimer = await js(`document.querySelector("#table-banque tbody tr a").getAttribute("href").slice("#/exercice/".length)`);
  await aller(`#/exercice/${aSupprimer}`);
  await jusqua(`!document.querySelector("#btn-supprimer").disabled && document.querySelector("#ex-statut").textContent === "À relire"`);
  await js(`document.querySelector("#btn-supprimer").click()`);
  await jusqua(`document.querySelector("#dialogue").open`);
  verifier("supprimer : confirmation sans champ de motif", await js(`document.querySelector("#dialogue-champ").hidden`));
  await js(`document.querySelector("#dialogue-annuler").click()`);
  verifier("supprimer : annuler ne supprime rien", await js(`location.hash`) === `#/exercice/${aSupprimer}`);
  await js(`document.querySelector("#btn-supprimer").click()`);
  await jusqua(`document.querySelector("#dialogue").open`);
  await js(`document.querySelector("#dialogue-ok").click()`);
  await jusqua(`location.hash === "#/banque" && document.querySelector("#banque-etat").textContent.includes("supprimé")`);
  verifier("supprimer : retour à la banque", existsSync(join(dossier, "banque", "supprimes", `${aSupprimer}.json`)), "fichier dans banque/supprimes/");

  // 6. (option) annuler une vraie génération par le modèle, pendant qu'il écrit
  if (AVEC_MODELE) {
    await aller("#/generer");
    await jusqua(`document.querySelector("#type").options.length > 0`);
    await js(`document.querySelector("#btn-a-la-main").click()`);
    await js(`(() => { const choisir = (id, v) => { const e = document.querySelector(id); e.value = v; };
      choisir("#matiere", "francais"); choisir("#niveau", "5e"); choisir("#notion", "le passé composé"); })()`);
    await js(`document.querySelector("#btn-generer").click()`);
    await jusqua(`!document.querySelector("#btn-annuler-generation").hidden`);
    await jusqua(`document.querySelector("#prog-message").textContent.includes("écriture")`, 60000);
    await js(`document.querySelector("#btn-annuler-generation").click()`);
    await jusqua(`document.querySelector("#prog-message").textContent.startsWith("Génération annulée")`, 30000);
    verifier("annuler une génération en cours d'écriture", await js(`document.querySelector("#btn-annuler-generation").hidden &&
      !document.querySelector("#btn-generer").disabled`));
  }

  // 7. téléphone : pas de défilement horizontal
  await cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  for (const chemin of ["#/generer", "#/banque", `#/exercice/${ident}`]) {
    await aller(chemin);
    await attendre(800);
    verifier(`téléphone ${chemin.split("/")[1]} : pas de défilement horizontal`, await js(`document.documentElement.scrollWidth <= window.innerWidth`));
  }
  await capture("3-telephone");
} catch (e) {
  verifier("parcours interrompu", false, e.message);
}
verifier("aucune erreur JavaScript ni violation de CSP", problemes.length === 0, problemes.join(" ; "));
for (const r of resultats) console.log(`${r.ok ? "✔" : "✘"} ${r.nom}${r.detail ? ` — ${r.detail}` : ""}`);
const echecs = resultats.filter((r) => !r.ok).length;
console.log(`\n${resultats.length - echecs} contrôle(s) sur ${resultats.length} ; captures et banque copiée : ${dossier}`);
ws.close();
arreter();
process.exit(echecs ? 1 : 0);
