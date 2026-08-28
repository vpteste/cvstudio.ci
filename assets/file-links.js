/* ============================================================
   file-links.js — rend la navigation utilisable quand le site est ouvert
   DEPUIS LE DISQUE (double-clic sur un fichier, protocole file://).

   Le problème : les liens internes pointent vers « carte-de-visite/ », sans
   « index.html ». C'est ce qu'il faut pour le SEO — les URL canoniques et le
   sitemap déclarent la forme avec barre oblique finale, et doubler les URL
   (avec et sans /index.html) dilue le maillage. Mais hors serveur HTTP, aucun
   navigateur ne sert index.html tout seul : Chrome affiche l'index du dossier,
   une page noire qui n'a rien à voir avec le site.

   Le correctif ne s'applique QUE si location.protocol vaut 'file:'. Servi en
   HTTP — le mode normal, cf. README — ce fichier ne fait strictement rien.

   Interception au clic plutôt que réécriture au chargement : l'éditeur de CV
   reconstruit son DOM en permanence, des liens réécrits une fois seraient
   perdus au premier rendu.
   ============================================================ */
(function () {
  'use strict';
  if (location.protocol !== 'file:') return;

  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || a.target === '_blank' || a.hasAttribute('download')) return;

    const href = a.getAttribute('href');
    // on ne touche ni aux URL absolues (http:, mailto:, data:…) ni aux ancres
    if (!href || href.charAt(0) === '#' || /^[a-z][a-z0-9+.-]*:/i.test(href) || href.slice(0, 2) === '//') return;

    const [path, hash] = href.split('#');
    if (path.slice(-1) !== '/') return;          // seuls les liens « dossier » posent problème
    e.preventDefault();
    location.href = path + 'index.html' + (hash ? '#' + hash : '');
  }, true);
})();
