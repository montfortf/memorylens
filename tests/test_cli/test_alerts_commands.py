from __future__ import annotations

import time

import pytest
from typer.testing import CliRunner

from memorylens.cli.main import app


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


class TestAlertsAddCommand:
    def test_add_drift_rule(self, db_path):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["alerts", "add", "my-drift-rule", "--type", "drift", "--threshold", "4.0", "--db-path", db_path],
        )
        assert result.exit_code == 0, result.output
        assert "my-drift-rule" in result.output
        assert "added" in result.output

    def test_add_cost_rule_with_webhook(self, db_path):
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "alerts", "add", "cost-spike",
                "--type", "cost",
                "--threshold", "0.05",
                "--webhook", "https://hooks.slack.com/xyz",
                "--db-path", db_path,
            ],
        )
        assert result.exit_code == 0, result.output
        assert "cost-spike" in result.output

    def test_add_all_valid_types(self, db_path):
        runner = CliRunner()
        for alert_type in ["drift", "cost", "retrieval", "compression_loss", "error_rate"]:
            result = runner.invoke(
                app,
                ["alerts", "add", f"rule-{alert_type}", "--type", alert_type, "--threshold", "0.5", "--db-path", db_path],
            )
            assert result.exit_code == 0, f"Failed for type {alert_type}: {result.output}"

    def test_add_invalid_type_fails(self, db_path):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["alerts", "add", "bad-rule", "--type", "unknown_type", "--threshold", "1.0", "--db-path", db_path],
        )
        assert result.exit_code != 0
        assert "Unknown alert type" in result.output


class TestAlertsListCommand:
    def test_list_empty(self, db_path):
        runner = CliRunner()
        result = runner.invoke(app, ["alerts", "list", "--db-path", db_path])
        assert result.exit_code == 0
        assert "No alert rules" in result.output

    def test_list_shows_rules(self, db_path):
        runner = CliRunner()
        runner.invoke(app, ["alerts", "add", "rule-1", "--type", "drift", "--threshold", "4.0", "--db-path", db_path])
        runner.invoke(app, ["alerts", "add", "rule-2", "--type", "cost", "--threshold", "0.05", "--db-path", db_path])
        result = runner.invoke(app, ["alerts", "list", "--db-path", db_path])
        assert result.exit_code == 0
        assert "rule-1" in result.output
        assert "rule-2" in result.output
        assert "drift" in result.output
        assert "cost" in result.output


class TestAlertsRemoveCommand:
    def test_remove_existing_rule(self, db_path):
        runner = CliRunner()
        runner.invoke(app, ["alerts", "add", "to-remove", "--type", "drift", "--threshold", "4.0", "--db-path", db_path])
        result = runner.invoke(app, ["alerts", "remove", "to-remove", "--db-path", db_path])
        assert result.exit_code == 0
        assert "removed" in result.output

        # Verify it's gone
        list_result = runner.invoke(app, ["alerts", "list", "--db-path", db_path])
        assert "to-remove" not in list_result.output

    def test_remove_nonexistent_rule(self, db_path):
        runner = CliRunner()
        result = runner.invoke(app, ["alerts", "remove", "nonexistent", "--db-path", db_path])
        assert result.exit_code == 0
        assert "not found" in result.output.lower() or "No rule" in result.output


class TestAlertsEnableDisable:
    def test_enable_rule(self, db_path):
        runner = CliRunner()
        runner.invoke(app, ["alerts", "add", "my-rule", "--type", "drift", "--threshold", "4.0", "--db-path", db_path])
        runner.invoke(app, ["alerts", "disable", "my-rule", "--db-path", db_path])
        result = runner.invoke(app, ["alerts", "enable", "my-rule", "--db-path", db_path])
        assert result.exit_code == 0
        assert "enabled" in result.output

    def test_disable_rule(self, db_path):
        runner = CliRunner()
        runner.invoke(app, ["alerts", "add", "my-rule", "--type", "drift", "--threshold", "4.0", "--db-path", db_path])
        result = runner.invoke(app, ["alerts", "disable", "my-rule", "--db-path", db_path])
        assert result.exit_code == 0
        assert "disabled" in result.output

    def test_enable_nonexistent(self, db_path):
        runner = CliRunner()
        result = runner.invoke(app, ["alerts", "enable", "nonexistent", "--db-path", db_path])
        assert result.exit_code == 0
        assert "not found" in result.output.lower() or "No rule" in result.output

    def test_disable_nonexistent(self, db_path):
        runner = CliRunner()
        result = runner.invoke(app, ["alerts", "disable", "nonexistent", "--db-path", db_path])
        assert result.exit_code == 0


class TestAlertsHistoryCommand:
    def test_history_empty(self, db_path):
        runner = CliRunner()
        result = runner.invoke(app, ["alerts", "history", "--db-path", db_path])
        assert result.exit_code == 0
        assert "No alert history" in result.output

    def test_history_shows_events(self, db_path):
        from memorylens._exporters.sqlite import SQLiteExporter

        exp = SQLiteExporter(db_path=db_path)
        exp.save_alert_rule({"name": "r1", "alert_type": "drift", "threshold": 4.0, "webhook_url": None, "enabled": 1, "created_at": time.time()})
        rule = exp.get_alert_rule("r1")
        exp.save_alert_event({
            "rule_id": rule["id"],
            "alert_type": "drift",
            "message": "Grade F detected",
            "details": {},
            "fired_at": time.time(),
        })
        exp.shutdown()

        runner = CliRunner()
        result = runner.invoke(app, ["alerts", "history", "--db-path", db_path])
        assert result.exit_code == 0
        assert "Grade F detected" in result.output

    def test_history_filter_by_type(self, db_path):
        from memorylens._exporters.sqlite import SQLiteExporter

        exp = SQLiteExporter(db_path=db_path)
        exp.save_alert_rule({"name": "r1", "alert_type": "drift", "threshold": 4.0, "webhook_url": None, "enabled": 1, "created_at": time.time()})
        rule = exp.get_alert_rule("r1")
        exp.save_alert_event({"rule_id": rule["id"], "alert_type": "drift", "message": "drift msg", "details": {}, "fired_at": time.time()})
        exp.save_alert_event({"rule_id": rule["id"], "alert_type": "cost", "message": "cost msg", "details": {}, "fired_at": time.time()})
        exp.shutdown()

        runner = CliRunner()
        result = runner.invoke(app, ["alerts", "history", "--type", "drift", "--db-path", db_path])
        assert result.exit_code == 0
        assert "drift msg" in result.output
        assert "cost msg" not in result.output
