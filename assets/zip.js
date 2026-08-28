/* ============================================================
   zip.js — écriture d'une archive ZIP « store » (sans compression).
   Assez pour un .docx : Word accepte les entrées non compressées, et cela
   évite d'embarquer un deflate.

   NB : app.html garde sa PROPRE copie de ce code. Ce n'est pas un oubli :
   tools/test-docx.mjs extrait l'export Word du CV comme un bloc contigu
   entre deux marqueurs, et sortir zipStore() de ce bloc casserait le test.
   Ce fichier sert les pages qui n'ont pas cette contrainte.
   ============================================================ */
(function (root) {
  'use strict';
  const T = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    T[n] = c;
  }
  function crc32(bytes) {
    let c = -1;
    for (let i = 0; i < bytes.length; i++) c = T[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ -1) >>> 0;
  }

  /* files : [{name, data}] où data est une chaîne (XML) ou un Uint8Array. */
  function zipStore(files, mime) {
    const enc = new TextEncoder(), chunks = [], central = [];
    let offset = 0;
    const u16 = v => [v & 0xFF, (v >>> 8) & 0xFF];
    const u32 = v => [v & 0xFF, (v >>> 8) & 0xFF, (v >>> 16) & 0xFF, (v >>> 24) & 0xFF];
    for (const f of files) {
      const name = enc.encode(f.name);
      const body = (f.data instanceof Uint8Array) ? f.data : enc.encode(f.data);
      const crc = crc32(body);
      // drapeau 0x0800 : noms de fichiers en UTF-8
      const local = [...u32(0x04034b50), ...u16(20), ...u16(0x0800), ...u16(0), ...u16(0), ...u16(0),
                     ...u32(crc), ...u32(body.length), ...u32(body.length), ...u16(name.length), ...u16(0)];
      chunks.push(new Uint8Array(local), name, body);
      central.push([...u32(0x02014b50), ...u16(20), ...u16(20), ...u16(0x0800), ...u16(0), ...u16(0), ...u16(0),
                    ...u32(crc), ...u32(body.length), ...u32(body.length), ...u16(name.length),
                    ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(0), ...u32(offset), ...Array.from(name)]);
      offset += local.length + name.length + body.length;
    }
    const cdBytes = new Uint8Array(central.flat());
    const eocd = new Uint8Array([...u32(0x06054b50), ...u16(0), ...u16(0),
                                 ...u16(files.length), ...u16(files.length),
                                 ...u32(cdBytes.length), ...u32(offset), ...u16(0)]);
    return new Blob([...chunks, cdBytes, eocd], { type: mime || 'application/zip' });
  }

  root.ZipStore = zipStore;
  root.ZipStore.crc32 = crc32;
})(typeof window !== 'undefined' ? window : globalThis);
