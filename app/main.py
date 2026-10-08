from __future__ import annotations
import hashlib,hmac,os,secrets,smtplib,ssl
from email.message import EmailMessage
from typing import Any
import psycopg
from cryptography.fernet import Fernet
from fastapi import Cookie,FastAPI,Header,HTTPException,Response
from pydantic import BaseModel,EmailStr,Field
DATABASE_URL=os.environ.get('DATABASE_URL',''); MASTER_KEY=os.environ.get('PROSPEKTO_MASTER_KEY',''); COOKIE_SECURE=os.environ.get('COOKIE_SECURE','true').lower()=='true'
app=FastAPI(title='Prospekto',version='0.2.0')
def db():
 if not DATABASE_URL: raise RuntimeError('DATABASE_URL is required; SQLite is not supported')
 return psycopg.connect(DATABASE_URL)
def cipher():
 if not MASTER_KEY: raise RuntimeError('PROSPEKTO_MASTER_KEY is required')
 return Fernet(MASTER_KEY.encode())
def token_hash(t): return hashlib.sha256(t.encode()).hexdigest()
def require_csrf(c,h):
 if not c or not h or not hmac.compare_digest(c,h): raise HTTPException(403,'CSRF validation failed')
def require_user(session):
 if not session: raise HTTPException(401,'Authentication required')
 with db() as c, c.cursor() as q:
  q.execute("SELECT u.id,u.email,u.is_admin FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=%s AND s.expires_at>now()",(token_hash(session),)); r=q.fetchone()
 if not r: raise HTTPException(401,'Invalid or expired session')
 return {'id':r[0],'email':r[1],'is_admin':r[2]}
class Login(BaseModel): email:EmailStr; password:str=Field(min_length=12,max_length=256)
class SmtpProfile(BaseModel): name:str=Field(min_length=1,max_length=100); host:str; port:int=Field(ge=1,le=65535); username:str; password:str=Field(min_length=1); use_tls:bool=True
class SendRequest(BaseModel): contact_id:int; profile_id:int; subject:str=Field(min_length=1,max_length=998); body:str=Field(min_length=1,max_length=100000); idempotency_key:str=Field(min_length=16,max_length=200)
@app.get('/healthz')
def healthz():
 with db() as c:c.execute('SELECT 1')
 return {'status':'ok','database':'postgresql'}
@app.post('/auth/csrf')
def csrf(response:Response):
 t=secrets.token_urlsafe(32); response.set_cookie('csrf_token',t,httponly=False,secure=COOKIE_SECURE,samesite='lax'); return {'csrf_token':t}
@app.post('/auth/login')
def login(p:Login,response:Response,csrf_token:str|None=Cookie(default=None),x_csrf_token:str|None=Header(default=None)):
 require_csrf(csrf_token,x_csrf_token)
 from passlib.hash import bcrypt
 with db() as c,c.cursor() as q:
  q.execute('SELECT id,password_hash FROM users WHERE lower(email)=lower(%s)',(p.email,)); r=q.fetchone()
 if not r or not bcrypt.verify(p.password,r[1]): raise HTTPException(401,'Invalid credentials')
 raw=secrets.token_urlsafe(48)
 with db() as c:c.execute("INSERT INTO sessions(user_id,token_hash,expires_at) VALUES(%s,%s,now()+interval '12 hours')",(r[0],token_hash(raw)))
 response.set_cookie('session',raw,httponly=True,secure=COOKIE_SECURE,samesite='lax',max_age=43200); return {'authenticated':True}
@app.post('/smtp/profiles')
def create_profile(p:SmtpProfile,response:Response,session:str|None=Cookie(default=None),csrf_token:str|None=Cookie(default=None),x_csrf_token:str|None=Header(default=None)):
 u=require_user(session); require_csrf(csrf_token,x_csrf_token); enc=cipher().encrypt(p.password.encode()).decode()
 with db() as c,c.cursor() as q:q.execute('INSERT INTO smtp_profiles(owner_id,name,host,port,username,password_ciphertext,use_tls) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id',(u['id'],p.name,p.host,p.port,p.username,enc,p.use_tls)); pid=q.fetchone()[0]
 return {'id':pid,'name':p.name,'host':p.host,'port':p.port,'username':p.username,'use_tls':p.use_tls}
@app.get('/smtp/profiles')
def profiles(session:str|None=Cookie(default=None)):
 u=require_user(session)
 with db() as c,c.cursor() as q:q.execute('SELECT id,name,host,port,username,use_tls FROM smtp_profiles WHERE owner_id=%s ORDER BY name',(u['id'],)); rows=q.fetchall()
 return [{'id':r[0],'name':r[1],'host':r[2],'port':r[3],'username':r[4],'use_tls':r[5]} for r in rows]
@app.post('/send/reviewed')
def send(p:SendRequest,response:Response,session:str|None=Cookie(default=None),csrf_token:str|None=Cookie(default=None),x_csrf_token:str|None=Header(default=None)):
 u=require_user(session); require_csrf(csrf_token,x_csrf_token)
 with db() as c,c.cursor() as q:
  q.execute('SELECT id,status FROM send_attempts WHERE owner_id=%s AND idempotency_key=%s FOR UPDATE',(u['id'],p.idempotency_key)); old=q.fetchone()
  if old:return {'attempt_id':old[0],'status':old[1],'replayed':True}
  q.execute('SELECT email FROM contacts WHERE id=%s AND owner_id=%s',(p.contact_id,u['id'])); contact=q.fetchone(); q.execute('SELECT host,port,username,password_ciphertext,use_tls FROM smtp_profiles WHERE id=%s AND owner_id=%s',(p.profile_id,u['id'])); prof=q.fetchone()
  if not contact or not prof:raise HTTPException(404,'Contact or SMTP profile not found')
  q.execute('SELECT 1 FROM suppressions WHERE lower(email)=lower(%s)',(contact[0],))
  if q.fetchone():raise HTTPException(409,'Recipient is globally suppressed')
  q.execute("INSERT INTO send_attempts(owner_id,contact_id,profile_id,idempotency_key,status,subject,body) VALUES(%s,%s,%s,%s,'sending',%s,%s) RETURNING id",(u['id'],p.contact_id,p.profile_id,p.idempotency_key,p.subject,p.body)); aid=q.fetchone()[0]
 m=EmailMessage();m['To']=contact[0];m['Subject']=p.subject;m['From']=prof[2];m.set_content(p.body)
 try:
  s=smtplib.SMTP(prof[0],prof[1],timeout=15)
  if prof[5]:s.starttls(context=ssl.create_default_context())
  s.login(prof[2],cipher().decrypt(prof[3].encode()).decode());s.send_message(m);s.quit()
 except Exception as e:
  with db() as c:c.execute("UPDATE send_attempts SET status='uncertain',error_code='delivery_outcome_unknown',error_message=%s WHERE id=%s",(str(e)[:500],aid))
  return {'attempt_id':aid,'status':'uncertain','retry_allowed':False}
 with db() as c:c.execute("UPDATE send_attempts SET status='sent',sent_at=now() WHERE id=%s",(aid,))
 return {'attempt_id':aid,'status':'sent'}
