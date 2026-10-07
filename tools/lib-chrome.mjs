/* Pilote Chrome headless partagé par les tests navigateur (CV et lettre).
   Sert le dépôt sur un port éphémère, ouvre une page, et expose l'évaluation
   JavaScript et l'impression PDF via CDP. Aucune dépendance npm. */
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { join, extname, resolve } from 'node:path';
import { tmpdir } from 'node:os';

export const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const MIME = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css',
               '.json':'application/json', '.svg':'image/svg+xml', '.png':'image/png' };

/* `opts.width` / `opts.height` : taille de fenêtre, posée AU LANCEMENT.
   Passer par Emulation.setDeviceMetricsOverride après coup réinitialise le
   contexte d'exécution — les globales de la page deviennent introuvables. */
export async function open(pagePath, opts = {}) {
  const ROOT = resolve(import.meta.dirname, '..');
  const server = createServer(async (req, res) => {
    try {
      const pathname = new URL(req.url, 'http://localhost').pathname;
      if (pathname === '/api/index' && req.method === 'GET') {
        const body = Buffer.from(JSON.stringify({
          ok: true, stats_available: true, endpoints: []
        }));
        res.writeHead(200, {
          'content-type': 'application/json; charset=utf-8',
          'content-length': body.length,
          'connection': 'close',
        });
        res.end(body);
        return;
      }
      if (pathname === '/analytics/event' && req.method === 'POST') {
        const body = Buffer.from('{"ok":true}');
        res.writeHead(200, {
          'content-type': 'application/json; charset=utf-8',
          'content-length': body.length,
          'connection': 'close',
        });
        res.end(body);
        return;
      }
      let rel = decodeURIComponent(req.url.split('?')[0]);
      if (rel.endsWith('/')) rel += 'index.html';
      const f = join(ROOT, rel);
      if (!f.startsWith(ROOT)) { res.writeHead(403).end(); return; }
      const buf = await readFile(f);        // lire AVANT d'écrire l'en-tête,
      // 'content-length' explicite : sans lui la réponse part en codage
      // « chunked », et une troncature passe inaperçue — le navigateur rend
      // alors une page à moitié chargée, sans erreur. C'est ce qui faisait
      // échouer un test sur trois : le <script> inline était coupé.
      res.writeHead(200, {
        'content-type': MIME[extname(f)] || 'application/octet-stream',
        'content-length': buf.length,
        'connection': 'close',
      });
      res.end(buf);                         // sinon un 404 tenterait de le réécrire
    } catch { res.writeHead(404).end('404'); }
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;

  const profile = await mkdtemp(join(tmpdir(), 'cvtest-'));
  const url = `http://127.0.0.1:${port}${pagePath}`;
  // Port de débogage 0 : Chrome en choisit un libre et l'écrit dans
  // DevToolsActivePort. Un port fixe dialoguerait avec une instance restée
  // en vie d'un run précédent — et testerait donc l'ancienne page.
  const args = ['--headless', '--disable-gpu', '--no-sandbox', '--no-first-run',
    '--disable-extensions', '--hide-scrollbars', `--user-data-dir=${profile}`, '--remote-debugging-port=0'];
  if (opts.width && opts.height) args.push(`--window-size=${opts.width},${opts.height}`);
  // On démarre sur about:blank et on navigue APRÈS s'être attaché (voir plus
  // bas) : ouvrir directement la page laissait une chance sur trois de
  // s'attacher au contexte d'exécution du document initial, contexte que la
  // navigation détruit — les évaluations suivantes ne voyaient alors jamais
  // les variables de la page. Test intermittent garanti.
  const chrome = spawn(CHROME, [...args, 'about:blank'], { stdio: 'ignore' });

  let dbg = null;
  for (let i = 0; i < 60 && !dbg; i++) {
    await new Promise(r => setTimeout(r, 250));
    try { dbg = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0].trim(); } catch {}
  }
  if (!dbg) throw new Error('Chrome n’a pas publié son port de débogage');

  let target = null;
  for (let i = 0; i < 60 && !target; i++) {
    await new Promise(r => setTimeout(r, 250));
    try {
      const list = await (await fetch(`http://127.0.0.1:${dbg}/json/list`)).json();
      target = list.find(t => t.type === 'page');
    } catch {}
  }
  if (!target) throw new Error('Chrome n’a ouvert aucun onglet');

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let seq = 0; const pending = new Map(); const waiters = new Map();
  /* Contexte d'exécution courant de la page.
     Runtime.evaluate SANS contextId vise « le contexte par défaut », et ce
     défaut n'est pas toujours celui du document qui vient d'être chargé : on
     retombait par moments sur celui de la page initiale, où aucune variable de
     la page n'existe. Résultat : un test qui échouait une fois sur trois, en
     accusant la page. On suit donc explicitement le contexte par défaut de la
     frame principale et on l'adresse par son id. */
  let ctxId = null;
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id !== undefined) { const r = pending.get(m.id); if (r) { pending.delete(m.id); r(m); } return; }
    if (m.method === 'Runtime.executionContextCreated') {
      if (m.params.context.auxData && m.params.context.auxData.isDefault) ctxId = m.params.context.id;
    } else if (m.method === 'Runtime.executionContextDestroyed') {
      if (m.params.executionContextId === ctxId) ctxId = null;
    } else if (m.method === 'Runtime.executionContextsCleared') {
      ctxId = null;
    }
    const w = waiters.get(m.method); if (w) { waiters.delete(m.method); w(m.params); }
  };
  const send = (method, params) => new Promise(res => { const id = ++seq; pending.set(id, res); ws.send(JSON.stringify({ id, method, params })); });
  const once = method => new Promise(res => waiters.set(method, res));
  const ctxPret = async () => {
    for (let i = 0; i < 80 && ctxId === null; i++) await new Promise(r => setTimeout(r, 100));
    if (ctxId === null) throw new Error('aucun contexte d’exécution disponible');
    return ctxId;
  };

  // Attachés d'abord, on navigue ensuite et on attend l'événement `load`.
  await send('Page.enable');
  await send('Runtime.enable');
  const loaded = once('Page.loadEventFired');
  await send('Page.navigate', { url });
  await Promise.race([loaded, new Promise(r => setTimeout(r, 20000))]);
  await ctxPret();

  return {
    send,
    /* Évalue une expression et renvoie sa valeur (promesses attendues). */
    async eval(expression, awaitPromise = false) {
      const contextId = await ctxPret();
      const r = await send('Runtime.evaluate', { expression, awaitPromise, returnByValue: true, timeout: 180000, contextId });
      if (r?.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 500));
      return r?.result?.result?.value;
    },
    /* Attend qu'une expression devienne vraie (page encore en cours de script). */
    async waitFor(expression, tries = 60) {
      for (let i = 0; i < tries; i++) {
        if (await this.eval(expression)) return true;
        await new Promise(r => setTimeout(r, 250));
      }
      return false;
    },
    /* Imprime en respectant @page (preferCSSPageSize) et renvoie le PDF. */
    async pdf() {
      const r = await send('Page.printToPDF', { printBackground: true, preferCSSPageSize: true });
      return Buffer.from(r.result.data, 'base64');
    },
    async close() {
      try { ws.close(); } catch {}
      chrome.kill(); server.close();
      await rm(profile, { recursive: true, force: true }).catch(() => {});
    },
  };
}
