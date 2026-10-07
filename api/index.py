#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CV Studio — endpoints serveur.

SOURCE UNIQUE de la logique serveur. Deux portes d'entrée, un seul code :
  · en ligne : Vercel importe la classe `handler` ci-dessous. C'est la fonction
               serverless /api/index ; les URL publiques (/lead, /log/error) y
               arrivent via les `rewrites` de vercel.json, qui passent la route
               en query (?route=lead).
  · en local : server.py importe ROUTES et sert le tout sur http://localhost:8788.

Ne dupliquez pas la logique de ROUTES dans server.py.

--- Écritures disque ---
Vercel monte un système de fichiers EN LECTURE SEULE : /lead et /log/error ne
peuvent pas y écrire de fichier. Ils écrivent donc sur la sortie standard
(Observability → Logs, exportable par un Log Drain), et /lead peut en plus
recopier l'inscription vers LEAD_WEBHOOK_URL. En local, server.py définit
CVSTUDIO_DATA_DIR et on retrouve leads.jsonl / errors.jsonl comme avant.
"""
import datetime, json, os, re, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Répertoire où écrire leads.jsonl / errors.jsonl. Vide = pas d'écriture disque
# (cas Vercel) : server.py le renseigne, la fonction serverless jamais.
DATA_DIR = os.environ.get("CVSTUDIO_DATA_DIR", "").strip()

# Recopie facultative des inscriptions vers un service externe (Formspree, Zapier,
# Make, un webhook Slack…). Sans lui, en ligne, un lead ne vit que dans les logs.
LEAD_WEBHOOK_URL = os.environ.get("LEAD_WEBHOOK_URL", "").strip()

# Origines autorisées à appeler l'API depuis un AUTRE domaine. Vide = aucune :
# le front est servi par le même domaine, il n'a pas besoin de CORS, et fermer
# par défaut évite qu'un site tiers fasse tourner la facture API.
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "").strip()

MAX_BODY = 256 * 1024          # limite les corps des requêtes publiques
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[a-zA-Z]{2,}$")


def load_env():
    """Lit .env (KEY=VALUE) sans écraser l'environnement. Inutile sur Vercel,
    indispensable en local — le fichier n'est jamais déployé (.vercelignore)."""
    p = os.path.join(ROOT, ".env")
    if not os.path.exists(p):
        return
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()


# ---------------------------------------------------------------- endpoints
def ep_lead(body):
    """Enregistre un email volontairement laissé après un téléchargement.

    RGPD : on garde la date et la source du consentement — rien d'autre, et
    surtout AUCUNE donnée du CV.

    Destinations, dans l'ordre : leads.jsonl si CVSTUDIO_DATA_DIR est défini
    (local), la sortie standard toujours (seule trace en ligne), et
    LEAD_WEBHOOK_URL s'il est renseigné (seule persistance durable en ligne).
    """
    email = str(body.get("email", "")).strip().lower()[:180]
    if not EMAIL_RE.match(email):
        # on lève : le handler répond alors en erreur HTTP, et le front ne peut
        # pas confondre un refus de validation avec une inscription réussie
        raise RuntimeError("Adresse email invalide")
    rec = {"email": email,
           "source": str(body.get("source", ""))[:60],
           "consent": "bouton « Me tenir au courant » après téléchargement",
           "at": datetime.datetime.now().isoformat(timespec="seconds")}

    if DATA_DIR:
        path = os.path.join(DATA_DIR, "leads.jsonl")
        if os.path.exists(path):                      # pas de doublon
            for line in open(path, encoding="utf-8"):
                try:
                    if json.loads(line).get("email") == email:
                        return {"ok": True, "already": True}
                except Exception:
                    continue
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("[lead] " + json.dumps(rec, ensure_ascii=False), flush=True)

    if LEAD_WEBHOOK_URL:
        # jamais bloquant : un webhook en panne ne doit pas transformer une
        # inscription réussie en message d'erreur à l'utilisateur
        try:
            req = urllib.request.Request(
                LEAD_WEBHOOK_URL, data=json.dumps(rec).encode("utf-8"),
                method="POST", headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=8).read()
        except Exception as e:
            print("[lead] webhook KO : %s" % e, flush=True)

    return {"ok": True}


def ep_log_error(body):
    """Journalise une erreur client.

    Ne contient jamais de données de CV : le front n'envoie que message, pile,
    page et user-agent. En local : errors.jsonl (tail -f). En ligne : les logs
    de la fonction, qui sont justement faits pour ça.
    """
    keep = ("where", "message", "stack", "page", "ua", "v", "at")
    rec = {k: str(body.get(k, ""))[:1500] for k in keep}
    rec["received"] = datetime.datetime.now().isoformat(timespec="seconds")

    if DATA_DIR:
        path = os.path.join(DATA_DIR, "errors.jsonl")
        if os.path.exists(path) and os.path.getsize(path) > 5 * 1024 * 1024:
            os.replace(path, path + ".1")          # rotation simple
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("[erreur client] %s — %s" % (rec["where"], rec["message"][:200]), flush=True)
    return {"ok": True}


# Clé = nom de route passé par vercel.json (?route=…) ET chemin public utilisé
# par le front. Les deux formes résolvent vers la même fonction, cf. resolve().
ROUTES = {
    "/log/error": ep_log_error,
    "/lead": ep_lead,
}

ALIASES = {"log-error": "/log/error", "lead": "/lead"}


def resolve(path):
    """Retrouve l'endpoint depuis une URL, quelle que soit la porte d'entrée.

    Vercel réécrit les chemins publics en /api/index?route=... : le chemin
    d'origine est perdu, seul le paramètre `route` fait foi. En local, server.py appelle avec
    le chemin public. On accepte les deux — et la barre finale, que l'option
    trailingSlash de vercel.json peut ajouter.
    """
    parts = urllib.parse.urlsplit(path)
    route = urllib.parse.parse_qs(parts.query).get("route", [""])[0]
    if route in ALIASES:
        return ROUTES[ALIASES[route]]
    clean = parts.path.rstrip("/") or "/"
    return ROUTES.get(clean)


class handler(BaseHTTPRequestHandler):
    """Contrat de la runtime Python de Vercel : une classe nommée `handler`."""

    def _cors(self):
        # Par défaut AUCUN en-tête CORS : le front est sur le même domaine.
        # Un site tiers ne peut donc pas faire tourner la facture API depuis
        # un navigateur. CORS_ORIGIN ouvre explicitement si besoin.
        if CORS_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code); self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def _origin_ok(self):
        """Refuse un appel de navigateur venu d'un autre site.

        Ne protège pas d'un curl (rien ne le peut sans authentification) mais
        ferme le cas réel : une page tierce qui appelle l'API gratuitement.
        """
        origin = self.headers.get("Origin")
        if not origin or CORS_ORIGIN in ("*", origin):
            return True
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or ""
        return urllib.parse.urlsplit(origin).netloc == host

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        self._json(200, {"ok": True, "service": "CV Studio",
                         "endpoints": sorted(ROUTES.keys())})

    def do_POST(self):
        if not self._origin_ok():
            return self._json(403, {"error": "Origine non autorisée"})
        fn = resolve(self.path)
        if not fn:
            return self._json(404, {"error": "Endpoint inconnu"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n > MAX_BODY:
                return self._json(413, {"error": "Requête trop volumineuse"})
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            if not isinstance(body, dict):
                raise ValueError("objet attendu")
        except Exception:
            return self._json(400, {"error": "Requête JSON invalide"})
        try:
            return self._json(200, fn(body))
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def log_message(self, *a):  # silencieux : Vercel journalise déjà les requêtes
        pass
