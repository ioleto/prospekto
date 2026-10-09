import ast
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from app import main


ROOT = Path(__file__).parents[1]


class CampaignRegressionTests(unittest.TestCase):
    def test_mutating_campaign_and_association_routes_require_authentication(self):
        client = TestClient(main.app)
        for path in (
            "/campaigns",
            "/campaigns/example/edit",
            "/campaigns/example/status",
            "/prospects/example/campaign",
        ):
            response = client.post(path, follow_redirects=False)
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


if __name__ == "__main__":
    unittest.main()
