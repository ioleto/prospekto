import ast
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app import main


ROOT = Path(__file__).parents[1]


class CampaignRegressionTests(unittest.TestCase):
    class _RecordingConnection:
        def __init__(self):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            self.calls.append((query, params))
            return self

        def fetchall(self):
            return []

    def test_mutating_campaign_and_association_routes_require_authentication(self):
        client = TestClient(main.app)
        requests = (
            ("/campaigns", {"name": "Example"}),
            ("/campaigns/example/edit", {"name": "Example", "segment_type": "b2b"}),
            ("/campaigns/example/status", {"status": "active"}),
            ("/prospects/example/campaign", {"campaign_id": ""}),
        )
        for path, data in requests:
            response = client.post(path, data=data, follow_redirects=False)
            self.assertEqual(response.status_code, 401, path)

    def test_campaign_validation_rejects_bad_segment_and_status(self):
        with self.assertRaises(main.HTTPException) as bad_segment:
            main.validate_campaign("name", "consumer", "draft", [], [])
        self.assertEqual(bad_segment.exception.status_code, 422)

        with self.assertRaises(main.HTTPException) as bad_status:
            main.validate_campaign("name", "b2b", "sending", [], [])
        self.assertEqual(bad_status.exception.status_code, 422)

    def test_campaign_validation_rejects_include_exclude_overlap(self):
        with self.assertRaises(main.HTTPException) as overlap:
            main.validate_campaign("name", "b2b", "draft", ["finance"], ["finance"])
        self.assertEqual(overlap.exception.status_code, 422)

    def test_campaign_routes_call_guard_and_csrf_before_database_work(self):
        tree = ast.parse((ROOT / "app" / "main.py").read_text())
        expected = {"create_campaign", "edit_campaign", "campaign_status", "associate_prospect"}
        found = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in expected:
                calls = {
                    child.func.id
                    for child in ast.walk(node)
                    if isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Name)
                }
                found[node.name] = calls
        self.assertEqual(set(found), expected)
        for name, calls in found.items():
            self.assertIn("guard", calls, name)
            self.assertIn("require_csrf", calls, name)

    def test_campaign_migration_matches_application_contract(self):
        migration = (ROOT / "migrations" / "003_campaign_management.sql").read_text()
        for column in (
            "segment_type",
            "inclusion_criteria",
            "exclusion_criteria",
            "smtp_profile_id",
        ):
            self.assertIn(column, migration)
        self.assertIn("REFERENCES smtp_profiles(id)", migration)
        self.assertIn("idx_prospects_campaign_id", migration)

    def test_prospects_query_explicitly_types_nullable_campaign_filter(self):
        source = (ROOT / "app" / "main.py").read_text()
        self.assertIn("(%s::text IS NULL OR p.campaign_id=%s)", source)

    def test_campaign_write_queries_wrap_jsonb_parameters(self):
        fake_conn = self._RecordingConnection()
        with (
            patch.object(main, "conn", return_value=fake_conn),
            patch.object(main, "guard"),
            patch.object(main, "require_csrf"),
            patch.object(main.secrets, "token_hex", return_value="campaign-id"),
        ):
            main.create_campaign(
                request=object(),
                name="Campagne",
                segment_type="b2b",
                inclusion_sector="",
                exclusion_sector="",
                inclusion_type="",
                exclusion_type="",
                inclusion_size="",
                exclusion_size="",
                inclusion_geography="",
                exclusion_geography="",
                inclusion_language="",
                exclusion_language="",
                smtp_profile_id="",
                csrf_token="csrf",
            )
            main.edit_campaign(
                campaign_id="campaign-id",
                request=object(),
                name="Campagne",
                segment_type="b2b",
                inclusion_sector="",
                exclusion_sector="",
                inclusion_type="",
                exclusion_type="",
                inclusion_size="",
                exclusion_size="",
                inclusion_geography="",
                exclusion_geography="",
                inclusion_language="",
                exclusion_language="",
                smtp_profile_id="",
                csrf_token="csrf",
            )

        insert_params = fake_conn.calls[0][1]
        self.assertIsInstance(insert_params[3], Jsonb)
        self.assertIsInstance(insert_params[4], Jsonb)

        update_params = fake_conn.calls[1][1]
        self.assertIsInstance(update_params[2], Jsonb)
        self.assertIsInstance(update_params[3], Jsonb)


if __name__ == "__main__":
    unittest.main()
