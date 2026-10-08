import csv
import hmac
import io
import os
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
DB=os.getenv('DATABASE_URL','sqlite:///./prospekto.db')
SQLITE=DB.startswith('sqlite'); path=DB.replace('sqlite:///','') if SQLITE else ':memory:'
app=FastAPI(title='Prospekto',version='0.2.0')
app.add_middleware(SessionMiddleware,secret_key=os.getenv('SESSION_SECRET','dev-only-change-me'),same_site='lax',https_only=os.getenv('APP_ENV')=='production',max_age=3600)
LOGIN_ATTEMPTS={}; PH=PasswordHasher()
def conn():
 c=sqlite3.connect(path); c.row_factory=sqlite3.Row; return c
def now(): return datetime.now(timezone.utc).isoformat()
def init_db():
 c=conn()
 with open(os.path.join(os.path.dirname(os.path.dirname(__file__)),'migrations','001_initial.sql'),encoding='utf-8') as f: c.executescript(f.read())
 c.commit(); c.close()
init_db()
def configured_password_hash():
 configured=os.getenv('ADMIN_PASSWORD_HASH','').strip()
 if configured and configured.startswith('$argon2'): return configured
 bootstrap=os.getenv('ADMIN_PASSWORD_BOOTSTRAP','')
 return PH.hash(bootstrap) if bootstrap else ''
def valid_password(candidate):
 try: return bool(configured_password_hash()) and PH.verify(configured_password_hash(),candidate)
 except (VerifyMismatchError,VerificationError,InvalidHashError): return False
def csrf(request):
 token=request.session.get('csrf') or secrets.token_urlsafe(24); request.session['csrf']=token; return token
def require_csrf(request,supplied):
 if not supplied or not hmac.compare_digest(csrf(request),supplied): raise HTTPException(403,'CSRF')
def guard(request):
 if not request.session.get('admin'): raise HTTPException(401,'Authentification requise')
def page(title,body,request):
 nav='<a href="/">Tableau</a><a href="/campaigns">Campagnes</a><a href="/prospects">Prospects</a>'
 if request.session.get('admin'): nav+='<a href="/logout">Déconnexion</a>'
 return HTMLResponse(f'<!doctype html><html lang="fr"><meta name="viewport" content="width=device-width"><title>{title} · Prospekto</title><style>body{{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;background:#f7f8fa;color:#18212b}}nav{{display:flex;gap:1rem;flex-wrap:wrap}}a,button{{color:#075985}}.card{{background:white;padding:1rem;margin:1rem 0;border-radius:10px;box-shadow:0 1px 5px #ccd}}input{{padding:.6rem;margin:.2rem}}.danger{{color:#b91c1c}}</style><nav>{nav}</nav><main><h1>{title}</h1>{body}</main></html>',headers={'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer'})
@app.get('/health')
def health(): return {'status':'ok','app':'prospekto'}
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
@app.get('/',response_class=HTMLResponse)
def home(request:Request):
 guard(request); c=conn(); camps=c.execute('select count(*) n from campaigns').fetchone()['n']; pros=c.execute('select count(*) n from prospects where deleted_at is null and status != "opposed"').fetchone()['n']; c.close(); return page('Tableau de bord',f'<div class="card"><b>{camps}</b> campagnes · <b>{pros}</b> prospects actifs</div><p>Envoi, collecte, IA et connecteur entreprise : désactivés.</p>',request)
@app.get('/campaigns',response_class=HTMLResponse)
def campaigns(request:Request):
 guard(request); c=conn(); rows=c.execute('select * from campaigns order by created_at desc').fetchall(); c.close(); items=''.join(f'<li>{r["name"]} — {r["status"]}</li>' for r in rows); return page('Campagnes',f'<form method="post"><input name="name" required placeholder="Nom de campagne"><input type="hidden" name="csrf" value="{csrf(request)}"><button>Créer</button></form><ul>{items}</ul>',request)
@app.post('/campaigns')
def create_campaign(request:Request,name:str=Form(),csrf_token:str|None=Form(None,alias='csrf')):
 guard(request); require_csrf(request,csrf_token)
 if not name.strip(): raise HTTPException(422,'Nom obligatoire')
 c=conn(); c.execute('insert into campaigns values (?,?,?,?)',(secrets.token_hex(8),name.strip(),'draft',now())); c.commit(); c.close(); return RedirectResponse('/campaigns',303)
@app.get('/prospects',response_class=HTMLResponse)
def prospects(request:Request):
 guard(request); c=conn(); rows=c.execute('select * from prospects where deleted_at is null and status != "opposed" order by created_at desc').fetchall(); c.close(); items=''.join(f'<li>{r["company_name"]} — {r["email"] or "sans email"} — {r["provenance"]} <form style="display:inline" method="post" action="/prospects/{r["id"]}/opposition"><input type="hidden" name="csrf" value="{csrf(request)}"><button class="danger">Marquer opposition</button></form></li>' for r in rows); return page('Prospects',f'<form method="post"><input name="company_name" required placeholder="Entreprise"><input name="email" placeholder="Email"><input name="provenance" required placeholder="Provenance documentée"><input type="hidden" name="csrf" value="{csrf(request)}"><button>Ajouter</button></form><p><a href="/prospects/export.csv">Exporter les prospects non opposés</a></p><ul>{items}</ul>',request)
@app.post('/prospects')
def create_prospect(request:Request,company_name:str=Form(),provenance:str=Form(),email:str|None=Form(None),consent_documented:bool=Form(False),csrf_token:str|None=Form(None,alias='csrf')):
 guard(request); require_csrf(request,csrf_token)
 if not provenance.strip(): raise HTTPException(422,'Provenance obligatoire')
 c=conn(); c.execute('insert into prospects values (?,?,?,?,?,?,?,?,?,?,?,?,?)',(secrets.token_hex(8),None,company_name.strip(),email,None,None,provenance.strip(),0,int(consent_documented),None,'new',None,now())); c.commit(); c.close(); return RedirectResponse('/prospects',303)
@app.post('/prospects/{prospect_id}/opposition')
def oppose(prospect_id:str,request:Request,csrf_token:str|None=Form(None,alias='csrf')):
 guard(request); require_csrf(request,csrf_token); c=conn(); c.execute('update prospects set status="opposed",deleted_at=? where id=?',(now(),prospect_id)); c.commit(); c.close(); return RedirectResponse('/prospects',303)
@app.get('/prospects/export.csv')
def export_prospects(request:Request):
 guard(request); c=conn(); rows=c.execute('select company_name,email,provenance,status,created_at from prospects where deleted_at is null and status != "opposed" order by created_at').fetchall(); c.close(); out=io.StringIO(); import csv as _csv; w=_csv.writer(out); w.writerow(['company_name','email','provenance','status','created_at']); w.writerows(rows); return StreamingResponse(iter([out.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=prospects.csv'})
@app.get('/api/status')
def status(): return {'smtp_enabled':False,'mammouth_enabled':False,'company_connector_enabled':False,'real_sending':False}
