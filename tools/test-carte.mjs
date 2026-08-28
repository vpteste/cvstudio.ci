/* Contrôle du générateur de carte de visite.
   Le livrable de cette page est un PDF qui part chez un imprimeur : on vérifie
   donc la géométrie RÉELLE des pages produites (85×55 mm, 91×61 avec fonds
   perdus, planche A4), pas seulement que la page s'affiche.
   Usage : node tools/test-carte.mjs        (nécessite Google Chrome) */
import { open } from './lib-chrome.mjs';

const PT = 72 / 25.4;                       // 1 mm en points PostScript
const near = (a, b, tol = 1.5) => Math.abs(a - b) <= tol;
let fails = [];
const check = (nom, cond, detail = '') => {
  console.log((cond ? '  ✓ ' : '  ✗ ') + nom + (cond ? '' : ' — ' + detail));
  if (!cond) fails.push(nom);
};

/* Taille de chaque page : Chrome écrit un /MediaBox par page. */
function mediaBoxes(pdf) {
  const s = pdf.toString('latin1');
  return [...s.matchAll(/\/MediaBox\s*\[\s*([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s*\]/g)]
    .map(m => [parseFloat(m[3]) - parseFloat(m[1]), parseFloat(m[4]) - parseFloat(m[2])]);
}

const page = await open('/carte-de-visite/');
if (!await page.waitFor("typeof window.exportCards === 'function' && typeof S !== 'undefined'")) {
  console.error('La page carte-de-visite ne s’est pas initialisée'); await page.close(); process.exit(1);
}
await page.eval('window.print = function(){}');   // l'export doit peupler le DOM sans ouvrir de dialogue

console.log('Carte de visite — géométrie des exports');

/* 1. PDF recto + verso au format carte */
await page.eval('S.bleed=false; exportCards();');
let boxes = mediaBoxes(await page.pdf());
check('PDF carte : 2 pages (recto + verso)', boxes.length === 2, boxes.length + ' page(s)');
check('PDF carte : format 85 × 55 mm',
  boxes.length === 2 && boxes.every(b => near(b[0], 85 * PT) && near(b[1], 55 * PT)),
  JSON.stringify(boxes.map(b => b.map(v => +(v / PT).toFixed(1)))));

/* 2. Fonds perdus : le format augmente de 3 mm sur chaque bord */
await page.eval("document.getElementById('printArea').innerHTML=''; S.bleed=true; exportCards();");
boxes = mediaBoxes(await page.pdf());
check('Fonds perdus : format 91 × 61 mm',
  boxes.length === 2 && boxes.every(b => near(b[0], 91 * PT) && near(b[1], 61 * PT)),
  JSON.stringify(boxes.map(b => b.map(v => +(v / PT).toFixed(1)))));

/* 3. Planche A4 de 10 cartes */
await page.eval("document.getElementById('printArea').innerHTML=''; S.bleed=false; exportSheet();");
const sheetCards = await page.eval("document.querySelectorAll('#printArea .cell .card').length");
boxes = mediaBoxes(await page.pdf());
check('Planche : 10 cartes', sheetCards === 10, sheetCards + ' carte(s)');
check('Planche : une seule page A4',
  boxes.length === 1 && near(boxes[0][0], 210 * PT, 3) && near(boxes[0][1], 297 * PT, 3),
  JSON.stringify(boxes.map(b => b.map(v => +(v / PT).toFixed(1)))));

/* 4. Chaque modèle rend ses deux faces, sans exception ni face vide */
const tplReport = await page.eval(`(function(){
  const out = {};
  for (const t of TPL) {
    S.tpl = t.id;
    try {
      const r = cardHTML('recto'), v = cardHTML('verso');
      out[t.id] = (r.length > 200 && v.length > 200) ? 'ok' : 'trop court';
    } catch (e) { out[t.id] = 'ERREUR ' + e.message; }
  }
  return out;
})()`);
for (const id in tplReport) check('modèle « ' + id +' » : recto et verso rendus', tplReport[id] === 'ok', tplReport[id]);

/* 5. Le QR encode bien une fiche MECARD exploitable, et refuse le trop long */
const qr = await page.eval(`(function(){
  S.qrMode='mecard';
  const p = qrPayload();
  let enc = 'ok'; try { QR.matrix(p, 'M'); } catch(e){ enc = e.message; }
  S.qrMode='url'; S.qrUrl='x'.repeat(400);
  let refus = 'pas de refus'; try { QR.matrix(qrPayload(), 'M'); } catch(e){ refus = 'refus'; }
  S.qrMode='mecard';
  return { p, enc, refus };
})()`);
check('QR : charge MECARD bien formée',
  /^MECARD:/.test(qr.p) && /TEL:/.test(qr.p) && /EMAIL:/.test(qr.p) && qr.p.endsWith(';'), qr.p.slice(0, 60));
check('QR : la fiche contact tient dans un code', qr.enc === 'ok', qr.enc);
check('QR : une URL trop longue est refusée, pas encodée de travers', qr.refus === 'refus', qr.refus);

/* 6. Onglets du panneau : le formulaire est coupé en « Contenu » / « Style »
      pour tenir dans un écran. Chacun doit masquer l'autre. */
const onglets = await page.eval(`(function(){
  pickPane('style');
  const a = { styleActif: document.getElementById('tab-style').classList.contains('on'),
              contenuMasque: document.getElementById('pane-contenu').hidden,
              modeles: document.querySelectorAll('#tplGrid .tplb').length };
  pickPane('contenu');
  a.retour = !document.getElementById('pane-contenu').hidden
             && document.getElementById('pane-style').hidden;
  return a;
})()`);
check('onglet Style : affiche les modèles et masque le contenu',
  onglets.styleActif && onglets.contenuMasque && onglets.modeles === 4, JSON.stringify(onglets));
check('retour sur Contenu : les deux panneaux se croisent bien', onglets.retour === true);

/* 7. Les écouteurs ne doivent pas s'empiler. paint() est rappelé à chaque clic
      sur un modèle ou une couleur ; s'il reposait des écouteurs, une seule
      frappe finirait par déclencher autant de rendus qu'il y a eu de clics. */
const rendus = await page.eval(`(function(){
  paint(); paint(); paint();                     // trois changements de style
  const el = document.getElementById('fullName'), avant = el.value;
  let n = 0; const vrai = window.render;
  window.render = function(){ n++; };
  el.value = 'Zzz'; el.dispatchEvent(new Event('input'));
  window.render = vrai;
  el.value = avant; S.fullName = avant;
  return n;
})()`);
check('une frappe ne déclenche qu’un seul rendu (écouteurs non empilés)',
  rendus === 1, rendus + ' rendus pour une frappe');

/* 8. Échec d'enregistrement : l'utilisateur doit être prévenu, pas perdre son
      travail en silence (navigation privée, stockage plein). */
const stockage = await page.eval(`(function(){
  const vrai = localStorage.setItem.bind(localStorage);
  localStorage.setItem = function(){ throw new DOMException('QuotaExceededError'); };
  save();
  const prevenu = document.getElementById('storeWarn').classList.contains('on');
  localStorage.setItem = vrai; save();
  return prevenu;
})()`);
check('un échec d’enregistrement est signalé à l’utilisateur', stockage === true);

/* 9. Sélection au clic : cliquer une zone de la carte doit ouvrir son champ.
      Les quatre modèles doivent rester cliquables — ils écrivent leur propre
      markup, un modèle peut donc perdre la sélection sans rien casser d'autre. */
const couverture = await page.eval(`(function(){
  const manquants = [];
  for (const t of TPL) {
    S.tpl = t.id; render();
    const vus = new Set([...document.querySelectorAll('.faces [data-edit]')].map(e => e.getAttribute('data-edit')));
    for (const champ of ['fullName','title','phone','email'])
      if (!vus.has(champ)) manquants.push(t.id + ' : ' + champ);
  }
  S.tpl = 'vagues'; render();
  return manquants;
})()`);
check('les 4 modèles rendent des zones cliquables', couverture.length === 0, couverture.join(' | '));

const clic = await page.eval(`(function(){
  const out = [];
  for (const champ of ['fullName','title','phone','email','company']) {
    const zone = document.querySelector('.faces [data-edit="' + champ + '"]');
    if (!zone) { out.push(champ + ' : zone absente'); continue; }
    pickPane('style');                       // on part du mauvais onglet exprès
    zone.click();
    if (document.activeElement !== document.getElementById(champ))
      out.push(champ + ' : focus sur ' + (document.activeElement && document.activeElement.id));
    if (document.getElementById('pane-contenu').hidden) out.push(champ + ' : onglet Contenu non ouvert');
    if (!document.querySelector('.faces .is-selected')) out.push(champ + ' : zone non surlignée');
  }
  // la sélection survit au re-rendu
  document.querySelector('.faces [data-edit="fullName"]').click();
  S.title = 'X'; render();
  if (!document.querySelector('.faces .is-selected')) out.push('sélection perdue au re-rendu');
  return out;
})()`);
check('un clic ouvre l’onglet Contenu et focalise le bon champ',
  clic.length === 0, clic.slice(0, 4).join(' | '));

/* 10. Aucune donnée ne sort du navigateur : la page ne doit contenir aucun appel réseau */
const net = await page.eval(`(function(){
  const src = document.documentElement.innerHTML;
  return /fetch\\(|XMLHttpRequest|navigator\\.sendBeacon/.test(src) ? 'appel réseau trouvé' : 'aucun';
})()`);
check('Aucun envoi réseau depuis la page', net === 'aucun', net);

await page.close();
console.log(fails.length ? `\n${fails.length} échec(s)` : '\nTous les tests passent');
process.exit(fails.length ? 1 : 0);
