# CV Studio — Créateur de CV professionnel + moteur SEO

Deux briques :
1. **Trois outils**, tous 100 % dans le navigateur, sans inscription :
   - `app.html` — création de CV : édition à gauche, aperçu A4 temps réel à
     droite, pagination réelle, export PDF et Word. **11 modèles.**
   - `lettre-de-motivation/` — lettre guidée par la structure **vous · moi ·
     nous**, jauge de longueur, export PDF et Word.
   - `carte-de-visite/` — carte 85 × 55 mm recto-verso avec QR code, export PDF
     pour l'imprimeur (fonds perdus) et planche A4 de 10 cartes.
2. **Un site SEO statique** (`index.html` + pages générées) : une page par
   mot-clé / métier, pour attirer du trafic Google et le convertir vers les outils.

## Démarrer

**Le plus simple : double-cliquez `demarrer.command`.** Il lance le serveur et
ouvre le navigateur.

En ligne de commande :

```bash
cd "cv-creator" && python3 -m http.server 8777
# puis http://localhost:8777/  (landing)  ·  /app.html  (le générateur de CV)
#      /carte-de-visite/  ·  /lettre-de-motivation/  ·  /analyser-cv/
```

> **Servez toujours via HTTP.** En `file://`, le chargement des fichiers
> `assets/*.data.js` n'est garanti par aucun navigateur.
>
> Le site reste néanmoins navigable en `file://` grâce à
> `assets/file-links.js` : hors serveur, un lien vers `carte-de-visite/`
> ouvrirait l'**index du dossier** — une page noire sans rapport avec le site —
> parce qu'aucun navigateur ne sert `index.html` tout seul hors HTTP. Le script
> réécrit ces liens au clic, et **uniquement** quand `location.protocol` vaut
> `file:`. Les `href` du HTML restent en URL propres : les canoniques et le
> sitemap déclarent la forme avec barre oblique finale, et doubler les URL
> diluerait le maillage interne.

## Arborescence

```
cv-creator/
├── demarrer.command        lance le serveur + ouvre le navigateur (double-clic)
├── index.html              landing marketing (promesse ATS + 3 CTA + annuaire)
├── app.html                l'app de création de CV (+ import, score, IA, funnel ?job=)
├── analyser-cv/index.html  outil gratuit : analyseur de CV ATS (entonnoir)
├── lettre-de-motivation/   générateur de lettre (structure guidée, PDF + Word)
├── carte-de-visite/        générateur de carte de visite (QR, PDF, planche A4)
├── vercel.json             hébergement : routes de l'API, cache, en-têtes
├── .vercelignore           ce qui NE part PAS en ligne (tout déployé est public)
├── api/index.py            endpoints IA — SOURCE UNIQUE, serverless en ligne
├── server.py               la même API en local (importe api/index.py) sur :8788
├── generate.py             génère les pages SEO depuis data/content.json
├── data/content.json       SOURCE UNIQUE du contenu SEO (métiers + guides)
├── tools/
│   ├── make-icons.py       (re)génère favicon + image OG depuis la charte
│   ├── test-site.py        contrôle SEO/liens morts de toutes les pages
│   ├── test-deploy.py      contrat Vercel : routes, secrets non publiés, API
│   ├── test-docx.mjs       export Word du CV (ZIP + XML + relecture par Word)
│   ├── test-modeles.mjs    robustesse du rendu des 11 modèles + intégrité de l'état
│   ├── test-lettre.mjs     lettre : PDF 1 page, jauge, .docx relu par Word
│   ├── test-carte.mjs      carte : géométrie réelle des PDF produits
│   ├── test-qr.mjs         QR relu par un vrai décodeur (BarcodeDetector)
│   └── lib-chrome.mjs      pilote Chrome headless partagé par ces trois tests
├── assets/
│   ├── favicon.svg/.ico/-32/-180/-512.png, og.png   (générés par make-icons.py)
│   ├── site.css            style des pages SEO / landing
│   ├── score.js            scorer de CV (heuristique, local, sans IA)
│   ├── qr.js               encodeur QR autonome (SVG) — voir tools/test-qr.mjs
│   ├── zip.js              écriture ZIP « store » (paquet .docx de la lettre)
│   ├── file-links.js       rend les liens « dossier/ » suivables en file://
│   ├── config.js           active l'IA (endpoint du proxy — jamais la clé !)
│   ├── jobs.data.js        (généré) pré-remplissage de l'app par métier
│   └── signature.data.js   (généré) signature virale + QR code
├── <slug>/index.html       (généré) une page par métier et par guide
├── sitemap.xml, robots.txt (générés)
└── README.md
```

## Moteur SEO — ajouter / modifier des pages

Tout le contenu vit dans **`data/content.json`** (jamais dans le HTML généré).

```bash
# 1. éditez data/content.json (ajoutez un métier ou un guide)
# 2. régénérez tout :
python3 generate.py
```

> **L'annuaire de la landing est du HTML statique.** `generate.py` écrit les
> cartes métier, les modèles, les guides et les liens de pied de page
> directement dans `index.html`, entre des marqueurs `<!--METIERS:START-->` …
> `<!--METIERS:END-->`. Ces listes étaient auparavant construites en JavaScript
> depuis un `site.data.js` : elles disparaissaient dès que le script ne
> s'exécutait pas (page ouverte en `file://`, erreur JS), et avec elles **tout
> le maillage interne** du site. `tools/test-site.py` vérifie zone par zone que
> chaque page reste liée.

- **Ajouter un métier** → un objet dans `metiers[]` (slug, titre, résumé exemple,
  compétences, conseils ATS, FAQ…). Il apparaît automatiquement sur la landing,
  dans le footer, le sitemap, et alimente le bouton « Créer ce CV » (`?job=`).
- **Ajouter un guide** → un objet dans `topics[]`.
- **Changer le domaine** (pour le sitemap et les URL canoniques) → `site.domain`
  dans `content.json`, puis `python3 generate.py`. *(placeholder actuel :
  `cvstudio.ci`).*
- **Principe qualité** : chaque page porte un contenu réel et unique (exemple de
  résumé, compétences, conseils ATS, FAQ) — pas un simple mot-clé permuté, comme
  le recommande Google (« helpful content »).

## Assistant IA (Mistral) — activation

L'IA est **optionnelle** : sans elle, tout fonctionne (le **score de CV** et
l'**analyseur ATS** sont 100 % locaux, sans clé, sans envoi de données). L'IA
sert à la **génération** (réécriture d'expérience, lettre de motivation).

> 🔒 **La clé API Mistral ne doit JAMAIS être dans le code client.** Elle reste
> côté serveur, dans le proxy `server.py`.

```bash
export MISTRAL_API_KEY="votre_clé_mistral"   # jamais commitée, jamais côté client
python3 server.py                            # → http://localhost:8788
```

Puis activez-la côté front en éditant **`assets/config.js`** :

```js
window.CVAI = { endpoint: … };  // déduit tout seul : localhost en local, location.origin en ligne
```

- Modèle par défaut : `mistral-large-latest` (surchargeable via `MISTRAL_MODEL`).
- Sans clé / sans proxy, les boutons IA affichent un message clair et le reste
  de l'app continue de marcher.

## Outils gratuits (aimants à trafic + entonnoir)

- **Analyseur de CV ATS** (`/analyser-cv/`) : l'utilisateur colle son CV → score
  ATS + points faibles (calcul **local**, `assets/score.js`) → bouton
  « Améliorer mon CV avec l'IA » qui envoie vers l'éditeur avec le CV pré-chargé.
- **Score du CV** dans l'éditeur (bouton « 📊 Score ») : ATS, lisibilité,
  expérience, compétences, présentation + score global et recommandations.
- **Lettre de motivation IA** (bouton « ✉ Lettre IA ») : poste + entreprise +
  offre → lettre générée, modifiable et téléchargeable.

## Le funnel de conversion

`/<métier>/` (page SEO) → bouton **« Créer ce CV »** → `app.html?job=<slug>` →
l'app démarre **pré-remplie** (titre, résumé, compétences du métier). L'app lit
aussi `?import=1` (ouvre l'import de l'ancien CV).

## Assistant IA (Score ATS, réécriture, lettre) — Mistral

L'app marche **sans IA** : le **Score de CV** utilise alors une analyse
instantanée hors-ligne (`assets/score.js`, aucune donnée envoyée). Pour activer
l'IA (score affiné, réécriture d'expérience, lettre de motivation), on passe par
un **proxy** qui garde la clé Mistral côté serveur.

> ⚠️ **Où mettre la clé Mistral ?** Dans un fichier **`.env`** à côté de
> `server.py` — **jamais** dans le navigateur ni dans `assets/config.js` (public).

```bash
# 1. Récupérez une clé sur https://console.mistral.ai (API Keys)
cp .env.example .env          # puis éditez .env : MISTRAL_API_KEY=votre_cle
# 2. Lancez le proxy IA (aucune dépendance, bibliothèque standard Python)
python3 server.py             # écoute sur http://localhost:8788
# 3. Servez le site (autre terminal) et ouvrez l'app
python3 -m http.server 8777   # http://localhost:8777/app.html
```

- `assets/config.js` pointe déjà sur `http://localhost:8788`. Laissez la chaîne
  vide (`""`) pour **désactiver** l'IA (le Score bascule sur l'analyse instantanée).
- Endpoints du proxy : `/ai/score` (note ATS + recommandations), `/ai/rewrite`
  (réécrit une expérience), `/ai/cover-letter` (lettre de motivation).
- **Repli propre** : si le proxy est injoignable ou la clé absente, le Score
  affiche le résultat instantané et un message explicite ; l'app ne casse jamais.
- **Production** : déployez `server.py` (ou une fonction serverless équivalente),
  mettez son URL dans `config.js`, et fixez `CORS_ORIGIN` sur votre domaine.

## Déploiement sur Vercel

Le site est statique, mais l'IA a besoin d'un serveur — la clé Mistral ne doit
jamais atteindre le navigateur. Sur Vercel, ce serveur est la fonction
`api/index.py`, et c'est **le même fichier** que celui qu'utilise `server.py` en
local : une seule implémentation, deux portes d'entrée. `tools/test-deploy.py`
refuse toute divergence.

### Mise en ligne

```bash
npx vercel login
npx vercel                      # aperçu, pour vérifier
npx vercel --prod               # production
```

Puis, une seule fois, la clé côté serveur :

```bash
npx vercel env add MISTRAL_API_KEY production
npx vercel --prod               # une variable n'atteint pas un déploiement déjà en place
```

Avant chaque mise en ligne :

```bash
python3 generate.py && python3 tools/test-site.py && python3 tools/test-deploy.py
```

### Ce que Vercel change, et comment c'est traité

| Contrainte de la plateforme | Traitement |
|---|---|
| Pas de `server.py` qui tourne | `api/index.py` — fonction serverless ; les URL `/ai/…`, `/lead`, `/log/error` y arrivent par les `rewrites` de `vercel.json`, qui passent la route en `?route=` (le chemin d'origine est perdu à la réécriture, d'où `resolve()`). |
| L'endpoint IA était codé en dur sur `localhost:8788` | `assets/config.js` le déduit : `localhost`/`file://` → le proxy local, sinon `location.origin`. Il renvoie `location.origin` et **non** `""`, parce que `aiReady()` teste la vérité de l'endpoint — une chaîne vide couperait l'IA. |
| 10 s de temps d'exécution par défaut | `maxDuration: 60` dans `vercel.json` — une lettre de motivation prend 10 à 20 s. Le timeout interne vers Mistral est à 45 s, pour rendre une erreur JSON plutôt que de se faire tuer par la plateforme. |
| Disque en **lecture seule** | `leads.jsonl` / `errors.jsonl` ne peuvent pas exister en ligne. Les deux endpoints écrivent sur la sortie standard (Observability → Logs). Voir la limite ci-dessous. |
| Tout fichier déployé est **public** | `.vercelignore` écarte `.env`, `server.py`, `generate.py`, `data/`, `tools/`, `models/` (15 Mo de maquettes) et les `.md`. `tools/test-deploy.py` vérifie en plus qu'aucun fichier publié ne contient la clé. |
| L'API est ouverte sur Internet | Plus de `CORS_ORIGIN=*` par défaut : sans en-tête CORS, aucun site tiers ne peut consommer votre quota Mistral depuis un navigateur. Un appel direct (curl) reste possible — surveillez la consommation sur console.mistral.ai. |

### Limite assumée : les inscriptions email

`/lead` ne peut plus rien écrire sur disque. En ligne, une inscription part dans
les logs de la fonction, qui sont **purgés**. Pour la conserver, renseignez
`LEAD_WEBHOOK_URL` (Formspree, Zapier, Make, webhook Slack…) : chaque
inscription y est recopiée. Sans ce réglage, considérez la capture d'email
comme inactive en production.

### Le domaine

Les canoniques, le sitemap et `robots.txt` déclarent `site.domain` de
`data/content.json`, aujourd'hui **cvstudio.ci**. Tant que ce domaine n'est pas
rattaché au projet Vercel, les pages servies sur `*.vercel.app` se déclarent
canoniques sur une adresse qui ne répond pas — Google ne les indexera pas.
Pour publier sous une autre adresse : changez `site.domain`, puis
`python3 generate.py` (35 pages, sitemap et robots sont réécrits d'un coup).

## Fonctionnalités de l'app (v2)

- **Page de garde** avec galerie de 5 modèles pro (vraies mini-previews) **+
  section « Mes CV »** listant les CV enregistrés (ouvrir / dupliquer / supprimer).
- **Éditeur 2 panneaux** : formulaire à gauche, feuille A4 à droite, live.
- **Import « mon ancien CV »** : collez le texte de votre CV → détection auto
  (nom, email, téléphone, LinkedIn) + pré-remplissage.
- Sections : identité + photo, contact/liens, profil, expériences, formation,
  compétences (niveaux 1–5), langues, centres d'intérêt.
- **Design** : couleur d'accent, police, taille du texte, espacement, photo
  ronde, affichage/masquage de sections, changement de modèle **sans perdre les
  données**.
- **Pagination A4 réelle** : le contenu est mesuré et découpé en **feuilles A4
  distinctes** (coupe toujours sur une frontière de bloc — jamais au milieu
  d'une entrée), barre latérale colorée **continue** sur chaque page, marges
  hautes/basses uniformes.
- **Export PDF** sans **aucun en-tête/pied de navigateur** (`@page{margin:0}`),
  couleurs conservées, une feuille = une page.
- **Multi-CV** : gérez plusieurs CV nommés, tout est enregistré localement.
- **Annuler / Rétablir** (`Ctrl/Cmd+Z`, `Ctrl/Cmd+Maj+Z`), historique 60 pas.
- **Photo optimisée** à l'upload (redimensionnée ≤ 480 px, JPEG) pour ne pas
  saturer le stockage ; **sauvegarde protégée** (alerte si stockage plein).
- **Import robuste & versionné** (`normalizeState`) : tout JSON incomplet ou
  d'une ancienne version est réparé avec des valeurs par défaut, sans planter.
- **Garde-fou longueur** : alerte visuelle si le CV dépasse 2 pages.
- **Responsive mobile** (bascule Éditer / Aperçu) + **accessibilité** (aria-labels).

- **Import / export JSON**, réordonnancement des entrées (↑/↓), zoom de l'aperçu.

## Fonctionnement interne de l'app

- Un CV = un objet `state` = `{ v, id, name, template, design, data }`.
  Tous les CV sont stockés dans `localStorage['cvstudio.docs']` (indexés par id),
  le CV courant dans `cvstudio.current`. `normalizeState()` répare/valide toute
  entrée avant usage.
- À chaque frappe → `setPath()` met à jour l'état → `renderPreview()` re-rend
  l'aperçu (le focus reste dans le champ) → `pushHistory()` (undo) → autosave.
- Chaque modèle est une **fonction de rendu** `RENDER[id](data)` qui renvoie
  l'intérieur de `.cv-page`. Le style est piloté par deux variables :
  `--accent` (couleur) et `font-family` (police), injectées inline.
- **Pagination** : `computePages()` rend le CV dans un mesureur invisible
  (`#measure`), relève les frontières de blocs sûres, puis découpe en feuilles ;
  `renderPreview()` crée une `.sheet` par page (contenu complet translaté +
  `overflow:hidden`), ce qui garantit un rendu écran = rendu PDF identique.
- Blocs de contenu **partagés** entre modèles (`expBlock`, `eduBlock`,
  `skillsBars`, `langBlock`, …) → ajouter un modèle = écrire une fonction de
  rendu + un bloc CSS `.tpl-xxx`.

## Exports : PDF et Word

- **PDF** (`⤓ PDF`) : impression navigateur, pagination A4 réelle, sans en-tête.
  C'est l'export « fidèle au modèle ».
- **Word** (`⤓ Word`) : vrai `.docx` écrit à la main (ZIP + OOXML, **aucune
  dépendance**, voir section 15b de `app.html`). Le bouton propose **deux
  versions**, parce qu'aucune ne peut être bonne sur les deux tableaux :

  | Version | Rendu | Pour qui |
  |---|---|---|
  | **Fidèle au modèle** | Colonne latérale colorée, photo, barres de compétences — comme à l'écran | Envoi direct à un recruteur (email, main propre) |
  | **Version ATS** (`_ATS.docx`) | Une seule colonne, aucun tableau | Dépôt sur une plateforme de recrutement |

  La version fidèle repose sur un **tableau à deux cellules** — la seule façon
  de faire deux colonnes en Word — et c'est précisément ce que les ATS lisent
  mal : beaucoup parcourent un tableau ligne par ligne et entremêlent la barre
  latérale avec le texte principal. D'où le choix laissé à l'utilisateur plutôt
  qu'un compromis imposé.

  Les polices du studio sont remplacées par leur équivalent installé partout
  (Inter/Poppins → Calibri, Lora → Georgia), et le document déclare
  `compatibilityMode 15` pour que Word ne l'ouvre pas en « Mode de compatibilité ».
- **La photo est reprise** dans le `.docx` si le CV en a une : insérée **en
  ligne** (jamais flottante, jamais dans un cadre — c'est la forme la moins
  gênante pour l'analyse automatique). Le réglage **« Photo ronde »** du panneau
  Design est respecté : géométrie `ellipse` + recadrage carré centré de la source
  (`a:srcRect`), sans quoi le visage serait ovalisé. Une photo illisible n'échoue
  pas l'export : le CV part sans elle et l'incident est journalisé.

  > L'aperçu Quick Look de macOS ignore `prstGeom` et affiche la photo
  > rectangulaire : le rendu rond ne se vérifie que dans Word ou LibreOffice.
  *(Rappel : certains ATS anglo-saxons ignorent les images ; en France et en
  Afrique de l'Ouest la photo reste attendue par les recruteurs.)*
- **Navigateurs intégrés** (WhatsApp, Facebook, Instagram…) : ils n'implémentent
  pas `window.print()`. Le bouton PDF y détecte le cas et propose d'ouvrir le
  lien dans Chrome/Safari, ou de replier sur l'export Word. Point important :
  le lien de parrainage circule justement sur WhatsApp.

## Sélection au clic : cliquer l'aperçu pour éditer

Le formulaire compte une dizaine de sections repliables. Retrouver « la
troisième puce de la deuxième expérience » demandait de dérouler et de
chercher. Désormais on **clique l'élément sur la feuille A4** : sa section
s'ouvre, la vue défile jusqu'au champ, et celui-ci prend le focus. Le bloc
cliqué reste surligné.

- Les chemins sont posés par les **blocs de rendu partagés** (`data-edit="experiences.2.role"`),
  pas modèle par modèle : les onze en héritent d'un coup. Le nom et l'intitulé
  sont écrits par chaque modèle — ils sont reconnus à leur classe (`.cv-name`,
  `.cv-title`) plutôt que d'imposer onze retouches.
- Le surlignage utilise **`outline`, jamais `border`** : l'outline ne prend pas
  de place dans le flux, donc la mesure de pagination reste identique au pixel.
  Un encadrement qui décale le contenu ferait bouger les coupures de page au
  simple survol.
- Le contenu est **dupliqué sur chaque feuille** (la pagination translate le
  même bloc) : toutes les occurrences sont marquées, sinon un bloc à cheval sur
  deux pages ne serait surligné que sur l'une d'elles.
- Le champ reçoit le focus **sans `select()`** : tout sélectionner ferait
  effacer la valeur à la première frappe, alors qu'on vient le plus souvent
  corriger un détail.
- Sur mobile, l'aperçu occupe tout l'écran : un clic bascule sur le formulaire.
- Ni survol ni sélection à l'impression.

Le générateur de carte de visite a le même geste : cliquer une zone de la carte
ouvre l'onglet « Contenu » et focalise son champ.

## Les 11 modèles de CV

Six modèles d'origine (Moderne, Élégant, Classique, Minimal, Compact, Prestige)
et cinq repris des maquettes du dossier `models/` :

| Modèle | Mise en page | Pour qui |
|---|---|---|
| **Contraste** | Colonne teintée à droite, photo ronde | administratif, secrétariat |
| **Duo** | Colonne colorée pleine hauteur, titres soulignés | secrétariat, assistanat |
| **Athlète** | Page sombre, accents vifs, frise verticale | footballeur, sportifs |
| **Champion** | Cadre coloré plein cadre, en-tête encadré | sportifs, profils jeunes |
| **Coach** | Colonne grise, dates en couleur, barres | coach sportif, préparateur |

Ajouter un modèle = une fonction `RENDER[id]` + un bloc CSS `.tpl-id` + une
entrée dans `TEMPLATES` (section 1 de `app.html`). Deux points de vigilance :

- **Fond pleine hauteur.** Le contenu d'un CV s'arrête souvent avant le bas de
  la feuille. Un modèle à aplat (bandeau latéral, page sombre, cadre) doit donc
  déclarer une entrée dans `SIDEBAR_TPL` : une fonction `accent -> valeur CSS
  background` appliquée à la `.sheet`, qui doit reproduire **à l'identique** le
  `background` du bloc `.tpl-id`, sinon une lisière blanche apparaît en bas.
- **Teintes dérivées.** `--tint`, `--tint-2` et `--soft` sont calculées en JS
  dans `cvPageHTML()` (et non avec `color-mix`), précisément pour que
  `SIDEBAR_TPL` puisse produire la même couleur. Une seule source de vérité.

### L'export Word doit suivre le modèle

Les onze modèles ont chacun **leur** constructeur OOXML dans `DOCX_TPL`. Un
premier jet s'était contenté d'alias vers les constructeurs existants : à
l'écran on voyait « Athlète » (page sombre, deux colonnes), et le `.docx`
sortait la mise en page de « Prestige ». Le bouton promet *fidèle au modèle* —
il doit l'être. `tools/test-docx.mjs` épingle désormais, pour chacun des onze,
ce qui le distingue (colonne à gauche ou à droite, fond, cadre) et vérifie que
les onze rendus sont réellement différents.

Deux points valent d'être connus :

- **Page sombre (Athlète)** : Word peint `<w:background>` uniquement si
  `settings.xml` porte `<w:displayBackgroundShape/>` — et il ne l'**imprime**
  que si l'option « imprimer les couleurs d'arrière-plan » est cochée, ce
  qu'elle n'est pas par défaut. Le noir imprimé vient donc des **cellules** :
  une seule table, haute d'une page entière, qui couvre la feuille dans tous
  les cas. C'est aussi pourquoi l'identité vit dans la colonne de gauche
  plutôt que dans un bandeau séparé — deux tables ne peuvent pas se partager
  une hauteur de page.
- **Cadre (Champion)** : `<w:pgBorders>`, avec `w:sz` en huitièmes de point
  plafonné à 96, soit ~4,2 mm — le cadre le plus épais que Word accepte.
  *(L'aperçu Quick Look de macOS ne dessine ni les bordures de page ni celles
  de tableau : le cadre ne se vérifie que dans Word ou LibreOffice.)*

## Carte de visite (`carte-de-visite/`)

Éditeur + aperçu recto-verso à l'échelle réelle, 4 modèles, et trois sorties :

- **PDF 85 × 55 mm**, une face par page — le format standard des porte-cartes.
- **Fonds perdus 3 mm** (91 × 61 mm) pour l'imprimeur : les aplats débordent du
  format final, ce qui évite le liseré blanc si la coupe dérive. Le texte, lui,
  n'est jamais mis à l'échelle — seuls les fonds le sont.
- **Planche A4 de 10 cartes** à découper soi-même.

Deux formats d'impression ne peuvent pas coexister (`@page` ne se conditionne
pas par une classe) : `printMode()` réécrit la règle `@page` et désactive la
feuille inutile avant `window.print()`.

Le bouton **« Reprendre les infos de mon CV »** lit `localStorage['cvstudio.docs']`
et reprend le CV le plus récent.

### Le QR code (`assets/qr.js`)

Encodeur écrit à la main — mode octet, versions 1 à 10, niveaux L/M/Q/H — dans
la même logique que l'écriture OOXML du CV : aucune dépendance. La sortie est du
**SVG** et non un PNG : à 13 mm de côté, un bitmap redimensionné par l'imprimeur
devient illisible.

Le QR part à l'impression : une erreur ne se verrait qu'après le tirage. Il est
donc vérifié à trois niveaux par `node tools/test-qr.mjs` :

1. **39 charges utiles relues par un vrai décodeur** (`BarcodeDetector` de
   Chrome, adossé au framework Vision de macOS) — URL, MECARD, accents UTF-8,
   toutes les versions de 1 à 10 ;
2. **refus explicite au-delà de la capacité** plutôt qu'un code faux ;
3. **vecteur de non-régression Reed-Solomon** vérifié contre `segno`.

Le code est **toujours sombre sur clair**, y compris sur les modèles de carte
sombres (d'où la plaque blanche `.qr`) : un QR inversé n'est pas fiable au scan.

## Lettre de motivation (`lettre-de-motivation/`)

L'éditeur impose l'ordre qui fonctionne — **accroche · vous · moi · nous** —
avec un bloc par temps et son mode d'emploi. Une case permet de repasser en
texte libre.

- **Jauge de longueur** : elle mesure la hauteur réelle du dernier bloc, pas le
  nombre de mots, et passe à l'orange puis au rouge **avant** que la deuxième
  page n'apparaisse. Une lettre qui déborde perd sa demande d'entretien, qui est
  toujours en fin de texte.
- **La lettre n'est pas paginée** : elle doit tenir sur une page, et l'outil
  prévient au lieu de créer une seconde feuille.
- **Export Word** : OOXML linéaire (aucun tableau, donc lisible par un ATS),
  empaqueté avec `assets/zip.js`.
- **Reprise du CV** : coordonnées **et charte** (couleur d'accent, police), pour
  que les deux documents se répondent sur le bureau du recruteur.
- `?job=<métier>` pré-remplit le poste et la couleur depuis `assets/jobs.data.js` :
  c'est le lien posé par chaque page métier.

## Icônes et aperçu de partage

`assets/favicon.*` et `assets/og.png` (1200×630, affichée par WhatsApp /
LinkedIn / X) sont **générés** :

```bash
python3 tools/make-icons.py     # après tout changement de couleurs de marque
```

## Capture d'email (liste de contacts)

L'email est demandé **uniquement après un téléchargement réussi** (PDF ou Word),
une seule fois, et le refus est définitif. Jamais avant l'export : toutes les
pages SEO promettent « sans inscription », et un mur d'email à cet endroit
ferait chuter la conversion.

Les inscriptions arrivent sur `/lead` et sont écrites dans `leads.jsonl`
(doublons ignorés, date et origine du consentement conservées, ignoré par git) :

```bash
wc -l leads.jsonl                                   # taille de la liste
python3 -c "import json;print('\n'.join(json.loads(l)['email'] for l in open('leads.jsonl')))"
```

> ⚠️ Il n'y a **aucun envoi d'email** pour l'instant : la liste s'accumule, mais
> il faudra brancher un service d'envoi (Brevo, Resend, Mailchimp…) et ajouter
> un lien de désinscription avant la première campagne.

## Remontée d'erreurs

Les plantages côté client partent vers `/log/error` du proxy, qui les écrit
dans `errors.jsonl` (rotation à 5 Mo, fichier ignoré par git) :

```bash
tail -f errors.jsonl
```

**Aucune donnée de CV n'est envoyée** — seulement message, pile, page et
user-agent, plafonnés à 8 envois par session. Sans proxy configuré, tout est
inerte.

## Tests

```bash
python3 tools/test-site.py      # 35 pages : SEO, favicon, OG, liens morts, sitemap
python3 tools/test-deploy.py    # déploiement : routes API, rien qui fuite, API qui répond
node tools/test-docx.mjs        # export Word du CV : les 2 variantes, tous les modèles
node tools/test-modeles.mjs     # les 11 modèles face à des données hostiles (77 combinaisons)
node tools/test-lettre.mjs      # lettre : PDF 1 page A4, jauge, .docx relu par Word
node tools/test-carte.mjs       # carte : géométrie des PDF produits + charge du QR
node tools/test-qr.mjs          # QR : 39 charges utiles relues par un vrai décodeur
```

Les trois derniers pilotent **Google Chrome en headless** via CDP
(`tools/lib-chrome.mjs`, sans dépendance npm) et vérifient les fichiers
réellement produits, pas seulement l'affichage.

`test-docx.mjs` extrait le vrai code d'export de `app.html` et fait relire le
fichier produit par `textutil` (moteur OOXML d'Apple) : si Word sait l'ouvrir,
le test passe.

`test-deploy.py` lance un vrai serveur avec la classe `handler` de production
(Mistral bouchonné) et refait la liste des fichiers qui partiraient en ligne
pour y chercher la clé — le déploiement rate rarement bruyamment.

## Feuille de route (améliorations proposées)

| Priorité | Amélioration | Intérêt |
|---|---|---|
| ⭐⭐⭐ | **Score ATS** : coller une offre → analyse mots-clés & compatibilité | Gros différenciateur |
| ⭐⭐⭐ | Réordonnancement **drag & drop** des sections | Confort d'édition |
| ⭐⭐ | Versions **multilingues** (FR/EN) et par poste | Candidatures ciblées |
| ⭐⭐ | **Assistant IA** (reformuler une expérience, générer le résumé) via API Claude | Valeur ajoutée forte |
| ⭐⭐ | **Auth + cloud** (Supabase) pour retrouver ses CV | Rétention |
| ⭐ | ~~**Lettre de motivation** au même thème~~ | ✅ fait — page dédiée `lettre-de-motivation/` |
| ⭐ | ~~**Carte de visite**~~ | ✅ fait — `carte-de-visite/`, QR vectoriel |
| ⭐ | Export **PDF haute fidélité** (serveur Puppeteer) | Fiabilité sur mobile |
| ⭐ | ~~Export **Word (.docx)**~~ | ✅ fait — version ATS mono-colonne |

## Évolution technique possible

Cette v1 vanilla est volontairement sans build pour démarrer sans friction.
Pour industrialiser (comptes, IA, paiement) : migrer vers **Next.js** en
réutilisant les fonctions de rendu des modèles telles quelles (elles deviennent
des composants), + **Supabase** (auth + stockage) et une route serveur pour
l'IA et l'export PDF Puppeteer.
