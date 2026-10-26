// Essai de la page d'exercice de l'élève (le fichier HTML autonome) dans Chrome, au clavier seul (E5.4, E7). Sans dépendance.
//
//     node tests/navigateur/exercice.mjs              (depuis Arrera-School-IA ; Node 22 ou plus, Google Chrome)
//
// Rend un exercice de 4 questions avec le vrai gabarit, en 5e (style « collège ») et en 6e (style « enfant »), l'ouvre
// en file:// (hors de tout serveur), puis le fait de bout en bout sans aucun événement de souris, avec les touches
// qu'envoie un Stream Deck : aide « ? », réponses par lettre et par chiffre (dont le chiffre d'un clavier AZERTY),
// Entrée pour vérifier puis passer, flèche, lecture à voix haute « L », rejouer « R ».
// Le parcours se fait d'abord animations coupées (prefers-reduced-motion : le jeu doit être le même), puis avec
// les animations, dans les deux styles : la vague (6e) et le balayage (collège) entre deux questions, l'écran de fin.
// La synthèse vocale est remplacée par une fausse, qui note ce qu'on lui fait lire ; une voix en ligne n'est jamais
// utilisée. Puis la page avec la voix de Piper rangée dedans (si elle est installée) : les morceaux joués dans
// l'ordre affiché, et un vrai morceau MP3 décodé par Chrome (CSP media-src data:). Aucune erreur JavaScript ni
// violation de CSP. Code de sortie : 0 si tous les contrôles passent, 1 sinon.
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, existsSync, readFileSync, statSync } from "node:fs";
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
function rendre(nom, niveau, ...options) {
  const json = join(dossier, `${nom}.json`);
  writeFileSync(json, JSON.stringify({ ...EXERCICE, niveau }));
  const rendu = spawnSync(python, ["-m", "generateur.moteur.rendu", json, "--sortie", join(dossier, `${nom}.html`), ...options],
    { encoding: "utf-8" });
  if (rendu.status !== 0) { console.error(rendu.stderr); process.exit(1); }
  return pathToFileURL(join(dossier, `${nom}.html`)).href;
}
const URL_COLLEGE = rendre("college", "5e", "--sans-voix");  // la voix du navigateur
const URL_ENFANT = rendre("enfant", "6e", "--sans-voix");
const URL_VOIX_RANGEE = rendre("voix", "5e");                // la voix de Piper, si elle est installée
const AVEC_PIPER = readFileSync(join(dossier, "voix.html"), "utf-8").includes('id="voix-rangee"');

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
async function jusqua(expression, ms = 5000) {
  for (let t = 0; t < ms; t += 50) { if (await js(expression).catch(() => false)) return true; await attendre(50); }
  throw new Error(`délai dépassé : ${expression}`);
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
  ArrowRight: ["ArrowRight", "ArrowRight", 39], Tab: ["Tab", "Tab", 9],
};
async function appuyer(nom) {
  const [key, code, windowsVirtualKeyCode, modifiers = 0] = TOUCHES[nom];
  const text = key === "Enter" ? "\r" : key.length === 1 ? key : undefined;
  await cdp("Input.dispatchKeyEvent", { type: text ? "keyDown" : "rawKeyDown", key, code, windowsVirtualKeyCode, modifiers, text });
  await cdp("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode, modifiers });
  await attendre(60);
}

// la fausse synthèse vocale : une voix installée (hors ligne) et une voix en ligne, ou rien du tout ;
// avec audio « faux », un faux lecteur de sons qui note ce qu'on lui fait jouer (window.__fin : morceau terminé)
let script = null;
async function ouvrir(url, { voix = VOIX, audio = "vrai", calme = true } = {}) {
  await cdp("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: calme ? "reduce" : "no-preference" }] });
  if (script) await cdp("Page.removeScriptToEvaluateOnNewDocument", { identifier: script });
  const r = await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
    const voix = ${JSON.stringify(voix)};
    window.__lu = []; window.__annule = 0; window.__joue = []; window.__pauses = 0; window.__auto = true;
    if (${JSON.stringify(audio)} === "faux") window.Audio = function () {
      const fin = [];
      const son = { src: "", addEventListener(type, f) { if (type === "ended") fin.push(f); },
        play() {
          window.__joue.push(son.src);
          window.__fin = () => { if (!son.arrete) fin.forEach((f) => f()); };
          if (window.__auto) setTimeout(window.__fin, 1);
          return Promise.resolve();
        },
        pause() { son.arrete = true; window.__pauses++; } };
      return son;
    };
    if (voix === null) { Object.defineProperty(window, "speechSynthesis", { value: undefined }); return; }
    window.SpeechSynthesisUtterance = function (texte) { this.text = texte; };
    Object.defineProperty(window, "speechSynthesis", { value: {
      getVoices: () => voix, addEventListener() {}, removeEventListener() {},
      speak: (u) => window.__lu.push({ texte: u.text, voix: u.voice.name, enLigne: !u.voice.localService }),
      cancel: () => { window.__annule++; },
    } });
  })()` });
  script = r.result.identifier;
  await cdp("Page.navigate", { url });
  for (let i = 0; i < 50 && !(await js(`document.readyState === "complete"`).catch(() => false)); i++) await attendre(100);
  await attendre(100);
}
const VOIX = [{ name: "Google français", lang: "fr-FR", localService: false }, { name: "Thomas", lang: "fr-FR", localService: true },
  { name: "Daniel", lang: "en-GB", localService: true }];

// l'état de la page
const visible = () => js(`[...document.querySelectorAll(".question")].findIndex((q) => !q.hidden)`);
const rangBon = () => js(`(() => { const q = [...document.querySelectorAll(".question")].find((x) => !x.hidden);
  return [...q.querySelectorAll(".reponse")].findIndex((b) => b.dataset.index === q.dataset.correct); })()`);
const nbProps = () => js(`[...document.querySelectorAll(".question")].find((x) => !x.hidden).querySelectorAll(".reponse").length`);
const choisie = () => js(`(() => { const q = [...document.querySelectorAll(".question")].find((x) => !x.hidden);
  return [...q.querySelectorAll(".reponse")].findIndex((b) => b.getAttribute("aria-pressed") === "true"); })()`);
const texte = (sel) => js(`document.querySelector(${JSON.stringify(sel)}).textContent.trim()`);
const verifiee = () => js(`!document.querySelector("#verdict").hidden`);
// répondre juste (ou faux) à la question affichée, vérifier, passer
async function repondre(juste, { passer = true } = {}) {
  const bon = await rangBon(), n = await nbProps();
  await appuyer("abcd"[juste ? bon : (bon + 1) % n]);
  await appuyer("Enter");
  if (passer) await appuyer("Enter");
}

await cdp("Runtime.enable"); await cdp("Log.enable"); await cdp("Page.enable");
try {
  // ---------- 1. le collège (5e), au clavier, animations coupées ----------
  await ouvrir(URL_COLLEGE);
  verifier("5e : style « collège », une seule question à l'écran, aide cachée, « Vérifier » inactif tant qu'on n'a pas choisi",
    await js(`document.body.dataset.style === "college" && document.querySelectorAll(".question:not([hidden])").length === 1`) &&
    await visible() === 0 && await js(`document.querySelector("#touches").hidden && document.querySelector("#btn-principal").disabled`) &&
    await js(`document.querySelectorAll("#progression .etape").length === 4`));
  verifier("5e : la police Atkinson Hyperlegible est rangée dans la page (aucune ressource extérieure)",
    await js(`document.fonts.check('16px "Atkinson Hyperlegible"') && [...document.styleSheets[0].cssRules].some((r) => r.cssText.includes("data:font/woff2"))`));
  await appuyer("?");
  verifier("« ? » : la carte de touches s'affiche", await js(`!document.querySelector("#touches").hidden &&
    document.querySelector("#btn-touches").getAttribute("aria-expanded") === "true"`));
  await appuyer("Escape");
  verifier("Échap : la carte de touches se ferme", await js(`document.querySelector("#touches").hidden`));

  await appuyer("Enter");
  verifier("Entrée sans réponse choisie : rien n'est vérifié, la page le dit",
    !(await verifiee()) && (await texte("#annonce")).startsWith("Choisis d'abord une réponse"));

  await appuyer("l");
  let lu = await js(`window.__lu`);
  const lettres = await js(`[...document.querySelectorAll(".question")[0].querySelectorAll(".reponse")].map((b, i) => "ABCD"[i] + " : " + b.querySelector(".texte").textContent.replace(/(\\d)\\/(\\d)/g, "$1 sur $2"))`);
  verifier("L : la question 1 est lue (énoncé, puis les propositions dans l'ordre affiché)", lu.length === 1 &&
    lu[0].texte.startsWith("Question 1 sur 4. Quelle fraction est égale à 3 sur 4 ?") && lettres.every((l) => lu[0].texte.includes(l)), lu[0]?.texte);
  verifier("L : la voix française installée, jamais la voix en ligne", lu[0]?.voix === "Thomas" && !lu[0]?.enLigne);
  const annulees = await js(`window.__annule`);
  await appuyer("l");
  verifier("L une deuxième fois : la lecture s'arrête", (await js(`window.__annule`)) > annulees && (await js(`window.__lu.length`)) === 1);

  const bon1 = await rangBon();
  await appuyer("abcd"[bon1]);
  verifier("lettre : la réponse est choisie, et annoncée", await choisie() === bon1 &&
    (await texte("#annonce")) === `Réponse ${"ABCD"[bon1]} choisie. Entrée pour vérifier.`);
  await appuyer("Enter");
  verifier("Entrée : la réponse est vérifiée, « ✓ Juste ! », l'explication, +100 points", await verifiee() &&
    (await texte("#verdict strong")) === "✓ Juste !" && (await texte("#verdict p")).startsWith("On multiplie") &&
    (await texte("#points")) === "100 pts" && await js(`document.querySelector(".question:not([hidden]) .reponse.juste .marque").textContent === "✓ bonne réponse"`));
  await appuyer("a");
  verifier("après la vérification, la réponse ne change plus", await choisie() === bon1);
  await appuyer("Enter");
  verifier("Entrée encore : la question 2, le curseur sur son énoncé", await visible() === 1 && !(await verifiee()) &&
    await js(`document.activeElement === document.querySelector("#enonce-2")`));

  await appuyer("d");
  verifier("D sur une question à 3 propositions : rien n'est choisi", await choisie() === -1);
  await appuyer("Tab"); // « Écouter »
  await appuyer("Tab"); // la première proposition
  const surBouton = await js(`document.activeElement.classList.contains("reponse") ? [...document.activeElement.closest(".reponses").querySelectorAll(".reponse")].indexOf(document.activeElement) : -1`);
  await appuyer("Enter");
  verifier("Tab Tab, puis Entrée sur une proposition : elle est choisie, rien n'est vérifié ; le curseur revient sur l'énoncé",
    surBouton === 0 && await choisie() === 0 && !(await verifiee()) && await js(`document.activeElement === document.querySelector("#enonce-2")`), String(surBouton));
  await appuyer("&");
  verifier("le « 1 » d'un clavier AZERTY (touche & sans Maj) choisit A", await choisie() === 0);
  const bon2 = await rangBon();
  await appuyer(String(bon2 + 1));
  verifier("chiffre : la réponse est choisie", await choisie() === bon2);
  await appuyer("Enter");
  verifier("deux justes de suite : la série « ×2 » s'allume, 220 points (100 + 120)", (await texte("#serie")) === "×2" &&
    await js(`document.querySelector("#serie").classList.contains("active")`) && (await texte("#points")) === "220 pts");
  await appuyer("ArrowRight");
  verifier("→ après la vérification : la question suivante", await visible() === 2);

  await repondre(false, { passer: false });
  verifier("une réponse fausse : « ✗ À revoir », la bonne réponse montrée, la série retombe à ×0", (await texte("#verdict strong")) === "✗ À revoir" &&
    await js(`document.querySelectorAll(".question:not([hidden]) .reponse.faux").length === 1 && document.querySelectorAll(".question:not([hidden]) .reponse.juste").length === 1`) &&
    (await texte("#serie")) === "×0");
  await appuyer("l");
  lu = await js(`window.__lu`);
  const r3 = await js(`(() => { const q = document.querySelector("#question-3"), b = [...q.querySelectorAll(".reponse")];
    return ["ABCD"[b.indexOf(q.querySelector(".faux"))], "ABCD"[b.indexOf(q.querySelector(".juste"))]]; })()`);
  verifier("L après la vérification : la réponse, la bonne réponse et l'explication sont lues aussi",
    lu.at(-1)?.texte.includes(`Ta réponse : ${r3[0]}. La bonne réponse est ${r3[1]}.`) && lu.at(-1)?.texte.includes("Explication : 18 divisé par 2 = 9."), lu.at(-1)?.texte);
  verifier("la progression suit les réponses (juste, juste, faux)", await js(`[...document.querySelectorAll("#progression .etape")].slice(0, 3).map((e) => e.className.includes("juste") ? "j" : e.className.includes("faux") ? "f" : "?").join("") === "jjf"`));
  await appuyer("Enter");
  await repondre(true, { passer: false });
  verifier("dernière question : « Voir mon score »", (await texte("#btn-principal")).startsWith("Voir mon score"));
  await appuyer("Enter");
  verifier("fin : « Score : 3 / 4 », le titre, les points, la meilleure série", await js(`!document.querySelector("#ecran-fin").hidden && document.querySelector("#ecran-question").hidden`) &&
    (await texte("#score")).startsWith("Score : 3 / 4") && (await texte("#fin-titre")) === "Bon score" && (await texte("#fin-points")) === "320" && (await texte("#fin-serie")) === "×2");
  await capture("1-college-fin");
  await appuyer("r");
  verifier("R : on rejoue (question 1, aucune réponse, 0 point)", await visible() === 0 && await choisie() === -1 && (await texte("#points")) === "0 pt" &&
    await js(`document.querySelector("#ecran-fin").hidden`));
  for (let i = 0; i < 4; i++) await repondre(true);
  verifier("un deuxième tour au clavier seul : « Score : 4 / 4 », « Défi réussi »", (await texte("#score")).startsWith("Score : 4 / 4") && (await texte("#fin-titre")) === "Défi réussi");

  // ---------- 2. la 6e : le style « enfant », animations coupées ----------
  await ouvrir(URL_ENFANT);
  verifier("6e : style « enfant », la police Andika rangée dans la page, le compagnon, une étoile par question",
    await js(`document.body.dataset.style === "enfant" && document.fonts.check('16px "Andika"') && !!document.querySelector("#compagnon")`) &&
    await js(`document.querySelectorAll("#progression .etape svg").length === 4 && !document.querySelector("#points")`));
  await repondre(true, { passer: false });
  verifier("6e, juste : le compagnon dit bravo, l'étoile est gagnée", ["Bravo !", "Super !", "Bien joué !", "Génial !"].includes(await texte("#bulle")) &&
    await js(`document.querySelectorAll("#progression .etape")[0].classList.contains("juste")`));
  await appuyer("Enter");
  await repondre(false, { passer: false });
  verifier("6e, faux : « Presque ! Lis l'explication. »", (await texte("#bulle")) === "Presque ! Lis l'explication.");
  await appuyer("Enter");
  await repondre(true); await repondre(true);
  verifier("6e, fin : 3 sur 4, 2 étoiles, « Très bien ! »", (await texte("#score")) === "Score : 3 / 4. 2 étoiles." && (await texte("#fin-titre")) === "Très bien !" &&
    await js(`document.querySelectorAll("#grandes-etoiles svg.gagnee").length === 2`));
  verifier("animations coupées : aucune particule, aucun rideau", await js(`document.querySelectorAll(".particule").length === 0 && document.querySelector("#rideau").hidden`));

  // ---------- 3. avec les animations : la vague (6e), le balayage (collège) ----------
  await ouvrir(URL_ENFANT, { calme: false });
  await repondre(true, { passer: false });
  await attendre(250);
  verifier("6e animée : une étoile s'envole vers la progression, des étincelles", await js(`document.querySelectorAll(".particule").length > 0`));
  await capture("2-enfant-juste");
  await appuyer("Enter");
  await attendre(260);
  verifier("6e animée : la vague couvre la carte entre deux questions", await js(`!document.querySelector("#rideau").hidden && document.querySelector("#rideau").classList.contains("vague")`));
  await capture("3-enfant-vague");
  await appuyer("a");
  verifier("pendant la vague, les touches attendent (rien n'est choisi)", await choisie() === -1);
  await jusqua(`document.querySelector("#rideau").hidden`, 3000);
  verifier("6e animée : après la vague, la question 2, entière", await visible() === 1 && await js(`[...document.querySelectorAll("#question-2 .reponse")].every((b) => getComputedStyle(b.parentElement).opacity === "1")`));
  for (let i = 0; i < 3; i++) {
    await repondre(true, { passer: false });
    await attendre(900);
    await appuyer("Enter");
    if (i < 2) await jusqua(`document.querySelector("#rideau").hidden`, 3000);
  }
  await jusqua(`!document.querySelector("#ecran-fin").hidden`, 3000);
  await attendre(900);
  verifier("6e animée : fin à 3 étoiles, confettis", (await texte("#score")) === "Score : 4 / 4. 3 étoiles." && await js(`document.querySelectorAll(".particule").length > 20`));
  await capture("4-enfant-fin");

  await ouvrir(URL_COLLEGE, { calme: false });
  await repondre(true, { passer: false });
  await attendre(120);
  verifier("collège animé : « +100 » s'envole au-dessus du compteur", await js(`!!document.querySelector(".envol")`));
  await attendre(900);
  await appuyer("Enter");
  await attendre(330);
  verifier("collège animé : le balayage annonce la question 2 (« 2/4 »)", await js(`!document.querySelector("#rideau").hidden && document.querySelector("#rideau").classList.contains("balayage")`) &&
    (await texte("#annonce-num")) === "2" && (await texte("#annonce-total")) === "/4");
  await capture("5-college-balayage");
  await jusqua(`document.querySelector("#rideau").hidden`, 3000);
  verifier("collège animé : après le balayage, la question 2", await visible() === 1);

  // ---------- 4. les voix ----------
  await ouvrir(URL_COLLEGE, { voix: VOIX.filter((v) => v.name !== "Thomas") });
  await appuyer("l");
  verifier("sans voix française installée : rien n'est lu, un message l'explique", (await js(`window.__lu.length`)) === 0 &&
    (await texte("#annonce")).startsWith("Lecture impossible : aucune voix française"));
  await ouvrir(URL_COLLEGE, { voix: null });
  await appuyer("l");
  verifier("sans synthèse vocale : boutons « Écouter » cachés, L sans erreur",
    await js(`[...document.querySelectorAll(".ecouter")].every((b) => b.hidden)`) && (await texte("#annonce")) === "");

  if (!AVEC_PIPER) {
    console.log("⚠ voix de Piper absente (config.yaml, section lecture) : contrôles de la voix rangée sautés");
  } else {
    const attendus = (corrigee) => js(`(() => {
      const v = JSON.parse(document.getElementById("voix-rangee").textContent), f = v.fixes;
      const q = [...document.querySelectorAll(".question")].find((x) => !x.hidden), n = [...document.querySelectorAll(".question")].indexOf(q), d = v.questions[n];
      const b = [...q.querySelectorAll(".reponse")], cles = [d.titre, d.enonce];
      b.forEach((x, i) => cles.push(f["lettre_" + "ABCD"[i]], d.propositions[Number(x.dataset.index)]));
      if (${corrigee}) {
        const c = b.findIndex((x) => x.getAttribute("aria-pressed") === "true"), o = b.findIndex((x) => x.dataset.index === q.dataset.correct);
        if (c === o) cles.push(f.juste); else cles.push(f["choisie_" + "ABCD"[c]], f["bonne_" + "ABCD"[o]]);
        cles.push(f.explication, d.explication);
      }
      return cles.map((k) => "data:audio/mpeg;base64," + v.clips[k]);
    })()`);
    const memes = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
    await ouvrir(URL_VOIX_RANGEE, { audio: "faux" });
    await appuyer("l");
    await attendre(200);
    let joue = await js(`window.__joue`);
    verifier("voix rangée, L : les 10 morceaux de la question 1 (énoncé, lettres et propositions dans l'ordre affiché)",
      joue.length === 10 && memes(joue, await attendus(false)), `${joue.length} morceau(x)`);
    verifier("voix rangée : la voix du navigateur n'est pas utilisée", (await js(`window.__lu.length`)) === 0);
    await js(`window.__auto = false`);
    const pauses = await js(`window.__pauses`);
    await appuyer("l");
    await appuyer("l");
    await js(`window.__fin && window.__fin()`);
    verifier("voix rangée, L une deuxième fois : la lecture s'arrête", (await js(`window.__joue.length`)) === 11 && (await js(`window.__pauses`)) === pauses + 1);
    await js(`window.__auto = true`);
    await repondre(false, { passer: false });
    const avant = (await js(`window.__joue`)).length;
    await appuyer("l");
    await attendre(200);
    joue = (await js(`window.__joue`)).slice(avant);
    verifier("voix rangée après la vérification : « Ta réponse : … La bonne réponse est … », puis l'explication",
      memes(joue, await attendus(true)), `${joue.length} morceau(x)`);
    await ouvrir(URL_VOIX_RANGEE);
    const duree = await js(`new Promise((ok) => {
      const v = JSON.parse(document.getElementById("voix-rangee").textContent);
      const son = new Audio("data:audio/mpeg;base64," + v.clips[v.questions[0].enonce]);
      son.onloadedmetadata = () => ok(son.duration); son.onerror = () => ok(-1);
    })`);
    const poids = Math.round(statSync(join(dossier, "voix.html")).size / 1024);
    verifier(`un vrai morceau MP3 se décode (${duree.toFixed(1)} s ; page de 4 questions : ${poids} Ko)`, duree > 0.5);
  }

  // ---------- 5. téléphone : pas de défilement horizontal ----------
  await cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  for (const [nom, url] of [["5e", URL_COLLEGE], ["6e", URL_ENFANT]]) {
    await ouvrir(url);
    await appuyer("?");
    await repondre(false, { passer: false });
    verifier(`téléphone, ${nom}, aide ouverte et réponse vérifiée : pas de défilement horizontal`, await js(`document.documentElement.scrollWidth <= window.innerWidth`));
  }
  await capture("6-telephone");
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
