/* Contrôle du générateur de lettre de motivation.
   Deux livrables partent chez un recruteur : un PDF et un .docx. On vérifie
   donc que le PDF fait bien UNE page A4 (une lettre qui déborde perd sa
   demande d'entretien, toujours en fin de texte) et que Word sait relire le
   .docx — via textutil, le moteur OOXML d'Apple, comme tools/test-docx.mjs.
   Usage : node tools/test-lettre.mjs      (nécessite Google Chrome + macOS) */
import { open } from './lib-chrome.mjs';
import { writeFile, mkdir, rm, readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { join, resolve } from 'node:path';
import { runInNewContext } from 'node:vm';

const OUT = resolve(import.meta.dirname, '..', '.test-out');
await mkdir(OUT, { recursive: true });
const PT = 72 / 25.4;
const near = (a, b, tol = 3) => Math.abs(a - b) <= tol;
let fails = [];
const check = (nom, cond, detail = '') => {
  console.log((cond ? '  ✓ ' : '  ✗ ') + nom + (cond ? '' : ' — ' + detail));
  if (!cond) fails.push(nom);
};

const fileLinksSource = await readFile(new URL('../assets/file-links.js', import.meta.url), 'utf8');
let fileClick;
const fileLocation = { protocol: 'file:', href: '' };
runInNewContext(fileLinksSource, {
  location: fileLocation,
  document: { addEventListener: (_name, callback) => { fileClick = callback; } }
});
let prevented = false;
fileClick({
  defaultPrevented: false, button: 0, metaKey: false, ctrlKey: false,
  shiftKey: false, altKey: false,
  target: { closest: () => ({
    target: '', hasAttribute: () => false,
    getAttribute: () => 'lettre-de-motivation/?cv=cv_81z5coq5ttb'
  }) },
  preventDefault: () => { prevented = true; }
});
check('navigation file:// vers la lettre conserve ?cv= après index.html',
  prevented && fileLocation.href === 'lettre-de-motivation/index.html?cv=cv_81z5coq5ttb',
  fileLocation.href);

const mediaBoxes = pdf => [...pdf.toString('latin1')
  .matchAll(/\/MediaBox\s*\[\s*([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s*\]/g)]
  .map(m => [parseFloat(m[3]) - parseFloat(m[1]), parseFloat(m[4]) - parseFloat(m[2])]);

const page = await open('/lettre-de-motivation/');
if (!await page.waitFor("typeof docxBlob === 'function' && typeof S !== 'undefined'")) {
  console.error('La page lettre-de-motivation ne s’est pas initialisée'); await page.close(); process.exit(1);
}
console.log('Lettre de motivation');

const reprise = await page.eval(`(function(){
  const id='cv-integration-test';
  const donnees={
    id, name:'CV de test', template:'prestige',
    design:{accent:'#a16207',font:'Poppins'},
    data:{
      fullName:'Awa Test',title:'Comptable',location:'Abidjan, Côte d’Ivoire',
      phone:'+225 01020304',email:'awa@example.ci',
      summary:'Comptable avec expérience en clôtures mensuelles.',
      experiences:[{role:'Comptable',company:'Entreprise Réelle',desc:'• Réduit le délai de clôture de 5 à 3 jours'}]
    }
  };
  localStorage.setItem('cvstudio.docs', JSON.stringify({
    [id]:donnees, autre:{...donnees,id:'autre',name:'CV plus récent',data:{...donnees.data,fullName:'Autre personne'}}
  }));
  localStorage.setItem('cvstudio.current', id);
  history.replaceState({}, '', '?cv=' + id);
  handleLetterParams();
  const imported=S.fullName==='Awa Test';
  const result = {imported, name:S.fullName, title:S.title, poste:S.poste, email:S.email,
    address:S.address, color:S.ac, font:S.font, template:S.tpl, company:S.company,
    accroche:S.accroche, vous:S.vous, moi:S.moi, nous:S.nous};
  const missing=fromCV('cv-introuvable',true);
  result.missingIdRejected=missing===false && S.fullName==='Awa Test';
  localStorage.removeItem('cvstudio.lettre');
  S={...DEF}; paint(); render();
  return result;
})()`);
check('reprise des données du CV explicitement sélectionné',
  reprise.imported && reprise.name==='Awa Test' && reprise.title==='Comptable' &&
  reprise.poste==='Comptable' && reprise.email==='awa@example.ci' &&
  reprise.address==='Abidjan, Côte d’Ivoire' && reprise.color==='#a16207' &&
  reprise.font==='Poppins' && reprise.template==='moderne' &&
  reprise.company==='' && reprise.vous==='' &&
  reprise.moi.includes('Entreprise Réelle') &&
  reprise.moi.includes('5 à 3 jours') && !reprise.moi.includes('Orange') &&
  reprise.missingIdRejected,
  JSON.stringify(reprise));

const scripts = await page.eval(`[...document.scripts].map(s=>s.src+' '+s.textContent).join('\\n')`);
check('la lettre charge le suivi d’activité et le contrôle de téléchargement',
  scripts.includes('/assets/analytics.js') && scripts.includes('/assets/download-gate.js'));
check('la lettre ne contient aucun endpoint IA', !/\/ai\/|CVAI|MISTRAL_API_KEY/i.test(scripts));
const gate = await page.eval(`(function(){
  sessionStorage.removeItem('cvstudio.download-contact');
  let downloaded=false;
  CVDownloadGate.request('letter_docx',()=>{downloaded=true;});
  const blocked=!downloaded && !document.querySelector('#downloadGate').hidden;
  document.querySelector('#downloadGate .download-gate-cancel').click();
  const canceled=!downloaded && document.querySelector('#downloadGate').hidden;
  return {blocked,canceled};
})()`);
check('le téléchargement de la lettre est lui aussi protégé par la demande de contact',
  gate.blocked && gate.canceled, JSON.stringify(gate));

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

/* Les données du CV ne sont pas incluses dans les requêtes analytics/contact. */
const analyticsSource = await readFile(new URL('../assets/analytics.js', import.meta.url), 'utf8');
const gateSource = await readFile(new URL('../assets/download-gate.js', import.meta.url), 'utf8');
check('le suivi transmet les événements, jamais le contenu du CV',
  /action,\s*target:\s*target\s*\|\|\s*'',\s*page,\s*session_id:\s*sessionId/.test(analyticsSource) &&
  !/S\.|state\.data|cvstudio\.docs/.test(analyticsSource + gateSource));

await page.close();
console.log(fails.length ? `\n${fails.length} échec(s)` : `\nTous les tests passent\n\nFichier de contrôle : .test-out/lettre-test.docx`);
process.exit(fails.length ? 1 : 0);
