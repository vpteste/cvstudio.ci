/* Contrôle du générateur de lettre de motivation.
   Deux livrables partent chez un recruteur : un PDF et un .docx. On vérifie
   donc que le PDF fait bien UNE page A4 (une lettre qui déborde perd sa
   demande d'entretien, toujours en fin de texte) et que Word sait relire le
   .docx — via textutil, le moteur OOXML d'Apple, comme tools/test-docx.mjs.
   Usage : node tools/test-lettre.mjs      (nécessite Google Chrome + macOS) */
import { open } from './lib-chrome.mjs';
import { writeFile, mkdir, rm } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { join, resolve } from 'node:path';

const OUT = resolve(import.meta.dirname, '..', '.test-out');
await mkdir(OUT, { recursive: true });
const PT = 72 / 25.4;
const near = (a, b, tol = 3) => Math.abs(a - b) <= tol;
let fails = [];
const check = (nom, cond, detail = '') => {
  console.log((cond ? '  ✓ ' : '  ✗ ') + nom + (cond ? '' : ' — ' + detail));
  if (!cond) fails.push(nom);
};
const mediaBoxes = pdf => [...pdf.toString('latin1')
  .matchAll(/\/MediaBox\s*\[\s*([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s*\]/g)]
  .map(m => [parseFloat(m[3]) - parseFloat(m[1]), parseFloat(m[4]) - parseFloat(m[2])]);

const page = await open('/lettre-de-motivation/');
if (!await page.waitFor("typeof docxBlob === 'function' && typeof S !== 'undefined'")) {
  console.error('La page lettre-de-motivation ne s’est pas initialisée'); await page.close(); process.exit(1);
}
console.log('Lettre de motivation');

/* 1. Le PDF par défaut tient sur une seule page A4 */
let boxes = mediaBoxes(await page.pdf());
check('PDF : une seule page', boxes.length === 1, boxes.length + ' page(s)');
check('PDF : format A4', boxes.length >= 1 && near(boxes[0][0], 210 * PT) && near(boxes[0][1], 297 * PT),
  JSON.stringify(boxes.map(b => b.map(v => +(v / PT).toFixed(1)))));

/* 2. La jauge doit dire « tient » sur l'exemple, et alerter sur une lettre longue */
const g1 = await page.eval("document.getElementById('gtxt').textContent");
check('Jauge : l’exemple tient sur une page', /tient sur une page/.test(g1), g1);
await page.eval("S.moi = S.moi.repeat(9); render();");
const g2 = await page.eval("document.getElementById('gtxt').textContent");
boxes = mediaBoxes(await page.pdf());
check('Jauge : une lettre trop longue est signalée', /dépasse/.test(g2), g2);
check('… et elle déborde effectivement sur 2 pages', boxes.length === 2, boxes.length + ' page(s)');
await page.eval("S = load(); S.date = S.date || new Date().toISOString().slice(0,10); paint(); render();");

/* 3. Les quatre modèles rendent une lettre complète */
const tplReport = await page.eval(`(function(){
  const out = {};
  for (const t of TPL){ S.tpl = t.id;
    try { const h = letterHTML(); out[t.id] = (h.includes('lt-' + t.id) && h.length > 600) ? 'ok' : 'incomplet'; }
    catch(e){ out[t.id] = 'ERREUR ' + e.message; } }
  S.tpl = 'moderne'; return out;
})()`);
for (const id in tplReport) check('modèle « ' + id + ' » rendu', tplReport[id] === 'ok', tplReport[id]);

/* 4. Objet et formule de politesse se construisent tout seuls */
const derive = await page.eval(`(function(){
  S.objet=''; S.poste='Comptable'; S.salut=1;
  return { objet: objetTxt(), cloture: clotureTxt(), salut: salutTxt() };
})()`);
check('Objet construit depuis le poste', derive.objet === 'Candidature au poste de Comptable', derive.objet);
check('Formule de politesse reprend l’appel choisi', derive.cloture.includes('Madame,'), derive.cloture);

/* 5. Le .docx : structure du paquet, puis relecture par le moteur OOXML d'Apple */
const b64 = await page.eval(`(async function(){
  S = load(); paint(); render();
  const buf = await docxBlob().arrayBuffer();
  let s = ''; const u = new Uint8Array(buf);
  for (let i = 0; i < u.length; i++) s += String.fromCharCode(u[i]);
  return btoa(s);
})()`, true);
const docx = Buffer.from(b64, 'base64');
const file = join(OUT, 'lettre-test.docx');
await writeFile(file, docx);
check('.docx : signature ZIP', docx.slice(0, 2).toString() === 'PK', docx.slice(0, 4).toString('hex'));

const listing = execFileSync('unzip', ['-l', file]).toString();
for (const part of ['[Content_Types].xml', '_rels/.rels', 'word/_rels/document.xml.rels',
                    'word/document.xml', 'word/styles.xml', 'word/settings.xml'])
  check('.docx contient ' + part, listing.includes(part));

const xml = execFileSync('unzip', ['-p', file, 'word/document.xml']).toString();
execFileSync('xmllint', ['--noout', '-'], { input: xml });
check('.docx : document.xml bien formé', true);
check('.docx : format de page A4', /w:pgSz w:w="11906" w:h="16838"/.test(xml));
check('.docx : aucun tableau (linéaire, donc lisible par un ATS)', !xml.includes('<w:tbl>'));
check('.docx : mode de compatibilité Word 15',
  execFileSync('unzip', ['-p', file, 'word/settings.xml']).toString().includes('w:val="15"'));

const texte = execFileSync('textutil', ['-convert', 'txt', '-stdout', file]).toString();
for (const [nom, attendu] of [
  ['le nom du candidat', 'Amina Koné'],
  ['l’objet', 'Candidature au poste de'],
  ['le corps de la lettre', 'time-to-market'],
  ['la formule de politesse', 'salutations distinguées'],
]) check('Word relit ' + nom, texte.includes(attendu), texte.slice(0, 120).replace(/\n/g, ' '));

/* Échec d'enregistrement : prévenir plutôt que perdre le travail en silence */
const stockage = await page.eval(`(function(){
  const vrai = localStorage.setItem.bind(localStorage);
  localStorage.setItem = function(){ throw new DOMException('QuotaExceededError'); };
  save();
  const prevenu = document.getElementById('storeWarn').classList.contains('on');
  localStorage.setItem = vrai; save();
  return prevenu;
})()`);
check('un échec d’enregistrement est signalé à l’utilisateur', stockage === true);

/* 6. Rien ne sort du navigateur */
const net = await page.eval("(/fetch\\(|XMLHttpRequest|navigator\\.sendBeacon/.test(document.documentElement.innerHTML) ? 'appel réseau trouvé' : 'aucun')");
check('Aucun envoi réseau depuis la page', net === 'aucun', net);

await page.close();
console.log(fails.length ? `\n${fails.length} échec(s)` : `\nTous les tests passent\n\nFichier de contrôle : .test-out/lettre-test.docx`);
process.exit(fails.length ? 1 : 0);
