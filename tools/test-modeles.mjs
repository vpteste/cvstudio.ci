/* Rendu des onze modèles de CV et sélection au clic, dans la vraie page.

   Trois bugs réels sont épinglés ici :
   1. cvPageHTML() aligne temporairement `state` sur le design demandé pour
      rendre une vignette. Sans `finally`, la moindre exception d'un modèle
      laissait `state` figé sur {design} : plus de state.data, l'autosave
      écrasait le CV et chaque frappe suivante relançait une erreur.
   2. Un modèle inconnu (CV importé d'une version future) levait au lieu de
      retomber sur Moderne.
   3. Un tableau contenant des trous ([null]) faisait lever les onze modèles.

   La seconde moitié couvre la sélection au clic : cliquer un bloc de l'aperçu
   doit ouvrir sa section, faire défiler jusqu'au champ et lui donner le focus.
   Les chemins `data-edit` vivent dans les blocs de rendu partagés — un modèle
   qui rendrait ses compétences autrement (barres, lignes, pastilles, puces)
   perdrait la sélection sans que rien d'autre ne casse.

   Usage : node tools/test-modeles.mjs        (nécessite Google Chrome) */
import { open } from './lib-chrome.mjs';

let fails = [];
const check = (nom, cond, detail = '') => {
  console.log((cond ? '  ✓ ' : '  ✗ ') + nom + (cond ? '' : ' — ' + detail));
  if (!cond) fails.push(nom);
};

const page = await open('/app.html');
if (!await page.waitFor("typeof cvPageHTML === 'function' && typeof TEMPLATES !== 'undefined'")) {
  console.error('app.html ne s’est pas initialisée'); await page.close(); process.exit(1);
}
console.log('Modèles de CV — robustesse du rendu');

await page.eval("startNew('moderne')");     // un vrai CV ouvert dans l'éditeur

const r = await page.eval(`(function(){
  const cas = {
    'vide':                {},
    'null partout':        {fullName:null,title:null,summary:null,experiences:null,education:null,skills:null,languages:null,interests:null,photo:null},
    'tableaux troués':     {experiences:[null],education:[null],skills:[null],languages:[null],interests:[null]},
    'html injecté':        {fullName:'<img src=x onerror=alert(1)>',title:'"><script>',summary:'a & b < c'},
    'très long':           {fullName:'X'.repeat(400),title:'Y'.repeat(400),summary:'Z'.repeat(4000)},
    'niveaux hors bornes': {skills:[{name:'a',level:99},{name:'b',level:-5},{name:'c',level:null}]},
    'photo invalide':      {photo:'pas-une-image'},
  };
  const design = {accent:'#2563eb',font:'Inter',fontScale:1,spacing:1,photoRound:true,show:{}};
  const erreurs = [];
  const idAvant = state && state.id;
  for (const t of TEMPLATES) for (const [nom, d] of Object.entries(cas)) {
    try {
      const h = cvPageHTML(t.id, d, design);
      if (typeof h !== 'string' || !h.length) erreurs.push(t.id + ' / ' + nom + ' : rendu vide');
    } catch (e) { erreurs.push(t.id + ' / ' + nom + ' : ' + e.name + ' ' + e.message.slice(0, 60)); }
  }

  let inconnu = 'ok';
  try { cvPageHTML('modele-du-futur', {}, design); } catch (e) { inconnu = e.name + ' ' + e.message.slice(0, 60); }

  // état préservé même quand un rendu lève : on force une exception
  const sauve = RENDER.moderne;
  let etatApresErreur;
  RENDER.moderne = function(){ throw new Error('boum'); };
  try { cvPageHTML('moderne', {}, design); } catch (e) {}
  etatApresErreur = state && state.id;
  RENDER.moderne = sauve;

  // le HTML doit être échappé, jamais injecté
  const injecte = cvPageHTML('moderne', {fullName:'<img src=x onerror=alert(1)>'}, design).includes('<img src=x');

  // la case « Photo ronde » doit avoir un effet sur tout modèle qui affiche une photo
  const photoInerte = [];
  for (const t of TEMPLATES) {
    if (!t.photo) continue;
    const d = Object.assign({}, sampleData(), {photo:'data:image/gif;base64,R0lGODlhAQABAAAAACw='});
    const rond  = cvPageHTML(t.id, d, Object.assign({}, design, {photoRound:true}));
    const carre = cvPageHTML(t.id, d, Object.assign({}, design, {photoRound:false}));
    if (rond === carre) photoInerte.push(t.id);
  }
  return { erreurs, inconnu, idAvant, etatApresErreur, injecte, photoInerte,
           combinaisons: TEMPLATES.length * Object.keys(cas).length };
})()`);

check(`${r.combinaisons} combinaisons modèle × données hostiles : aucune exception`,
  r.erreurs.length === 0, r.erreurs.slice(0, 6).join(' | '));
check('modèle inconnu : repli silencieux sur Moderne', r.inconnu === 'ok', r.inconnu);
check('une exception de rendu ne corrompt pas l’état du CV',
  r.etatApresErreur === r.idAvant, `${r.idAvant} → ${r.etatApresErreur}`);
check('le contenu utilisateur est échappé, jamais injecté', r.injecte === false);
check('« Photo ronde » agit sur tous les modèles qui affichent une photo',
  r.photoInerte.length === 0, 'inerte sur : ' + r.photoInerte.join(', '));


/* ---------------- Sélection au clic ---------------- */
console.log('\nSélection au clic dans l’aperçu');

/* Chaque modèle doit rendre des blocs cliquables pour toutes ses sections :
   c'est ce qui casse si un modèle cesse de passer par les blocs partagés. */
const couverture = await page.eval(`(function(){
  const manquants = [];
  for (const t of TEMPLATES) {
    if (t.premium && !isPremium()) continue;
    changeTemplate(t.id);
    const vus = new Set([...document.querySelectorAll('#pageWrap [data-edit]')]
      .map(el => el.getAttribute('data-edit').split('.')[0]));
    const attendus = ['summary','experiences','education','skills','languages'];
    const absents = attendus.filter(k => !vus.has(k));
    if (absents.length) manquants.push(t.id + ' : ' + absents.join(', '));
  }
  changeTemplate('moderne');
  return manquants;
})()`);
check('les 11 modèles rendent des blocs cliquables pour chaque section',
  couverture.length === 0, couverture.join(' | '));

/* Un clic réel sur l'aperçu, pas un appel direct à selectBlock() : on veut
   vérifier la délégation d'événement et la remontée au bloc porteur. */
const clics = await page.eval(`(function(){
  const essais = [
    ['.cv-name',                        'fullName',            'identite'],
    ['.cv-title',                       'title',               'identite'],
    ['[data-edit="email"]',             'email',               'contact'],
    ['[data-edit="summary"]',           'summary',             'profil'],
    ['[data-edit="experiences.1.role"]','experiences.1.role',  'experiences'],
    ['[data-edit="education.0.degree"]','education.0.degree',  'education'],
    ['[data-edit="skills.2.name"]',     'skills.2.name',       'skills'],
    ['[data-edit="languages.1.name"]',  'languages.1.name',    'languages'],
  ];
  const out = [];
  for (const [sel, chemin, groupe] of essais) {
    const cible = document.querySelector('#pageWrap ' + sel);
    if (!cible) { out.push(sel + ' : absent de l’aperçu'); continue; }
    cible.click();
    const actif = document.activeElement;
    if (!actif || actif.getAttribute('data-path') !== chemin)
      out.push(sel + ' : focus sur ' + (actif && actif.getAttribute('data-path')) + ' au lieu de ' + chemin);
    const grp = document.querySelector('#pane-content .group[data-group="' + groupe + '"]');
    if (!grp || !grp.open) out.push(sel + ' : section « ' + groupe + ' » restée fermée');
    if (!document.querySelector('#pageWrap .is-selected')) out.push(sel + ' : bloc non surligné');
  }
  return out;
})()`);
check('un clic ouvre la bonne section et focalise le bon champ',
  clics.length === 0, clics.slice(0, 4).join(' | '));

/* L'aperçu est reconstruit à chaque frappe : la sélection doit survivre. */
const survie = await page.eval(`(function(){
  document.querySelector('#pageWrap [data-edit="skills.0.name"]').click();
  const avant = document.querySelectorAll('#pageWrap .is-selected').length;
  setPath('fullName', 'Frappe ' + Date.now());   // provoque un renderPreview()
  const apres = document.querySelectorAll('#pageWrap .is-selected').length;
  return {avant, apres};
})()`);
check('la sélection survit au re-rendu de l’aperçu',
  survie.avant > 0 && survie.apres > 0, JSON.stringify(survie));

/* Cliquer le vide désélectionne, et rien ne doit rester surligné à l'impression. */
const vide = await page.eval(`(function(){
  document.querySelector('#pageWrap .sheet').click();
  return document.querySelectorAll('#pageWrap .is-selected').length;
})()`);
check('cliquer une zone vide désélectionne', vide === 0, vide + ' bloc(s) encore surlignés');

const impression = await page.eval(`(function(){
  const css = [...document.querySelectorAll('style')].map(s => s.textContent).join('').replace(/\\s+/g,'');
  const bloc = css.slice(css.indexOf('@mediaprint'));   // les espaces ont été retirés juste au-dessus
  return bloc.includes('.is-selected') && bloc.includes('outline:none!important');
})()`);
check('surbrillance et sélection sont retirées à l’impression', impression === true);

await page.close();
console.log(fails.length ? `\n${fails.length} échec(s)` : '\nTous les tests passent');
process.exit(fails.length ? 1 : 0);
