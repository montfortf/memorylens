from __future__ import annotations

import time

import pytest

from memorylens._exporters.sqlite import SQLiteExporter


@pytest.fixture
def exporter(tmp_path):
    db_path = str(tmp_path / "test.db")
    exp = SQLiteExporter(db_path=db_path)
    yield exp
    exp.shutdown()


def _make_rule(**kwargs):
    defaults = {
        "name": "test-rule",
        "alert_type": "drift",
        "threshold": 4.0,
        "webhook_url": None,
        "enabled": True,
        "created_at": time.time(),
    }
    defaults.update(kwargs)
    return defaults


class TestAlertRuleCRUD:
    def test_save_and_get(self, exporter):
        rule = _make_rule(name="rule-1")
        exporter.save_alert_rule(rule)
        fetched = exporter.get_alert_rule("rule-1")
        assert fetched is not None
        assert fetched["name"] == "rule-1"
        assert fetched["alert_type"] == "drift"
        assert fetched["threshold"] == 4.0

    def test_get_nonexistent_returns_none(self, exporter):
        assert exporter.get_alert_rule("no-such-rule") is None

    def test_list_all_rules(self, exporter):
        exporter.save_alert_rule(_make_rule(name="r1", alert_type="drift"))
        exporter.save_alert_rule(_make_rule(name="r2", alert_type="cost"))
        rules = exporter.list_alert_rules()
        assert len(rules) == 2
        names = {r["name"] for r in rules}
        assert names == {"r1", "r2"}

    def test_list_enabled_only(self, exporter):
        exporter.save_alert_rule(_make_rule(name="r-enabled", enabled=True))
        exporter.save_alert_rule(_make_rule(name="r-disabled", enabled=False))
        enabled = exporter.list_alert_rules(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0]["name"] == "r-enabled"

    def test_delete_rule(self, exporter):
        exporter.save_alert_rule(_make_rule(name="to-delete"))
        exporter.delete_alert_rule("to-delete")
        assert exporter.get_alert_rule("to-delete") is None

    def test_delete_nonexistent_is_safe(self, exporter):
        # should not raise
        exporter.delete_alert_rule("nonexistent")

    def test_update_enabled_flag(self, exporter):
        exporter.save_alert_rule(_make_rule(name="my-rule", enabled=True))
        exporter.update_alert_rule("my-rule", {"enabled": 0})
        fetched = exporter.get_alert_rule("my-rule")
        assert fetched["enabled"] == 0

    def test_update_threshold(self, exporter):
        exporter.save_alert_rule(_make_rule(name="my-rule", threshold=3.0))
        exporter.update_alert_rule("my-rule", {"threshold": 5.0})
        fetched = exporter.get_alert_rule("my-rule")
        assert fetched["threshold"] == 5.0

    def test_update_with_unknown_keys_is_safe(self, exporter):
        exporter.save_alert_rule(_make_rule(name="my-rule"))
        # Should not raise, just ignore unknown keys
        exporter.update_alert_rule("my-rule", {"nonexistent_field": "value"})

    def test_list_empty_db(self, exporter):
        rules = exporter.list_alert_rules()
        assert rules == []


class TestAlertHistory:
    def test_save_and_list_history(self, exporter):
        exporter.save_alert_rule(_make_rule(name="drift-rule"))
        rule = exporter.get_alert_rule("drift-rule")
        event = {
            "rule_id": rule["id"],
            "alert_type": "drift",
            "message": "Drift threshold exceeded",
            "details": {"grade": "F", "key": "user_pref"},
            "fired_at": time.time(),
        }
        exporter.save_alert_event(event)
        history = exporter.list_alert_history()
        assert len(history) == 1
        assert history[0]["message"] == "Drift threshold exceeded"
        assert history[0]["alert_type"] == "drift"
        assert isinstance(history[0]["details"], dict)

    def test_list_history_filter_by_type(self, exporter):
        exporter.save_alert_rule(_make_rule(name="rule-drift", alert_type="drift"))
        exporter.save_alert_rule(_make_rule(name="rule-cost", alert_type="cost"))
        drift_rule = exporter.get_alert_rule("rule-drift")
        cost_rule = exporter.get_alert_rule("rule-cost")

        exporter.save_alert_event(
            {"rule_id": drift_rule["id"], "alert_type": "drift", "message": "d", "details": {}, "fired_at": time.time()}
        )
        exporter.save_alert_event(
            {"rule_id": cost_rule["id"], "alert_type": "cost", "message": "c", "details": {}, "fired_at": time.time()}
        )

        drift_history = exporter.list_alert_history(alert_type="drift")
        assert len(drift_history) == 1
        assert drift_history[0]["alert_type"] == "drift"

        cost_history = exporter.list_alert_history(alert_type="cost")
        assert len(cost_history) == 1

    def test_list_history_limit(self, exporter):
        exporter.save_alert_rule(_make_rule(name="rule-1"))
        rule = exporter.get_alert_rule("rule-1")
        for i in range(10):
            exporter.save_alert_event(
                {"rule_id": rule["id"], "alert_type": "drift", "message": f"msg-{i}", "details": {}, "fired_at": time.time() + i}
            )
        limited = exporter.list_alert_history(limit=5)
        assert len(limited) == 5

    def test_list_history_empty(self, exporter):
        history = exporter.list_alert_history()
        assert history == []

    def test_get_last_alert_time(self, exporter):
        exporter.save_alert_rule(_make_rule(name="rule-1"))
        rule = exporter.get_alert_rule("rule-1")
        now = time.time()
        exporter.save_alert_event(
            {"rule_id": rule["id"], "alert_type": "drift", "message": "x", "details": {}, "fired_at": now - 10}
        )
        exporter.save_alert_event(
            {"rule_id": rule["id"], "alert_type": "drift", "message": "y", "details": {}, "fired_at": now}
        )
        last_time = exporter.get_last_alert_time(rule["id"])
        assert last_time is not None
        assert abs(last_time - now) < 1.0

    def test_get_last_alert_time_no_history(self, exporter):
        result = exporter.get_last_alert_time(9999)
        assert result is None
