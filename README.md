# CV Studio — Créateur de CV professionnel + moteur SEO

CV Studio propose la création de CV et de lettres, avec export PDF/Word. Le
contenu du CV et de la lettre reste dans le navigateur. Les exports sont
gratuits et ne demandent ni compte ni coordonnées. L'espace admin affiche
uniquement quatre compteurs temporaires (visites et exports), sans base de
données, coordonnées ni historique. Sur Vercel, les compteurs sont approximatifs
car chaque instance serverless garde sa propre mémoire temporaire.
Le site SEO (`index.html` + pages générées) dirige vers ces outils.

## Démarrer

**Le plus simple : double-cliquez `demarrer.command`.** Il lance le serveur et
ouvre le navigateur.

En ligne de commande :

```bash
# terminal 1
python3 server.py
# terminal 2
python3 -m http.server 8777
# ouvrir http://localhost:8777/ ou http://localhost:8777/admin/
```

Pour configurer l'accès admin, créez un fichier `.env` à la racine (non commité)
contenant `ADMIN_PASSWORD=...` avec un mot de passe robuste d'au moins
16 caractères. Aucun stockage de base de données n'est utilisé ; les compteurs
locaux sont remis à zéro à chaque redémarrage de l'API.

> **Servez toujours via HTTP.** En `file://`, le chargement des fichiers
> `assets/*.data.js` n'est garanti par aucun navigateur.
>
> Le site reste néanmoins navigable en `file://` grâce à
> `assets/file-links.js` : hors serveur, un lien vers un dossier de page
> ouvrirait l'**index du dossier** — une page noire sans rapport avec le site —
> parce qu'aucun navigateur ne sert `index.html` tout seul hors HTTP. Le script
> réécrit ces liens au clic, conserve leurs paramètres (par exemple l'identifiant
> du CV envoyé à la lettre), et **uniquement** quand `location.protocol` vaut
> `file:`. Les `href` du HTML restent en URL propres : les canoniques et le
> sitemap déclarent la forme avec barre oblique finale, et doubler les URL
> diluerait le maillage interne.

## Arborescence

```
cv-creator/
├── demarrer.command        lance le serveur + ouvre le navigateur (double-clic)
├── index.html              landing marketing (générateur CV + lettre + annuaire)
├── app.html                l'app de création de CV (+ import, export, funnel ?job=)
├── lettre-de-motivation/   outil autonome de rédaction et export de lettres
├── admin/index.html        tableau de bord privé (API protégée par mot de passe)
├── vercel.json             hébergement : routes de l'API, cache, en-têtes
├── .vercelignore           ce qui NE part PAS en ligne (tout déployé est public)
├── api/index.py            API compteurs, admin et erreurs (SOURCE UNIQUE)
├── server.py               la même API en local (importe api/index.py) sur :8788
├── generate.py             génère les pages SEO depuis data/content.json
├── data/content.json       SOURCE UNIQUE du contenu SEO (métiers + guides)
├── tools/
│   ├── make-icons.py       (re)génère favicon + image OG depuis la charte
│   ├── test-site.py        contrôle SEO/liens morts de toutes les pages
│   ├── test-deploy.py      contrat Vercel : routes, fichiers publics, API
│   ├── test-docx.mjs       export Word du CV (ZIP + XML + relecture par Word)
│   ├── test-modeles.mjs    robustesse du rendu des 11 modèles + intégrité de l'état
│   ├── test-lettre.mjs     reprise du CV sélectionné + exports PDF/Word
│   ├── test-deploy.py      contrat d'API et tests de l'authentification admin
│   └── lib-chrome.mjs      pilote Chrome headless partagé par les tests navigateur
├── assets/
│   ├── favicon.svg/.ico/-32/-180/-512.png, og.png   (générés par make-icons.py)
│   ├── site.css            style des pages SEO / landing
│   ├── zip.js              écriture ZIP « store » (historique lettre, conservé)
│   ├── analytics.js        envoi des visites et actions sans contenu de CV
│   ├── download-gate.js    collecte obligatoire email/téléphone avant export
│   ├── file-links.js       rend les liens « dossier/ » suivables en file:// en conservant leurs paramètres
│   ├── jobs.data.js        (généré) pré-remplissage de l'app par métier
│   └── signature.data.js   (généré) données de signature
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

## Le funnel de conversion

`/<métier>/` (page SEO) → bouton **« Créer ce CV »** → `app.html?job=<slug>` →
l'app démarre **pré-remplie** (titre, résumé, compétences du métier). L'app lit
aussi `?import=1` (ouvre l'import de l'ancien CV).

## Lettre reliée au CV

Depuis l'éditeur, le lien « Rédiger une lettre avec ce CV » transmet l'identifiant
du CV ouvert à `lettre-de-motivation/?cv=<id>`. La lettre relit ce CV précis dans
le stockage local partagé ; elle ne remplace pas un CV manquant par un autre.
Les éléments du candidat sont repris de ses données enregistrées, sans inventer
d'employeur, de destinataire ou de résultats.

## Espace admin, compteurs et téléchargements

Les exports PDF/Word/JSON du CV et PDF/Word de la lettre sont gratuits et
immédiats : aucun contact ni compte n'est demandé. Le contenu du CV reste dans
le navigateur. L'endpoint statistique ne reçoit que l'action comptée (visite ou
export), sans page, identifiant de session, coordonnée ni contenu du document.

L'espace admin est accessible à `/admin/`. Il affiche seulement quatre chiffres :
visites, exports CV, exports lettre et total. Le mot de passe `ADMIN_PASSWORD`
doit comporter au moins 16 caractères ; en local, configurez-le dans `.env`,
et sur Vercel dans les variables d'environnement du projet. L'API délivre un
jeton signé valable 8 heures.

Les compteurs sont en mémoire uniquement : le serveur local les remet à zéro à
son redémarrage. Sur Vercel, chaque instance conserve ses propres compteurs
temporaires ; les chiffres peuvent donc être incomplets, différents d'une
instance à l'autre et remis à zéro lors d'un redémarrage. Ils ne constituent
pas des statistiques durables ou exactes. Aucun historique ou contact n'est
enregistré.

```bash
# Alternative au script : lancer ces commandes dans deux terminaux.
python3 server.py             # API et compteurs temporaires sur :8788
python3 -m http.server 8777   # site sur http://localhost:8777
```

## Déploiement sur Vercel

Le site et son API fonctionnent sur Vercel. Les exports sont immédiats, et les
compteurs sont affichés dans l'espace admin avec les limites de mémoire
temporaire propres aux fonctions serverless. Pour ouvrir `/admin/` en ligne,
définissez `ADMIN_PASSWORD` (16 caractères minimum) dans les variables
d'environnement Vercel. Le `.env` local n'est jamais déployé.

### Mise en ligne

```bash
npx vercel login
npx vercel                      # aperçu, pour vérifier
npx vercel --prod               # production
```

Avant chaque mise en ligne :

```bash
python3 generate.py && python3 tools/test-site.py && python3 tools/test-deploy.py
```

### Ce que Vercel change, et comment c'est traité

| Contrainte de la plateforme | Traitement |
|---|---|
| Pas de `server.py` qui tourne | `api/index.py` — fonction serverless ; les routes passent par les `rewrites` de `vercel.json` en `?route=` (le chemin d'origine est perdu à la réécriture, d'où `resolve()`). |
| Mémoire serverless temporaire et distribuée | Les compteurs sont par instance, approximatifs et réinitialisés au redémarrage ; aucune base de données n'est utilisée. |
| Tout fichier déployé est **public** | `.vercelignore` écarte `.env`, les anciennes bases locales, `server.py`, `generate.py`, `data/`, `tools/`, `models/` et les fichiers Markdown. |
| L'API est ouverte sur Internet | Les routes admin exigent un jeton HMAC ; seule l'ingestion des six actions de compteur est publique. CORS n'est pas ouvert sur Vercel. |

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

Chaque modèle expose `data-edit` sur ses blocs pour activer ce geste.

## Les 11 modèles de CV

Les onze modèles sont gratuits et accessibles sans parrainage. Six modèles
d'origine (Moderne, Élégant, Classique, Minimal, Compact, Prestige)
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

## Lettre de motivation

La page autonome réutilise le CV choisi via son identifiant, sur la même origine
et sans envoyer ses données. Le contenu prérempli est déterministe et basé sur
le profil et les expériences sauvegardés. L'utilisateur complète lui-même
l'entreprise et le poste visés avant d'exporter sa lettre.

## Icônes et aperçu de partage

`assets/favicon.*` et `assets/og.png` (1200×630, affichée par WhatsApp /
LinkedIn / X) sont **générés** :

```bash
python3 tools/make-icons.py     # après tout changement de couleurs de marque
```

## Statistiques et confidentialité

Le suivi est limité aux visites et demandes d'export : l'API reçoit uniquement
le nom de l'action, sans page, identifiant de session, contact ou contenu de CV.
Les quatre compteurs en mémoire sont temporaires et approximatifs sur Vercel ;
aucun historique, base de données ou contact n'est conservé.

## Remontée d'erreurs

Les plantages côté client partent vers `/log/error` du proxy, qui les écrit
dans `errors.jsonl` (rotation à 5 Mo, fichier ignoré par git) :

```bash
tail -f errors.jsonl
```

**Aucune donnée de CV n'est envoyée** — seulement message, pile, page et
user-agent, plafonnés à 8 envois par session.

## Tests

```bash
python3 tools/test-site.py      # pages SEO, admin noindex, favicon, OG, liens morts, sitemap
python3 tools/test-deploy.py    # routes API, authentification admin, compteurs en mémoire
node tools/test-docx.mjs        # export Word du CV : les 2 variantes, tous les modèles
node tools/test-modeles.mjs     # les 11 modèles face à des données hostiles (77 combinaisons)
node tools/test-lettre.mjs      # transfert du CV ouvert et exports de la lettre
```

`test-lettre.mjs` pilote **Google Chrome en headless** via CDP
(`tools/lib-chrome.mjs`, sans dépendance npm) et vérifie le CV repris et les
fichiers réellement produits, pas seulement l'affichage.

`test-docx.mjs` extrait le vrai code d'export de `app.html` et fait relire le
fichier produit par `textutil` (moteur OOXML d'Apple) : si Word sait l'ouvrir,
le test passe.

`test-deploy.py` lance un vrai serveur avec la classe `handler` de production
et refait la liste des fichiers qui partiraient en ligne — le déploiement
rate rarement bruyamment.

## Feuille de route (améliorations proposées)

| Priorité | Amélioration | Intérêt |
|---|---|---|
| ⭐⭐⭐ | Réordonnancement **drag & drop** des sections | Confort d'édition |
| ⭐⭐ | Versions **multilingues** (FR/EN) et par poste | Candidatures ciblées |
| ⭐ | Export **PDF haute fidélité** (serveur Puppeteer) | Fiabilité sur mobile |
| ⭐ | ~~Export **Word (.docx)**~~ | ✅ fait — version ATS mono-colonne |

## Évolution technique possible

Cette version vanilla est volontairement sans build. Les seuls compteurs sont
temporaires et en mémoire ; les CV restent locaux et aucun traitement IA n'est
effectué.
