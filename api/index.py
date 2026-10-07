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

Les statistiques et coordonnées sont enregistrées dans SQLite sur le serveur
local. Le stockage durable nécessite de garder server.py en marche ; il n'est
pas disponible dans les fonctions serverless Vercel.
"""
import base64, contextlib, datetime, hashlib, hmac, json, os, re, sqlite3, time, uuid, urllib.parse
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Répertoire du journal d'erreurs local.
DATA_DIR = os.environ.get("CVSTUDIO_DATA_DIR", "").strip()

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


@contextlib.contextmanager
def database():
    if os.environ.get("VERCEL") == "1":
        raise ApiError(503, "Le stockage SQLite local est indisponible sur Vercel. Utilisez le serveur local.")
    path = os.environ.get("CVSTUDIO_DB_PATH", "").strip() or os.path.join(ROOT, "cvstudio.sqlite3")
    connection = None
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        connection = sqlite3.connect(path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS site_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                page TEXT NOT NULL,
                target TEXT NOT NULL DEFAULT '',
                session_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS site_events_created_at_idx
                ON site_events (created_at DESC);
            CREATE INDEX IF NOT EXISTS site_events_action_created_at_idx
                ON site_events (action, created_at DESC);
            CREATE TABLE IF NOT EXISTS download_contacts (
                id TEXT PRIMARY KEY,
                email TEXT,
                phone TEXT,
                source TEXT NOT NULL,
                page TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                CHECK (email IS NOT NULL OR phone IS NOT NULL)
            );
            CREATE INDEX IF NOT EXISTS download_contacts_created_at_idx
                ON download_contacts (created_at DESC);
        """)
        yield connection
        connection.commit()
    except sqlite3.Error as error:
        if connection:
            connection.rollback()
        print("[sqlite] erreur base locale : %s" % error, flush=True)
        raise ApiError(503, "La base de données locale est indisponible.")
    except OSError as error:
        print("[sqlite] accès au fichier de base refusé : %s" % error, flush=True)
        raise ApiError(503, "Le fichier de base locale ne peut pas être ouvert.")
    finally:
        if connection:
            connection.close()


EVENT_ACTIONS = {
    "page_view", "interface_action", "navigation", "cv_create", "cv_open",
    "cv_import", "template_select", "download_pdf", "download_docx", "download_json",
    "letter_pdf", "letter_docx", "contact_submitted", "form_change",
}


def safe_uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ApiError(400, "Identifiant de session invalide.")


def safe_page(value):
    page = str(value or "/")[:120]
    if not page.startswith("/") or "?" in page or "#" in page or "\\" in page:
        raise ApiError(400, "Page invalide.")
    if not re.fullmatch(r"/[a-zA-Z0-9_./-]*", page):
        raise ApiError(400, "Page invalide.")
    return page


def ep_analytics_event(body):
    action = str(body.get("action", ""))
    if action not in EVENT_ACTIONS:
        raise ApiError(400, "Action non autorisée.")
    target = str(body.get("target", ""))[:48]
    if target and not re.fullmatch(r"[a-zA-Z0-9_.:-]+", target):
        target = ""
    rec = {
        "action": action,
        "page": safe_page(body.get("page")),
        "target": target,
        "session_id": safe_uuid(body.get("session_id")),
    }
    rec["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with database() as db:
        db.execute(
            "INSERT INTO site_events (action, page, target, session_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (rec["action"], rec["page"], rec["target"], rec["session_id"], rec["created_at"]),
        )
    return {"ok": True}


def ep_contact(body):
    email = str(body.get("email", "")).strip().lower()[:180]
    phone = re.sub(r"[^\d+]", "", str(body.get("phone", "")))[:20]
    if email and not EMAIL_RE.match(email):
        raise ApiError(400, "Adresse email invalide.")
    digits = re.sub(r"\D", "", phone)
    if phone and (len(digits) < 8 or len(digits) > 15):
        raise ApiError(400, "Numéro de téléphone invalide.")
    if not email and not phone:
        raise ApiError(400, "Saisissez une adresse email ou un numéro de téléphone.")
    source = str(body.get("source", "cv"))
    if source not in ("download_pdf", "download_docx", "download_json", "letter_pdf", "letter_docx", "cv", "letter"):
        raise ApiError(400, "Origine du téléchargement invalide.")
    rec = {
        "id": str(uuid.uuid4()),
        "email": email or None,
        "phone": phone or None,
        "source": source,
        "page": safe_page(body.get("page")),
        "request_id": safe_uuid(body.get("request_id")),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    with database() as db:
        db.execute(
            """INSERT OR IGNORE INTO download_contacts
               (id, email, phone, source, page, request_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (rec["id"], rec["email"], rec["phone"], rec["source"], rec["page"],
             rec["request_id"], rec["created_at"]),
        )
    return {"ok": True}


def _admin_stats():
    with database() as db:
        counts = db.execute("""
            SELECT count(*) AS events_total,
                   count(*) FILTER (WHERE action = 'page_view') AS page_views_total,
                   count(DISTINCT session_id) FILTER (WHERE action = 'page_view') AS visitors_total,
                   count(*) FILTER (WHERE action IN
                       ('download_pdf', 'download_docx', 'download_json', 'letter_pdf', 'letter_docx')) AS downloads_total,
                   count(*) FILTER (WHERE julianday(created_at) >= julianday('now', '-30 days')) AS events_30_days,
                   count(*) FILTER (WHERE action = 'page_view' AND julianday(created_at) >= julianday('now', '-30 days')) AS page_views_30_days,
                   count(*) FILTER (WHERE action IN
                       ('download_pdf', 'download_docx', 'download_json', 'letter_pdf', 'letter_docx')
                       AND julianday(created_at) >= julianday('now', '-30 days')) AS downloads_30_days
            FROM site_events
        """).fetchone()
        contacts_total = db.execute("SELECT count(*) FROM download_contacts").fetchone()[0]
        action_counts = {
            row["action"]: row["total"]
            for row in db.execute("SELECT action, count(*) AS total FROM site_events GROUP BY action")
        }
        daily_rows = db.execute("""
            SELECT date(created_at) AS day,
                   count(*) FILTER (WHERE action = 'page_view') AS visits,
                   count(*) FILTER (WHERE action IN
                       ('download_pdf', 'download_docx', 'download_json', 'letter_pdf', 'letter_docx')) AS downloads
            FROM site_events
            WHERE date(created_at) >= date('now', '-29 days')
            GROUP BY date(created_at)
        """).fetchall()
    by_day = {row["day"]: row for row in daily_rows}
    today = datetime.datetime.now(datetime.timezone.utc).date()
    daily = []
    for days_ago in range(29, -1, -1):
        day = (today - datetime.timedelta(days=days_ago)).isoformat()
        row = by_day.get(day)
        daily.append({
            "day": day,
            "visits": row["visits"] if row else 0,
            "downloads": row["downloads"] if row else 0,
        })
    return dict(counts), contacts_total, action_counts, daily


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


def _admin_offset(request):
    raw = urllib.parse.parse_qs(urllib.parse.urlsplit(request.path).query).get("offset", ["0"])[0]
    try:
        offset = int(raw)
    except (TypeError, ValueError):
        raise ApiError(400, "Page demandée invalide.")
    if offset < 0 or offset > 1_000_000:
        raise ApiError(400, "Page demandée invalide.")
    return offset


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
    counts, contacts_total, action_counts, daily = _admin_stats()
    stats = dict(counts)
    stats.update(contacts_total=contacts_total, action_counts=action_counts, daily=daily)
    return {"ok": True, "stats": stats}


def ep_admin_events(body, request):
    del body
    _admin_authenticated(request)
    offset = _admin_offset(request)
    with database() as db:
        events = [dict(row) for row in db.execute(
            "SELECT id, action, page, target, created_at FROM site_events "
            "ORDER BY created_at DESC, id DESC LIMIT 200 OFFSET ?", (offset,)
        )]
    return {"ok": True, "events": events, "offset": offset, "has_more": len(events) == 200}


def ep_admin_contacts(body, request):
    del body
    _admin_authenticated(request)
    offset = _admin_offset(request)
    with database() as db:
        contacts = [dict(row) for row in db.execute(
            "SELECT id, email, phone, source, page, created_at FROM download_contacts "
            "ORDER BY created_at DESC, id DESC LIMIT 100 OFFSET ?", (offset,)
        )]
    return {"ok": True, "contacts": contacts, "offset": offset, "has_more": len(contacts) == 100}


def ep_admin_delete_contact(body, request):
    _admin_authenticated(request)
    contact_id = str(body.get("id", ""))
    try:
        contact_id = str(uuid.UUID(contact_id))
    except (ValueError, TypeError, AttributeError):
        raise ApiError(400, "Identifiant de contact invalide.")
    with database() as db:
        db.execute("DELETE FROM download_contacts WHERE id = ?", (contact_id,))
    return {"ok": True}


# Clé = nom de route passé par vercel.json (?route=…) ET chemin public utilisé
# par le front. Les deux formes résolvent vers la même fonction, cf. resolve().
ROUTES = {
    "/log/error": ep_log_error,
    "/analytics/event": ep_analytics_event,
    "/contact": ep_contact,
    "/admin/login": ep_admin_login,
    "/admin/stats": ep_admin_stats,
    "/admin/events": ep_admin_events,
    "/admin/contacts": ep_admin_contacts,
    "/admin/contact-delete": ep_admin_delete_contact,
}

ALIASES = {
    "log-error": "/log/error",
    "analytics-event": "/analytics/event",
    "contact": "/contact",
    "admin-login": "/admin/login",
    "admin-stats": "/admin/stats",
    "admin-events": "/admin/events",
    "admin-contacts": "/admin/contacts",
    "admin-contact-delete": "/admin/contact-delete",
}

ADMIN_ROUTES = {ep_admin_login, ep_admin_stats, ep_admin_events, ep_admin_contacts, ep_admin_delete_contact}
GET_ROUTES = {ep_admin_stats, ep_admin_events, ep_admin_contacts}


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
        if urllib.parse.urlsplit(self.path).path in ("/", "/api/index"):
            return self._json(200, {"ok": True, "service": "CV Studio",
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
