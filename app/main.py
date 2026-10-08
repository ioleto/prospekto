import csv, hmac, io, os, secrets, sqlite3, time
from cryptography.fernet import Fernet
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

DB=os.getenv('DATABASE_URL','sqlite:///./prospekto.db'); SQLITE=DB.startswith('sqlite'); path=DB.replace('sqlite:///','') if SQLITE else ':memory:'
app=FastAPI(title='Prospekto',version='0.3.0')
app.add_middleware(SessionMiddleware,secret_key=os.getenv('SESSION_SECRET','dev-only-change-me'),same_site='lax',https_only=os.getenv('APP_ENV')=='production',max_age=3600)
LOGIN_ATTEMPTS={}; PH=PasswordHasher()
def conn():
    if not SQLITE: raise RuntimeError('PostgreSQL adapter is not implemented; SQLite is the only supported runtime')
    c=sqlite3.connect(path); c.row_factory=sqlite3.Row; return c
def now(): return datetime.now(timezone.utc).isoformat()
def init_db():
    if not SQLITE: raise RuntimeError('PostgreSQL adapter is not implemented; deployment is blocked')
    c=conn(); base=os.path.join(os.path.dirname(os.path.dirname(__file__)),'migrations','001_initial.sql'); c.executescript(open(base,encoding='utf8').read())
    if SQLITE:
        c.executescript("CREATE TABLE IF NOT EXISTS suppressions (email TEXT PRIMARY KEY, reason TEXT NOT NULL DEFAULT 'manual', created_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS send_attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL, prospect_id TEXT NOT NULL, profile_id INTEGER NOT NULL, idempotency_key TEXT NOT NULL, status TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, error_code TEXT, error_message TEXT, sent_at TEXT, created_at TEXT NOT NULL, UNIQUE(owner_id,idempotency_key));")
    else:
        secure=os.path.join(os.path.dirname(os.path.dirname(__file__)),'migrations','002_secure_sending.sql')
        if os.path.exists(secure): c.executescript(open(secure,encoding='utf8').read())
    c.commit(); c.close()
init_db()
def configured_password_hash():
    value=os.getenv('ADMIN_PASSWORD_HASH','').strip()
    if value.startswith('$argon2'): return value
    bootstrap=os.getenv('ADMIN_PASSWORD_BOOTSTRAP','')
    return PH.hash(bootstrap) if bootstrap else ''
def valid_password(candidate):
    stored=configured_password_hash()
    try: return bool(stored) and PH.verify(stored,candidate)
    except (VerifyMismatchError,VerificationError,InvalidHashError): return False
def csrf(request):
    token=request.session.get('csrf') or secrets.token_urlsafe(24); request.session['csrf']=token; return token
def require_csrf(request,supplied):
    if not supplied or not hmac.compare_digest(csrf(request),supplied): raise HTTPException(403,'CSRF')
def guard(request):
    if not request.session.get('admin'): raise HTTPException(401,'Authentification requise')
def page(title,body,request):
    nav='<a href="/">Tableau</a><a href="/campaigns">Campagnes</a><a href="/prospects">Prospects</a><a href="/smtp-profiles">SMTP</a>'
    if request.session.get('admin'): nav+='<a href="/logout">Déconnexion</a>'
    return HTMLResponse(f'<!doctype html><html lang="fr"><meta name="viewport" content="width=device-width"><title>{title} · Prospekto</title><style>body{{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;background:#f7f8fa;color:#18212b}}nav{{display:flex;gap:1rem;flex-wrap:wrap}}a,button{{color:#075985}}.card{{background:white;padding:1rem;margin:1rem 0;border-radius:10px;box-shadow:0 1px 5px #ccd}}input,textarea,select{{padding:.6rem;margin:.2rem;width:min(100%,34rem)}}textarea{{min-height:8rem}}.danger{{color:#b91c1c}}</style><nav>{nav}</nav><main><h1>{title}</h1>{body}</main></html>',headers={'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer'})
@app.get('/health')
def health(): return {'status':'ok','app':'prospekto','runtime':'sqlite' if SQLITE else 'unsupported-postgresql'}
@app.get('/login',response_class=HTMLResponse)
def login(request:Request): return page('Connexion','<form method="post"><input name="username" placeholder="Identifiant"><input name="password" type="password" placeholder="Mot de passe"><input type="hidden" name="csrf" value="'+csrf(request)+'"><button>Se connecter</button></form>',request)
@app.post('/login')
def do_login(request:Request,username:str=Form(),password:str=Form(),csrf_token:str|None=Form(None,alias='csrf')):
    require_csrf(request,csrf_token); key=str(request.client.host if request.client else 'unknown'); attempts=[x for x in LOGIN_ATTEMPTS.get(key,[]) if time.time()-x<600]
    if len(attempts)>=10: raise HTTPException(429,'Trop de tentatives')
    if not hmac.compare_digest(username,os.getenv('ADMIN_USERNAME','admin')) or not valid_password(password): LOGIN_ATTEMPTS[key]=attempts+[time.time()]; raise HTTPException(401,'Identifiants invalides')
    request.session.clear(); request.session['admin']=username; request.session['csrf']=secrets.token_urlsafe(24); return RedirectResponse('/',303)
@app.get('/logout')
def logout(request:Request): request.session.clear(); return RedirectResponse('/login',303)
def row_id(): return secrets.token_hex(8)
@app.get('/',response_class=HTMLResponse)
def home(request:Request):
    guard(request); c=conn(); camps=c.execute('select count(*) n from campaigns').fetchone()['n']; pros=c.execute('select count(*) n from prospects where deleted_at is null and status != "opposed"').fetchone()['n']; c.close(); return page('Tableau de bord',f'<div class="card"><b>{camps}</b> campagnes · <b>{pros}</b> prospects actifs</div><p>Envoi réel, collecte, IA et connecteurs : désactivés par défaut.</p>',request)
@app.get('/campaigns',response_class=HTMLResponse)
def campaigns(request:Request):
    guard(request); c=conn(); rows=c.execute('select * from campaigns order by created_at desc').fetchall(); c.close(); items=''.join(f'<li><a href="/campaigns/{r["id"]}">{r["name"]}</a> — {r["status"]}</li>' for r in rows); return page('Campagnes',f'<form method="post"><input name="name" required placeholder="Nom de campagne"><input type="hidden" name="csrf" value="{csrf(request)}"><button>Créer</button></form><ul>{items}</ul>',request)
@app.post('/campaigns')
def create_campaign(request:Request,name:str=Form(),csrf_token:str|None=Form(None,alias='csrf')):
    guard(request); require_csrf(request,csrf_token); name=name.strip()
    if not name: raise HTTPException(422,'Nom obligatoire')
    c=conn(); c.execute('insert into campaigns values (?,?,?,?)',(row_id(),name,'draft',now())); c.commit(); c.close(); return RedirectResponse('/campaigns',303)
@app.get('/campaigns/{campaign_id}',response_class=HTMLResponse)
def edit_campaign(campaign_id:str,request:Request):
    guard(request); c=conn(); r=c.execute('select * from campaigns where id=?',(campaign_id,)).fetchone(); c.close()
    if not r: raise HTTPException(404,'Campagne introuvable')
    body=f'<form method="post"><label>Nom<br><input name="name" value="{r["name"]}" required></label><br><label>Statut<br><select name="status"><option>draft</option><option>ready</option><option>paused</option></select></label><br><input type="hidden" name="csrf" value="{csrf(request)}"><button>Enregistrer le brouillon</button></form>'
    return page('Modifier la campagne',body,request)
@app.post('/campaigns/{campaign_id}')
def update_campaign(campaign_id:str,request:Request,name:str=Form(),status:str=Form('draft'),csrf_token:str|None=Form(None,alias='csrf')):
    guard(request); require_csrf(request,csrf_token)
    if status not in {'draft','ready','paused'}: raise HTTPException(422,'Statut invalide')
    c=conn(); cur=c.execute('update campaigns set name=?,status=? where id=?',(name.strip(),status,campaign_id)); c.commit(); c.close()
    if cur.rowcount != 1: raise HTTPException(404,'Campagne introuvable')
    return RedirectResponse(f'/campaigns/{campaign_id}',303)
@app.get('/prospects',response_class=HTMLResponse)
def prospects(request:Request):
    guard(request); c=conn(); rows=c.execute('select * from prospects where deleted_at is null and status != "opposed" order by created_at desc').fetchall(); c.close(); items=''.join(f'<li>{r["company_name"]} — {r["email"] or "sans email"} — {r["provenance"]} <form style="display:inline" method="post" action="/prospects/{r["id"]}/opposition"><input type="hidden" name="csrf" value="{csrf(request)}"><button class="danger">Marquer opposition</button></form></li>' for r in rows); return page('Prospects',f'<form method="post"><input name="company_name" required placeholder="Entreprise"><input name="email" placeholder="Email"><input name="provenance" required placeholder="Provenance documentée"><input type="hidden" name="csrf" value="{csrf(request)}"><button>Ajouter</button></form><p><a href="/prospects/export.csv">Exporter les prospects non opposés</a></p><ul>{items}</ul>',request)
@app.post('/prospects')
def create_prospect(request:Request,company_name:str=Form(),provenance:str=Form(),email:str|None=Form(None),csrf_token:str|None=Form(None,alias='csrf')):
    guard(request); require_csrf(request,csrf_token)
    if not provenance.strip(): raise HTTPException(422,'Provenance obligatoire')
    c=conn(); c.execute('insert into prospects values (?,?,?,?,?,?,?,?,?,?,?,?,?)',(row_id(),None,company_name.strip(),email,None,None,provenance.strip(),0,0,None,'new',None,now())); c.commit(); c.close(); return RedirectResponse('/prospects',303)
@app.post('/prospects/{prospect_id}/opposition')
def oppose(prospect_id:str,request:Request,csrf_token:str|None=Form(None,alias='csrf')):
    guard(request); require_csrf(request,csrf_token); c=conn(); c.execute('update prospects set status="opposed",deleted_at=? where id=?',(now(),prospect_id)); c.commit(); c.close(); return RedirectResponse('/prospects',303)
@app.get('/prospects/export.csv')
def export_prospects(request:Request):
    guard(request); c=conn(); rows=c.execute('select company_name,email,provenance,status,created_at from prospects where deleted_at is null and status != "opposed" order by created_at').fetchall(); c.close(); out=io.StringIO(); w=csv.writer(out); w.writerow(['company_name','email','provenance','status','created_at']); w.writerows(rows); return StreamingResponse(iter([out.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=prospects.csv'})
@app.get('/smtp-profiles',response_class=HTMLResponse)
def smtp_profiles(request:Request):
    guard(request); c=conn(); rows=c.execute('select id,name,host,port,username,use_tls from smtp_profiles order by created_at desc').fetchall(); c.close(); items=''.join(f'<li>{r["name"]} — {r["host"]}:{r["port"]} — mot de passe chiffré non affiché <form style="display:inline" method="post" action="/smtp-profiles/{r["id"]}/test"><input type="hidden" name="csrf" value="{csrf(request)}"><input type="hidden" name="confirm" value="TEST SMTP"><button>Tester</button></form></li>' for r in rows); body=f'<p>Le test est bloqué sans SMTP_TEST_MODE=true. Aucun envoi réel n’est activé.</p><form method="post"><input name="name" required placeholder="Nom"><input name="host" required placeholder="smtp.example.org"><input name="port" type="number" value="587"><input name="username" required placeholder="Utilisateur"><input name="password" type="password" required placeholder="Mot de passe"><label><input type="checkbox" name="use_tls" checked> TLS</label><input type="hidden" name="csrf" value="{csrf(request)}"><button>Enregistrer le profil</button></form><ul>{items}</ul>'; return page('Profils SMTP',body,request)
@app.post('/smtp-profiles')
def create_smtp(request:Request,name:str=Form(),host:str=Form(),port:int=Form(),username:str=Form(),password:str=Form(),use_tls:bool=Form(False),csrf_token:str|None=Form(None,alias='csrf')):
    guard(request); require_csrf(request,csrf_token)
    if not (name.strip() and host.strip() and username.strip() and password): raise HTTPException(422,'Champs SMTP obligatoires')
    # Fernet provides authenticated encryption; a missing key fails closed.
    try:
        encrypted=Fernet(os.environ['SMTP_ENCRYPTION_KEY']).encrypt(password.encode()).decode()
    except KeyError as exc:
        raise HTTPException(503,'Chiffrement SMTP non configuré') from exc
    except ValueError as exc:
        raise HTTPException(503,'Clé de chiffrement SMTP invalide') from exc
    c=conn(); c.execute('insert into smtp_profiles (owner_id,name,host,port,username,password_ciphertext,use_tls,created_at) values (?,?,?,?,?,?,?,?)',(request.session['admin'],name.strip(),host.strip(),port,username.strip(),encrypted,int(use_tls),now())); c.commit(); c.close(); return RedirectResponse('/smtp-profiles',303)
@app.post('/smtp-profiles/{profile_id}/test')
def test_smtp(profile_id:int,request:Request,confirm:str|None=Form(None),csrf_token:str|None=Form(None,alias='csrf')):
    guard(request); require_csrf(request,csrf_token)
    if confirm != 'TEST SMTP': raise HTTPException(400,'Confirmation explicite requise')
    if os.getenv('SMTP_TEST_MODE','false').lower() != 'true': raise HTTPException(409,'Test SMTP désactivé; aucun réseau contacté')
    return {'status':'not_implemented','profile_id':profile_id,'sent':False}
@app.post('/campaigns/{campaign_id}/send-confirm')
def confirm_send(campaign_id:str,request:Request,prospect_id:str=Form(),confirm:str|None=Form(None),csrf_token:str|None=Form(None,alias='csrf')):
    guard(request); require_csrf(request,csrf_token)
    if confirm != 'CONFIRMER ENVOI INDIVIDUEL': raise HTTPException(400,'Confirmation explicite requise')
    raise HTTPException(409,'Envoi réel désactivé; aucun message ni retry effectué')
@app.get('/api/status')
def status(): return {'smtp_enabled':os.getenv('SMTP_ENABLED','false').lower()=='true','mammouth_enabled':False,'company_connector_enabled':False,'real_sending':False,'uncertain_retry':False}
