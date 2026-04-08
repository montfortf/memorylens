from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from memorylens._ui.server import create_app

    db_path = str(tmp_path / "test.db")
    app = create_app(db_path=db_path)
    return TestClient(app), db_path


@pytest.fixture
def client_with_data(tmp_path):
    from memorylens._exporters.sqlite import SQLiteExporter
    from memorylens._ui.server import create_app

    db_path = str(tmp_path / "test.db")
    exp = SQLiteExporter(db_path=db_path)
    now = time.time()

    # Add rules
    exp.save_alert_rule({"name": "drift-rule", "alert_type": "drift", "threshold": 4.0, "webhook_url": None, "enabled": 1, "created_at": now})
    exp.save_alert_rule({"name": "cost-rule", "alert_type": "cost", "threshold": 0.05, "webhook_url": "https://hooks.slack.com/x", "enabled": 0, "created_at": now})

    drift_rule = exp.get_alert_rule("drift-rule")
    # Add history
    exp.save_alert_event({
        "rule_id": drift_rule["id"],
        "alert_type": "drift",
        "message": "Entity user_pref has grade F",
        "details": {"grade": "F"},
        "fired_at": now,
    })
    exp.shutdown()

    app = create_app(db_path=db_path)
    return TestClient(app), db_path


class TestAlertsPage:
    def test_empty_page_returns_200(self, client):
        c, _ = client
        response = c.get("/alerts")
        assert response.status_code == 200
        assert "Alerts" in response.text

    def test_empty_page_shows_no_rules_message(self, client):
        c, _ = client
        response = c.get("/alerts")
        assert response.status_code == 200
        assert "No alert rules defined" in response.text

    def test_empty_page_shows_no_history_message(self, client):
        c, _ = client
        response = c.get("/alerts")
        assert response.status_code == 200
        assert "No alert history found" in response.text

    def test_page_with_rules_shows_rules(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/alerts")
        assert response.status_code == 200
        assert "drift-rule" in response.text
        assert "cost-rule" in response.text

    def test_page_shows_alert_types(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/alerts")
        assert response.status_code == 200
        assert "drift" in response.text
        assert "cost" in response.text

    def test_page_shows_history(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/alerts")
        assert response.status_code == 200
        assert "Entity user_pref has grade F" in response.text

    def test_type_filter_shows_filtered_history(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/alerts?type=drift")
        assert response.status_code == 200
        assert "Entity user_pref has grade F" in response.text

    def test_type_filter_hides_other_types(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/alerts?type=cost")
        assert response.status_code == 200
        # No cost alerts were saved, so the drift alert should not appear
        assert "Entity user_pref has grade F" not in response.text

    def test_nav_has_alerts_link(self, client):
        c, _ = client
        response = c.get("/alerts")
        assert response.status_code == 200
        assert 'href="/alerts"' in response.text

    def test_alerts_nav_is_active(self, client):
        c, _ = client
        response = c.get("/alerts")
        assert response.status_code == 200
        # The active nav class should be applied
        assert "active_nav" in response.text or "text-indigo-400" in response.text

    def test_webhook_url_displayed(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/alerts")
        assert response.status_code == 200
        assert "hooks.slack.com" in response.text

    def test_enabled_status_shown(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/alerts")
        assert response.status_code == 200
        # Both enabled and disabled rules are present
        assert "yes" in response.text
        assert "no" in response.text
