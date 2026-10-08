import os, unittest
os.environ['DATABASE_URL']='sqlite:////tmp/prospekto-test.db'; os.environ['SESSION_SECRET']='test-secret'; os.environ['ADMIN_PASSWORD']='pw'
from app.main import health, init_db, conn, status
class ProspektoTests(unittest.TestCase):
 def test_health(self): self.assertEqual(health()['status'],'ok')
 def test_schema_and_safe_defaults(self):
  init_db(); c=conn(); self.assertIsNotNone(c.execute("select name from sqlite_master where type='table' and name='prospects'").fetchone()); c.close(); self.assertFalse(status()['real_sending'])
if __name__=='__main__': unittest.main()
