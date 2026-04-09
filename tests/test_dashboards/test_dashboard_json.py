from __future__ import annotations

import json

from memorylens.dashboards import get_dashboard_path, list_dashboards


class TestDashboardJSON:
    def test_grafana_dashboards_exist(self):
        names = list_dashboards("grafana")
        assert set(names) == {"operations", "retrieval", "cost", "drift"}

    def test_datadog_dashboards_exist(self):
        names = list_dashboards("datadog")
        assert set(names) == {"operations", "retrieval", "cost", "drift"}

    def test_grafana_json_valid(self):
        for name in list_dashboards("grafana"):
            path = get_dashboard_path("grafana", name)
            data = json.loads(path.read_text())
            assert "title" in data, f"grafana/{name}.json missing 'title'"
            assert "panels" in data, f"grafana/{name}.json missing 'panels'"
            assert len(data["panels"]) > 0, f"grafana/{name}.json has no panels"

    def test_datadog_json_valid(self):
        for name in list_dashboards("datadog"):
            path = get_dashboard_path("datadog", name)
            data = json.loads(path.read_text())
            assert "title" in data, f"datadog/{name}.json missing 'title'"
            assert "widgets" in data, f"datadog/{name}.json missing 'widgets'"
            assert len(data["widgets"]) > 0, f"datadog/{name}.json has no widgets"

    def test_grafana_has_memorylens_tag(self):
        for name in list_dashboards("grafana"):
            path = get_dashboard_path("grafana", name)
            data = json.loads(path.read_text())
            assert "memorylens" in data.get("tags", [])

    def test_nonexistent_dashboard_raises(self):
        try:
            get_dashboard_path("grafana", "nonexistent")
            assert False, "Should raise"
        except FileNotFoundError:
            pass

    def test_nonexistent_platform_empty(self):
        assert list_dashboards("unknown") == []
