import os, re, unittest
os.environ['DATABASE_URL']='sqlite:////tmp/prospekto-test.db'; os.environ['SESSION_SECRET']='test-secret'; os.environ['ADMIN_USERNAME']='admin'; from cryptography.fernet import Fernet, InvalidToken
os.environ['SMTP_ENCRYPTION_KEY']=Fernet.generate_key().decode()
from fastapi.testclient import TestClient
from argon2 import PasswordHasher
from app import main
class ProspektoTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  try: os.unlink('/tmp/prospekto-test.db')
  except FileNotFoundError: pass
  os.environ['ADMIN_PASSWORD_HASH']=PasswordHasher().hash('pw'); main.init_db(); cls.client=TestClient(main.app)
 def csrf(self,path='/login'):
  r=self.client.get(path); self.assertEqual(r.status_code,200); return re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
 def login(self):
  t=self.csrf(); self.assertEqual(self.client.post('/login',data={'username':'admin','password':'pw','csrf':t},follow_redirects=False).status_code,303)
 def test_health_and_safe_status(self): self.assertEqual(main.health()['status'],'ok'); self.assertFalse(main.status()['real_sending'])
 def test_auth_csrf_and_suppression(self):
  self.assertEqual(TestClient(main.app).get('/').status_code,401); self.login(); t=self.csrf('/prospects'); self.assertEqual(self.client.post('/prospects',data={'company_name':'Acme','provenance':'annuaire'},follow_redirects=False).status_code,403); self.assertEqual(self.client.post('/prospects',data={'company_name':'Acme','provenance':'annuaire','csrf':t},follow_redirects=False).status_code,303); row=main.conn().execute("select id from prospects where company_name='Acme'").fetchone(); self.assertEqual(self.client.post(f'/prospects/{row[0]}/opposition',data={'csrf':t},follow_redirects=False).status_code,303); self.assertNotIn('Acme',self.client.get('/prospects/export.csv').text)
 def test_editable_draft_and_smtp_confirmation(self):
  self.login(); t=self.csrf('/campaigns'); self.assertEqual(self.client.post('/campaigns',data={'name':'Draft','csrf':t},follow_redirects=False).status_code,303); row=main.conn().execute("select id from campaigns where name='Draft'").fetchone(); t=self.csrf(f'/campaigns/{row[0]}'); self.assertEqual(self.client.post(f'/campaigns/{row[0]}',data={'name':'Draft édité','status':'ready','csrf':t},follow_redirects=False).status_code,303); t=self.csrf('/smtp-profiles'); self.assertEqual(self.client.post('/smtp-profiles',data={'name':'Fake','host':'localhost','port':1025,'username':'u','password':'p','csrf':t},follow_redirects=False).status_code,303); self.assertEqual(self.client.post('/campaigns/no/send-confirm',data={'prospect_id':'x','confirm':'CONFIRMER ENVOI INDIVIDUEL','csrf':t}).status_code,409)
 def test_smtp_password_is_fernet_encrypted(self):
  self.login(); t=self.csrf('/smtp-profiles'); self.assertEqual(self.client.post('/smtp-profiles',data={'name':'Crypto','host':'localhost','port':1025,'username':'u','password':'secret-value','csrf':t},follow_redirects=False).status_code,303); stored=main.conn().execute("select password_ciphertext from smtp_profiles where name='Crypto'").fetchone()[0]; self.assertNotEqual(stored,'secret-value'); self.assertEqual(Fernet(os.environ['SMTP_ENCRYPTION_KEY'].encode()).decrypt(stored.encode()).decode(),'secret-value')
 def test_smtp_test_requires_explicit_confirmation_and_mode(self):
  self.login(); t=self.csrf('/smtp-profiles'); self.client.post('/smtp-profiles',data={'name':'Fake2','host':'localhost','port':1025,'username':'u','password':'p','csrf':t},follow_redirects=False); pid=main.conn().execute("select id from smtp_profiles where name='Fake2'").fetchone()[0]; self.assertEqual(self.client.post(f'/smtp-profiles/{pid}/test',data={'csrf':t},).status_code,400); self.assertEqual(self.client.post(f'/smtp-profiles/{pid}/test',data={'csrf':t,'confirm':'TEST SMTP'}).status_code,409)
if __name__=='__main__': unittest.main()
