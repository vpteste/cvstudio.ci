#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CV Studio — proxy IA local (Mistral).

Ce fichier ne contient AUCUNE logique métier : les endpoints, les prompts et la
clé vivent dans api/index.py, qui est aussi la fonction serverless déployée sur
Vercel. Une seule implémentation, deux portes d'entrée — sans quoi les prompts
divergeraient entre le local et la production.

--- Où mettre la clé Mistral ? ---
Créez un fichier .env à côté de ce script (copie de .env.example) :
    MISTRAL_API_KEY=votre_cle_ici

--- Lancer ---
    python3 server.py
Écoute sur http://localhost:8788 (/ai/score, /ai/rewrite, /ai/cover-letter,
/lead, /log/error). Aucune dépendance externe.

--- En ligne ---
Rien à lancer : Vercel exécute api/index.py, et assets/config.js pointe
automatiquement sur le domaine courant. Voir la section « Déploiement » du README.
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
    print("CV Studio — proxy IA sur http://localhost:%d" % PORT)
    print("  Modèle : %s   |   Clé Mistral : %s"
          % (api.MODEL, "OK" if api.api_key() else "MANQUANTE (voir .env)"))
    print("  Endpoints : %s" % ", ".join(sorted(api.ROUTES)))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
