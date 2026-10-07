#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CV Studio — serveur local (API statistiques, contacts admin, /log/error).

Ce fichier ne contient aucune logique métier : les endpoints vivent dans
api/index.py, aussi exécuté sur Vercel. Une seule implémentation, deux
portes d'entrée.

--- Lancer ---
    python3 server.py
Écoute sur http://localhost:8788. Les statistiques et coordonnées sont
enregistrées dans le fichier SQLite cvstudio.sqlite3 (ou le chemin défini par
CVSTUDIO_DB_PATH).

--- En ligne ---
Vercel peut servir le site statique, mais le stockage SQLite local y est
désactivé : les statistiques et exports nécessitent le serveur local.
"""
import os, sys
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8788"))

# En local, le disque conserve la base SQLite et le journal errors.jsonl.
os.environ.setdefault("CVSTUDIO_DATA_DIR", ROOT)
# Le front local est servi sur un AUTRE port (8777) : autoriser uniquement
# cette origine permet les appels d'administration et bloque les autres sites.
os.environ.setdefault("CORS_ORIGIN", "http://localhost:8777,http://127.0.0.1:8777")

sys.path.insert(0, os.path.join(ROOT, "api"))
import index as api                       # noqa: E402  (le chemin doit précéder)

Handler = api.handler                     # même classe qu'en production

if __name__ == "__main__":
    print("CV Studio — serveur local sur http://localhost:%d" % PORT)
    print("  Endpoints : %s" % ", ".join(sorted(api.ROUTES)))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
