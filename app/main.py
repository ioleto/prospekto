import csv, hmac, io, os, secrets, time
from datetime import datetime, timezone
from html import escape
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet
import psycopg
from psycopg.rows import dict_row

app = FastAPI(title="Prospekto", version="0.4.0")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", ""), same_site="lax", https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true", max_age=3600)
PH = PasswordHasher()
LOGIN_ATTEMPTS = {}


def conn():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url or not url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL must be a PostgreSQL URL")
    return psycopg.connect(url, row_factory=dict_row)


def now():
    return datetime.now(timezone.utc)


def csrf(request):
    token = request.session.get("csrf") or secrets.token_urlsafe(24)
    request.session["csrf"] = token
    return token


def require_csrf(request, supplied):
    if not supplied or not hmac.compare_digest(csrf(request), supplied):
        raise HTTPException(403, "CSRF")


def guard(request):
    if not request.session.get("admin"):
        raise HTTPException(401, "Authentification requise")


def password_hash():
    value = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
    if value.startswith("$argon2"):
        return value
    bootstrap = os.getenv("ADMIN_PASSWORD_BOOTSTRAP", "")
    return PH.hash(bootstrap) if bootstrap else ""


def valid_password(candidate):
    try:
        stored = password_hash()
        return bool(stored) and PH.verify(stored, candidate)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def page(title, body, request):
    nav = '<a href="/">Tableau</a> <a href="/campaigns">Campagnes</a> <a href="/prospects">Prospects</a> <a href="/smtp-profiles">SMTP</a>'
    if request.session.get("admin"):
        nav += ' <a href="/logout">Déconnexion</a>'
    return HTMLResponse(f'<!doctype html><html lang="fr"><meta name="viewport" content="width=device-width"><title>{escape(title)} · Prospekto</title><style>body{{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;background:#f7f8fa;color:#18212b}}nav{{display:flex;gap:1rem;flex-wrap:wrap}}a,button{{color:#075985}}.card{{background:white;padding:1rem;margin:1rem 0;border-radius:10px}}input,textarea,select{{padding:.6rem;margin:.2rem;width:min(100%,34rem)}}.danger{{color:#b91c1c}}</style><nav>{nav}</nav><main><h1>{escape(title)}</h1>{body}</main></html>', headers={"X-Content-Type-Options":"nosniff", "X-Frame-Options":"DENY", "Referrer-Policy":"no-referrer"})


@app.get("/health")
def health():
    try:
        with conn() as c:
            c.execute("SELECT 1")
        return {"status": "ok", "app": "prospekto", "runtime": "postgresql"}
    except Exception:
        raise HTTPException(503, "database unavailable")


@app.get("/login", response_class=HTMLResponse)
def login(request: Request):
    return page("Connexion", f'<form method="post"><input name="username" placeholder="Identifiant"><input name="password" type="password" placeholder="Mot de passe"><input type="hidden" name="csrf" value="{csrf(request)}"><button>Se connecter</button></form>', request)


@app.post("/login")
def do_login(request: Request, username: str = Form(), password: str = Form(), csrf_token: str | None = Form(None, alias="csrf")):
    require_csrf(request, csrf_token)
    key = str(request.client.host if request.client else "unknown")
    attempts = [x for x in LOGIN_ATTEMPTS.get(key, []) if time.time() - x < 600]
    if len(attempts) >= 10:
        raise HTTPException(429, "Trop de tentatives")
    if not hmac.compare_digest(username, os.getenv("ADMIN_USERNAME", "admin")) or not valid_password(password):
        LOGIN_ATTEMPTS[key] = attempts + [time.time()]
        raise HTTPException(401, "Identifiants invalides")
    request.session.clear(); request.session["admin"] = username; request.session["csrf"] = secrets.token_urlsafe(24)
    return RedirectResponse("/", 303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear(); return RedirectResponse("/login", 303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    guard(request)
    with conn() as c:
        camps = c.execute("SELECT count(*) AS n FROM campaigns").fetchone()["n"]
        pros = c.execute("SELECT count(*) AS n FROM prospects WHERE deleted_at IS NULL AND status <> 'opposed'").fetchone()["n"]
    return page("Tableau de bord", f'<div class="card"><b>{camps}</b> campagnes · <b>{pros}</b> prospects actifs</div><p>Envoi réel, collecte, IA et connecteurs : désactivés par défaut.</p>', request)


@app.get("/campaigns", response_class=HTMLResponse)
def campaigns(request: Request):
    guard(request)
    with conn() as c: rows = c.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()
    items = "".join(f'<li><a href="/campaigns/{escape(r["id"])}">{escape(r["name"])}</a> — {escape(r["status"])}</li>' for r in rows)
    return page("Campagnes", f'<form method="post"><input name="name" required placeholder="Nom de campagne"><input type="hidden" name="csrf" value="{csrf(request)}"><button>Créer</button></form><ul>{items}</ul>', request)


@app.post("/campaigns")
def create_campaign(request: Request, name: str = Form(), csrf_token: str | None = Form(None, alias="csrf")):
    guard(request); require_csrf(request, csrf_token); name = name.strip()
    if not name: raise HTTPException(422, "Nom obligatoire")
    with conn() as c: c.execute("INSERT INTO campaigns (id,name,status,created_at) VALUES (%s,%s,%s,%s)", (secrets.token_hex(8), name, "draft", now()))
    return RedirectResponse("/campaigns", 303)


@app.get("/prospects", response_class=HTMLResponse)
def prospects(request: Request):
    guard(request)
    with conn() as c: rows = c.execute("SELECT * FROM prospects WHERE deleted_at IS NULL AND status <> 'opposed' ORDER BY created_at DESC").fetchall()
    items = "".join(f'<li>{escape(r["company_name"])} — {escape(r["email"] or "sans email")} — {escape(r["provenance"])} <form style="display:inline" method="post" action="/prospects/{r["id"]}/opposition"><input type="hidden" name="csrf" value="{csrf(request)}"><button class="danger">Marquer opposition</button></form></li>' for r in rows)
    body = f'<form method="post"><input name="company_name" required placeholder="Entreprise"><input name="email" placeholder="Email"><input name="provenance" required placeholder="Provenance documentée"><input type="hidden" name="csrf" value="{csrf(request)}"><button>Ajouter</button></form><p><a href="/prospects/export.csv">Exporter les prospects non opposés</a></p><ul>{items}</ul>'
    return page("Prospects", body, request)


@app.post("/prospects")
def create_prospect(request: Request, company_name: str = Form(), provenance: str = Form(), email: str | None = Form(None), csrf_token: str | None = Form(None, alias="csrf")):
    guard(request); require_csrf(request, csrf_token)
    if not provenance.strip(): raise HTTPException(422, "Provenance obligatoire")
    with conn() as c: c.execute("INSERT INTO prospects (id,company_name,email,provenance,status,created_at) VALUES (%s,%s,%s,%s,%s,%s)", (secrets.token_hex(8), company_name.strip(), email, provenance.strip(), "new", now()))
    return RedirectResponse("/prospects", 303)


@app.post("/prospects/{prospect_id}/opposition")
def oppose(prospect_id: str, request: Request, csrf_token: str | None = Form(None, alias="csrf")):
    guard(request); require_csrf(request, csrf_token)
    with conn() as c: c.execute("UPDATE prospects SET status='opposed', deleted_at=%s WHERE id=%s", (now(), prospect_id))
    return RedirectResponse("/prospects", 303)


@app.get("/prospects/export.csv")
def export_prospects(request: Request):
    guard(request)
    with conn() as c: rows = c.execute("SELECT company_name,email,provenance,status,created_at FROM prospects WHERE deleted_at IS NULL AND status <> 'opposed' ORDER BY created_at").fetchall()
    out = io.StringIO(); w = csv.writer(out); w.writerow(["company_name", "email", "provenance", "status", "created_at"]); w.writerows([tuple(r.values()) for r in rows])
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=prospects.csv"})


@app.get("/smtp-profiles", response_class=HTMLResponse)
def smtp_profiles(request: Request):
    guard(request)
    with conn() as c: rows = c.execute("SELECT id,name,host,port,username,use_tls FROM smtp_profiles ORDER BY created_at DESC").fetchall()
    items = "".join(f'<li>{escape(r["name"])} — {escape(r["host"])}:{r["port"]} — mot de passe chiffré non affiché</li>' for r in rows)
    body = f'<p>Les tests et envois SMTP restent désactivés. Aucun réseau sortant n’est contacté.</p><form method="post"><input name="name" required placeholder="Nom"><input name="host" required placeholder="smtp.example.org"><input name="port" type="number" value="587"><input name="username" required placeholder="Utilisateur"><input name="password" type="password" required placeholder="Mot de passe"><input type="hidden" name="csrf" value="{csrf(request)}"><button>Enregistrer le profil</button></form><ul>{items}</ul>'
    return page("Profils SMTP", body, request)


@app.post("/smtp-profiles")
def create_smtp(request: Request, name: str = Form(), host: str = Form(), port: int = Form(), username: str = Form(), password: str = Form(), use_tls: bool = Form(False), csrf_token: str | None = Form(None, alias="csrf")):
    guard(request); require_csrf(request, csrf_token)
    if not (name.strip() and host.strip() and username.strip() and password): raise HTTPException(422, "Champs SMTP obligatoires")
    try: encrypted = Fernet(os.environ["SMTP_ENCRYPTION_KEY"]).encrypt(password.encode()).decode()
    except (KeyError, ValueError): raise HTTPException(503, "Clé de chiffrement SMTP invalide ou absente")
    with conn() as c: c.execute("INSERT INTO smtp_profiles (owner_id,name,host,port,username,password_ciphertext,use_tls,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (request.session["admin"], name.strip(), host.strip(), port, username.strip(), encrypted, use_tls, now()))
    return RedirectResponse("/smtp-profiles", 303)


@app.get("/api/status")
def status():
    return {"smtp_enabled": False, "mammouth_enabled": False, "company_connector_enabled": False, "real_sending": False, "uncertain_retry": False, "runtime": "postgresql"}
