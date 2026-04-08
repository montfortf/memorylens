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
    # Pre-populate versions and a report
    exporter = SQLiteExporter(db_path=db_path)
    now = time.time()
    for i in range(3):
        exporter.save_version(
            {
                "memory_key": "user_42_prefs",
                "version": i + 1,
                "span_id": f"span-{i}",
                "operation": "memory.write",
                "content": f"User preference version {i + 1}.",
                "embedding": None,
                "agent_id": "agent-1",
                "session_id": f"sess-{i}",
                "timestamp": now - (3 - i) * 3600,
            }
        )
    exporter.save_drift_report(
        {
            "report_type": "entity",
            "key": "user_42_prefs",
            "drift_score": 0.25,
            "contradiction_score": 0.10,
            "staleness_score": 0.05,
            "volatility_score": 0.80,
            "grade": "B",
            "details": {"version_count": 3},
            "created_at": now,
        }
    )
    exporter.shutdown()

    app = create_app(db_path=db_path)
    return TestClient(app), db_path


class TestDriftDashboard:
    def test_dashboard_empty(self, client):
        c, _ = client
        response = c.get("/drift")
        assert response.status_code == 200
        assert "Drift" in response.text
        assert "No drift reports found" in response.text

    def test_dashboard_with_data(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift")
        assert response.status_code == 200
        assert "user_42_prefs" in response.text

    def test_dashboard_type_filter_entity(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift?type=entity")
        assert response.status_code == 200

    def test_dashboard_type_filter_session(self, client):
        c, _ = client
        response = c.get("/drift?type=session")
        assert response.status_code == 200

    def test_dashboard_type_filter_topic(self, client):
        c, _ = client
        response = c.get("/drift?type=topic")
        assert response.status_code == 200

    def test_dashboard_grade_filter(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift?grade=D")
        assert response.status_code == 200

    def test_dashboard_active_nav(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift")
        assert response.status_code == 200
        # Nav should mark drift as active
        assert "active_nav" in response.text or "Drift" in response.text


class TestDriftDetail:
    def test_detail_unknown_key_returns_404(self, client):
        c, _ = client
        response = c.get("/drift/nonexistent_key")
        assert response.status_code == 404

    def test_detail_known_key_returns_200(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift/user_42_prefs")
        assert response.status_code == 200
        assert "user_42_prefs" in response.text

    def test_detail_shows_grade(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift/user_42_prefs")
        assert response.status_code == 200
        assert "B" in response.text  # grade

    def test_detail_shows_version_history(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift/user_42_prefs")
        assert response.status_code == 200
        assert "Version History" in response.text

    def test_detail_shows_health_scores(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift/user_42_prefs")
        assert response.status_code == 200
        # Score labels should appear
        assert "Drift" in response.text
        assert "Contradiction" in response.text
