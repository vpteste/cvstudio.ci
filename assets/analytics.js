(function () {
  'use strict';
  if (!/^https?:$/.test(location.protocol)) return;

  const localApiBase = ['localhost', '127.0.0.1'].includes(location.hostname) && location.port !== '8788'
    ? 'http://' + location.hostname + ':8788'
    : '';
  let apiBase = '';
  async function health(base) {
    const response = await fetch(base + '/api/index');
    if (!response.ok) throw new Error('API indisponible (' + response.status + ').');
    return response.json();
  }

  const actions = new Set([
    'page_view', 'download_pdf', 'download_docx', 'download_json', 'letter_pdf', 'letter_docx'
  ]);
  const ready = (async () => {
    let status;
    try {
      status = await health('');
    } catch (error) {
      if (!localApiBase) throw error;
      apiBase = localApiBase;
      status = await health(apiBase);
    }
    return status.ok === true && status.stats_available === true;
  })();

  function track(action) {
    if (!actions.has(action)) return;
    ready.then(available => {
      if (!available) return;
      fetch(apiBase + '/analytics/event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
        keepalive: true
      }).then(response => {
        if (!response.ok) console.warn('Compteur non mis à jour :', response.status);
      }).catch(error => console.warn('Compteurs momentanément indisponibles.', error));
    }).catch(error => console.warn('Compteurs momentanément indisponibles.', error));
  }

  window.CVAnalytics = { ready, track };
  track('page_view');
})();
