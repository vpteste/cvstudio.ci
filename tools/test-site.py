#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contrôle de non-régression du site statique.

    python3 tools/test-site.py

Vérifie sur TOUTES les pages : métadonnées SEO/social présentes, favicon
câblé, et surtout qu'aucun lien local (css, js, image, page) ne pointe dans
le vide — l'erreur la plus facile à introduire en régénérant le site.
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails, checked = [], 0


def pages():
    for name in sorted(os.listdir(ROOT)):
        p = os.path.join(ROOT, name)
        if name.endswith(".html"):
            yield name, p
        elif os.path.isdir(p) and not name.startswith((".", "assets", "data", "tools")):
            idx = os.path.join(p, "index.html")
            if os.path.exists(idx):
                yield name + "/index.html", idx


def fail(page, msg):
    fails.append(f"{page} : {msg}")


REQUIRED = [("<title>", "titre absent"),
            ('name="description"', "meta description absente"),
            ('rel="icon"', "favicon non câblé"),
            ('name="viewport"', "viewport absent"),
            # Sans lui, un site ouvert en file:// (double-clic) renvoie sur
            # l'index du dossier dès qu'on suit un lien « métier/ ».
            ("assets/file-links.js", "file-links.js absent : navigation cassée hors serveur HTTP")]

for rel, path in pages():
    checked += 1
    html = open(path, encoding="utf-8").read()
    base = os.path.dirname(path)

    for needle, msg in REQUIRED:
        if needle not in html:
            fail(rel, msg)

    # l'app est une page outil : pas de canonical ni d'OG social attendus
    if rel != "app.html":
        for needle, msg in (('rel="canonical"', "canonical absent"),
                            ('property="og:image"', "image OG absente (partage nu sur WhatsApp)")):
            if needle not in html:
                fail(rel, msg)

    # liens locaux : href/src pointant vers un fichier du projet
    for attr in re.findall(r'(?:href|src)="([^"]+)"', html):
        if attr.startswith(("http", "//", "#", "mailto:", "data:", "javascript:")):
            continue
        if "${" in attr or "{{" in attr:      # attribut construit en JS, pas un lien réel
            continue
        target = attr.split("?")[0].split("#")[0]
        if not target:
            continue
        full = os.path.normpath(os.path.join(base, target))
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.exists(full):
            fail(rel, f"lien mort → {attr}")

# Les outils retirés ne doivent plus avoir de page publique.
for obsolete in ("analyser-cv/index.html", "carte-de-visite/index.html"):
    if os.path.exists(os.path.join(ROOT, obsolete)):
        fail(obsolete, "cet outil a été retiré et ne doit plus être publié")

# L'annuaire de la landing doit être du HTML statique : c'est lui qui porte le
# maillage interne. S'il redevient dépendant du JS, toutes les pages métier
# deviennent orphelines dès que le script ne s'exécute pas (file://, erreur JS).
# On contrôle CHAQUE zone séparément : le pied de page ne doit pas masquer un
# annuaire vide (les mêmes liens s'y trouvent).
import json as _json

landing = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
_data = _json.load(open(os.path.join(ROOT, "data", "content.json"), encoding="utf-8"))


def _zone(tag):
    a, b = landing.find(f"<!--{tag}:START-->"), landing.find(f"<!--{tag}:END-->")
    if a < 0 or b < 0:
        fails.append(f"index.html : marqueurs {tag} absents")
        return None
    return landing[a:b]


for tag, items, key in (("METIERS", _data["metiers"], "slug"),
                        ("FOOTMETIERS", _data["metiers"], "slug"),
                        ("GUIDES", _data["topics"], "slug"),
                        ("FOOTGUIDES", _data["topics"], "slug")):
    zone = _zone(tag)
    if zone is None:
        continue
    for it in items:
        if f'href="{it[key]}/"' not in zone:
            fails.append(f'index.html [{tag}] : lien statique manquant vers /{it[key]}/')

# Le nombre de modèles vient de generate.py (source unique) : figer un chiffre
# ici obligeait à modifier le test à chaque modèle ajouté, et ne vérifiait rien
# de plus que « quelqu'un a pensé à mettre à jour les deux ».
_src = open(os.path.join(ROOT, "generate.py"), encoding="utf-8").read()
_bloc = re.search(r"MODELES = \[(.*?)\]\n", _src, re.S)
_attendu = _bloc.group(1).count("(") if _bloc else 0
_mod = _zone("MODELES")
if _mod is not None and _attendu and _mod.count("<a class") != _attendu:
    fails.append(f'index.html [MODELES] : {_attendu} modèles attendus (generate.py), '
                 f'{_mod.count("<a class")} trouvés — relancez generate.py')

# le sitemap doit refléter exactement les pages publiées
sitemap = open(os.path.join(ROOT, "sitemap.xml"), encoding="utf-8").read()
for obsolete in ("/analyser-cv/", "/carte-de-visite/"):
    if obsolete in sitemap:
        fails.append(f"sitemap.xml : ancienne route encore publiée {obsolete}")
for rel, _ in pages():
    slug = "" if rel == "index.html" else (rel[:-len("index.html")] if rel.endswith("/index.html") else rel)
    if slug in ("app.html",) or rel == "app.html":
        continue
    if f"/{slug}<" not in sitemap.replace("</loc>", "<"):
        fails.append(f"sitemap.xml : /{slug} absent")

print(f"\n{checked} pages contrôlées")
if fails:
    print(f"\n{len(fails)} problème(s) :")
    for f in fails[:40]:
        print("  ✗ " + f)
    sys.exit(1)
print("  ✓ métadonnées, favicon, OG, liens locaux et sitemap : tout est cohérent\n")
