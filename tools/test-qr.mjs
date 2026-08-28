/* Vérifie assets/qr.js en faisant RELIRE les codes produits par un décodeur réel
   (BarcodeDetector de Chrome, adossé au framework Vision de macOS) : le QR d'une
   carte de visite part à l'impression, une erreur ne se verrait pas autrement.
   Usage : node tools/test-qr.mjs        (nécessite Google Chrome) */
import { open } from './lib-chrome.mjs';

const page = await open('/tools/test-qr.html');
const fin = async code => { await page.close(); process.exit(code); };

/* La page peut n'avoir pas fini d'exécuter son script au moment où l'on
   s'attache : on attend que la promesse existe avant de l'attendre. */
if (!await page.waitFor("typeof window.__done === 'object'")) {
  console.error('La page de test n’a jamais exposé window.__done'); await fin(1);
}
const val = await page.eval('window.__done', true);
if (!val) { console.error('Aucun résultat renvoyé par la page'); await fin(1); }
if (val.skip) { console.log('SKIP — BarcodeDetector indisponible sur cette machine'); await fin(0); }

console.log(`QR — relecture par un décodeur réel : ${val.ok}/${val.total}`);
console.log(val.txt.split('\n').filter(l => l.startsWith('capacité')).join('\n'));
for (const k of val.ko) console.log(`  ✗ [${k.level} · ${k.len} car.] attendu « ${k.attendu} » — obtenu « ${k.obtenu} »`);
if (val.ko.length === 0) console.log('Tous les tests passent');
await fin(val.ko.length ? 1 : 0);
