#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contrôle du contrat de déploiement Vercel.

    python3 tools/test-deploy.py

Un déploiement rate rarement bruyamment : il rate en servant une page qui
marche mais dont l'IA renvoie 404, ou — bien pire — en publiant un fichier qui
devait rester privé. Ce script vérifie AVANT la mise en ligne :

  1. tout chemin appelé par le front a bien une route dans vercel.json,
     et cette route retombe sur une vraie fonction de api/index.py ;
  2. .vercelignore écarte les secrets et les sources, et AUCUN fichier
     déployé ne contient la clé Mistral ;
  3. l'API répond vraiment — un serveur est lancé avec la classe `handler`
     de production, Mistral étant remplacé par un bouchon ;
  4. server.py ne duplique pas la logique de api/index.py.
"""
import json, os, re, sys, threading, urllib.error, urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))

fails, checks = [], 0


def check(label, ok, detail=""):
    global checks
    checks += 1
    if not ok:
        fails.append(label + (" — " + str(detail) if detail else ""))


def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


# ------------------------------------------------------------------ 1. routes
VJ = json.loads(read("vercel.json"))
check("vercel.json : trailingSlash actif", VJ.get("trailingSlash") is True,
      "les URL canoniques finissent par / — sans ce réglage chacune redirige")
check("vercel.json : maxDuration relevé",
      VJ.get("functions", {}).get("api/index.py", {}).get("maxDuration", 10) >= 30,
      "les 10 s par défaut coupent une lettre de motivation en pleine génération")

import index as api                                   # noqa: E402

# Les chemins que le front appelle réellement, relevés dans le code du front.
app = read("app.html")
appeles = set(re.findall(r"aiCall\('([^']+)'", app))
appeles |= set(re.findall(r"CVAI\.endpoint\+'([^']+)'", app))
check("des appels IA ont été trouvés dans app.html", len(appeles) >= 5, sorted(appeles))

sources = {r["source"].rstrip("/") or "/": r["destination"] for r in VJ.get("rewrites", [])}
for path in sorted(appeles):
    dest = sources.get(path)
    check("vercel.json route %s" % path, dest is not None, "aucune rewrite : 404 en ligne")
    if dest:
        check("la route %s vise une vraie fonction" % path, api.resolve(dest) is not None,
              "destination %s inconnue de api/index.py" % dest)
    # la barre finale que trailingSlash peut ajouter doit être routée aussi
    check("vercel.json route %s/ (barre finale)" % path,
          any(r["source"] == path + "/" for r in VJ.get("rewrites", [])),
          "trailingSlash redirige %s vers %s/ : sans cette rewrite, 404" % (path, path))

# les deux formes d'adressage doivent mener au même endpoint
for path in sorted(appeles):
    check("resolve() accepte le chemin public %s" % path, api.resolve(path) is not None)
check("resolve() ignore la barre finale", api.resolve("/ai/score/") is api.resolve("/ai/score"))
check("resolve() refuse une route inconnue", api.resolve("/api/index?route=nimporte") is None)


# ------------------------------------------------------------- 2. rien ne fuit
ignore = [l.strip() for l in read(".vercelignore").splitlines()
          if l.strip() and not l.startswith("#")]
for motif in (".env", "models/", "tools/", "data/", "server.py", "generate.py", "README.md"):
    check(".vercelignore écarte %s" % motif, motif in ignore,
          "tout fichier déployé est public")


def deployes():
    """Fichiers qui partiraient en ligne (lecture simplifiée de .vercelignore)."""
    exclus_dir = {m.rstrip("/") for m in ignore if m.endswith("/")}
    exclus_fic = {m for m in ignore if not m.endswith("/")}
    for cur, dirs, files in os.walk(ROOT):
        rel = os.path.relpath(cur, ROOT)
        dirs[:] = [d for d in dirs
                   if d not in exclus_dir and not d.startswith(".") and d != "__pycache__"]
        for f in files:
            r = f if rel == "." else os.path.join(rel, f)
            if f in exclus_fic or r in exclus_fic or f.startswith("."):
                continue
            yield r


fichiers = sorted(deployes())
check("le site déployé contient bien les pages", "index.html" in fichiers and "app.html" in fichiers)
check("la fonction serverless est déployée", os.path.join("api", "index.py") in fichiers)
for interdit in ("server.py", "generate.py", "README.md", ".env"):
    check("%s reste hors ligne" % interdit, interdit not in fichiers)

# la clé Mistral ne doit apparaître dans AUCUN fichier publié
cle = ""
if os.path.exists(os.path.join(ROOT, ".env")):
    for line in read(".env").splitlines():
        if line.startswith("MISTRAL_API_KEY="):
            cle = line.split("=", 1)[1].strip().strip('"').strip("'")
if len(cle) >= 12:
    fuites = []
    for r in fichiers:
        try:
            if cle in open(os.path.join(ROOT, r), encoding="utf-8", errors="ignore").read():
                fuites.append(r)
        except Exception:
            pass
    check("la clé Mistral n'est dans aucun fichier publié", not fuites, fuites)
else:
    checks += 1          # pas de clé en local : rien à vérifier, le contrôle reste compté

check("assets/config.js ne contient pas de clé",
      not re.search(r"[A-Za-z0-9]{24,}", read("assets/config.js")))
check("config.js déduit l'endpoint du domaine",
      "location.origin" in read("assets/config.js"),
      "un endpoint codé en dur casserait l'IA en ligne")


# ---------------------------------------------------- 3. l'API répond vraiment
api.mistral = lambda messages, temperature=0.4, json_mode=False: (
    json.dumps({"scores": {"ats": 80, "readability": 70, "experience": 60,
                           "skills": 90, "presentation": 50, "global": 0},
                "recommendations": ["Chiffrez vos résultats."]})
    if json_mode else "**Texte** rédigé par le bouchon.")

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % srv.server_address[1]


def post(path, body, headers=None, raw=None):
    data = raw if raw is not None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method="POST",
                                 headers=dict({"Content-Type": "application/json"}, **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


code, j = post("/api/index?route=score", {"data": {"fullName": "A"}})
check("/ai/score répond 200", code == 200, j)
check("/ai/score borne les notes à 0-100", all(0 <= v <= 100 for v in j.get("scores", {}).values()), j)
check("/ai/score recalcule le global manquant", j.get("scores", {}).get("global", 0) == 70, j)

code, j = post("/api/index?route=rewrite", {"role": "Vendeur"})
check("/ai/rewrite répond 200", code == 200, j)
check("/ai/rewrite retire le Markdown", "**" not in j.get("text", ""), j)

code, j = post("/api/index?route=cover-letter", {"poste": "Vendeur"})
check("/ai/cover-letter répond 200", code == 200, j)

code, j = post("/api/index?route=lead", {"email": "test@exemple.ci", "source": "t"})
check("/lead accepte une adresse valide", code == 200 and j.get("ok"), j)
code, j = post("/api/index?route=lead", {"email": "pas-une-adresse"})
check("/lead refuse une adresse invalide", code == 500 and "error" in j, j)
check("/lead n'écrit rien sans CVSTUDIO_DATA_DIR",
      api.DATA_DIR != "" or not os.path.exists(os.path.join(ROOT, "leads.jsonl")),
      "le disque est en lecture seule sur Vercel : une écriture y planterait")

code, j = post("/api/index?route=log-error", {"where": "test", "message": "boum"})
check("/log/error répond 200", code == 200 and j.get("ok"), j)

code, j = post("/api/index?route=inconnue", {})
check("une route inconnue renvoie 404", code == 404, j)
code, j = post("/api/index?route=score", None, raw=b"pas du json")
check("un corps invalide renvoie 400", code == 400, j)
code, j = post("/api/index?route=score", {"data": {"x": "y" * 300000}})
check("un corps trop gros renvoie 413", code == 413, j)
code, j = post("/api/index?route=score", {"data": {}}, headers={"Origin": "https://site-tiers.example"})
check("une origine étrangère est refusée", code == 403, "sinon n'importe quel site consomme la clé")

with urllib.request.urlopen(BASE + "/api/index", timeout=5) as r:
    j = json.loads(r.read().decode("utf-8"))
check("GET expose un état de santé", j.get("ok") and set(j.get("endpoints", [])) == set(api.ROUTES), j)
srv.shutdown()


# ------------------------------------------------- 4. une seule implémentation
srv_src = read("server.py")
check("server.py ne duplique pas les prompts de api/index.py",
      "Tu es un expert" not in srv_src and "def ep_" not in srv_src,
      "deux copies divergeraient entre local et production")
check("server.py réutilise la classe de production", "api.handler" in srv_src)
check("server.py réactive l'écriture disque en local", "CVSTUDIO_DATA_DIR" in srv_src)

print("\n%d contrôles de déploiement" % checks)
if fails:
    print("\n%d problème(s) :" % len(fails))
    for f in fails[:30]:
        print("  ✗ " + f)
    sys.exit(1)
print("  ✓ routes, secrets, API et non-duplication : prêt pour Vercel\n")
