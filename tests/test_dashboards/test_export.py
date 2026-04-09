from __future__ import annotations

from typer.testing import CliRunner

from memorylens.cli.main import app

runner = CliRunner()


class TestExportDashboard:
    def test_export_grafana_all(self, tmp_path):
        result = runner.invoke(app, ["export", "dashboard", "--format", "grafana", "--output", str(tmp_path)])
        assert result.exit_code == 0
        assert "4 dashboard" in result.stdout
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 4

    def test_export_datadog_all(self, tmp_path):
        result = runner.invoke(app, ["export", "dashboard", "--format", "datadog", "--output", str(tmp_path)])
        assert result.exit_code == 0
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 4

    def test_export_single(self, tmp_path):
        result = runner.invoke(app, ["export", "dashboard", "--format", "grafana", "--name", "operations", "--output", str(tmp_path)])
        assert result.exit_code == 0
        assert "1 dashboard" in result.stdout
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1

    def test_export_unknown_platform(self, tmp_path):
        result = runner.invoke(app, ["export", "dashboard", "--format", "unknown", "--output", str(tmp_path)])
        assert result.exit_code == 1

    def test_export_unknown_name(self, tmp_path):
        result = runner.invoke(app, ["export", "dashboard", "--format", "grafana", "--name", "nonexistent", "--output", str(tmp_path)])
        assert result.exit_code == 1
