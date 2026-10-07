#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Générateur de pages SEO statiques pour CV Studio.

Lit data/content.json et produit :
  - <slug>/index.html          pour chaque métier et chaque page thématique
  - sitemap.xml, robots.txt
  - assets/jobs.data.js        (window.JOBS -> pré-remplissage de l'app via ?job=)

Aucune dépendance externe. Lancer :  python3 generate.py
Pour ajouter une page : éditer data/content.json puis relancer ce script.
"""
import json, os, html, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = json.load(open(os.path.join(ROOT, "data", "content.json"), encoding="utf-8"))
SITE = DATA["site"]
BASE = "https://" + SITE["domain"]
YEAR = SITE.get("annee", str(datetime.date.today().year))


def esc(s):
    return html.escape(str(s), quote=True)


def head(title, desc, canonical, rel):
    """<head> commun. rel = préfixe vers la racine ('' ou '../')."""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}"/>
<link rel="canonical" href="{esc(canonical)}"/>
<meta property="og:type" content="website"/>
<meta property="og:title" content="{esc(title)}"/>
<meta property="og:description" content="{esc(desc)}"/>
<meta property="og:url" content="{esc(canonical)}"/>
<meta property="og:image" content="{BASE}/assets/og.png"/>
<meta property="og:image:width" content="1200"/>
<meta property="og:image:height" content="630"/>
<meta property="og:site_name" content="{esc(SITE['name'])}"/>
<meta property="og:locale" content="fr_FR"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:image" content="{BASE}/assets/og.png"/>
<meta name="robots" content="index,follow"/>
<link rel="icon" href="{rel}assets/favicon.svg" type="image/svg+xml"/>
<link rel="icon" href="{rel}assets/favicon-32.png" sizes="32x32"/>
<link rel="apple-touch-icon" href="{rel}assets/favicon-180.png"/>
<meta name="theme-color" content="#6366f1"/>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet"/>
<link rel="stylesheet" href="{rel}assets/site.css?v=2"/>
</head>
<body>"""


def nav(rel):
    return f"""
<header class="nav">
  <a class="brand" href="{rel}index.html"><span class="mark">CV</span> CV Studio</a>
  <nav class="nav-links">
    <a href="{rel}index.html#metiers">CV par métier</a>
    <a href="{rel}lettre-de-motivation/">Lettre de motivation</a>
    <a class="btn primary" href="{rel}app.html">Créer mon CV</a>
  </nav>
</header>"""


def footer(rel):
    mlinks = " ".join(f'<a href="{rel}{m["slug"]}/">{esc(m["titreCourt"])}</a>' for m in DATA["metiers"])
    tlinks = " ".join(f'<a href="{rel}{t["slug"]}/">{esc(t["slug"].replace("cv-","CV ").replace("-"," "))}</a>' for t in DATA["topics"])
    return f"""
<footer class="footer">
  <div class="foot-col"><h4>CV par métier</h4><div class="foot-links">{mlinks}</div></div>
  <div class="foot-col"><h4>Guides CV</h4><div class="foot-links">{tlinks}</div></div>
  <div class="foot-col"><h4>CV Studio</h4><div class="foot-links">
    <a href="{rel}app.html">Créer mon CV</a>
    <a href="{rel}lettre-de-motivation/">Lettre de motivation</a>
    <a href="{rel}index.html#modeles">Voir les modèles</a>
  </div></div>
  <div class="foot-bottom">© {YEAR} CV Studio — Créateur de CV gratuit, professionnel et optimisé ATS.</div>
</footer>
<script src="{rel}assets/file-links.js"></script>
<script src="{rel}assets/analytics.js"></script>
</body></html>"""


def faq_block(faq, rel):
    if not faq:
        return ""
    items = "".join(
        f'<details class="faq-item"><summary>{esc(f["q"])}</summary><p>{esc(f["r"])}</p></details>'
        for f in faq
    )
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": f["q"],
             "acceptedAnswer": {"@type": "Answer", "text": f["r"]}}
            for f in faq
        ],
    }
    return (f'<section class="block"><h2>Questions fréquentes</h2>{items}</section>'
            f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>')


def breadcrumb(rel, parent_label, parent_href, current):
    return (f'<nav class="crumb"><a href="{rel}index.html">Accueil</a> › '
            f'<a href="{rel}{parent_href}">{esc(parent_label)}</a> › <span>{esc(current)}</span></nav>')


def cta(href, label):
    return f'<div class="cta-box"><a class="btn primary big" href="{esc(href)}">{esc(label)}</a><span class="cta-note">Création et téléchargement gratuits · sans compte ni coordonnées</span></div>'


def related_block(slugs, rel):
    if not slugs:
        return ""
    lookup = {m["slug"]: m["titreCourt"] for m in DATA["metiers"]}
    lookup.update({t["slug"]: t["slug"].replace("cv-", "CV ").replace("-", " ") for t in DATA["topics"]})
    links = "".join(f'<a class="pill" href="{rel}{s}/">{esc(lookup.get(s, s))}</a>' for s in slugs if s in lookup)
    return f'<section class="block"><h2>À consulter aussi</h2><div class="pills">{links}</div></section>'


# Vitrine des modèles de la landing. Le 4e champ est l'identifiant du modèle
# dans app.html : la carte ouvre directement CE modèle (app.html?tpl=…) au lieu
# de renvoyer sur la galerie, où l'utilisateur devait le retrouver.
MODELES = [("Moderne",   "#2563eb", "Barre latérale colorée",      "moderne"),
           ("Élégant",   "#7c3aed", "Bandeau d'en-tête",           "elegant"),
           ("Classique", "#0f4c81", "Sobre, une colonne",          "classique"),
           ("Minimal",   "#0f766e", "Épuré",                       "minimal"),
           ("Compact",   "#ea580c", "Dense, une page",             "compact"),
           ("Contraste", "#7c3aed", "Colonne teintée à droite",    "contraste"),
           ("Duo",       "#ca8a04", "Colonne colorée pleine page", "duo"),
           ("Athlète",   "#eab308", "Fond sombre, profils sportifs", "athlete"),
           ("Champion",  "#2563eb", "Cadre coloré, profils sportifs", "champion"),
           ("Coach",     "#dc2626", "Colonne grise, dates colorées", "coach")]


def models_strip(job, rel):
    """Bande de modèles d'une page métier.

    Chaque vignette ouvre SON modèle, pré-rempli (`?job=…&tpl=…`). Auparavant
    les cinq liens pointaient tous vers la même URL : on cliquait « Compact »
    et on arrivait sur « Moderne ». La liste vient de MODELES, pour qu'un
    modèle ajouté à l'app apparaisse ici sans édition supplémentaire.
    """
    cards = "".join(
        f'<a class="mini-model" href="{rel}app.html?job={job}&amp;tpl={tid}">'
        f'<span class="mm-bar" style="background:{c}"></span>{esc(n)}</a>'
        for n, c, _d, tid in MODELES
    )
    return (f'<section class="block"><h2>{len(MODELES)} modèles adaptés à ce métier</h2>'
            f'<div class="mini-models">{cards}</div></section>')


def outils_block(job, rel):
    return (
        '<section class="block"><h2>Passez à l\'action</h2>'
        '<div class="mini-models">'
        f'<a class="mini-model" href="{rel}app.html?job={job}">'
        '<span class="mm-bar" style="background:#6366f1"></span>Créer mon CV pour ce poste</a>'
        f'<a class="mini-model" href="{rel}lettre-de-motivation/?job={job}">'
        '<span class="mm-bar" style="background:#0f766e"></span>Préparer ma lettre de motivation</a>'
        '</div></section>')


def metier_page(m):
    slug, rel = m["slug"], "../"
    canonical = f"{BASE}/{slug}/"
    # `tpl` (facultatif dans content.json) : le métier ouvre le modèle qui lui va.
    # URL brute : cta() passe déjà le href dans esc(), l'échapper ici le
    # doublerait (&amp;amp;) et casserait le paramètre.
    app_href = f"{rel}app.html?job={m['job']}" + (f"&tpl={m['tpl']}" if m.get("tpl") else "")
    tech = "".join(f"<li>{esc(x)}</li>" for x in m["competences"])
    soft = "".join(f"<li>{esc(x)}</li>" for x in m.get("competencesSoft", []))
    ats = "".join(f"<li>{esc(x)}</li>" for x in m.get("ats", []))
    err = "".join(f"<li>{esc(x)}</li>" for x in m.get("erreurs", []))
    body = f"""{head(m['metaTitle'], m['metaDesc'], canonical, rel)}{nav(rel)}
<main class="page" style="--accent:{m.get('accent','#2563eb')}">
  {breadcrumb(rel, "CV par métier", "index.html#metiers", m['titreCourt'])}
  <h1>{esc(m['h1'])}</h1>
  <p class="lead">{esc(m['intro'])}</p>
  {cta(app_href, "Créer mon CV " + m['titreCourt'])}

  {models_strip(m['job'], rel)}

  <section class="block">
    <h2>Exemple de résumé professionnel — {esc(m['titreCourt'])}</h2>
    <blockquote class="example">{esc(m['resume'])}</blockquote>
    <p class="hint">Astuce : personnalisez ce résumé avec vos propres chiffres. Il est déjà pré-rempli si vous cliquez sur « Créer mon CV » ci-dessus.</p>
  </section>

  <section class="block two-col">
    <div><h2>Compétences techniques</h2><ul class="ticks">{tech}</ul></div>
    <div><h2>Qualités (soft skills)</h2><ul class="ticks">{soft}</ul></div>
  </section>

  <section class="block"><h2>Conseils ATS pour un CV de {esc(m['titreCourt'])}</h2><ul class="ticks">{ats}</ul></section>
  <section class="block"><h2>Erreurs à éviter</h2><ul class="crosses">{err}</ul></section>

  {faq_block(m.get('faq'), rel)}
  {outils_block(m['job'], rel)}
  {related_block(m.get('related'), rel)}
  {cta(app_href, "Créer mon CV " + m['titreCourt'] + " maintenant")}
</main>
{footer(rel)}"""
    return body


def topic_page(t):
    slug, rel = t["slug"], "../"
    canonical = f"{BASE}/{slug}/"
    secs = "".join(f'<section class="block"><h2>{esc(s["h2"])}</h2>{s["html"]}</section>' for s in t.get("sections", []))
    body = f"""{head(t['metaTitle'], t['metaDesc'], canonical, rel)}{nav(rel)}
<main class="page">
  {breadcrumb(rel, "Guides CV", "index.html#guides", t['h1'])}
  <h1>{esc(t['h1'])}</h1>
  <p class="lead">{esc(t['intro'])}</p>
  {cta(rel + "app.html", "Créer mon CV gratuitement")}
  {secs}
  {faq_block(t.get('faq'), rel)}
  {related_block(t.get('related'), rel)}
  {cta(rel + "app.html", "Créer mon CV maintenant")}
</main>
{footer(rel)}"""
    return body


def write(path, content):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w", encoding="utf-8").write(content)
    return path


# Les modèles présentés sur la landing (miroir de TEMPLATES dans app.html)
def fill_landing():
    """Écrit l'annuaire directement dans index.html, entre les marqueurs.

    Ces listes étaient auparavant construites en JavaScript depuis
    site.data.js. Or elles PORTENT LE MAILLAGE INTERNE du site : si le JS
    ne s'exécute pas (ouverture en file://, script bloqué, erreur), toutes
    les pages métier deviennent orphelines. On les fige donc en HTML.
    """
    path = os.path.join(ROOT, "index.html")
    html = open(path, encoding="utf-8").read()

    cards = "".join(
        f'<a class="jobcard" style="--accent:{m["accent"]}" href="{m["slug"]}/">'
        f'<div class="jc-bar" style="background:{m["accent"]}"></div>'
        f'<h3>CV {esc(m["titreCourt"])}</h3><p>Modèle, exemple &amp; conseils ATS</p></a>'
        for m in DATA["metiers"])
    modeles = "".join(
        f'<a class="jobcard" style="--accent:{c}" href="app.html?tpl={tid}">'
        f'<div class="jc-bar" style="background:{c}"></div>'
        f'<h3>{esc(n)}</h3><p>{esc(d)}</p></a>' for n, c, d, tid in MODELES)
    guides = "".join(f'<a href="{t["slug"]}/">{esc(t["h1"])}</a>' for t in DATA["topics"])
    foot_m = "".join(f'<a href="{m["slug"]}/">CV {esc(m["titreCourt"])}</a>' for m in DATA["metiers"])
    foot_g = "".join(f'<a href="{t["slug"]}/">{esc(t["h1"])}</a>' for t in DATA["topics"])

    for tag, content in (("METIERS", cards), ("MODELES", modeles), ("GUIDES", guides),
                         ("FOOTMETIERS", foot_m), ("FOOTGUIDES", foot_g)):
        start, end = f"<!--{tag}:START-->", f"<!--{tag}:END-->"
        i, j = html.find(start), html.find(end)
        if i < 0 or j < 0:
            raise SystemExit(f"index.html : marqueurs {tag} introuvables")
        html = html[:i + len(start)] + content + html[j:]

    open(path, "w", encoding="utf-8").write(html)
    return f"index.html ({len(DATA['metiers'])} métiers, {len(DATA['topics'])} guides)"


def main():
    written = []
    for m in DATA["metiers"]:
        written.append(write(f"{m['slug']}/index.html", metier_page(m)))
    for t in DATA["topics"]:
        written.append(write(f"{t['slug']}/index.html", topic_page(t)))

    # Données pour l'app (pré-remplissage ?job=)
    jobs = {m["job"]: {"titre": m["titre"], "resume": m["resume"],
                       "competences": m["competences"], "exempleExp": m.get("exempleExp", ""),
                       "accent": m.get("accent", "#2563eb")} for m in DATA["metiers"]}
    write("assets/jobs.data.js", "window.JOBS=" + json.dumps(jobs, ensure_ascii=False) + ";")

    # Signature textuelle du CV, sans code QR ni dépendance externe.
    sign = {"name": SITE["name"], "url": BASE, "urlShort": SITE["domain"]}
    write("assets/signature.data.js", "window.SIGN=" + json.dumps(sign, ensure_ascii=False) + ";")

    # Données pour l'annuaire de la landing

    # sitemap.xml
    print("  " + fill_landing())

    urls = [BASE + "/", BASE + "/app.html", BASE + "/lettre-de-motivation/"] + \
           [f"{BASE}/{m['slug']}/" for m in DATA["metiers"]] + \
           [f"{BASE}/{t['slug']}/" for t in DATA["topics"]]
    today = datetime.date.today().isoformat()
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        sm += f"  <url><loc>{u}</loc><lastmod>{today}</lastmod></url>\n"
    sm += "</urlset>\n"
    write("sitemap.xml", sm)
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")

    print(f"OK — {len(written)} pages générées :")
    for p in written:
        print("  " + p)
    print("  assets/jobs.data.js, sitemap.xml, robots.txt")


if __name__ == "__main__":
    main()
