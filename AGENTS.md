# AGENTS.md — CV Studio

Projet 100 % vanilla : aucun build, aucun `package.json`, aucune dépendance npm/pip obligatoire. Code, commentaires, UI et tests sont en français. `app.html` fait ~3 000 lignes (CSS + JS inline) : le chercher dedans, ne pas supposer une arborescence src/.

Deux outils, un site SEO : `app.html` (CV) + `lettre-de-motivation/` (lettre). Chaque outil est un fichier HTML autonome — même parti pris que `app.html`.

## Commandes

```bash
python3 -m http.server 8777     # servir le site — jamais file:// (assets/*.data.js bloqués)
./demarrer.command              # idem + ouvre le navigateur (double-cliquable dans le Finder)
python3 generate.py             # régénère les pages SEO depuis data/content.json
python3 tools/test-deploy.py    # contrat de déploiement Vercel (routes, secrets, API)
npx vercel --prod               # mise en ligne
python3 tools/test-site.py      # non-régression SEO + liens morts, toutes les pages (lit les fichiers, sans serveur)
node tools/test-docx.mjs        # export Word du CV — écrit .test-out/*.docx
node tools/test-modeles.mjs     # rendu des 11 modèles sous données hostiles + intégrité de `state`
node tools/test-lettre.mjs      # transfert du CV choisi + exports PDF/Word de la lettre
python3 server.py               # API locale sur :8788 (stats, admin, erreurs)
python3 tools/make-icons.py     # après tout changement de couleurs de marque
```

- `test-docx.mjs` requiert les outils macOS `textutil`, `xmllint`, `unzip` (il fait relire le .docx par le moteur OOXML d'Apple).
- `test-lettre.mjs` pilote **Google Chrome en headless** via CDP (`tools/lib-chrome.mjs`, WebSocket natif de Node, zéro dépendance npm) et vérifie le transfert du CV et les fichiers réellement produits.
- Trois pièges de `lib-chrome.mjs`, chacun ayant produit un test intermittent : le serveur doit envoyer un **`content-length`** explicite (sans lui la réponse part en « chunked » et une troncature rend une page à moitié chargée, sans erreur) ; il faut **s'attacher avant de naviguer** puis attendre `Page.loadEventFired` ; et `Runtime.evaluate` doit viser le **contextId** de la frame principale, suivi via `Runtime.executionContextCreated`. Ne pas utiliser `Emulation.setDeviceMetricsOverride` après coup — passer `{width, height}` à `open()`, qui pose `--window-size` au lancement.

## Architecture

- **`app.html`** = toute l'app dans un seul fichier, sections numérotées en commentaires. Sa `.topbar` porte `.topnav` (lien vers la lettre + landing). Toute nouvelle page-outil doit y être ajoutée, pas seulement dans `generate.py` (qui ne touche pas `app.html`). Un CV = `{v, id, name, template, design, data}` dans `localStorage['cvstudio.docs']` ; `normalizeState()` répare tout import ancien/incomplet. La lettre récupère le CV explicitement transmis par `?cv=<id>` sur la même origine.
- **Pagination A4** : `computePages()` mesure dans un `#measure` invisible et découpe en `.sheet` — l'aperçu écran et le PDF sont identiques par construction.
- **Site SEO** : `data/content.json` est la SOURCE UNIQUE. Ne jamais éditer à la main `cv-*/index.html`, `sitemap.xml`, `robots.txt`, `assets/jobs.data.js`, ni le HTML entre `<!--METIERS:START-->` et `<!--METIERS:END-->` dans `index.html` — tout est écrasé par `generate.py`. La vitrine des modèles vient de `MODELES` dans `generate.py` (source unique dont `tools/test-site.py` lit le compte). Un métier peut porter un champ facultatif `tpl` : sa page ouvre alors ce modèle (`app.html?job=…&tpl=…`). Les URL passées à `cta()` doivent contenir un `&` **brut** — `cta()` les passe déjà dans `esc()`.
- **`api/index.py` est la SOURCE UNIQUE des endpoints** (compteurs en mémoire, admin, `/log/error`). C'est à la fois l'API locale (`server.py`) et la fonction routée par Vercel — ne jamais dupliquer la logique dans `server.py`. La réécriture Vercel perd le chemin d'origine (la route passe en `?route=`, d'où `resolve()`). Seuls les compteurs de visites et d'exports sont gardés en mémoire ; ils sont temporaires, non partagés et peuvent être incomplets sur Vercel. Aucun contact ni historique n'est collecté. Mot de passe admin dans `.env` local ou `ADMIN_PASSWORD` dans Vercel, jamais dans le dépôt.
- **Tout fichier déployé est public** : ajouter une source, un outil ou un secret impose de vérifier `.vercelignore` (`tools/test-deploy.py` refait la liste des fichiers publiés et y cherche la clé).
- **Sélection au clic** (`selectBlock()` dans app.html) : cliquer un bloc de l'aperçu ouvre sa section et focalise son champ. Les chemins `data-edit` sont posés dans les **blocs de rendu partagés** — un modèle qui écrirait son propre markup pour une section (c'était le cas du profil de Champion) perd la sélection sans rien casser d'autre ; `tools/test-modeles.mjs` vérifie la couverture des onze modèles. Les champs du formulaire portent `data-path`, les `<details>` portent `data-group`. Surligner avec **`outline`, jamais `border`** : une bordure décalerait le contenu et changerait les coupures de page au survol.
- **`cvPageHTML()` aligne temporairement `state`** sur le design demandé (pour rendre la vignette d'un autre CV que le CV courant) et le restaure dans un `finally`. Ce `finally` n'est pas décoratif : sans lui, la moindre exception d'un modèle laissait `state` figé sur `{design}` — plus de `state.data`, l'autosave écrasait le CV et chaque frappe suivante relançait l'erreur. Un modèle inconnu retombe sur Moderne, même politique que `docxDocumentVisual()`. `tools/test-modeles.mjs` épingle les deux.
- Les blocs de rendu partagés **filtrent les entrées nulles** (`.filter(Boolean)`) : un JSON importé peut contenir des trous que `normalizeState` n'a pas vus.
- **Modèles de CV (11)** : ajouter un modèle = une fonction `RENDER[id](data)` + un bloc CSS `.tpl-id` + une entrée dans `TEMPLATES`, en réutilisant les blocs de contenu partagés (`expBlock`, `skillsBars`, `skillsBullets`…). Quatre contrats faciles à oublier :
  - un modèle à aplat (bandeau, page sombre, cadre) doit déclarer `SIDEBAR_TPL[id] = accent => valeur CSS background`, **identique** au `background` de son bloc `.tpl-id` — sinon le fond s'arrête au bas du texte au lieu du bas de la feuille ;
  - les teintes `--tint`/`--tint-2`/`--soft` sont calculées en JS (`tint()` dans `cvPageHTML()`), **pas** avec `color-mix`, pour que `SIDEBAR_TPL` produise exactement la même couleur ;
  - `.tpl-champion` peint son cadre hors feuille seulement : la règle `.sheet .tpl-champion, #measure .tpl-champion` remet le modèle à plat. **`#measure` doit toujours recevoir le même traitement que `.sheet`**, sinon la mesure de pagination se décale et toutes les coupes sont fausses.
  - **chaque modèle a SON constructeur dans `DOCX_TPL`** — pas d'alias. Un premier jet aliasait les cinq nouveaux vers les constructeurs existants : l'écran montrait « Athlète » et le .docx sortait « Prestige ». `tools/test-docx.mjs` épingle maintenant la signature de chacun des onze (largeurs de `gridCol`, aplats, `pgBorders`) et exige onze rendus distincts.
  - fond de page sombre : `<w:background>` exige `<w:displayBackgroundShape/>` dans settings.xml, et Word ne l'IMPRIME pas par défaut — le noir imprimé doit venir de cellules remplies couvrant la page (`wTable(..., {height:PG_H})`).
  - jamais de `wGrid2()` **dans** une cellule : cela crée un tableau imbriqué, que plusieurs lecteurs rendent de travers (le test le refuse).
- **`assets/file-links.js`** : hors serveur HTTP, un lien se terminant par `/` ouvre l'index du dossier (aucun navigateur ne sert `index.html` tout seul en `file://`) — c'est la « page noire » que voit qui double-clique un fichier. Le script réécrit ces liens **au clic**, conserve les paramètres (dont l'ID du CV transmis à la lettre), et agit seulement si `location.protocol === 'file:'`. Les `href` restent en URL propres : canoniques et sitemap déclarent la forme avec barre oblique finale. **Toute nouvelle page doit charger ce script** — `tools/test-site.py` le vérifie.
- **`assets/zip.js`** : écriture ZIP « store » (historique de la lettre, conservé pour référence). `app.html` garde sa propre copie `zipStore()` : `test-docx.mjs` extrait l'export du CV comme un bloc contigu entre deux marqueurs, et déplacer `zipStore()` hors de ce bloc casserait le test.

## Export Word (.docx) — section « 15b » de app.html

- OOXML écrit à la main dans un ZIP « store » non compressé, zéro dépendance.
- `tools/test-docx.mjs` extrait le code entre le marqueur `15b. EXPORT .DOCX` et `function resetSample(){` : garder le code d'export dans ces limites, sinon le test n'extrait plus rien.
- Deux variantes : `docxDocument()` (ATS mono-colonne, sans tableau) et `docxDocumentVisual()` + `DOCX_TPL` (fidèle au modèle, tableaux).
- Contraintes Word non négociables (vérifiées par les tests) : pas de tableaux imbriqués, un paragraphe obligatoire entre deux `<w:tbl>` (le `GAP`), le corps ne doit pas se terminer par un tableau, largeurs en pourcentage + `gridCol` exacts.
- Les tests épinglent des mesures précises (ex. `<w:gridCol w:w="3969"/>` = les 70 mm du modèle Moderne) : modifier la géométrie d'un modèle impose de mettre à jour `tools/test-docx.mjs`.

## Vérification après modification

- `app.html` (surtout l'export Word) → `node tools/test-docx.mjs`
- `data/content.json`, `generate.py`, `index.html` → `python3 generate.py` puis `python3 tools/test-site.py`
- `api/index.py`, `server.py`, `vercel.json`, `.vercelignore` → `python3 tools/test-deploy.py`
- `lettre-de-motivation/index.html` → `node tools/test-lettre.mjs`
- toute nouvelle page à la racine → `python3 generate.py` (sitemap) puis `python3 tools/test-site.py`

Le dossier `models/` contient les maquettes de référence (images) dont sont tirés cinq modèles de CV. Il n'est pas publié : aucune page ne le référence.
