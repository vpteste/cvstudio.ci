(function () {
  'use strict';
  window.CVDownloadGate = {
    request(action, callback) {
      if (typeof callback !== 'function') throw new TypeError('Une action de téléchargement est requise.');
      if (window.CVAnalytics) window.CVAnalytics.track(action, '');
      callback();
    }
  };
})();
