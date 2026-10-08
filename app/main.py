import os, sqlite3, secrets, hmac, time
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
DB=os.getenv('DATABASE_URL','sqlite:///./prospekto.db'); path=DB.replace('sqlite:///','') if DB.startswith('sqlite') else ':memory:'
app=FastAPI(title='Prospekto', version='0.1.0')
app.add_middleware(SessionMiddleware, secret_key=os.getenv('SESSION_SECRET','dev-only-change-me'), same_site='lax', https_only=os.getenv('APP_ENV')=='production')
LOGIN_ATTEMPTS={}
def conn():
 c=sqlite3.connect(path); c.row_factory=sqlite3.Row; return c
def now(): return datetime.now(timezone.utc).isoformat()
def init_db():
 c=conn();
 with open('migrations/001_initial.sql') as f: c.executescript(f.read())
 c.commit(); c.close()
init_db()
def csrf(request):
 token=request.session.get('csrf') or secrets.token_urlsafe(24); request.session['csrf']=token; return token
def guard(request):
 if not request.session.get('admin'): raise HTTPException(401,'Authentification requise')
def page(title,body,request):
 return HTMLResponse(f'''<!doctype html><html lang="fr"><meta name="viewport" content="width=device-width"><title>{title} · Prospekto</title><style>body{{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;background:#f7f8fa;color:#18212b}}nav{{display:flex;gap:1rem;flex-wrap:wrap}}a,button{{color:#075985}}.card{{background:white;padding:1rem;margin:1rem 0;border-radius:10px;box-shadow:0 1px 5px #ccd}}input,select{{padding:.6rem;margin:.2rem}}</style><nav><a href="/">Tableau</a><a href="/campaigns">Campagnes</a><a href="/prospects">Prospects</a>{'<a href="/logout">Déconnexion</a>' if request.session.get('admin') else ''}</nav><main><h1>{title}</h1>{body}</main></html>''')
@app.get('/health')
def health(): return {'status':'ok','app':'prospekto'}
@app.get('/login',response_class=HTMLResponse)
def login(request): return page('Connexion','<form method="post"><input name="username" placeholder="Identifiant"><input name="password" type="password" placeholder="Mot de passe"><input type="hidden" name="csrf" value="'+csrf(request)+'"><button>Se connecter</button></form>',request)
@app.post('/login')
def do_login(request:Request,username:str=Form(),password:str=Form(),csrf_token:str=Form(alias='csrf')):
 if not hmac.compare_digest(csrf(request),csrf_token): raise HTTPException(403,'CSRF')
 key=str(request.client.host); attempts=[x for x in LOGIN_ATTEMPTS.get(key,[]) if time.time()-x<600]
 if len(attempts)>=10: raise HTTPException(429,'Trop de tentatives')
 ok=hmac.compare_digest(username,os.getenv('ADMIN_USERNAME','admin')) and hmac.compare_digest(password,os.getenv('ADMIN_PASSWORD','change-me'))
 if not ok: LOGIN_ATTEMPTS[key]=attempts+[time.time()]; raise HTTPException(401,'Identifiants invalides')
 request.session['admin']=username; return RedirectResponse('/',303)
@app.get('/logout')
def logout(request): request.session.clear(); return RedirectResponse('/login',303)
@app.get('/',response_class=HTMLResponse)
def home(request):
 guard(request); c=conn(); camps=c.execute('select count(*) n from campaigns').fetchone()['n']; pros=c.execute('select count(*) n from prospects where deleted_at is null').fetchone()['n']; c.close()
 return page('Tableau de bord',f'<div class="card"><b>{camps}</b> campagnes · <b>{pros}</b> prospects actifs</div><p>Envoi, collecte, IA et connecteur entreprise : désactivés.</p>',request)
@app.get('/campaigns',response_class=HTMLResponse)
def campaigns(request):
 guard(request); c=conn(); rows=c.execute('select * from campaigns order by created_at desc').fetchall(); c.close(); items=''.join(f'<li>{r["name"]} — {r["status"]}</li>' for r in rows)
 return page('Campagnes',f'<form method="post"><input name="name" required placeholder="Nom de campagne"><input type="hidden" name="csrf" value="{csrf(request)}"><button>Créer</button></form><ul>{items}</ul>',request)
@app.post('/campaigns')
def create_campaign(request:Request,name:str=Form(),csrf_token:str=Form(alias='csrf')):
 guard(request)
 if not hmac.compare_digest(csrf(request),csrf_token): raise HTTPException(403,'CSRF')
 c=conn(); c.execute('insert into campaigns values (?,?,?,?)',(secrets.token_hex(8),name,'draft',now())); c.commit(); c.close(); return RedirectResponse('/campaigns',303)
@app.get('/prospects',response_class=HTMLResponse)
def prospects(request):
 guard(request); c=conn(); rows=c.execute('select * from prospects where deleted_at is null order by created_at desc').fetchall(); c.close(); items=''.join(f'<li>{r["company_name"]} — {r["email"] or "sans email"} — {r["provenance"]}</li>' for r in rows)
 return page('Prospects',f'<form method="post"><input name="company_name" required placeholder="Entreprise"><input name="email" placeholder="Email"><input name="provenance" required placeholder="Provenance documentée"><label><input type="checkbox" name="consent_documented"> consentement documenté</label><input type="hidden" name="csrf" value="{csrf(request)}"><button>Ajouter</button></form><ul>{items}</ul>',request)
@app.post('/prospects')
def create_prospect(request:Request,company_name:str=Form(),provenance:str=Form(),email:str|None=Form(None),consent_documented:bool=Form(False),csrf_token:str=Form(alias='csrf')):
 guard(request)
 if not hmac.compare_digest(csrf(request),csrf_token): raise HTTPException(403,'CSRF')
 if not provenance.strip(): raise HTTPException(422,'Provenance obligatoire')
 c=conn(); c.execute('insert into prospects values (?,?,?,?,?,?,?,?,?,?,?,?,?)',(secrets.token_hex(8),None,company_name,email,None,None,provenance,0,int(consent_documented),None,'new',None,now())); c.commit(); c.close(); return RedirectResponse('/prospects',303)
@app.get('/api/status')
def status(): return {'smtp_enabled':False,'mammouth_enabled':False,'company_connector_enabled':False,'real_sending':False}
