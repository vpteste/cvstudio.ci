#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vérifie les routes, le déploiement et les compteurs mémoire de l'API."""
import fnmatch, json, os, re, sys, threading, urllib.error, urllib.request
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
    with open(os.path.join(ROOT, rel), encoding="utf-8") as file:
        return file.read()


VJ = json.loads(read("vercel.json"))
check("vercel.json conserve les URL canoniques", VJ.get("trailingSlash") is True)
check("la fonction serverless a une durée maximale", VJ.get("functions", {}).get(
    "api/index.py", {}).get("maxDuration", 0) >= 5)

import index as api  # noqa: E402

app = read("app.html")
front = app + read("assets/analytics.js") + read("assets/download-gate.js") + read("admin/index.html")
routes_in_front = set(api.ROUTES)
check("les routes de l'API sont utilisées par le site ou l'admin",
      all(path in front or path == "/log/error" for path in routes_in_front), sorted(routes_in_front))

rewrites = {r["source"]: r["destination"] for r in VJ.get("rewrites", [])}
for path in sorted(routes_in_front):
    for suffix in ("", "/"):
        source = path + suffix
        destination = rewrites.get(source)
        check("rewrite Vercel %s" % source, destination is not None)
        if destination:
            check("rewrite %s résolue par l'API" % source,
                  api.resolve(destination) is not None, destination)

check("la résolution refuse une route inconnue",
      api.resolve("/api/index?route=unknown") is None)
check("les routes contacts et historique ont disparu",
      not any("contact" in path or "events" in path for path in api.ROUTES))
check("aucun module SQLite n'est importé par l'API",
      not re.search(r"\bsqlite3?\b|CVSTUDIO_DB_PATH", read("api/index.py"), re.I))

ignore = [line.strip() for line in read(".vercelignore").splitlines()
          if line.strip() and not line.startswith("#")]
for motif in (".env", "cvstudio.sqlite3*", "models/", "tools/", "data/",
              "server.py", "generate.py", "README.md"):
    check(".vercelignore écarte %s" % motif, motif in ignore)

def deployed_files():
    excluded_dirs = {m.rstrip("/") for m in ignore if m.endswith("/")}
    excluded_files = set(ignore) - {m for m in ignore if m.endswith("/")}
    for current, dirs, files in os.walk(ROOT):
        relative = os.path.relpath(current, ROOT)
        dirs[:] = [d for d in dirs if d not in excluded_dirs and
                   not d.startswith(".") and d != "__pycache__"]
        for name in files:
            path = name if relative == "." else os.path.join(relative, name)
            if any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(path, pattern)
                   for pattern in excluded_files) or name.startswith("."):
                continue
            yield path


files = set(deployed_files())
check("les pages du site sont déployées", {"index.html", "app.html"} <= files)
check("la fonction API et l'admin sont déployés",
      {"api/index.py", "admin/index.html"} <= files)
check("les fichiers secrets et de développement restent privés",
      not any(path in files for path in (".env", "server.py", "generate.py", "README.md")))
check("les anciennes bases locales ne seraient pas publiées",
      not any(os.path.basename(path).startswith("cvstudio.sqlite3") for path in files))
check("aucun traitement IA ne reste dans l'app ou l'API",
      not re.search(r"MISTRAL_API_KEY|OPENAI_API_KEY|aiCall|/ai/", app + read("api/index.py"), re.I))
check("les outils IA supprimés ne sont pas déployés",
      not any(path.startswith(("analyser-cv/", "carte-de-visite/")) for path in files))
check("l'admin ne contient ni contacts ni historique",
      not re.search(r"contact|csv|<table", read("admin/index.html"), re.I))
check("l'API n'accepte que les compteurs prévus",
      "stats_available" in read("api/index.py") and
      "instance-memory" in read("api/index.py"))
check("les exports ne dépendent pas d'un formulaire de contact",
      not re.search(r"contact|email|telephone", read("assets/download-gate.js"), re.I))

server = ThreadingHTTPServer(("127.0.0.1", 0), api.handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % server.server_address[1]
previous_origin = api.CORS_ORIGIN
api.CORS_ORIGIN = "http://localhost:8777,http://127.0.0.1:8777"
previous_password = os.environ.get("ADMIN_PASSWORD")
os.environ["ADMIN_PASSWORD"] = "test-password-for-admin-2026"


def request(path, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
        headers=dict({"Content-Type": "application/json"}, **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read().decode()
        return error.code, json.loads(raw) if raw else {}


status, health = request("/api/index")
check("le health check annonce les compteurs mémoire",
      status == 200 and health.get("stats_available") is True and
      health.get("stats_scope") == "instance-memory", health)

status, wrong_login = request("/admin/login", "POST", {"password": "incorrect"})
check("le mot de passe admin incorrect est refusé", status == 401, wrong_login)
status, unauthorized = request("/admin/stats")
check("les chiffres admin sont protégés", status == 401, unauthorized)
status, login = request("/admin/login", "POST", {"password": os.environ["ADMIN_PASSWORD"]})
token = login.get("token", "")
check("la connexion admin retourne un jeton signé", status == 200 and bool(token), login)
auth = {"Authorization": "Bearer " + token}

for action in ("page_view", "download_pdf", "download_docx", "letter_pdf"):
    status, result = request("/analytics/event", "POST", {"action": action})
    check("compte l'action %s" % action, status == 200 and result.get("ok"), result)

status, stats_response = request("/admin/stats", headers=auth)
stats = stats_response.get("stats", {})
check("l'admin expose exactement les quatre chiffres",
      status == 200 and set(stats) == {
          "visits", "cv_exports", "letter_exports", "total_exports"
      } and all(type(value) is int for value in stats.values()), stats)
check("les compteurs augmentent précisément en mémoire",
      stats == {"visits": 1, "cv_exports": 2, "letter_exports": 1, "total_exports": 3}, stats)

status, invalid = request("/analytics/event", "POST", {"action": "page_view", "page": "/app.html"})
check("l'API refuse les données de suivi supplémentaires", status == 400, invalid)
status, invalid_action = request("/analytics/event", "POST", {"action": "contact"})
check("l'API refuse une action non statistique", status == 400, invalid_action)
status, missing = request("/contact", "POST", {"email": "user@example.ci"})
check("aucune coordonnée ne peut être envoyée", status == 404, missing)
status, missing = request("/admin/contacts")
check("aucun endpoint d'historique de contacts ne subsiste", status == 404, missing)
status, missing = request("/admin/events", headers=auth)
check("aucun endpoint d'historique d'événements ne subsiste", status == 404, missing)

request("/analytics/event", "POST", {"action": "page_view"})
status, stats_response = request("/admin/stats", headers=auth)
check("un nouveau compteur apparaît sur la prochaine lecture admin",
      status == 200 and stats_response.get("stats", {}).get("visits") == 2, stats_response)

options = urllib.request.Request(base + "/analytics/event", method="OPTIONS",
    headers={"Origin": "http://localhost:8777"})
with urllib.request.urlopen(options, timeout=5) as response:
    check("CORS local autorise GET, POST et Authorization",
          response.headers.get("Access-Control-Allow-Methods") == "GET, POST, OPTIONS" and
          response.headers.get("Access-Control-Allow-Headers") == "Content-Type, Authorization")

if previous_password is None:
    os.environ.pop("ADMIN_PASSWORD", None)
else:
    os.environ["ADMIN_PASSWORD"] = previous_password
api.CORS_ORIGIN = previous_origin
server.shutdown()

server_source = read("server.py")
check("server.py réutilise l'API sans stockage SQLite",
      "api.handler" in server_source and "SQLite" not in server_source and
      "sqlite" not in server_source.lower())

print("\n%d contrôles de déploiement" % checks)
if fails:
    print("\n%d problème(s) :" % len(fails))
    for failure in fails[:30]:
        print("  ✗ " + failure)
    sys.exit(1)
print("  ✓ Routes, chiffres seulement, authentification et compteurs mémoire vérifiés\n")
