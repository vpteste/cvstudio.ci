#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CV Studio — endpoints serveur.

SOURCE UNIQUE de la logique serveur. Deux portes d'entrée, un seul code :
  · en ligne : Vercel importe la classe `handler` ci-dessous. C'est la fonction
               serverless /api/index ; les routes publiques et admin y
               arrivent via les rewrites de vercel.json.
  · en local : server.py importe ROUTES et sert le tout sur http://localhost:8788.

Ne dupliquez pas la logique de ROUTES dans server.py.

Les statistiques sont des compteurs en mémoire uniquement ; aucune coordonnée
ni aucun historique n'est conservé. En serverless, les chiffres sont
approximatifs, propres à chaque instance et réinitialisés à son redémarrage.
"""
import base64, datetime, hashlib, hmac, json, os, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Répertoire du journal d'erreurs local.
DATA_DIR = os.environ.get("CVSTUDIO_DATA_DIR", "").strip()

# Origines autorisées à appeler l'API depuis un AUTRE domaine. Vide = aucune :
# le front est servi par le même domaine, il n'a pas besoin de CORS, et fermer
# par défaut évite qu'un site tiers fasse tourner la facture API.
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "").strip()

MAX_BODY = 256 * 1024          # limite les corps des requêtes publiques
STATS_LOCK = threading.Lock()
STATS = {"visits": 0, "cv_exports": 0, "letter_exports": 0}


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


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


EVENT_ACTIONS = {
    "page_view", "download_pdf", "download_docx", "download_json", "letter_pdf", "letter_docx",
}


def ep_analytics_event(body):
    if set(body) != {"action"}:
        raise ApiError(400, "Seule l'action statistique est acceptée.")
    action = str(body.get("action", ""))
    if action not in EVENT_ACTIONS:
        raise ApiError(400, "Action non autorisée.")
    with STATS_LOCK:
        if action == "page_view":
            STATS["visits"] += 1
        elif action in ("download_pdf", "download_docx", "download_json"):
            STATS["cv_exports"] += 1
        elif action in ("letter_pdf", "letter_docx"):
            STATS["letter_exports"] += 1
    return {"ok": True}


def _b64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _admin_password():
    return os.environ.get("ADMIN_PASSWORD", "")


def _sign_admin_token(expires):
    password = _admin_password().encode("utf-8")
    payload = _b64url(str(expires).encode("ascii"))
    signature = _b64url(hmac.new(password, payload.encode("ascii"), hashlib.sha256).digest())
    return payload + "." + signature


def _admin_authenticated(request):
    password = _admin_password()
    if not password:
        raise ApiError(503, "L'accès admin n'est pas configuré.")
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else ""
    try:
        payload, signature = token.split(".", 1)
        expires = int(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode("ascii"))
        expected = _sign_admin_token(expires)
    except (ValueError, TypeError, UnicodeError):
        raise ApiError(401, "Session admin invalide ou expirée.")
    if not hmac.compare_digest(token, expected) or expires < int(time.time()):
        raise ApiError(401, "Session admin invalide ou expirée.")


def ep_admin_login(body, request):
    del request
    password = _admin_password()
    if not password:
        raise ApiError(503, "Configurez ADMIN_PASSWORD dans les variables secrètes du serveur.")
    if len(password) < 16:
        raise ApiError(503, "ADMIN_PASSWORD doit contenir au moins 16 caractères.")
    supplied = str(body.get("password", ""))[:256]
    if not hmac.compare_digest(supplied, password):
        raise ApiError(401, "Mot de passe incorrect.")
    expires = int(time.time()) + 8 * 60 * 60
    return {"ok": True, "token": _sign_admin_token(expires), "expires_at": expires}


def ep_admin_stats(body, request):
    del body
    _admin_authenticated(request)
    with STATS_LOCK:
        stats = dict(STATS)
    stats["total_exports"] = stats["cv_exports"] + stats["letter_exports"]
    return {"ok": True, "stats": stats}


# Clé = nom de route passé par vercel.json (?route=…) ET chemin public utilisé
# par le front. Les deux formes résolvent vers la même fonction, cf. resolve().
ROUTES = {
    "/log/error": ep_log_error,
    "/analytics/event": ep_analytics_event,
    "/admin/login": ep_admin_login,
    "/admin/stats": ep_admin_stats,
}

ALIASES = {
    "log-error": "/log/error",
    "analytics-event": "/analytics/event",
    "admin-login": "/admin/login",
    "admin-stats": "/admin/stats",
}

ADMIN_ROUTES = {ep_admin_login, ep_admin_stats}
GET_ROUTES = {ep_admin_stats}


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
        # Le serveur local autorise seulement le site servi sur le port 8777.
        origin = self.headers.get("Origin", "")
        allowed_origins = {value.strip() for value in CORS_ORIGIN.split(",") if value.strip()}
        if "*" in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin and origin in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
        if allowed_origins and (origin in allowed_origins or "*" in allowed_origins):
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

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
        allowed_origins = {value.strip() for value in CORS_ORIGIN.split(",") if value.strip()}
        if not origin or "*" in allowed_origins or origin in allowed_origins:
            return True
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or ""
        return urllib.parse.urlsplit(origin).netloc == host

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        fn = resolve(self.path)
        if fn in GET_ROUTES:
            if not self._origin_ok():
                return self._json(403, {"error": "Origine non autorisée"})
            try:
                return self._json(200, fn({}, self))
            except ApiError as e:
                return self._json(e.status, {"error": str(e)})
            except Exception as e:
                print("[api] %s" % e, flush=True)
                return self._json(500, {"error": "Erreur serveur."})
        if urllib.parse.urlsplit(self.path).path in ("/", "/api/index", "/api/index/"):
            return self._json(200, {"ok": True, "service": "CV Studio",
                                    "stats_available": True,
                                    "stats_scope": "instance-memory",
                                    "endpoints": sorted(ROUTES.keys())})
        return self._json(404, {"error": "Endpoint inconnu"})

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
            result = fn(body, self) if fn in ADMIN_ROUTES else fn(body)
            return self._json(200, result)
        except ApiError as e:
            return self._json(e.status, {"error": str(e)})
        except Exception as e:
            print("[api] %s" % e, flush=True)
            return self._json(500, {"error": "Erreur serveur."})

    def log_message(self, *a):  # silencieux : Vercel journalise déjà les requêtes
        pass
