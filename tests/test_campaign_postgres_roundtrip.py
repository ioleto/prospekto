import os
from unittest.mock import patch

import pytest

from app import main


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith(("postgresql://", "postgres://")),
    reason="DATABASE_URL must point to the isolated PostgreSQL CI service",
)


def _campaign_form(**overrides):
    values = {
        "name": "Roundtrip campaign",
        "segment_type": "b2b",
        "inclusion_sector": "software, fintech",
        "exclusion_sector": "gambling",
        "inclusion_type": "saas",
        "exclusion_type": "agency",
        "inclusion_size": "11-50",
        "exclusion_size": "1-10",
        "inclusion_geography": "FR",
        "exclusion_geography": "US",
        "inclusion_language": "fr",
        "exclusion_language": "en",
        "smtp_profile_id": "",
        "csrf_token": "csrf",
    }
    values.update(overrides)
    return values


def test_campaign_create_edit_criteria_roundtrip_and_prospect_filter(monkeypatch):
    monkeypatch.setattr(main, "guard", lambda request: None)
    monkeypatch.setattr(main, "require_csrf", lambda request, token: None)
    monkeypatch.setattr(main, "csrf", lambda request: "csrf")
    campaign_id = "integration-roundtrip-campaign"
    prospect_ids = ("integration-roundtrip-prospect-a", "integration-roundtrip-prospect-b")

    with main.conn() as db:
        db.execute("DELETE FROM prospects WHERE id = ANY(%s)", (list(prospect_ids),))
        db.execute("DELETE FROM campaigns WHERE id=%s", (campaign_id,))

    try:
        with patch.object(main.secrets, "token_hex", return_value=campaign_id):
            response = main.create_campaign(request=object(), **_campaign_form())
        assert response.status_code == 303

        with main.conn() as db:
            created = db.execute(
                "SELECT inclusion_criteria, exclusion_criteria FROM campaigns WHERE id=%s",
                (campaign_id,),
            ).fetchone()
        assert created["inclusion_criteria"]["sector"] == ["software", "fintech"]
        assert created["exclusion_criteria"]["sector"] == ["gambling"]

        edited = _campaign_form(
            inclusion_sector="healthcare",
            exclusion_sector="crypto",
            inclusion_geography="DE",
            exclusion_geography="CN",
        )
        response = main.edit_campaign(campaign_id=campaign_id, request=object(), **edited)
        assert response.status_code == 303

        with main.conn() as db:
            updated = db.execute(
                "SELECT inclusion_criteria, exclusion_criteria FROM campaigns WHERE id=%s",
                (campaign_id,),
            ).fetchone()
            db.execute(
                "INSERT INTO prospects (id, company_name, email, provenance, status, created_at, campaign_id) "
                "VALUES (%s, %s, %s, %s, 'new', now(), %s), (%s, %s, %s, %s, 'new', now(), NULL)",
                (prospect_ids[0], "Filtered Co", "a@example.test", "integration", campaign_id,
                 prospect_ids[1], "Unfiltered Co", "b@example.test", "integration"),
            )
        assert updated["inclusion_criteria"]["sector"] == ["healthcare"]
        assert updated["exclusion_criteria"]["sector"] == ["crypto"]

        filtered = main.prospects(request=object(), campaign_id=campaign_id)
        unfiltered = main.prospects(request=object(), campaign_id=None)
        assert "Filtered Co" in filtered.body.decode()
        assert "Unfiltered Co" not in filtered.body.decode()
        assert "Filtered Co" in unfiltered.body.decode()
        assert "Unfiltered Co" in unfiltered.body.decode()
    finally:
        with main.conn() as db:
            db.execute("DELETE FROM prospects WHERE id = ANY(%s)", (list(prospect_ids),))
            db.execute("DELETE FROM campaigns WHERE id=%s", (campaign_id,))
