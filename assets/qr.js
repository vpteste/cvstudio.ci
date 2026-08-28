/* ============================================================
   qr.js — encodeur QR autonome (aucune dépendance)
   Utilisé par le générateur de carte de visite : le QR est imprimé,
   une erreur d'encodage coûterait un tirage entier. La sortie est du SVG
   (vectoriel) et non un PNG : à 12 mm de côté sur une carte, un bitmap
   redimensionné par l'imprimeur devient illisible.

   Portée volontairement limitée : mode octet (UTF-8), versions 1 à 10,
   niveaux de correction L/M/Q/H. Une URL ou un MECARD tiennent largement
   dans les 271 octets de la version 10-L.

   API :  QR.svg(texte, {level, margin, scale, dark, light})  -> chaîne SVG
          QR.dataURI(texte, opts)                             -> data:image/svg+xml
          QR.matrix(texte, level)                             -> {size, mods[][]}
   ============================================================ */
(function (root) {
  'use strict';

  /* ---------- GF(256), polynôme primitif 0x11D ---------- */
  var EXP = new Uint8Array(512), LOG = new Uint8Array(256);
  (function () {
    for (var i = 0, x = 1; i < 255; i++) {
      EXP[i] = x; LOG[x] = i;
      x <<= 1; if (x & 0x100) x ^= 0x11d;
    }
    for (i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
  })();
  function gmul(a, b) { return (a === 0 || b === 0) ? 0 : EXP[LOG[a] + LOG[b]]; }

  /* Polynôme générateur de degré n */
  function genPoly(n) {
    var g = [1];
    for (var i = 0; i < n; i++) {
      var ng = new Array(g.length + 1).fill(0);
      for (var j = 0; j < g.length; j++) {
        // g est rangé du degré le PLUS FORT au plus faible (g[0] = 1), ordre
        // qu'attend la division synthétique de ecBlock(). Multiplier par x
        // conserve l'indice, multiplier par α^i le décale.
        ng[j] ^= g[j];
        ng[j + 1] ^= gmul(g[j], EXP[i]);
      }
      g = ng;
    }
    return g;
  }

  /* Codewords de correction d'un bloc de données */
  function ecBlock(data, ecLen) {
    var g = genPoly(ecLen), res = new Array(data.length + ecLen).fill(0);
    for (var i = 0; i < data.length; i++) res[i] = data[i];
    for (i = 0; i < data.length; i++) {
      var f = res[i];
      if (f === 0) continue;
      for (var j = 0; j < g.length; j++) res[i + j] ^= gmul(g[j], f);
    }
    return res.slice(data.length);
  }

  /* ---------- Tables normatives (versions 1-10) ----------
     [ec par bloc, blocs groupe 1, données/bloc G1, blocs G2, données/bloc G2]
     Ordre des niveaux : L, M, Q, H. */
  var ECC = {
    1:  [[7,1,19,0,0],   [10,1,16,0,0],  [13,1,13,0,0],  [17,1,9,0,0]],
    2:  [[10,1,34,0,0],  [16,1,28,0,0],  [22,1,22,0,0],  [28,1,16,0,0]],
    3:  [[15,1,55,0,0],  [26,1,44,0,0],  [18,2,17,0,0],  [22,2,13,0,0]],
    4:  [[20,1,80,0,0],  [18,2,32,0,0],  [26,2,24,0,0],  [16,4,9,0,0]],
    5:  [[26,1,108,0,0], [24,2,43,0,0],  [18,2,15,2,16], [22,2,11,2,12]],
    6:  [[18,2,68,0,0],  [16,4,27,0,0],  [24,4,19,0,0],  [28,4,15,0,0]],
    7:  [[20,2,78,0,0],  [18,4,31,0,0],  [18,2,14,4,15], [26,4,13,1,14]],
    8:  [[24,2,97,0,0],  [22,2,38,2,39], [22,4,18,2,19], [26,4,14,2,15]],
    9:  [[30,2,116,0,0], [22,3,36,2,37], [20,4,16,4,17], [24,4,12,4,13]],
    10: [[18,2,68,2,69], [26,4,43,1,44], [24,6,19,2,20], [28,6,15,2,16]],
  };
  var LEVELS = { L: 0, M: 1, Q: 2, H: 3 };
  /* Indicateur de niveau dans l'information de format (≠ index du tableau) */
  var FMT_LEVEL = { L: 1, M: 0, Q: 3, H: 2 };
  /* Centres des motifs d'alignement (hors coins occupés par les détecteurs) */
  var ALIGN = {
    1: [], 2: [6,18], 3: [6,22], 4: [6,26], 5: [6,30],
    6: [6,34], 7: [6,22,38], 8: [6,24,42], 9: [6,26,46], 10: [6,28,50],
  };
  /* Bits de remplissage après les codewords, par version */
  var REMAINDER = {1:0,2:7,3:7,4:7,5:7,6:7,7:0,8:0,9:0,10:0};

  function capacity(v, lvl) {
    var t = ECC[v][LEVELS[lvl]];
    return t[1] * t[2] + t[3] * t[4];              // codewords de données
  }

  /* ---------- Encodage des données ---------- */
  function utf8(s) {
    var out = [], enc = encodeURIComponent(s);
    for (var i = 0; i < enc.length; i++) {
      if (enc[i] === '%') { out.push(parseInt(enc.substr(i + 1, 2), 16)); i += 2; }
      else out.push(enc.charCodeAt(i));
    }
    return out;
  }

  function bitsToCodewords(bits, total) {
    // terminateur (≤ 4 bits) puis alignement octet
    var t = Math.min(4, total * 8 - bits.length);
    for (var i = 0; i < t; i++) bits.push(0);
    while (bits.length % 8) bits.push(0);
    var cw = [];
    for (i = 0; i < bits.length; i += 8) {
      var b = 0;
      for (var j = 0; j < 8; j++) b = (b << 1) | bits[i + j];
      cw.push(b);
    }
    var pad = [0xEC, 0x11], k = 0;
    while (cw.length < total) cw.push(pad[k++ % 2]);
    return cw;
  }

  function encode(text, lvl) {
    var bytes = utf8(text), v = 0;
    for (var i = 1; i <= 10; i++) {
      var lenBits = i < 10 ? 8 : 16;
      if (bytes.length * 8 + 4 + lenBits <= capacity(i, lvl) * 8) { v = i; break; }
    }
    if (!v) throw new Error('QR : contenu trop long (' + bytes.length + ' octets, maximum ' + capacity(10, lvl) + ')');

    var bits = [], push = function (val, n) { for (var b = n - 1; b >= 0; b--) bits.push((val >> b) & 1); };
    push(4, 4);                                   // mode octet
    push(bytes.length, v < 10 ? 8 : 16);
    for (i = 0; i < bytes.length; i++) push(bytes[i], 8);

    var t = ECC[v][LEVELS[lvl]], ecLen = t[0];
    var cw = bitsToCodewords(bits, capacity(v, lvl));

    // découpage en blocs
    var blocks = [], p = 0, n;
    for (n = 0; n < t[1]; n++) { blocks.push(cw.slice(p, p + t[2])); p += t[2]; }
    for (n = 0; n < t[3]; n++) { blocks.push(cw.slice(p, p + t[4])); p += t[4]; }
    var ecs = blocks.map(function (b) { return ecBlock(b, ecLen); });

    // entrelacement : colonne par colonne, données puis correction
    var out = [], maxD = Math.max.apply(null, blocks.map(function (b) { return b.length; }));
    for (i = 0; i < maxD; i++)
      for (n = 0; n < blocks.length; n++) if (i < blocks[n].length) out.push(blocks[n][i]);
    for (i = 0; i < ecLen; i++)
      for (n = 0; n < ecs.length; n++) out.push(ecs[n][i]);

    return { version: v, codewords: out };
  }

  /* ---------- Construction de la matrice ---------- */
  function buildMatrix(v) {
    var size = v * 4 + 17;
    var m = [], fn = [];                          // fn = module fonctionnel (non données)
    for (var i = 0; i < size; i++) { m.push(new Array(size).fill(0)); fn.push(new Array(size).fill(0)); }

    function set(x, y, val) { if (x >= 0 && y >= 0 && x < size && y < size) { m[y][x] = val; fn[y][x] = 1; } }

    // détecteurs de position + séparateurs
    [[0, 0], [size - 7, 0], [0, size - 7]].forEach(function (o) {
      for (var y = -1; y <= 7; y++) for (var x = -1; x <= 7; x++) {
        var inRing = (x === 0 || x === 6 || y === 0 || y === 6);
        var inCore = (x >= 2 && x <= 4 && y >= 2 && y <= 4);
        var inside = x >= 0 && x <= 6 && y >= 0 && y <= 6;
        set(o[0] + x, o[1] + y, inside && (inRing || inCore) ? 1 : 0);
      }
    });

    // rythmes
    for (i = 8; i < size - 8; i++) { set(i, 6, i % 2 === 0 ? 1 : 0); set(6, i, i % 2 === 0 ? 1 : 0); }

    // motifs d'alignement (jamais sur un détecteur)
    var A = ALIGN[v];
    for (var a = 0; a < A.length; a++) for (var b = 0; b < A.length; b++) {
      var cx = A[a], cy = A[b];
      if ((cx <= 8 && cy <= 8) || (cx <= 8 && cy >= size - 9) || (cx >= size - 9 && cy <= 8)) continue;
      for (var dy = -2; dy <= 2; dy++) for (var dx = -2; dx <= 2; dx++)
        set(cx + dx, cy + dy, (Math.max(Math.abs(dx), Math.abs(dy)) !== 1) ? 1 : 0);
    }

    // zones réservées à l'information de format
    for (i = 0; i <= 8; i++) { if (i !== 6) { set(i, 8, 0); set(8, i, 0); } }
    for (i = 0; i < 8; i++) { set(size - 1 - i, 8, 0); set(8, size - 1 - i, 0); }

    // Module noir permanent — APRÈS les réservations : la boucle ci-dessus
    // balaie la colonne 8 jusqu'à size-8 et l'effacerait.
    set(8, size - 8, 1);

    // information de version (versions ≥ 7) : BCH(18,6), générateur 0x1F25
    if (v >= 7) {
      var d = v << 12, r = d;
      for (i = 0; i < 6; i++) if (r >> (17 - i) & 1) r ^= 0x1f25 << (5 - i);
      var vi = d | (r & 0xfff);
      for (i = 0; i < 18; i++) {
        var bit = (vi >> i) & 1, rr = Math.floor(i / 3), cc = i % 3;
        set(rr, size - 11 + cc, bit); set(size - 11 + cc, rr, bit);
      }
    }
    return { size: size, m: m, fn: fn };
  }

  function placeData(M, cw, v) {
    var size = M.size, bits = [];
    for (var i = 0; i < cw.length; i++) for (var b = 7; b >= 0; b--) bits.push((cw[i] >> b) & 1);
    for (i = 0; i < REMAINDER[v]; i++) bits.push(0);

    var idx = 0, up = true;
    for (var col = size - 1; col > 0; col -= 2) {
      if (col === 6) col--;                        // la colonne de rythme ne porte pas de données
      for (var r = 0; r < size; r++) {
        var y = up ? size - 1 - r : r;
        for (var c = 0; c < 2; c++) {
          var x = col - c;
          if (M.fn[y][x]) continue;
          M.m[y][x] = idx < bits.length ? bits[idx] : 0;
          idx++;
        }
      }
      up = !up;
    }
  }

  function maskFn(k) {
    return [
      function (x, y) { return (x + y) % 2 === 0; },
      function (x, y) { return y % 2 === 0; },
      function (x, y) { return x % 3 === 0; },
      function (x, y) { return (x + y) % 3 === 0; },
      function (x, y) { return (Math.floor(y / 2) + Math.floor(x / 3)) % 2 === 0; },
      function (x, y) { return (x * y) % 2 + (x * y) % 3 === 0; },
      function (x, y) { return ((x * y) % 2 + (x * y) % 3) % 2 === 0; },
      function (x, y) { return ((x + y) % 2 + (x * y) % 3) % 2 === 0; },
    ][k];
  }

  /* Pénalités N1..N4 de la norme — c'est ce qui rend le code lisible */
  function penalty(m, size) {
    var p = 0, i, j, run, dark = 0;
    for (i = 0; i < size; i++) {
      run = 1;
      for (j = 1; j < size; j++) {
        if (m[i][j] === m[i][j - 1]) { run++; } else { if (run >= 5) p += 3 + (run - 5); run = 1; }
      }
      if (run >= 5) p += 3 + (run - 5);
      run = 1;
      for (j = 1; j < size; j++) {
        if (m[j][i] === m[j - 1][i]) { run++; } else { if (run >= 5) p += 3 + (run - 5); run = 1; }
      }
      if (run >= 5) p += 3 + (run - 5);
    }
    for (i = 0; i < size - 1; i++) for (j = 0; j < size - 1; j++) {
      var s = m[i][j] + m[i][j + 1] + m[i + 1][j] + m[i + 1][j + 1];
      if (s === 0 || s === 4) p += 3;
    }
    var pat1 = [1,0,1,1,1,0,1,0,0,0,0], pat2 = [0,0,0,0,1,0,1,1,1,0,1];
    function match(get, n) {
      for (var a = 0; a + 11 <= n; a++) {
        var ok1 = true, ok2 = true;
        for (var b = 0; b < 11; b++) { var vv = get(a + b); if (vv !== pat1[b]) ok1 = false; if (vv !== pat2[b]) ok2 = false; }
        if (ok1 || ok2) p += 40;
      }
    }
    for (i = 0; i < size; i++) {
      (function (i) { match(function (k) { return m[i][k]; }, size); match(function (k) { return m[k][i]; }, size); })(i);
    }
    for (i = 0; i < size; i++) for (j = 0; j < size; j++) if (m[i][j]) dark++;
    p += Math.floor(Math.abs(dark * 100 / (size * size) - 50) / 5) * 10;
    return p;
  }

  function formatBits(lvl, mask) {
    var d = (FMT_LEVEL[lvl] << 3) | mask, r = d << 10;
    for (var i = 0; i < 5; i++) if (r >> (14 - i) & 1) r ^= 0x537 << (4 - i);
    return ((d << 10) | (r & 0x3ff)) ^ 0x5412;
  }

  function applyFormat(M, lvl, mask) {
    var f = formatBits(lvl, mask), size = M.size, i;
    // m[ligne][colonne]. Première copie : bits 0-8 le long de la COLONNE 8
    // (de haut en bas), bits 9-14 le long de la LIGNE 8 (de droite à gauche).
    for (i = 0; i <= 5; i++) M.m[i][8] = (f >> i) & 1;
    M.m[7][8] = (f >> 6) & 1; M.m[8][8] = (f >> 7) & 1; M.m[8][7] = (f >> 8) & 1;
    for (i = 9; i <= 14; i++) M.m[8][14 - i] = (f >> i) & 1;
    // Seconde copie : bits 0-7 sur la LIGNE 8 (à droite), bits 8-14 sur la
    // COLONNE 8 (en bas). L'inverse écrase le module noir en (8, size-8).
    for (i = 0; i <= 7; i++) M.m[8][size - 1 - i] = (f >> i) & 1;
    for (i = 8; i <= 14; i++) M.m[size - 15 + i][8] = (f >> i) & 1;
  }

  function matrix(text, lvl) {
    lvl = lvl || 'M';
    if (!(lvl in LEVELS)) throw new Error('QR : niveau inconnu ' + lvl);
    var enc = encode(String(text), lvl);
    var M = buildMatrix(enc.version);
    placeData(M, enc.codewords, enc.version);

    // on masque une copie pour évaluer, on garde la meilleure
    var best = null, bestP = Infinity;
    for (var k = 0; k < 8; k++) {
      var f = maskFn(k), cand = M.m.map(function (row) { return row.slice(); });
      for (var y = 0; y < M.size; y++) for (var x = 0; x < M.size; x++)
        if (!M.fn[y][x] && f(x, y)) cand[y][x] ^= 1;
      var T = { size: M.size, m: cand, fn: M.fn };
      applyFormat(T, lvl, k);
      var p = penalty(cand, M.size);
      if (p < bestP) { bestP = p; best = T; best.mask = k; }
    }
    return { size: best.size, mods: best.m, version: enc.version, mask: best.mask, level: lvl };
  }

  /* ---------- Sorties ---------- */
  function svg(text, o) {
    o = o || {};
    var q = matrix(text, o.level || 'M');
    var margin = o.margin == null ? 2 : o.margin;      // « zone calme » : 4 modules recommandés, 2 suffisent à cette taille
    var s = o.scale || 4, n = q.size + margin * 2, W = n * s;
    // Un seul <path> : le SVG reste léger et l'imprimeur ne voit qu'un tracé.
    var d = '';
    for (var y = 0; y < q.size; y++) for (var x = 0; x < q.size; x++)
      if (q.mods[y][x]) d += 'M' + ((x + margin) * s) + ' ' + ((y + margin) * s) + 'h' + s + 'v' + s + 'h-' + s + 'z';
    return '<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + W + '" viewBox="0 0 ' + W + ' ' + W +
      '" shape-rendering="crispEdges"><rect width="' + W + '" height="' + W + '" fill="' + (o.light || '#ffffff') +
      '"/><path d="' + d + '" fill="' + (o.dark || '#000000') + '"/></svg>';
  }
  function dataURI(text, o) {
    return 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svg(text, o))));
  }

  // __ecBlock n'est exposé que pour le vecteur de non-régression de
  // tools/test-qr.mjs : l'arithmétique GF(256) casse sans bruit.
  root.QR = { matrix: matrix, svg: svg, dataURI: dataURI, capacity: capacity, __ecBlock: ecBlock };
})(typeof window !== 'undefined' ? window : globalThis);
