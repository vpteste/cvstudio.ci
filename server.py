#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CV Studio — serveur local (compteurs admin et /log/error).

Ce fichier ne contient aucune logique métier : les endpoints vivent dans
api/index.py, aussi exécuté sur Vercel. Une seule implémentation, deux
portes d'entrée.

--- Lancer ---
    python3 server.py
Écoute sur http://localhost:8788. Les compteurs sont stockés temporairement
en mémoire et repartent à zéro à l'arrêt du serveur.

--- En ligne ---
Vercel peut servir le site et expose également des compteurs en mémoire par
instance ; ils ne sont ni partagés ni durables.
"""
import os, sys
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8788"))

# Le journal d'erreurs local est conservé sur disque ; les statistiques non.
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
