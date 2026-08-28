/* Configuration de l'assistant IA (Score ATS, réécriture, lettre de motivation).

   L'IA passe par un PROXY qui garde la clé Mistral côté serveur.
   -> Ne mettez JAMAIS la clé Mistral ici : ce fichier est PUBLIC.

   L'endpoint se déduit tout seul, parce que le proxy ne vit pas au même endroit
   selon le contexte :
     · en local  — le site est servi sur :8777 et le proxy tourne à part
                   (python3 server.py) sur :8788 ;
     · en ligne  — Vercel exécute api/index.py sur LE MÊME domaine que le site,
                   les URL /ai/… y sont routées par les rewrites de vercel.json.

   Activation en local :
     1. Copiez .env.example en .env et mettez votre clé : MISTRAL_API_KEY=...
     2. Lancez le proxy :  python3 server.py
   Activation en ligne :
     Vercel → Settings → Environment Variables → MISTRAL_API_KEY, puis redéployez.

   Pour DÉSACTIVER l'IA (le reste de l'app fonctionne, le Score bascule sur
   l'analyse instantanée hors-ligne), forcez la chaîne vide ci-dessous. */
window.CVAI = (function () {
  var FORCE = null;                     // ex. "" pour couper l'IA, ou l'URL d'un proxy tiers
  if (FORCE !== null) return { endpoint: FORCE };

  var h = location.hostname;
  var local = location.protocol === 'file:' ||
              h === 'localhost' || h === '127.0.0.1' || h === '::1' || h === '[::1]';

  // location.origin et non "" : app.html teste la vérité de l'endpoint pour
  // savoir si l'IA est disponible (aiReady()), une chaîne vide la désactiverait.
  return { endpoint: local ? 'http://localhost:8788' : location.origin };
})();
