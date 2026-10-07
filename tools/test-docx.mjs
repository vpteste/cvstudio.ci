/**
 * Vérifie l'export .docx de app.html sans navigateur.
 *
 *     node tools/test-docx.mjs
 *
 * Extrait la section « 15b » de app.html, l'exécute avec des stubs, écrit un
 * .docx de test puis contrôle : ZIP valide, XML bien formé, texte relu par
 * Word (via `textutil`, l'implémentation OOXML d'Apple).
 */
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const OUT = path.join(ROOT, '.test-out');
const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');

const from = src.indexOf('/* ============================================================\n   15b. EXPORT .DOCX');
const to = src.indexOf('function resetSample(){');
if (from < 0 || to < 0) throw new Error("Section 15b introuvable dans app.html");

const stubs = `
  const toast = (m, err) => { if (err) throw new Error('toast erreur: ' + m); };
  const signName = () => 'CV Studio';
  let askedDownload = null;
  const requestCVDownload = (src, callback) => { askedDownload = src; callback(); };
  const getAskedDownload = () => askedDownload;
  const document = { createElement: () => ({ set href(v) {}, click() {} }) };
  const URL = { createObjectURL: b => (globalThis.__blob = b, 'blob:x'), revokeObjectURL() {} };
`;
const code = stubs + src.slice(from, to) +
  '\nexport { getAskedDownload, exportDOCX, docxDocumentVisual, zipStore, docxDocument, docxStyles, dateRangeTxt, bulletParas };';

const tmp = path.join(OUT, 'docx-module.mjs');
fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(tmp, code);
const M = await import(tmp + '?t=' + Date.now());

// --- CV de test : accents, puces, sauts de ligne, caractères XML dangereux
globalThis.state = {
  name: 'CV test', template: 'moderne',
  design: { accent: '#2563eb', font: 'Inter', signature: true, photoRound: true,
            show: { summary: true, experiences: true, education: true, skills: true, languages: true, interests: true } },
  data: {
    photo: 'data:image/jpeg;base64,' + fs.readFileSync(
      path.join(ROOT, 'tools/fixtures/photo-test.jpg')).toString('base64'),
    fullName: 'Aya Koné', title: 'Développeuse & « data » <senior>',
    email: 'aya@example.ci', phone: '+225 07 00 00 00', location: 'Abidjan',
    linkedin: 'linkedin.com/in/ayakone', website: '',
    summary: "Ingénieure logiciel, 6 ans d'expérience.\nSpécialiste Python & données.",
    experiences: [{ role: 'Lead développeuse', company: 'Orange CI', location: 'Abidjan',
                    start: '2021', end: '', current: true,
                    desc: "• Conduite d'une équipe de 5 personnes\n• Réduction de 40 % du temps de traitement\n• Migration vers AWS" }],
    education: [{ degree: 'Master informatique', school: 'INP-HB', location: 'Yamoussoukro',
                  start: '2016', end: '2018', desc: 'Mention très bien' }],
    skills: [{ name: 'Python', level: 5 }, { name: 'SQL', level: 4 }],
    languages: [{ name: 'Français', level: 'Langue maternelle' }, { name: 'Anglais', level: 'Professionnel' }],
    interests: ['Basket', 'Mentorat'],
  },
};

let failures = 0;
const check = (label, fn) => {
  try { fn(); console.log('  ✓ ' + label); }
  catch (e) { failures++; console.log('  ✗ ' + label + ' → ' + e.message); }
};

console.log('\nExport .docx');
M.exportDOCX('ats');
const blob = globalThis.__blob;
const buf = Buffer.from(await blob.arrayBuffer());
const file = path.join(OUT, 'cv-test.docx');
fs.writeFileSync(file, buf);

check('signature ZIP (PK\\x03\\x04) présente', () => {
  if (buf.subarray(0, 4).toString('hex') !== '504b0304') throw new Error('en-tête ZIP invalide');
});
check('type MIME docx sur le Blob', () => {
  if (!blob.type.includes('wordprocessingml')) throw new Error(blob.type);
});
check('ZIP lisible, toutes les entrées attendues présentes', () => {
  const list = execFileSync('unzip', ['-l', file], { encoding: 'utf8' });
  for (const n of ['[Content_Types].xml', '_rels/.rels', 'word/document.xml',
                   'word/styles.xml', 'word/_rels/document.xml.rels', 'word/media/photo.jpeg',
                   'word/settings.xml'])
    if (!list.includes(n)) throw new Error('entrée manquante : ' + n);
});
check('XML bien formé (document.xml + styles.xml)', () => {
  for (const part of ['word/document.xml', 'word/styles.xml', 'word/settings.xml']) {
    const xml = execFileSync('unzip', ['-p', file, part], { encoding: 'utf8' });
    execFileSync('xmllint', ['--noout', '-'], { input: xml });
  }
});
check('caractères spéciaux échappés (pas de < > & nus)', () => {
  const xml = execFileSync('unzip', ['-p', file, 'word/document.xml'], { encoding: 'utf8' });
  if (!xml.includes('&lt;senior&gt;')) throw new Error('« <senior> » non échappé');
  if (!xml.includes('&amp;')) throw new Error('« & » non échappé');
});
check('Word relit le fichier et retrouve tout le contenu (textutil)', () => {
  const txt = execFileSync('textutil', ['-convert', 'txt', '-stdout', file], { encoding: 'utf8' });
  for (const needle of ['Aya Koné', 'Lead développeuse', 'Orange CI', 'Master informatique',
                        'Python', 'Anglais', 'Réduction de 40 %', 'Aujourd’hui',
                        'Expériences professionnelles', 'Profil', 'Formation']) {
    if (!txt.includes(needle)) throw new Error('texte absent du rendu Word : ' + needle);
  }
  if (/undefined|\[object/.test(txt)) throw new Error('valeur non rendue dans le document');
});
check('photo embarquée dans le ZIP (word/media)', () => {
  const list = execFileSync('unzip', ['-l', file], { encoding: 'utf8' });
  if (!list.includes('word/media/photo.jpeg')) throw new Error('image absente du .docx');
});
check('photo intacte après le passage dans le ZIP', () => {
  const src = fs.readFileSync(path.join(ROOT, 'tools/fixtures/photo-test.jpg'));
  const out = execFileSync('unzip', ['-p', file, 'word/media/photo.jpeg'], { maxBuffer: 1 << 24 });
  if (Buffer.compare(src, out) !== 0) throw new Error('octets de l’image altérés');
});
check('image déclarée : relation rId2 + type de contenu', () => {
  const rels = execFileSync('unzip', ['-p', file, 'word/_rels/document.xml.rels'], { encoding: 'utf8' });
  if (!rels.includes('rId2') || !rels.includes('media/photo.jpeg'))
    throw new Error('relation vers l’image manquante');
  const ct = execFileSync('unzip', ['-p', file, '[[]Content_Types].xml'], { encoding: 'utf8' });
  if (!ct.includes('image/jpeg')) throw new Error('type de contenu image/jpeg absent');
});
check('image insérée en ligne et liée à sa relation', () => {
  const xml = execFileSync('unzip', ['-p', file, 'word/document.xml'], { encoding: 'utf8' });
  if (!xml.includes('<wp:inline')) throw new Error('image non ancrée en ligne');
  if (!xml.includes('r:embed="rId2"')) throw new Error('image non liée à la relation');
});
check('photo ronde -> extent carré ; photo carrée -> ratio d’origine', () => {
  const extent = xml => {
    const m = /<wp:extent cx="(\d+)" cy="(\d+)"\/>/.exec(xml);
    if (!m) throw new Error('dimensions absentes');
    return (+m[2]) / (+m[1]);
  };
  // design.photoRound = true (état de test) : cercle, donc extent carré
  if (Math.abs(extent(M.docxDocument(globalThis.state, { size: { w: 240, h: 320 }, relId: 'rId2' })) - 1) > 0.001)
    throw new Error('photo ronde : extent devrait être carré');
  // sans photo ronde : proportions de la source (240x320) conservées
  const carre = JSON.parse(JSON.stringify(globalThis.state));
  carre.design.photoRound = false;
  const r = extent(M.docxDocument(carre, { size: { w: 240, h: 320 }, relId: 'rId2' }));
  if (Math.abs(r - 320 / 240) > 0.02) throw new Error('photo déformée, ratio ' + r.toFixed(3));
});
check('sans photo : ni média ni relation rId2', () => {
  const sansPhoto = JSON.parse(JSON.stringify(globalThis.state));
  sansPhoto.data.photo = null;
  const xml = M.docxDocument(sansPhoto, null);
  if (xml.includes('<w:drawing>')) throw new Error('image insérée alors qu’il n’y en a pas');
});
check('la confirmation du contact précède l’export Word', () => {
  if (M.getAskedDownload() !== 'download_docx') throw new Error('garde de téléchargement Word non appelée');
});
check('entrées ATS sur une ligne : dates au taquet de la marge droite', () => {
  const xml = execFileSync('unzip', ['-p', file, 'word/document.xml'], { encoding: 'utf8' });
  // 9638 = 11906 (A4) − 2 × 1134 (marges de 2 cm)
  if (!xml.includes('<w:tab w:val="right" w:pos="9638"/>'))
    throw new Error('taquet droit à la marge absent : dates retombées en ligne séparée ?');
});
check('sections masquées absentes du document', () => {
  globalThis.state.design.show.interests = false;
  const xml = M.docxDocument(globalThis.state);
  if (xml.includes('Mentorat')) throw new Error('« Centres d’intérêt » masqué mais exporté');
  globalThis.state.design.show.interests = true;
});
check('CV vide : export sans exception', () => {
  const empty = { name: '', design: { accent: '#000', font: 'Inter', show: {} },
                  data: { fullName: '', title: '', email: '', phone: '', location: '', linkedin: '',
                          website: '', summary: '', experiences: [], education: [], skills: [],
                          languages: [], interests: [] } };
  M.docxDocument(empty);
});

// --- variante « fidèle au modèle »
console.log('\nExport .docx — variante fidèle au modèle');
M.exportDOCX('fidele');
const vbuf = Buffer.from(await globalThis.__blob.arrayBuffer());
const vfile = path.join(OUT, 'cv-test-fidele.docx');
fs.writeFileSync(vfile, vbuf);

check('XML bien formé', () => {
  const xml = execFileSync('unzip', ['-p', vfile, 'word/document.xml'], { encoding: 'utf8' });
  execFileSync('xmllint', ['--noout', '-'], { input: xml });
});
check('mise en page à deux colonnes (tableau + fond coloré)', () => {
  const xml = execFileSync('unzip', ['-p', vfile, 'word/document.xml'], { encoding: 'utf8' });
  if (!xml.includes('<w:tbl>')) throw new Error('aucun tableau : pas de colonne latérale');
  if (!xml.includes('w:fill="2563EB"')) throw new Error('fond de la colonne latérale absent');
  // 70 mm exactement — la valeur de .tpl-moderne dans le CSS (grid 70mm | 1fr)
  if (!/<w:gridCol w:w="3969"\/>/.test(xml)) throw new Error('largeur de colonne latérale incorrecte');
});
check('barres de compétences : remplissage proportionnel au niveau', () => {
  const xml = execFileSync('unzip', ['-p', vfile, 'word/document.xml'], { encoding: 'utf8' });
  const segs = [...xml.matchAll(/w:fill="([0-9A-F]{6})"\/><w:sz w:val="13"[\s\S]*?<w:t xml:space="preserve">(\u00A0+)<\/w:t>/g)]
    .map(m => ({ color: m[1], n: m[2].length }));
  if (segs.length !== 3)                     // Python 5/5 = 1 segment, SQL 4/5 = 2
    throw new Error('segments de barre attendus : 3, trouvés ' + segs.length);
  const N = segs[0].n;                       // barre pleine = référence de largeur
  if (segs[0].color !== 'FFFFFF') throw new Error('la portion pleine doit être blanche');
  if (segs[1].n + segs[2].n !== N) throw new Error('barres de largeurs inégales');
  const ratio = segs[1].n / N;               // SQL niveau 4 => 80 %
  if (Math.abs(ratio - 0.8) > 0.02) throw new Error('niveau 4 rendu à ' + Math.round(ratio * 100) + '%');
  if (segs[2].color === 'FFFFFF') throw new Error('la portion vide doit être d’une autre teinte');
});
check('photo ronde : géométrie ellipse + recadrage carré non déformant', () => {
  const xml = execFileSync('unzip', ['-p', vfile, 'word/document.xml'], { encoding: 'utf8' });
  if (!xml.includes('<a:prstGeom prst="ellipse">')) throw new Error('photo restée rectangulaire');
  const m = /<a:srcRect l="(\d+)" t="(\d+)" r="(\d+)" b="(\d+)"\/>/.exec(xml);
  if (!m) throw new Error('recadrage carré absent : le visage serait ovalisé');
  // fixture 240x320 (portrait) : on rogne en haut/bas, jamais sur les côtés
  if (+m[1] !== 0 || +m[3] !== 0) throw new Error('rognage latéral inattendu');
  if (Math.abs(+m[2] - 12500) > 100) throw new Error('rognage vertical incorrect : ' + m[2]);
  const e = /<wp:extent cx="(\d+)" cy="(\d+)"\/>/.exec(xml);
  if (e[1] !== e[2]) throw new Error('extent non carré : le cercle serait un ovale');
});
check('dates alignées à droite (taquet)', () => {
  const xml = execFileSync('unzip', ['-p', vfile, 'word/document.xml'], { encoding: 'utf8' });
  if (!xml.includes('<w:tab w:val="right"')) throw new Error('taquet droit absent');
});
check('colonne latérale sur toute la hauteur de page', () => {
  const xml = execFileSync('unzip', ['-p', vfile, 'word/document.xml'], { encoding: 'utf8' });
  if (!xml.includes('<w:trHeight w:val="16838" w:hRule="atLeast"/>'))
    throw new Error('la bande colorée s’arrêterait au bas du texte');
});
check('photo reprise dans la variante fidèle', () => {
  const list = execFileSync('unzip', ['-l', vfile], { encoding: 'utf8' });
  if (!list.includes('word/media/photo.jpeg')) throw new Error('photo absente');
});
check('Word relit la variante fidèle', () => {
  const txt = execFileSync('textutil', ['-convert', 'txt', '-stdout', vfile], { encoding: 'utf8' });
  for (const n of ['Aya Koné', 'Orange CI', 'Python', 'Anglais', 'Basket'])
    if (!txt.includes(n)) throw new Error('texte absent : ' + n);
});
check('aucune icône emoji couleur (📍, 🔗) dans les contacts', () => {
  for (const f of [file, vfile]) {
    const xml = execFileSync('unzip', ['-p', f, 'word/document.xml'], { encoding: 'utf8' });
    for (const e of ['📍', '🔗'])
      if (xml.includes(e)) throw new Error(e + ' présent dans ' + path.basename(f) + ' : rendu emoji hors de propos');
  }
});


// --- fidélité au modèle : les 6 modèles doivent produire 6 mises en page
// Le bug corrigé : quel que soit le modèle affiché, l'export « fidèle »
// redessinait toujours la barre latérale gauche du modèle Moderne.
console.log('\nExport .docx — un rendu par modèle');

const photo = { size: { w: 240, h: 320 }, relId: 'rId2' };
const forTpl = (id, tweak) => {
  const st = JSON.parse(JSON.stringify(globalThis.state));
  st.template = id;
  if (tweak) tweak(st);
  return M.docxDocumentVisual(st, photo);
};
const wellFormed = xml => execFileSync('xmllint', ['--noout', '-'], { input: xml });
// Tableau imbriqué = rendu de travers par plusieurs lecteurs (Aperçu macOS)
const nestedTable = xml => {
  let depth = 0;
  for (const m of xml.matchAll(/<w:(tbl|tc)[ >]|<\/w:(tbl|tc)>/g)) {
    const t = m[0];
    if (t.startsWith('</w:tbl')) depth--;
    else if (t.startsWith('<w:tbl')) { if (depth > 0) return true; depth++; }
  }
  return false;
};

const LAYOUTS = {
  // id            : [contrôle propre au modèle, description]
  moderne:   [x => /<w:gridCol w:w="3969"\/>/.test(x) && x.includes('w:fill="2563EB"'),
              'barre latérale colorée de 70 mm'],
  elegant:   [x => x.includes('w:fill="2563EB"')
                   && /<w:gridCol w:w="8845"\/><w:gridCol w:w="3061"\/>/.test(x)   // bandeau = pleine largeur
                   && /<w:gridCol w:w="6973"\/><w:gridCol w:w="624"\/><w:gridCol w:w="4309"\/>/.test(x),
              'bandeau pleine largeur + corps à 2 colonnes'],
  classique: [x => !x.includes('w:fill="2563EB"') && x.includes('<w:jc w:val="center"/>'),
              'une colonne, en-tête centré, sans aplat'],
  minimal:   [x => x.includes('w:val="30"') && !x.includes('w:fill="2563EB"'),
              'titres très espacés, sans aplat'],
  compact:   [x => /<w:pgMar w:top="680"/.test(x),
              'marges resserrées de 12 mm'],
  prestige:  [x => x.includes('w:fill="1F2430"'),
              'bandeau sombre'],

  /* Les cinq modèles repris de /models. Ils ont d'abord été livrés comme de
     simples ALIAS des constructeurs existants : à l'écran on voyait « Athlète »
     (page sombre), et le .docx sortait la mise en page de Prestige. Ces
     contrôles épinglent ce qui distingue chacun — colonne à gauche ou à
     DROITE, fond de page, cadre — pour que l'écart ne puisse pas revenir. */
  contraste: [x => /<w:tblGrid><w:gridCol w:w="8278"\/><w:gridCol w:w="3628"\/>/.test(x),
              'colonne teintée à DROITE (1fr | 64 mm)'],
  duo:       [x => /<w:tblGrid><w:gridCol w:w="8051"\/><w:gridCol w:w="3855"\/>/.test(x),
              'colonne colorée à DROITE (1fr | 68 mm)'],
  coach:     [x => /<w:tblGrid><w:gridCol w:w="3628"\/><w:gridCol w:w="8278"\/>/.test(x)
                   && x.includes('w:fill="ECECEF"'),
              'colonne GRISE à gauche (64 mm | 1fr)'],
  athlete:   [x => x.includes('<w:background w:color="15171C"/>') && x.includes('w:fill="15171C"')
                   && x.includes('<w:trHeight w:val="16838"'),
              'page sombre pleine page'],
  champion:  [x => /<w:pgBorders w:offsetFrom="page">/.test(x) && x.includes('w:sz="96"')
                   && /<w:tcBorders><w:top[^>]*\/><w:left[^>]*\/><w:bottom[^>]*\/><w:right[^>]*\/><\/w:tcBorders>/.test(x),
              'cadre coloré de page + identité encadrée'],
};

const rendus = {};
for (const [id, [ok, desc]] of Object.entries(LAYOUTS)) {
  check(`modèle « ${id} » : ${desc}`, () => {
    const xml = rendus[id] = forTpl(id);
    wellFormed(xml);
    if (!ok(xml)) throw new Error('mise en page non conforme au modèle');
    if (nestedTable(xml)) throw new Error('tableau imbriqué : rendu incertain hors de Word');
    if (/<\/w:tbl><w:tbl>/.test(xml)) throw new Error('deux tableaux collés : Word les fusionnerait');
    if (/<\/w:tbl>\s*<\/w:body>/.test(xml)) throw new Error('le corps se termine par un tableau');
  });
}
const NB = Object.keys(LAYOUTS).length;
check(`les ${NB} modèles donnent ${NB} mises en page différentes`, () => {
  const vus = new Map();
  for (const [id, xml] of Object.entries(rendus)) {
    if (vus.has(xml)) throw new Error(`« ${id} » rendu à l’identique de « ${vus.get(xml)} »`);
    vus.set(xml, id);
  }
});
check('le fond de page sombre est effectivement peint par Word', () => {
  // <w:background> n'est rendu que si settings.xml porte <w:displayBackgroundShape/>.
  if (!rendus.athlete.includes('<w:background')) throw new Error('fond de page absent du document');
  if (!src.includes('<w:displayBackgroundShape/>'))
    throw new Error('settings.xml sans displayBackgroundShape : Word ignorerait le fond');
});
check('tous les modèles gardent le contenu du CV', () => {
  for (const [id, xml] of Object.entries(rendus))
    for (const n of ['Aya Koné', 'Orange CI', 'INP-HB', 'Python', 'Anglais', 'Basket', 'Abidjan'])
      if (!xml.includes(n)) throw new Error(`« ${n} » absent du modèle ${id}`);
});
check('modèle inconnu : repli sur Moderne plutôt qu’un document vide', () => {
  if (forTpl('modele-du-futur') !== rendus.moderne) throw new Error('pas de repli');
});
check('sans photo, tous les modèles restent valides', () => {
  for (const id of Object.keys(LAYOUTS)) {
    const st = JSON.parse(JSON.stringify(globalThis.state));
    st.template = id; st.data.photo = null;
    const xml = M.docxDocumentVisual(st, null);
    wellFormed(xml);
    if (xml.includes('<w:drawing>')) throw new Error(`image fantôme dans ${id}`);
  }
});
check('CV vide : aucun modèle ne lève d’exception', () => {
  const empty = { template: 'x', design: { accent: '#000', font: 'Inter', show: {} },
                  data: { fullName: '', title: '', email: '', phone: '', location: '', linkedin: '',
                          website: '', summary: '', experiences: [], education: [], skills: [],
                          languages: [], interests: [] } };
  for (const id of Object.keys(LAYOUTS)) { empty.template = id; wellFormed(M.docxDocumentVisual(empty, null)); }
});
check('sections masquées absentes de tous les modèles', () => {
  for (const id of Object.keys(LAYOUTS)) {
    const st = JSON.parse(JSON.stringify(globalThis.state));
    st.template = id; st.design.show.interests = false; st.design.show.languages = false;
    const xml = M.docxDocumentVisual(st, null);
    if (xml.includes('Basket') || xml.includes('Langue maternelle'))
      throw new Error(`section masquée exportée dans ${id}`);
  }
});

console.log(failures ? `\n${failures} test(s) en échec\n` : '\nTous les tests passent\n');
console.log('Fichier de contrôle : ' + path.relative(ROOT, file));
process.exit(failures ? 1 : 0);
