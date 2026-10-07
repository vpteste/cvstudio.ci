#!/bin/bash
# Double-cliquez ce fichier pour lancer CV Studio dans le navigateur.
# Il sert le site en HTTP sur le port 8777 — le mode normal : ouvrir les
# fichiers directement (file://) fonctionne, mais le chargement des
# assets/*.data.js n'est garanti par aucun navigateur.
cd "$(dirname "$0")" || exit 1
PORT=8777
API_PORT=8788
API_SERVER=
SERVER=
ROOT="$(pwd)"

stop_servers() {
  [ -n "$SERVER" ] && kill "$SERVER" 2>/dev/null
  [ -n "$API_SERVER" ] && kill "$API_SERVER" 2>/dev/null
}
trap stop_servers EXIT INT TERM

# Démarre l'API locale pour les compteurs temporaires et le journal d'erreurs.
if ! curl -fsS "http://localhost:$API_PORT/api/index" >/dev/null ; then
  echo "Démarrage de l'API locale sur http://localhost:$API_PORT/ …"
  python3 server.py >"$ROOT/cvstudio-api.log" 2>&1 &
  API_SERVER=$!
  sleep 1
  if ! curl -fsS "http://localhost:$API_PORT/api/index" >/dev/null ; then
    echo "Impossible de démarrer l'API. Consultez cvstudio-api.log."
    exit 1
  fi
fi

# port déjà pris ? on ouvre simplement le navigateur sur le serveur existant
if ! curl -s -o /dev/null "http://localhost:$PORT/" ; then
  echo "Démarrage du serveur sur http://localhost:$PORT/ …"
  python3 -m http.server "$PORT" >/dev/null 2>&1 &
  SERVER=$!
  sleep 1
fi
open "http://localhost:$PORT/"
echo
echo "CV Studio tourne sur http://localhost:$PORT/"
echo "  ·  /app.html                 créer un CV"
echo "  ·  /lettre-de-motivation/    lettre de motivation (depuis le CV ouvert)"
echo "  ·  /admin/                   compteurs de statistiques"
echo
echo "Fermez cette fenêtre (ou Ctrl+C) pour arrêter le serveur."
if [ -n "$SERVER" ]; then
  wait "$SERVER"
elif [ -n "$API_SERVER" ]; then
  wait "$API_SERVER"
fi
