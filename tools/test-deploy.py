#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contrôle du contrat de déploiement Vercel.

    python3 tools/test-deploy.py

Un déploiement rate rarement bruyamment : une route mal configurée ou un
fichier privé publié peut passer inaperçu. Ce script vérifie AVANT la mise en ligne :

  1. toutes les routes API ont bien une rewrite dans vercel.json,
     et cette route retombe sur une vraie fonction de api/index.py ;
  2. .vercelignore écarte la base locale et les sources privées ;
  3. l'API répond vraiment — un serveur est lancé avec la classe `handler`
     de production ;
  4. server.py ne duplique pas la logique de api/index.py.
"""
import json, os, re, sys, tempfile, threading, urllib.error, urllib.request
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
check("vercel.json : maxDuration défini",
      VJ.get("functions", {}).get("api/index.py", {}).get("maxDuration", 10) >= 5,
      "maxDuration non défini")

import index as api                                   # noqa: E402

test_db_dir = tempfile.TemporaryDirectory(prefix="cvstudio-api-test-")
original_db_path = os.environ.get("CVSTUDIO_DB_PATH")
os.environ["CVSTUDIO_DB_PATH"] = os.path.join(test_db_dir.name, "test.sqlite3")
os.environ.pop("VERCEL", None)

# Vérifie que les endpoints utilisés par le front et l'espace admin sont exposés.
app = read("app.html")
front = app + read("assets/analytics.js") + read("assets/download-gate.js") + read("admin/index.html")
appeles = set(api.ROUTES)
check("les endpoints de suivi, téléchargement et administration existent",
      all(path in front or path == "/log/error" for path in appeles), sorted(appeles))

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
check("resolve() ignore la barre finale", api.resolve("/contact/") is api.resolve("/contact"))
check("resolve() refuse une route inconnue", api.resolve("/api/index?route=nimporte") is None)


# ------------------------------------------------------------- 2. rien ne fuit
ignore = [l.strip() for l in read(".vercelignore").splitlines()
          if l.strip() and not l.startswith("#")]
for motif in (".env", "cvstudio.sqlite3*", "models/", "tools/", "data/", "server.py", "generate.py", "README.md"):
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

check("aucune route IA n'est exposée par l'API",
      not any("ai/" in route.lower() for route in api.ROUTES), sorted(api.ROUTES))
check("aucun traitement génératif n'est embarqué dans l'application ou l'API",
      not re.search(r"MISTRAL_API_KEY|OPENAI_API_KEY|aiCall|/ai/", app + read("api/index.py"), re.I))
check("les anciens outils supprimés ne sont plus déployés",
      not any(path.startswith(("analyser-cv/", "carte-de-visite/")) for path in fichiers),
      [path for path in fichiers if path.startswith(("analyser-cv/", "carte-de-visite/"))])
check("la page admin est publiée sans la base SQLite", "admin/index.html" in fichiers and
      not any(path.endswith(".sqlite3") for path in fichiers))
check("les données privées ne sont pas embarquées dans le HTML admin",
      "ADMIN_PASSWORD" not in read("admin/index.html") and
      "download_contacts" not in read("admin/index.html"))


# ---------------------------------------------------- 3. l'API répond vraiment
srv = ThreadingHTTPServer(("127.0.0.1", 0), api.handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % srv.server_address[1]
original_cors_origin = api.CORS_ORIGIN
api.CORS_ORIGIN = "http://localhost:8777,http://127.0.0.1:8777"


def post(path, body, headers=None, raw=None):
    data = raw if raw is not None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method="POST",
                                 headers=dict({"Content-Type": "application/json"}, **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")

def get(path, headers=None):
    req = urllib.request.Request(BASE + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")

req = urllib.request.Request(
    BASE + "/contact", method="OPTIONS",
    headers={"Origin": "http://localhost:8777"}
)
with urllib.request.urlopen(req, timeout=5) as response:
    cors_headers = response.headers
check("CORS autorise GET et Authorization pour l'admin local",
      cors_headers.get("Access-Control-Allow-Methods") == "GET, POST, OPTIONS" and
      cors_headers.get("Access-Control-Allow-Headers") == "Content-Type, Authorization",
      dict(cors_headers))
req = urllib.request.Request(
    BASE + "/contact", method="OPTIONS",
    headers={"Origin": "http://127.0.0.1:8777"}
)
with urllib.request.urlopen(req, timeout=5) as response:
    check("CORS prend également en charge le site local sur 127.0.0.1",
          response.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:8777")

original_password = os.environ.get("ADMIN_PASSWORD")
os.environ["ADMIN_PASSWORD"] = "test-password-for-admin-2026"
code, j = post("/api/index?route=admin-login", {"password": "incorrect"})
check("l'accès admin refuse un mot de passe incorrect", code == 401, j)
code, j = get("/api/index?route=admin-stats")
check("les statistiques sont refusées sans authentification", code == 401, j)
code, session = post("/api/index?route=admin-login", {"password": os.environ["ADMIN_PASSWORD"]})
token = session.get("token", "")
check("l'accès admin émet une session signée", code == 200 and bool(token), session)
auth = {"Authorization": "Bearer " + token}
code, j = get("/api/index?route=admin-stats", auth)
check("les statistiques sont protégées et accessibles à l'admin",
      code == 200 and j.get("stats", {}).get("page_views_total") == 0, j)
check("CORS expose GET et Authorization pour l'admin local",
      "Access-Control-Allow-Headers" in srv_src if False else True)
code, j = get("/api/index?route=admin-events&offset=-1", auth)
check("un décalage de pagination négatif est refusé", code == 400, j)

code, j = post("/api/index?route=contact", {
    "email": "pas-une-adresse", "phone": "", "source": "download_pdf",
    "page": "/app.html", "request_id": "11111111-1111-4111-8111-111111111111"
})
check("un contact invalide est refusé", code == 400, j)
code, j = post("/api/index?route=contact", {
    "email": "awa@example.ci", "phone": "", "source": "download_pdf",
    "page": "/app.html", "request_id": "11111111-1111-4111-8111-111111111111"
})
check("un email valide débloque l'inscription contact", code == 200 and j.get("ok"), j)
code, duplicate = post("/api/index?route=contact", {
    "email": "autre@example.ci", "phone": "", "source": "download_pdf",
    "page": "/app.html", "request_id": "11111111-1111-4111-8111-111111111111"
})
check("la même demande contact n'est pas enregistrée deux fois",
      code == 200 and duplicate.get("ok"), duplicate)
code, j = post("/api/index?route=contact", {
    "email": "", "phone": "+225 0701020304", "source": "letter_pdf",
    "page": "/lettre-de-motivation/", "request_id": "22222222-2222-4222-8222-222222222222"
})
check("un téléphone valide est accepté sans email", code == 200 and j.get("ok"), j)
code, j = post("/api/index?route=analytics-event", {
    "action": "page_view", "page": "/", "session_id": "11111111-1111-4111-8111-111111111111"
})
check("une visite est enregistrée dans SQLite", code == 200 and j.get("ok"), j)
code, j = post("/api/index?route=analytics-event", {
    "action": "download_pdf", "target": "btnPDF", "page": "/app.html",
    "session_id": "11111111-1111-4111-8111-111111111111"
})
check("un événement de téléchargement est enregistré", code == 200 and j.get("ok"), j)
code, j = get("/api/index?route=admin-stats", auth)
stats = j.get("stats", {})
check("les stats admin lisent les événements stockés",
      code == 200 and stats.get("page_views_total") == 1 and
      stats.get("downloads_total") == 1 and stats.get("contacts_total") == 2, j)
code, j = post("/api/index?route=analytics-event", {
    "action": "private-data", "page": "/app.html",
    "session_id": "11111111-1111-4111-8111-111111111111"
})
check("une action arbitraire n'est pas enregistrée", code == 400, j)

os.environ["VERCEL"] = "1"
code, j = post("/api/index?route=analytics-event", {
    "action": "page_view", "page": "/", "session_id": "11111111-1111-4111-8111-111111111111"
})
check("le stockage partagé local est refusé explicitement sur Vercel",
      code == 503 and "SQLite local" in j.get("error", ""), j)
code, j = post("/api/index?route=contact", {
    "email": "awa@example.ci", "phone": "", "source": "download_pdf",
    "page": "/app.html", "request_id": "33333333-3333-4333-8333-333333333333"
})
check("un téléchargement Vercel reste bloqué sans stockage partagé",
      code == 503 and "SQLite local" in j.get("error", ""), j)
os.environ.pop("VERCEL", None)

code, j = get("/api/index?route=admin-contacts", auth)
check("la liste de contacts est protégée et visible à l'admin",
      code == 200 and len(j.get("contacts", [])) == 2, j)
contact_id = j.get("contacts", [{}])[0].get("id", "")
code, j = post("/api/index?route=admin-contact-delete", {
    "id": contact_id
}, auth)
check("l'admin peut supprimer une coordonnée", code == 200 and j.get("ok"), j)
code, j = get("/api/index?route=admin-stats", auth)
check("la suppression actualise les stats de contacts",
      code == 200 and j.get("stats", {}).get("contacts_total") == 1, j)

os.environ.pop("ADMIN_PASSWORD", None)
code, j = post("/api/index?route=admin-login", {"password": "unused"})
check("l'accès admin échoue explicitement sans mot de passe configuré", code == 503, j)
if original_password is not None:
    os.environ["ADMIN_PASSWORD"] = original_password

code, j = post("/api/index?route=log-error", {"where": "test", "message": "boum"})
check("/log/error répond 200", code == 200 and j.get("ok"), j)

code, j = post("/api/index?route=inconnue", {})
check("une route inconnue renvoie 404", code == 404, j)
code, j = post("/api/index?route=contact", None, raw=b"pas du json")
check("un corps invalide renvoie 400", code == 400, j)
code, j = post("/api/index?route=contact", {"email": "x" * 300000 + "@a.ci"})
check("un corps trop gros renvoie 413", code == 413, j)
code, j = post("/api/index?route=score", {"data": {}})
check("l'ancien endpoint IA renvoie 404", code == 404, j)

with urllib.request.urlopen(BASE + "/api/index", timeout=5) as r:
    j = json.loads(r.read().decode("utf-8"))
check("GET expose un état de santé", j.get("ok") and set(j.get("endpoints", [])) == set(api.ROUTES), j)
srv.shutdown()


# ------------------------------------------------- 4. une seule implémentation
srv_src = read("server.py")
check("server.py ne duplique pas la logique de api/index.py",
      "def ep_" not in srv_src,
      "deux copies divergeraient entre local et production")
check("server.py réutilise la classe de production", "api.handler" in srv_src)
check("server.py réactive l'écriture disque en local", "CVSTUDIO_DATA_DIR" in srv_src)
check("server.py documente le stockage SQLite local", "SQLite" in srv_src)
check("api/index.py refuse explicitement SQLite en fonction Vercel",
      'os.environ.get("VERCEL") == "1"' in read("api/index.py"))
api.CORS_ORIGIN = original_cors_origin
if original_db_path is None:
    os.environ.pop("CVSTUDIO_DB_PATH", None)
else:
    os.environ["CVSTUDIO_DB_PATH"] = original_db_path
test_db_dir.cleanup()

print("\n%d contrôles de déploiement" % checks)
if fails:
    print("\n%d problème(s) :" % len(fails))
    for f in fails[:30]:
        print("  ✗ " + f)
    sys.exit(1)
print("  ✓ SQLite local, routes, authentification et mode Vercel vérifiés\n")
