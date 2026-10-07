(function () {
  'use strict';
  const style = document.createElement('style');
  style.textContent = `
    .download-gate-overlay{position:fixed;inset:0;z-index:10000;display:grid;place-items:center;
      padding:18px;background:rgba(15,23,42,.68);backdrop-filter:blur(5px)}
    .download-gate-overlay[hidden]{display:none}
    .download-gate-card{width:min(100%,460px);max-height:calc(100vh - 36px);overflow:auto;
      padding:26px;background:var(--panel,#fff);color:var(--text,#1f2533);
      border:1px solid var(--line,#e3e7ef);border-radius:18px;
      box-shadow:0 24px 80px rgba(15,23,42,.28);font:inherit}
    .download-gate-card h2{margin:0 0 8px;font-size:21px;line-height:1.25}
    .download-gate-card p{margin:0 0 16px;color:var(--muted,#697386);font-size:14px;line-height:1.55}
    .download-gate-fields{display:grid;gap:10px}
    .download-gate-fields input{width:100%;padding:12px;border:1px solid var(--line,#e3e7ef);
      border-radius:10px;background:var(--panel-2,#f4f6fa);color:inherit;font:inherit}
    .download-gate-fields input:focus{outline:3px solid rgba(99,102,241,.22);border-color:#6366f1}
    .download-gate-error{color:#b91c1c!important;margin:10px 0 0!important}
    .download-gate-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:20px}
    .download-gate-actions button{min-height:42px;padding:9px 15px;border:1px solid var(--line,#e3e7ef);
      border-radius:10px;background:var(--panel-2,#f4f6fa);color:inherit;font:inherit;font-weight:650;cursor:pointer}
    .download-gate-actions .download-gate-submit{border-color:#4f46e5;background:#4f46e5;color:#fff}
    .download-gate-actions button:disabled{opacity:.6;cursor:wait}
    .download-gate-card :focus-visible{outline:3px solid rgba(99,102,241,.55);outline-offset:2px}
    @media(max-width:480px){.download-gate-card{padding:21px}.download-gate-actions{display:grid;grid-template-columns:1fr 1fr}
      .download-gate-actions button{justify-content:center}}
  `;
  document.head.appendChild(style);

  const overlay = document.createElement('div');
  overlay.id = 'downloadGate';
  overlay.className = 'download-gate-overlay';
  overlay.hidden = true;
  overlay.innerHTML = `
    <form class="download-gate-card" role="dialog" aria-modal="true"
      aria-labelledby="downloadGateTitle" aria-describedby="downloadGateDescription">
      <h2 id="downloadGateTitle">Un contact pour télécharger</h2>
      <p id="downloadGateDescription">Saisissez votre adresse email ou votre numéro de téléphone pour débloquer le téléchargement.</p>
      <div class="download-gate-fields">
        <input name="email" type="email" inputmode="email" autocomplete="email" maxlength="180"
          placeholder="Adresse email (facultatif si téléphone renseigné)" aria-label="Adresse email"/>
        <input name="phone" type="tel" inputmode="tel" autocomplete="tel" maxlength="24"
          placeholder="Téléphone (facultatif si email renseigné)" aria-label="Numéro de téléphone"/>
      </div>
      <p class="download-gate-error" role="alert" hidden></p>
      <div class="download-gate-actions">
        <button type="button" class="download-gate-cancel">Annuler</button>
        <button type="submit" class="download-gate-submit">Continuer</button>
      </div>
    </form>`;
  document.body.appendChild(overlay);

  const form = overlay.querySelector('form');
  const errorBox = overlay.querySelector('.download-gate-error');
  const submit = overlay.querySelector('.download-gate-submit');
  const emailInput = form.elements.email;
  const phoneInput = form.elements.phone;
  const apiBase = ['localhost', '127.0.0.1'].includes(location.hostname) && location.port !== '8788'
    ? 'http://' + location.hostname + ':8788'
    : '';
  function contactRequestId() {
    const key = 'cvstudio.download-contact-id';
    try {
      let id = sessionStorage.getItem(key);
      if (!id) {
        id = crypto.randomUUID();
        sessionStorage.setItem(key, id);
      }
      return id;
    } catch (error) {
      console.warn('Le navigateur ne peut pas préparer la demande de téléchargement.', error);
      return crypto.randomUUID();
    }
  }
  let pending = null;
  let returnFocus = null;
  let contactSaved = false;

  function close(continueDownload) {
    if (overlay.hidden) return;
    overlay.hidden = true;
    if (returnFocus && returnFocus.isConnected) returnFocus.focus();
    returnFocus = null;
    const callback = pending;
    pending = null;
    if (continueDownload && callback) callback();
  }

  overlay.querySelector('.download-gate-cancel').addEventListener('click', () => close(false));
  overlay.addEventListener('click', event => {
    if (event.target === overlay) close(false);
  });
  overlay.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      event.preventDefault();
      close(false);
    } else if (event.key === 'Tab') {
      const focusable = [...form.querySelectorAll('input:not(:disabled),button:not(:disabled)')];
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    errorBox.hidden = true;
    const email = emailInput.value.trim();
    const phone = phoneInput.value.trim();
    if (!email && !phone) {
      errorBox.textContent = 'Indiquez au moins une adresse email ou un numéro de téléphone.';
      errorBox.hidden = false;
      (emailInput.value ? phoneInput : emailInput).focus();
      return;
    }
    if (email && !emailInput.validity.valid) {
      errorBox.textContent = 'Vérifiez le format de votre adresse email.';
      errorBox.hidden = false;
      emailInput.focus();
      return;
    }
    const analytics = window.CVAnalytics;
    if (!analytics) {
      errorBox.textContent = 'Le formulaire doit être utilisé depuis le site en ligne ou son serveur local.';
      errorBox.hidden = false;
      return;
    }
    submit.disabled = true;
    submit.textContent = 'Enregistrement…';
    try {
      const response = await fetch(apiBase + '/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email, phone, source: pending && pending.source || 'cv',
          page: location.pathname.slice(0, 120), request_id: contactRequestId()
        })
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || 'Enregistrement impossible.');
      contactSaved = true;
      try { sessionStorage.setItem('cvstudio.download-contact', '1'); } catch (storageError) {
        console.warn('La validation est conservée pour cette page seulement.', storageError);
      }
      analytics.track('contact_submitted', '');
      close(true);
    } catch (error) {
      errorBox.textContent = error.message || 'Connexion impossible. Réessayez.';
      errorBox.hidden = false;
    } finally {
      submit.disabled = false;
      submit.textContent = 'Continuer';
    }
  });

  window.CVDownloadGate = {
    request(source, callback) {
      if (typeof callback !== 'function') throw new TypeError('Une action de téléchargement est requise.');
      let alreadyRegistered = contactSaved;
      try { alreadyRegistered = sessionStorage.getItem('cvstudio.download-contact') === '1'; } catch (error) {
        console.warn('Le navigateur ne peut pas mémoriser la validation du contact.', error);
      }
      if (alreadyRegistered) {
        window.CVAnalytics.track(source, '');
        callback();
        return;
      }
      pending = Object.assign(() => {
        window.CVAnalytics.track(source, '');
        callback();
      }, { source });
      returnFocus = document.activeElement;
      errorBox.hidden = true;
      overlay.hidden = false;
      emailInput.focus();
    }
  };
})();
