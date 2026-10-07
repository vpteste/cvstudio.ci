#!/bin/bash
# Double-cliquez ce fichier pour lancer CV Studio dans le navigateur.
# Il sert le site en HTTP sur le port 8777 — le mode normal : ouvrir les
# fichiers directement (file://) fonctionne, mais le chargement des
# assets/*.data.js n'est garanti par aucun navigateur.
cd "$(dirname "$0")" || exit 1
PORT=8777
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
echo
echo "Fermez cette fenêtre (ou Ctrl+C) pour arrêter le serveur."
[ -n "$SERVER" ] && wait "$SERVER"
