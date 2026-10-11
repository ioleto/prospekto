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
from psycopg.types.json import Jsonb

app = FastAPI(title="Prospekto", version="0.4.0")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", ""), same_site="lax", https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true", max_age=3600)
PH = PasswordHasher()
LOGIN_ATTEMPTS = {}


def conn():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url or not url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL must be a PostgreSQL URL")
    return psycopg.connect(url, row_factory=dict_row)


def now(): return datetime.now(timezone.utc)
def csrf(request):
    token = request.session.get("csrf") or secrets.token_urlsafe(24); request.session["csrf"] = token; return token
def require_csrf(request, supplied):
    if not supplied or not hmac.compare_digest(csrf(request), supplied): raise HTTPException(403, "CSRF")
def guard(request):
    if not request.session.get("admin"): raise HTTPException(401, "Authentification requise")
def password_hash():
    value=os.getenv("ADMIN_PASSWORD_HASH","").strip(); return value if value.startswith("$argon2") else (PH.hash(os.getenv("ADMIN_PASSWORD_BOOTSTRAP","")) if os.getenv("ADMIN_PASSWORD_BOOTSTRAP","") else "")
def valid_password(candidate):
    try: return bool(password_hash()) and PH.verify(password_hash(), candidate)
    except (VerifyMismatchError, VerificationError, InvalidHashError): return False
def page(title, body, request):
    nav='<a href="/">Tableau</a> <a href="/campaigns">Campagnes</a> <a href="/prospects">Prospects</a> <a href="/smtp-profiles">SMTP</a>'
    if request.session.get("admin"): nav+=' <a href="/logout">Déconnexion</a>'
    return HTMLResponse(f'<!doctype html><html lang="fr"><meta name="viewport" content="width=device-width"><title>{escape(title)} · Prospekto</title><style>body{{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;background:#f7f8fa;color:#18212b}}nav{{display:flex;gap:1rem;flex-wrap:wrap}}a,button{{color:#075985}}.card{{background:white;padding:1rem;margin:1rem 0;border-radius:10px}}input,textarea,select{{padding:.6rem;margin:.2rem;width:min(100%,34rem)}}.danger{{color:#b91c1c}}</style><nav>{nav}</nav><main><h1>{escape(title)}</h1>{body}</main></html>', headers={"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"no-referrer"})

@app.get("/health")
def health():
    try:
        with conn() as c: c.execute("SELECT 1")
        return {"status":"ok","app":"prospekto","runtime":"postgresql"}
    except Exception: raise HTTPException(503,"database unavailable")
@app.get("/login", response_class=HTMLResponse)
def login(request: Request): return page("Connexion", f'<form method="post"><input name="username" placeholder="Identifiant"><input name="password" type="password" placeholder="Mot de passe"><input type="hidden" name="csrf" value="{csrf(request)}"><button>Se connecter</button></form>', request)
@app.post("/login")
def do_login(request: Request, username: str=Form(), password: str=Form(), csrf_token: str|None=Form(None,alias="csrf")):
    require_csrf(request,csrf_token); key=str(request.client.host if request.client else "unknown"); attempts=[x for x in LOGIN_ATTEMPTS.get(key,[]) if time.time()-x<600]
    if len(attempts)>=10: raise HTTPException(429,"Trop de tentatives")
    if not hmac.compare_digest(username,os.getenv("ADMIN_USERNAME","admin")) or not valid_password(password): LOGIN_ATTEMPTS[key]=attempts+[time.time()]; raise HTTPException(401,"Identifiants invalides")
    request.session.clear(); request.session["admin"]=username; request.session["csrf"]=secrets.token_urlsafe(24); return RedirectResponse("/",303)
@app.get("/logout")
def logout(request: Request): request.session.clear(); return RedirectResponse("/login",303)
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    guard(request)
    with conn() as c: camps=c.execute("SELECT count(*) AS n FROM campaigns").fetchone()["n"]; pros=c.execute("SELECT count(*) AS n FROM prospects WHERE deleted_at IS NULL AND status <> 'opposed'").fetchone()["n"]
    return page("Tableau de bord",f'<div class="card"><b>{camps}</b> campagnes · <b>{pros}</b> prospects actifs</div><p>Envoi réel, collecte, IA et connecteurs : désactivés par défaut.</p>',request)

SEGMENT_TYPES={"b2b","b2c","both"}; CAMPAIGN_STATUSES={"draft","active","paused","completed","archived"}
def csv_values(value): return [v.strip() for v in (value or "").split(",") if v.strip()]
def validate_campaign(name,segment_type,status,inclusion,exclusion):
    if not name.strip() or segment_type not in SEGMENT_TYPES or status not in CAMPAIGN_STATUSES: raise HTTPException(422,"Critères de campagne invalides")
    if set(inclusion)&set(exclusion): raise HTTPException(422,"Une valeur ne peut pas être incluse et exclue")
def campaign_payload(form):
    criteria=("sector","type","size","geography","language")
    inclusion={k:csv_values(form.get(f"inclusion_{k}")) for k in criteria}; exclusion={k:csv_values(form.get(f"exclusion_{k}")) for k in criteria}
    for a,b in zip(inclusion.values(),exclusion.values()): validate_campaign("ok","b2b","draft",a,b)
    return inclusion,exclusion
def campaign_form(request,r=None):
    r=r or {"name":"","segment_type":"b2b","inclusion_criteria":{},"exclusion_criteria":{},"smtp_profile_id":""}
    for k in ("sector","type","size","geography","language"): r[f"inclusion_{k}"]=r.get("inclusion_criteria",{}).get(k,[])
    for k in ("sector","type","size","geography","language"): r[f"exclusion_{k}"]=r.get("exclusion_criteria",{}).get(k,[])
    def val(k): x=r.get(k,""); return ", ".join(x) if isinstance(x,list) else (x or "")
    opts=''.join(f'<option value="{x}" {"selected" if x==r.get("segment_type") else ""}>{x}</option>' for x in sorted(SEGMENT_TYPES)); fields=''.join(f'<label>{label}<br><input name="{key}" value="{escape(val(key))}" placeholder="valeur1, valeur2"></label><br>' for key,label in [("inclusion_sector","Secteurs inclus"),("exclusion_sector","Secteurs exclus"),("inclusion_type","Types inclus"),("exclusion_type","Types exclus"),("inclusion_size","Tailles incluses"),("exclusion_size","Tailles exclues"),("inclusion_geography","Géographies incluses"),("exclusion_geography","Géographies exclues"),("inclusion_language","Langues incluses"),("exclusion_language","Langues exclues")]); action=f'/campaigns/{r["id"]}/edit' if r.get("id") else '/campaigns'
    return f'<form method="post" action="{action}"><input name="name" required value="{escape(val("name"))}" placeholder="Nom"><select name="segment_type">{opts}</select>{fields}<input name="smtp_profile_id" value="{escape(str(r.get("smtp_profile_id") or ""))}" placeholder="ID profil SMTP (optionnel)"><input type="hidden" name="csrf" value="{csrf(request)}"><button>Enregistrer</button></form>'
@app.get("/campaigns",response_class=HTMLResponse)
def campaigns(request:Request):
    guard(request)
    with conn() as c: rows=c.execute("SELECT id,name,status,segment_type FROM campaigns ORDER BY created_at DESC").fetchall()
    return page("Campagnes",campaign_form(request)+"<ul>"+"".join(f'<li><a href="/campaigns/{r["id"]}">{escape(r["name"])}</a> — {r["status"]}</li>' for r in rows)+"</ul>",request)
@app.post("/campaigns")
def create_campaign(request:Request,name:str=Form(),segment_type:str=Form("b2b"),inclusion_sector:str=Form(""),exclusion_sector:str=Form(""),inclusion_type:str=Form(""),exclusion_type:str=Form(""),inclusion_size:str=Form(""),exclusion_size:str=Form(""),inclusion_geography:str=Form(""),exclusion_geography:str=Form(""),inclusion_language:str=Form(""),exclusion_language:str=Form(""),smtp_profile_id:str=Form(""),csrf_token:str|None=Form(None,alias="csrf")):
    guard(request); require_csrf(request,csrf_token); form=locals(); inclusion,exclusion=campaign_payload(form); validate_campaign(name,segment_type,"draft",[],[]); cid=secrets.token_hex(8)
    with conn() as c: c.execute("INSERT INTO campaigns (id,name,status,segment_type,inclusion_criteria,exclusion_criteria,smtp_profile_id,created_at) VALUES (%s,%s,'draft',%s,%s,%s,%s,%s)",(cid,name.strip(),segment_type,Jsonb(inclusion),Jsonb(exclusion),int(smtp_profile_id) if smtp_profile_id else None,now()))
    return RedirectResponse(f"/campaigns/{cid}",303)
@app.get("/campaigns/{campaign_id}",response_class=HTMLResponse)
def campaign_detail(campaign_id:str,request:Request):
    guard(request)
    with conn() as c: r=c.execute("SELECT * FROM campaigns WHERE id=%s",(campaign_id,)).fetchone()
    if not r: raise HTTPException(404,"Campagne introuvable")
    return page("Campagne",campaign_form(request,r)+f'<p>Statut: {escape(r["status"])}</p>',request)
@app.post("/campaigns/{campaign_id}/edit")
def edit_campaign(campaign_id:str,request:Request,name:str=Form(),segment_type:str=Form(),inclusion_sector:str=Form(""),exclusion_sector:str=Form(""),inclusion_type:str=Form(""),exclusion_type:str=Form(""),inclusion_size:str=Form(""),exclusion_size:str=Form(""),inclusion_geography:str=Form(""),exclusion_geography:str=Form(""),inclusion_language:str=Form(""),exclusion_language:str=Form(""),smtp_profile_id:str=Form(""),csrf_token:str|None=Form(None,alias="csrf")):
    guard(request); require_csrf(request,csrf_token); form=locals(); inclusion,exclusion=campaign_payload(form); validate_campaign(name,segment_type,"draft",[],[])
    with conn() as c: c.execute("UPDATE campaigns SET name=%s,segment_type=%s,inclusion_criteria=%s,exclusion_criteria=%s,smtp_profile_id=%s WHERE id=%s",(name.strip(),segment_type,Jsonb(inclusion),Jsonb(exclusion),int(smtp_profile_id) if smtp_profile_id else None,campaign_id))
    return RedirectResponse(f"/campaigns/{campaign_id}",303)
@app.post("/campaigns/{campaign_id}/status")
def campaign_status(campaign_id:str,request:Request,status:str=Form(),csrf_token:str|None=Form(None,alias="csrf")):
    guard(request); require_csrf(request,csrf_token)
    if status not in CAMPAIGN_STATUSES: raise HTTPException(422,"Statut invalide")
    with conn() as c: c.execute("UPDATE campaigns SET status=%s WHERE id=%s",(status,campaign_id))
    return RedirectResponse(f"/campaigns/{campaign_id}",303)
@app.get("/prospects",response_class=HTMLResponse)
def prospects(request:Request,campaign_id:str|None=None):
    guard(request)
    with conn() as c: rows=c.execute("SELECT p.*,c.name AS campaign_name FROM prospects p LEFT JOIN campaigns c ON c.id=p.campaign_id WHERE p.deleted_at IS NULL AND p.status <> 'opposed' AND (%s::text IS NULL OR p.campaign_id=%s) ORDER BY p.created_at DESC",(campaign_id,campaign_id)).fetchall(); camps=c.execute("SELECT id,name FROM campaigns ORDER BY name").fetchall()
    def opts(r): return ''.join(f'<option value="{x["id"]}" {"selected" if x["id"]==r["campaign_id"] else ""}>{escape(x["name"])}</option>' for x in camps)
    items=''.join(f'<li>{escape(r["company_name"])} — {escape(r["email"] or "sans email")} — campagne: {escape(r["campaign_name"] or "aucune")} <form style="display:inline" method="post" action="/prospects/{r["id"]}/campaign"><input type="hidden" name="csrf" value="{csrf(request)}"><select name="campaign_id"><option value="">Aucune</option>{opts(r)}</select><button>Associer</button></form></li>' for r in rows)
    return page("Prospects",f'<form method="post"><input name="company_name" required placeholder="Entreprise"><input name="email" placeholder="Email"><input name="provenance" required placeholder="Provenance documentée"><input type="hidden" name="csrf" value="{csrf(request)}"><button>Ajouter</button></form><p>Filtre: <a href="/prospects">toutes</a> | '+" | ".join(f'<a href="/prospects?campaign_id={x["id"]}">{escape(x["name"])}</a>' for x in camps)+f'</p><ul>{items}</ul>',request)
@app.post("/prospects/{prospect_id}/campaign")
def associate_prospect(prospect_id:str,request:Request,campaign_id:str|None=Form(None),csrf_token:str|None=Form(None,alias="csrf")):
    guard(request); require_csrf(request,csrf_token)
    with conn() as c: c.execute("UPDATE prospects SET campaign_id=%s WHERE id=%s",(campaign_id or None,prospect_id))
    return RedirectResponse("/prospects",303)
@app.post("/prospects")
def create_prospect(request:Request,company_name:str=Form(),email:str=Form(""),provenance:str=Form(),csrf_token:str|None=Form(None,alias="csrf")):
    guard(request); require_csrf(request,csrf_token)
    if not company_name.strip() or not provenance.strip(): raise HTTPException(422,"Entreprise et provenance obligatoires")
    with conn() as c: c.execute("INSERT INTO prospects (id,company_name,email,provenance,status,created_at) VALUES (%s,%s,%s,%s,'new',%s)",(secrets.token_hex(8),company_name.strip(),email.strip() or None,provenance.strip(),now()))
    return RedirectResponse("/prospects",303)
@app.post("/prospects/{prospect_id}/opposition")
def oppose(prospect_id:str,request:Request,csrf_token:str|None=Form(None,alias="csrf")):
    guard(request); require_csrf(request,csrf_token)
    with conn() as c: c.execute("UPDATE prospects SET status='opposed',deleted_at=%s WHERE id=%s",(now(),prospect_id))
    return RedirectResponse("/prospects",303)
@app.get("/prospects/export.csv")
def export_prospects(request:Request):
    guard(request)
    with conn() as c: rows=c.execute("SELECT company_name,email,provenance,status,created_at FROM prospects WHERE deleted_at IS NULL AND status <> 'opposed' ORDER BY created_at").fetchall()
    out=io.StringIO(); w=csv.writer(out); w.writerow(["company_name","email","provenance","status","created_at"]); w.writerows([tuple(r.values()) for r in rows]); return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=prospects.csv"})

@app.get("/smtp-profiles",response_class=HTMLResponse)
def smtp_profiles(request:Request):
    guard(request)
    with conn() as c: rows=c.execute("SELECT id,name,host,port,username,use_tls FROM smtp_profiles ORDER BY created_at DESC").fetchall()
    items=''.join(f'<li>{escape(r["name"])} — {escape(r["host"])}:{r["port"]} — mot de passe chiffré non affiché</li>' for r in rows)
    body=(f'<p>Les tests et envois SMTP restent désactivés. Aucun réseau sortant n’est contacté.</p>'
          f'<form method="post" action="/smtp-profiles">'
          f'<input name="name" required placeholder="Nom">'
          f'<input name="host" required placeholder="smtp.example.org">'
          f'<input name="port" type="number" min="1" max="65535" value="587" required>'
          f'<input name="username" required placeholder="Utilisateur">'
          f'<input name="password" type="password" required placeholder="Mot de passe">'
          f'<label><input name="use_tls" type="checkbox" value="true" checked> TLS</label>'
          f'<input type="hidden" name="csrf" value="{csrf(request)}">'
          f'<button type="submit">Enregistrer le profil</button></form><ul>{items}</ul>')
    return page("Profils SMTP",body,request)
@app.post("/smtp-profiles")
def create_smtp(request:Request,name:str=Form(),host:str=Form(),port:int=Form(587),username:str=Form(),password:str=Form(),use_tls:bool=Form(False),csrf_token:str|None=Form(None,alias="csrf")):
    guard(request); require_csrf(request,csrf_token)
    if not (name.strip() and host.strip() and username.strip() and password): raise HTTPException(422,"Champs SMTP obligatoires")
    try: encrypted=Fernet(os.environ["SMTP_ENCRYPTION_KEY"] ).encrypt(password.encode()).decode()
    except (KeyError,ValueError): raise HTTPException(503,"Clé de chiffrement SMTP invalide ou absente")
    with conn() as c: c.execute("INSERT INTO smtp_profiles (owner_id,name,host,port,username,password_ciphertext,use_tls,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(request.session["admin"],name.strip(),host.strip(),port,username.strip(),encrypted,use_tls,now()))
    return RedirectResponse("/smtp-profiles",303)
@app.get("/api/status")
def status(): return {"smtp_enabled":False,"mammouth_enabled":False,"company_connector_enabled":False,"real_sending":False,"uncertain_retry":False,"runtime":"postgresql"}
