// Essai de la page d'exercice de l'élève (le fichier HTML autonome) dans Chrome, au clavier seul (E5.4). Sans dépendance.
//
//     node tests/navigateur/exercice.mjs              (depuis Arrera-School-IA ; Node 22 ou plus, Google Chrome)
//
// Rend un exercice de 4 questions avec le vrai gabarit, l'ouvre en file:// (hors de tout serveur), puis le fait de
// bout en bout sans aucun événement de souris, avec les touches qu'envoie un Stream Deck : aide « ? », réponses par
// lettre et par chiffre (dont le chiffre d'un clavier AZERTY), flèches, Entrée, lecture à voix haute « L »,
// recommencer « R ». La synthèse vocale est remplacée par une fausse, qui note ce qu'on lui fait lire : on vérifie le
// texte, et qu'une voix en ligne n'est jamais utilisée. Aucune erreur JavaScript ni violation de CSP.
// Code de sortie : 0 si tous les contrôles passent, 1 sinon.
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const CHROMES = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome",
  "/usr/bin/chromium", "/usr/bin/chromium-browser"];
const DEBOGAGE = 9334;
const dossier = mkdtempSync(join(tmpdir(), "essai-exercice-"));
const python = existsSync(".venv/bin/python") ? ".venv/bin/python" : "python3";
const attendre = (ms) => new Promise((r) => setTimeout(r, ms));

// un exercice de démonstration : des questions à 3 et à 4 propositions, une fraction et un carré à prononcer
const EXERCICE = {
  type: "qcm", titre: "Essai du clavier", matiere: "maths", niveau: "5e", notion: "Fractions et carrés",
  consigne: "Pour chaque question, choisis la seule bonne réponse.",
  questions: [
    { enonce: "Quelle fraction est égale à 3/4 ?", propositions: ["6/8", "3/8", "4/3", "6/4"],
      explication: "On multiplie le numérateur et le dénominateur par 2 : 3/4 = 6/8.", index_correct: 0 },
    { enonce: "Combien vaut 5² ?", propositions: ["10", "25", "52"],
      explication: "5² = 5 × 5 = 25.", index_correct: 1 },
    { enonce: "Quelle est la moitié de 18 ?", propositions: ["6", "8", "9", "36"],
      explication: "18 ÷ 2 = 9.", index_correct: 2 },
    { enonce: "Quel nombre est un multiple de 7 ?", propositions: ["17", "27", "35"],
      explication: "35 = 7 × 5, donc 35 est un multiple de 7.", index_correct: 2 },
  ],
};
writeFileSync(join(dossier, "exercice.json"), JSON.stringify(EXERCICE));
const rendu = spawnSync(python, ["-m", "generateur.moteur.rendu", join(dossier, "exercice.json"), "--sortie",
  join(dossier, "exercice.html")], { encoding: "utf-8" });
if (rendu.status !== 0) { console.error(rendu.stderr); process.exit(1); }
const URL_EXERCICE = pathToFileURL(join(dossier, "exercice.html")).href;

const chrome = spawn(CHROMES.find(existsSync), ["--headless=new", `--remote-debugging-port=${DEBOGAGE}`,
  `--user-data-dir=${join(dossier, "profil")}`, "--window-size=1280,1000", "about:blank"], { stdio: "ignore" });
process.on("exit", () => chrome.kill());

async function prete(url) {
  for (let i = 0; i < 100; i++) { try { return await (await fetch(url)).json(); } catch { await attendre(200); } }
  throw new Error(`${url} ne répond pas`);
}
const onglet = (await prete(`http://127.0.0.1:${DEBOGAGE}/json`)).find((c) => c.type === "page");
const ws = new WebSocket(onglet.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));

let numero = 0;
const enAttente = new Map(), problemes = [];
ws.addEventListener("message", (m) => {
  const d = JSON.parse(m.data);
  if (d.id && enAttente.has(d.id)) { enAttente.get(d.id)(d); enAttente.delete(d.id); }
  if (d.method === "Runtime.exceptionThrown") problemes.push(`exception : ${d.params.exceptionDetails.exception?.description}`);
  if (d.method === "Log.entryAdded" && d.params.entry.level === "error") problemes.push(`console : ${d.params.entry.text}`);
});
const cdp = (method, params = {}) => new Promise((r) => {
  const id = ++numero; enAttente.set(id, r); ws.send(JSON.stringify({ id, method, params }));
});
async function js(expression) {
  const r = await cdp("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.result.exceptionDetails) throw new Error(`${expression} → ${r.result.exceptionDetails.text}`);
  return r.result.result.value;
}
async function capture(nom) {
  const r = await cdp("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(dossier, `${nom}.png`), Buffer.from(r.result.data, "base64"));
}
const resultats = [];
const verifier = (nom, ok, detail = "") => resultats.push({ nom, ok: Boolean(ok), detail });

// les touches, comme les envoie le clavier du système (donc un Stream Deck) : jamais d'événement de souris
const TOUCHES = {
  a: ["a", "KeyA", 65], b: ["b", "KeyB", 66], c: ["c", "KeyC", 67], d: ["d", "KeyD", 68],
  l: ["l", "KeyL", 76], r: ["r", "KeyR", 82], 1: ["1", "Digit1", 49], 2: ["2", "Digit2", 50],
  3: ["3", "Digit3", 51], 4: ["4", "Digit4", 52], "&": ["&", "Digit1", 49], // le « 1 » d'un clavier AZERTY, sans Maj
  "?": ["?", "Slash", 191, 8], Enter: ["Enter", "Enter", 13], Escape: ["Escape", "Escape", 27],
  ArrowRight: ["ArrowRight", "ArrowRight", 39], ArrowLeft: ["ArrowLeft", "ArrowLeft", 37], Tab: ["Tab", "Tab", 9],
};
async function appuyer(nom) {
  const [key, code, windowsVirtualKeyCode, modifiers = 0] = TOUCHES[nom];
  const text = key === "Enter" ? "\r" : key.length === 1 ? key : undefined;
  await cdp("Input.dispatchKeyEvent", { type: text ? "keyDown" : "rawKeyDown", key, code, windowsVirtualKeyCode, modifiers, text });
  await cdp("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode, modifiers });
  await attendre(60);
}

// la fausse synthèse vocale : une voix installée (hors ligne) et une voix en ligne, ou rien du tout
let script = null;
async function ouvrir(voix) {
  if (script) await cdp("Page.removeScriptToEvaluateOnNewDocument", { identifier: script });
  const r = await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
    const voix = ${JSON.stringify(voix)};
    window.__lu = []; window.__annule = 0;
    if (voix === null) { Object.defineProperty(window, "speechSynthesis", { value: undefined }); return; }
    window.SpeechSynthesisUtterance = function (texte) { this.text = texte; };
    Object.defineProperty(window, "speechSynthesis", { value: {
      getVoices: () => voix, addEventListener() {}, removeEventListener() {},
      speak: (u) => window.__lu.push({ texte: u.text, voix: u.voice.name, enLigne: !u.voice.localService }),
      cancel: () => { window.__annule++; },
    } });
  })()` });
  script = r.result.identifier;
  await cdp("Page.navigate", { url: URL_EXERCICE });
  for (let i = 0; i < 50 && !(await js(`document.readyState === "complete"`).catch(() => false)); i++) await attendre(100);
}
const VOIX = [{ name: "Google français", lang: "fr-FR", localService: false }, { name: "Thomas", lang: "fr-FR", localService: true },
  { name: "Daniel", lang: "en-GB", localService: true }];

// rang affiché (A = 0) de la bonne réponse, de la question n (le gabarit mélange les propositions)
const rangBon = (n) => js(`(() => { const q = document.querySelectorAll(".question")[${n}];
  return [...q.querySelectorAll(".prop")].findIndex((b) => b.dataset.index === q.dataset.correct); })()`);
const courante = () => js(`[...document.querySelectorAll(".question")].findIndex((q) => q.classList.contains("courante"))`);
const choisie = (n) => js(`(() => { const q = document.querySelectorAll(".question")[${n}];
  return [...q.querySelectorAll(".prop")].findIndex((b) => b.getAttribute("aria-pressed") === "true"); })()`);
const texte = (sel) => js(`document.querySelector(${JSON.stringify(sel)}).textContent`);

await cdp("Runtime.enable"); await cdp("Log.enable"); await cdp("Page.enable");
try {
  // 1. l'aide : « ? » l'ouvre, Échap la ferme ; la question 1 est la question en cours
  await ouvrir(VOIX);
  verifier("au départ : aide cachée, question 1 en cours, boutons « Écouter » affichés",
    await js(`document.querySelector("#touches").hidden`) && await courante() === 0 &&
    await js(`[...document.querySelectorAll(".ecouter")].every((b) => !b.hidden)`));
  await appuyer("?");
  verifier("« ? » : la carte de touches s'affiche", await js(`!document.querySelector("#touches").hidden &&
    document.querySelector("#btn-touches").getAttribute("aria-expanded") === "true"`));
  await capture("1-aide");
  await appuyer("Escape");
  verifier("Échap : la carte de touches se ferme", await js(`document.querySelector("#touches").hidden`));

  // 2. Entrée sans réponse : rien n'est corrigé, on revient à la première question sans réponse
  await appuyer("Enter");
  verifier("Entrée sans réponse : « Il reste 4 questions sans réponse », rien de corrigé",
    (await texte("#score")) === "Il reste 4 questions sans réponse." && await js(`!document.querySelector(".prop.juste")`));

  // 3. écouter la question 1 (fausse synthèse) : énoncé puis propositions, la fraction prononcée, la voix installée
  await appuyer("l");
  let lu = await js(`window.__lu`);
  const lettres = await js(`[...document.querySelectorAll(".question")[0].querySelectorAll(".prop")].map((b, i) => "ABCD"[i] + " : " + b.textContent.replace(/(\\d)\\/(\\d)/g, "$1 sur $2"))`);
  verifier("L : la question 1 est lue (énoncé, puis les propositions dans l'ordre affiché)", lu.length === 1 &&
    lu[0].texte.startsWith("Question 1 sur 4. Quelle fraction est égale à 3 sur 4 ?") &&
    lettres.every((l) => lu[0].texte.includes(l)), lu[0]?.texte);
  verifier("L : la voix française installée, jamais la voix en ligne", lu[0]?.voix === "Thomas" && !lu[0]?.enLigne);
  const annulees = await js(`window.__annule`);
  await appuyer("l");
  verifier("L une deuxième fois : la lecture s'arrête", (await js(`window.__annule`)) > annulees && (await js(`window.__lu.length`)) === 1);

  // 4. répondre : lettres et chiffres, la question 3 fausse exprès ; D sur une question à 3 propositions : sans effet
  const bons = [];
  for (let n = 0; n < 4; n++) bons.push(await rangBon(n));
  await appuyer("abcd"[bons[0]]);
  verifier("lettre : la réponse est choisie à la question 1", await choisie(0) === bons[0]);
  await appuyer("ArrowRight");
  verifier("→ : la question 2 devient la question en cours (et reçoit le curseur)", await courante() === 1 &&
    await js(`document.activeElement === document.querySelectorAll(".question")[1]`));
  await appuyer("d");
  verifier("D sur une question à 3 propositions : rien n'est choisi", await choisie(1) === -1);
  await appuyer(String(bons[1] + 1));
  verifier("chiffre : la réponse est choisie à la question 2", await choisie(1) === bons[1]);
  await appuyer("ArrowRight");
  const fausse = (bons[2] + 1) % 4;
  await appuyer("abcd"[fausse]);
  await appuyer("ArrowLeft");
  verifier("← : retour à la question 2, sa réponse est gardée", await courante() === 1 && await choisie(1) === bons[1]);
  await appuyer("ArrowRight");
  await appuyer("ArrowRight");
  verifier("la question en cours est encadrée, et annoncée après un choix", await courante() === 3 &&
    (await texte("#annonce")) === `Question 3 : réponse ${"ABCD"[fausse]}.`);

  // 5. Tab puis Entrée sur une proposition : Entrée appuie sur le bouton (le comportement habituel), sans valider
  await appuyer("Tab"); // « Écouter »
  await appuyer("Tab"); // la première proposition
  const surBouton = await js(`document.activeElement.classList.contains("prop") ? [...document.activeElement.closest(".question").querySelectorAll(".prop")].indexOf(document.activeElement) : -1`);
  await appuyer("Enter");
  verifier("Tab Tab, puis Entrée sur une proposition : elle est choisie, rien n'est corrigé", surBouton >= 0 &&
    await choisie(3) === surBouton && await js(`!document.querySelector(".prop.juste")`), String(surBouton));
  await appuyer("&");
  verifier("le « 1 » d'un clavier AZERTY (touche & sans Maj) choisit A, le curseur revient sur la question",
    await choisie(3) === 0 && await js(`document.activeElement === document.querySelectorAll(".question")[3]`));
  await appuyer(String(bons[3] + 1));
  await capture("2-reponses");

  // 6. Entrée : corrigé ; 3 sur 4, la réponse fausse marquée, les explications affichées
  await appuyer("Enter");
  verifier("Entrée : l'exercice est corrigé, « Score : 3 / 4 »", (await texte("#score")) === "Score : 3 / 4" &&
    await js(`document.querySelectorAll(".prop.faux").length === 1 && [...document.querySelectorAll(".explication")].every((e) => !e.hidden)`));
  await appuyer("a");
  verifier("après la correction, les réponses ne changent plus", await choisie(0) === bons[0]);
  await appuyer("ArrowLeft");
  verifier("après la correction, les flèches parcourent les questions", await courante() === 2);
  await appuyer("l");
  lu = await js(`window.__lu`);
  verifier("L après la correction : la réponse et l'explication sont lues aussi", lu.length === 2 &&
    lu[1].texte.includes(`Ta réponse : ${"ABCD"[fausse]}. La bonne réponse est ${"ABCD"[bons[2]]}.`) &&
    lu[1].texte.includes("Explication : 18 divisé par 2 = 9."), lu[1]?.texte);
  await capture("3-corrige");

  // 7. R : on recommence ; tout est remis à zéro, la question 1 en cours
  await appuyer("r");
  verifier("R : l'exercice recommence (aucune réponse, aucun score, question 1 en cours)",
    await js(`!document.querySelector('.prop[aria-pressed="true"], .prop.juste, .prop:disabled')`) &&
    (await texte("#score")) === "" && await courante() === 0);
  for (let n = 0; n < 4; n++) {
    await appuyer("abcd"[await rangBon(n)]);
    await appuyer("ArrowRight");
  }
  await appuyer("Enter");
  verifier("un deuxième tour au clavier seul : « Score : 4 / 4 »", (await texte("#score")) === "Score : 4 / 4");

  // 8. sans voix française installée : rien n'est lu (surtout pas par la voix en ligne), un message le dit
  await ouvrir(VOIX.filter((v) => v.name !== "Thomas"));
  await appuyer("l");
  verifier("sans voix française installée : rien n'est lu, un message l'explique", (await js(`window.__lu.length`)) === 0 &&
    (await texte("#annonce")).startsWith("Lecture impossible : aucune voix française"));

  // 9. navigateur sans synthèse vocale : pas de bouton « Écouter », L sans effet, le reste fonctionne
  await ouvrir(null);
  await appuyer("l");
  verifier("sans synthèse vocale : boutons « Écouter » cachés, L sans erreur",
    await js(`[...document.querySelectorAll(".ecouter")].every((b) => b.hidden)`) && (await texte("#annonce")) === "");

  // 10. téléphone, aide ouverte : pas de défilement horizontal
  await cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await ouvrir(VOIX);
  await appuyer("?");
  verifier("téléphone, aide ouverte : pas de défilement horizontal", await js(`document.documentElement.scrollWidth <= window.innerWidth`));
  await capture("4-telephone");
} catch (e) {
  verifier("parcours interrompu", false, e.message);
}
verifier("aucune erreur JavaScript ni violation de CSP", problemes.length === 0, problemes.join(" ; "));
for (const r of resultats) console.log(`${r.ok ? "✔" : "✘"} ${r.nom}${r.detail && !r.ok ? ` — ${r.detail}` : ""}`);
const echecs = resultats.filter((r) => !r.ok).length;
console.log(`\n${resultats.length - echecs} contrôle(s) sur ${resultats.length} ; captures : ${dossier}`);
ws.close();
chrome.kill();
process.exit(echecs ? 1 : 0);
