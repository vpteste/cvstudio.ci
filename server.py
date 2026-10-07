#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CV Studio — serveur local (API /lead, /log/error).

Ce fichier ne contient aucune logique métier : les endpoints vivent dans
api/index.py, aussi exécuté sur Vercel. Une seule implémentation, deux
portes d'entrée.

--- Lancer ---
    python3 server.py
Écoute sur http://localhost:8788 (/lead, /log/error). Aucune dépendance
externe.

--- En ligne ---
Rien à lancer : Vercel exécute api/index.py.
"""
import os, sys
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8788"))

# En local le disque est accessible : on réactive leads.jsonl et errors.jsonl,
# que la fonction serverless ne peut pas écrire (FS en lecture seule chez Vercel).
os.environ.setdefault("CVSTUDIO_DATA_DIR", ROOT)
# Le front local est servi sur un AUTRE port (8777) : sans CORS, le navigateur
# bloquerait l'appel. En ligne, front et API partagent le domaine — pas de CORS.
os.environ.setdefault("CORS_ORIGIN", "*")

sys.path.insert(0, os.path.join(ROOT, "api"))
import index as api                       # noqa: E402  (le chemin doit précéder)

Handler = api.handler                     # même classe qu'en production

if __name__ == "__main__":
    print("CV Studio — serveur local sur http://localhost:%d" % PORT)
    print("  Endpoints : %s" % ", ".join(sorted(api.ROUTES)))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
