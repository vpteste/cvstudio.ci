(function () {
  'use strict';
  if (!/^https?:$/.test(location.protocol)) return;

  const sessionKey = 'cvstudio.analytics.session';
  let sessionId;
  try {
    sessionId = sessionStorage.getItem(sessionKey);
    if (!sessionId) {
      sessionId = crypto.randomUUID();
      sessionStorage.setItem(sessionKey, sessionId);
    }
  } catch (error) {
    console.warn('Statistiques désactivées pour cette session.', error);
    return;
  }

  const page = location.pathname.slice(0, 120);
  const apiBase = ['localhost', '127.0.0.1'].includes(location.hostname) && location.port !== '8788'
    ? 'http://' + location.hostname + ':8788'
    : '';
  function track(action, target) {
    const body = { action, target: target || '', page, session_id: sessionId };
    fetch(apiBase + '/analytics/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      keepalive: true
    }).then(response => {
      if (!response.ok) console.warn('Événement statistique non enregistré :', response.status);
    }).catch(error => console.warn('Statistiques momentanément indisponibles.', error));
  }

  window.CVAnalytics = { sessionId, track };
  track('page_view', '');

  document.addEventListener('click', event => {
    const element = event.target && event.target.closest
      ? event.target.closest('a[href],button,[role="button"]')
      : null;
    if (!element || element.disabled || element.closest('#downloadGate')) return;
    const action = element.matches('a[href]') ? 'navigation' : 'interface_action';
    const target = element.dataset.track || element.id || (action === 'navigation' ? 'link' : 'button');
    track(action, target);
  }, true);

  document.addEventListener('change', event => {
    const field = event.target;
    if (!field || !field.matches('input,select,textarea') || field.type === 'file' ||
        field.closest('#downloadGate')) return;
    track('form_change', field.dataset.path || field.id || 'form_field');
  }, true);
})();
