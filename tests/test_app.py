import os
import re
import unittest

os.environ.setdefault("SESSION_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("SMTP_ENCRYPTION_KEY", "9Y9s8qT7uV3wX2yZ4aB6cD8eF0gH1jK3lM5nP7rS9tU=")

from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import main


class ProspektoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.getenv("DATABASE_URL", "").startswith(("postgresql://", "postgres://")):
            raise unittest.SkipTest("DATABASE_URL must point to PostgreSQL; migrations are applied by CI")
        os.environ["ADMIN_PASSWORD_HASH"] = PasswordHasher().hash("pw")
        with main.conn() as db:
            db.execute("DELETE FROM smtp_profiles")
            db.execute("DELETE FROM prospects")
            db.execute("DELETE FROM campaigns")
        cls.client = TestClient(main.app)

    def csrf(self, path="/login"):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        token = re.search(r'name="csrf" value="([^"]+)"', response.text)
        self.assertIsNotNone(token)
        return token.group(1)

    def login(self):
        token = self.csrf()
        response = self.client.post(
            "/login",
            data={"username": "admin", "password": "pw", "csrf": token},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

    def test_health_and_safe_status(self):
        self.assertEqual(main.health()["status"], "ok")
        self.assertFalse(main.status()["real_sending"])

    def test_auth_csrf_and_suppression(self):
        self.assertEqual(TestClient(main.app).get("/").status_code, 401)
        self.login()
        token = self.csrf("/prospects")
        self.assertEqual(
            self.client.post(
                "/prospects",
                data={"company_name": "Acme", "provenance": "annuaire"},
                follow_redirects=False,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/prospects",
                data={
                    "company_name": "Acme",
                    "provenance": "annuaire",
                    "csrf": token,
                },
                follow_redirects=False,
            ).status_code,
            303,
        )
        with main.conn() as db:
            prospect_id = db.execute(
                "SELECT id FROM prospects WHERE company_name=%s", ("Acme",)
            ).fetchone()["id"]
        self.assertEqual(
            self.client.post(
                f"/prospects/{prospect_id}/opposition",
                data={"csrf": token},
                follow_redirects=False,
            ).status_code,
            303,
        )
        self.assertNotIn("Acme", self.client.get("/prospects/export.csv").text)

    def test_campaign_creation_and_smtp_profile(self):
        self.login()
        token = self.csrf("/campaigns")
        self.assertEqual(
            self.client.post(
                "/campaigns", data={"name": "Draft"}, follow_redirects=False
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/campaigns",
                data={"name": "Draft", "csrf": token},
                follow_redirects=False,
            ).status_code,
            303,
        )
        token = self.csrf("/smtp-profiles")
        self.assertEqual(
            self.client.post(
                "/smtp-profiles",
                data={
                    "name": "Fake",
                    "host": "localhost",
                    "port": 1025,
                    "username": "u",
                    "password": "secret-value",
                    "csrf": token,
                },
                follow_redirects=False,
            ).status_code,
            303,
        )
        with main.conn() as db:
            stored = db.execute(
                "SELECT password_ciphertext FROM smtp_profiles WHERE name=%s",
                ("Fake",),
            ).fetchone()["password_ciphertext"]
        self.assertNotEqual(stored, "secret-value")
        self.assertEqual(
            Fernet(os.environ["SMTP_ENCRYPTION_KEY"].encode())
            .decrypt(stored.encode())
            .decode(),
            "secret-value",
        )


if __name__ == "__main__":
    unittest.main()
