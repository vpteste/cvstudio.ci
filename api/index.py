#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CV Studio — endpoints IA (Mistral).

SOURCE UNIQUE de la logique serveur. Deux portes d'entrée, un seul code :
  · en ligne : Vercel importe la classe `handler` ci-dessous. C'est la fonction
               serverless /api/index ; les URL publiques (/ai/score, /lead…) y
               arrivent via les `rewrites` de vercel.json, qui passent la route
               en query (?route=score).
  · en local : server.py importe ROUTES et sert le tout sur http://localhost:8788.

Ne dupliquez JAMAIS un prompt dans server.py : ils vivent ici et nulle part ailleurs.

--- La clé Mistral ---
Elle reste côté serveur, jamais dans le navigateur.
  · en local  : fichier .env  →  MISTRAL_API_KEY=...
  · sur Vercel: Settings → Environment Variables → MISTRAL_API_KEY (chiffrée)

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
MODEL = os.environ.get("MISTRAL_MODEL", "mistral-large-latest")

# Répertoire où écrire leads.jsonl / errors.jsonl. Vide = pas d'écriture disque
# (cas Vercel) : server.py le renseigne, la fonction serverless jamais.
DATA_DIR = os.environ.get("CVSTUDIO_DATA_DIR", "").strip()

# Recopie facultative des inscriptions vers un service externe (Formspree, Zapier,
# Make, un webhook Slack…). Sans lui, en ligne, un lead ne vit que dans les logs.
LEAD_WEBHOOK_URL = os.environ.get("LEAD_WEBHOOK_URL", "").strip()

# Origines autorisées à appeler l'API depuis un AUTRE domaine. Vide = aucune :
# le front est servi par le même domaine, il n'a pas besoin de CORS, et fermer
# par défaut évite qu'un site tiers fasse tourner la facture Mistral.
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "").strip()

MAX_BODY = 256 * 1024          # 256 Ko : un CV JSON pèse quelques dizaines de Ko


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


def api_key():
    # lue à chaque appel : sur Vercel la variable arrive par l'environnement de
    # la fonction, et une lecture au chargement du module la figerait au premier
    # démarrage de l'instance (redéploiement d'env sans rebuild).
    return os.environ.get("MISTRAL_API_KEY", "").strip()


def mistral(messages, temperature=0.4, json_mode=False):
    """Appelle l'API Mistral et renvoie le contenu texte de la réponse."""
    key = api_key()
    if not key:
        raise RuntimeError("Clé Mistral absente : renseignez MISTRAL_API_KEY "
                           "(.env en local, variables d'environnement sur Vercel)")
    payload = {"model": MODEL, "messages": messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        "https://api.mistral.ai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        # 45 s : sous les 60 s de maxDuration (vercel.json), pour que la fonction
        # rende une vraie erreur JSON plutôt que de se faire tuer par la plateforme.
        with urllib.request.urlopen(req, timeout=45) as r:
            j = json.loads(r.read().decode("utf-8"))
        return j["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError("Mistral %s : %s" % (e.code, detail))


def strip_md(text):
    """Retire la mise en forme Markdown (gras, titres) pour un rendu propre en CV/lettre."""
    t = (text or "").strip().replace("**", "").replace("__", "")
    out = []
    for l in t.split("\n"):
        s = l.strip()
        out.append(s.lstrip("#").strip() if s.startswith("#") else l)
    return "\n".join(out).strip()


# ---------------------------------------------------------------- endpoints
def ep_score(body):
    data = body.get("data", {})
    job = (body.get("job") or "").strip()
    sys = ("Tu es un expert en recrutement et en systèmes ATS (tri automatique de CV). "
           "Tu notes des CV de façon exigeante mais juste, et tu réponds STRICTEMENT en JSON.")
    ask = (
        "Analyse ce CV (données JSON ci-dessous)"
        + (" au regard de cette offre d'emploi :\n\"\"\"" + job[:2000] + "\"\"\"\n" if job else ".\n")
        + "Attribue une note de 0 à 100 pour chacun des axes : ats (compatibilité mots-clés/structure), "
          "readability (lisibilité), experience (qualité et impact des expériences), skills (pertinence des compétences), "
          "presentation (complétude et clarté). Calcule un score global cohérent. "
          "Donne de 2 à 6 recommandations concrètes et actionnables, en français, classées par impact. "
          "Réponds UNIQUEMENT avec un objet JSON de la forme : "
          '{"scores":{"ats":int,"readability":int,"experience":int,"skills":int,"presentation":int,"global":int},'
          '"recommendations":[string,...]}.\n\nCV JSON :\n' + json.dumps(data, ensure_ascii=False)[:6000]
    )
    out = mistral([{"role": "system", "content": sys}, {"role": "user", "content": ask}],
                  temperature=0.2, json_mode=True)
    r = json.loads(out)
    sc = r.get("scores", {})
    clip = lambda v: max(0, min(100, int(round(float(v))))) if isinstance(v, (int, float)) else 0
    scores = {k: clip(sc.get(k, 0)) for k in ("ats", "readability", "experience", "skills", "presentation", "global")}
    if not scores["global"]:
        scores["global"] = clip(sum(scores[k] for k in ("ats", "readability", "experience", "skills", "presentation")) / 5)
    recs = [str(x) for x in (r.get("recommendations") or [])][:6]
    return {"scores": scores, "recommendations": recs, "source": "mistral"}


def ep_rewrite(body):
    role = body.get("role", ""); company = body.get("company", ""); rough = body.get("rough", "")
    sys = "Tu es un coach carrière. Tu rédiges des descriptions d'expérience professionnelle percutantes pour un CV, en français."
    ask = ("Rédige la description d'une expérience pour un CV, sous forme de 3 à 4 puces commençant par '• ', "
           "des verbes d'action et si possible des résultats chiffrés. Poste : %s. Entreprise : %s. "
           "Éléments fournis (à reformuler, ne rien inventer de faux) : %s. "
           "Réponds UNIQUEMENT par les puces, sans introduction, en texte brut : "
           "AUCUNE mise en forme Markdown, aucun astérisque, aucun gras." % (role, company, rough))
    text = mistral([{"role": "system", "content": sys}, {"role": "user", "content": ask}], temperature=0.5)
    return {"text": strip_md(text)}


def ep_cover_letter(body):
    sys = "Tu es un expert en candidatures. Tu rédiges des lettres de motivation professionnelles, sincères et concises, en français."
    ask = ("Rédige une lettre de motivation (250-320 mots) pour la candidature suivante. "
           "Candidat : %s, %s. Poste visé : %s chez %s. "
           "Résumé du profil : %s. Expériences (JSON) : %s. "
           % (body.get("name", ""), body.get("title", ""), body.get("poste", ""), body.get("entreprise", ""),
              body.get("summary", ""), json.dumps(body.get("experiences", []), ensure_ascii=False)[:2500]))
    offre = (body.get("offre") or "").strip()
    if offre:
        ask += "Offre d'emploi à cibler :\n\"\"\"" + offre[:2000] + "\"\"\"\n"
    ask += ("Structure : commence DIRECTEMENT par 'Madame, Monsieur,', puis accroche, adéquation profil/poste, "
            "motivation pour l'entreprise, formule de politesse. "
            "N'invente AUCUNE coordonnée, n'utilise AUCUN crochet [ ] ni champ à remplir, "
            "aucun en-tête d'adresse/date, aucune mise en forme Markdown (pas d'astérisques).")
    text = mistral([{"role": "system", "content": sys}, {"role": "user", "content": ask}], temperature=0.6)
    return {"text": strip_md(text)}


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[a-zA-Z]{2,}$")


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
ROUTES = {"/ai/score": ep_score, "/ai/rewrite": ep_rewrite, "/ai/cover-letter": ep_cover_letter,
          "/log/error": ep_log_error, "/lead": ep_lead}

ALIASES = {"score": "/ai/score", "rewrite": "/ai/rewrite", "cover-letter": "/ai/cover-letter",
           "log-error": "/log/error", "lead": "/lead"}


def resolve(path):
    """Retrouve l'endpoint depuis une URL, quelle que soit la porte d'entrée.

    Vercel réécrit /ai/score en /api/index?route=score : le chemin d'origine est
    perdu, seul le paramètre `route` fait foi. En local, server.py appelle avec
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
        # Un site tiers ne peut donc pas faire tourner la facture Mistral depuis
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
        ferme le cas réel : une page tierce qui appelle notre IA gratuitement.
        """
        origin = self.headers.get("Origin")
        if not origin or CORS_ORIGIN in ("*", origin):
            return True
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or ""
        return urllib.parse.urlsplit(origin).netloc == host

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        self._json(200, {"ok": True, "service": "CV Studio AI proxy",
                         "model": MODEL, "key": bool(api_key()),
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
