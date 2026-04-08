from __future__ import annotations

import json
import time

import pytest

from memorylens._alerts.evaluator import AlertEvaluator, AlertEvent
from memorylens._exporters.sqlite import SQLiteExporter


@pytest.fixture
def exporter(tmp_path):
    db_path = str(tmp_path / "test.db")
    exp = SQLiteExporter(db_path=db_path)
    yield exp
    exp.shutdown()


@pytest.fixture
def evaluator(exporter):
    return AlertEvaluator(exporter)


def _make_rule(name="test-rule", alert_type="drift", threshold=4.0, rule_id=1):
    return {
        "id": rule_id,
        "name": name,
        "alert_type": alert_type,
        "threshold": threshold,
        "webhook_url": None,
        "enabled": 1,
        "created_at": time.time(),
    }


def _insert_span(exporter, span_id, operation="memory.read", status="ok", session_id="sess-1", attributes=None):
    """Helper: insert a span row directly."""
    attrs = json.dumps(attributes or {})
    exporter._conn.execute(
        """
        INSERT INTO spans (span_id, trace_id, parent_span_id, operation, status,
            start_time, end_time, duration_ms, agent_id, session_id, user_id,
            input_content, output_content, attributes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (span_id, "trace-1", None, operation, status,
         time.time(), time.time() + 0.1, 100.0, "agent-1", session_id, None,
         None, None, attrs),
    )
    exporter._conn.commit()


class TestDriftAlert:
    def test_drift_triggers_when_grade_meets_threshold(self, exporter, evaluator):
        exporter.save_drift_report({
            "report_type": "entity",
            "key": "user_pref",
            "drift_score": 0.82,
            "contradiction_score": 0.5,
            "staleness_score": 0.3,
            "volatility_score": 0.6,
            "grade": "F",  # F=5, threshold=4 => triggers
            "details": {},
            "created_at": time.time(),
        })
        rule = _make_rule(alert_type="drift", threshold=4.0)
        events = evaluator.evaluate_rule(rule)
        assert len(events) == 1
        assert events[0].alert_type == "drift"
        assert "user_pref" in events[0].message
        assert events[0].details["grade"] == "F"

    def test_drift_no_trigger_below_threshold(self, exporter, evaluator):
        exporter.save_drift_report({
            "report_type": "entity",
            "key": "user_pref",
            "drift_score": 0.1,
            "contradiction_score": 0.05,
            "staleness_score": 0.02,
            "volatility_score": 0.1,
            "grade": "A",  # A=1, threshold=4 => no trigger
            "details": {},
            "created_at": time.time(),
        })
        rule = _make_rule(alert_type="drift", threshold=4.0)
        events = evaluator.evaluate_rule(rule)
        assert len(events) == 0

    def test_drift_triggers_on_grade_equal_to_threshold(self, exporter, evaluator):
        exporter.save_drift_report({
            "report_type": "entity",
            "key": "entity-d",
            "drift_score": 0.5,
            "contradiction_score": 0.3,
            "staleness_score": 0.2,
            "volatility_score": 0.4,
            "grade": "D",  # D=4, threshold=4 => triggers
            "details": {},
            "created_at": time.time(),
        })
        rule = _make_rule(alert_type="drift", threshold=4.0)
        events = evaluator.evaluate_rule(rule)
        assert len(events) == 1
        assert events[0].details["grade"] == "D"

    def test_drift_no_data_returns_empty(self, evaluator):
        rule = _make_rule(alert_type="drift", threshold=4.0)
        events = evaluator.evaluate_rule(rule)
        assert events == []


class TestCostAlert:
    def test_cost_triggers_when_session_exceeds_threshold(self, exporter, evaluator):
        _insert_span(exporter, "s1", operation="memory.write", session_id="sess-expensive",
                     attributes={"cost_usd": 0.03})
        _insert_span(exporter, "s2", operation="memory.write", session_id="sess-expensive",
                     attributes={"cost_usd": 0.03})
        rule = _make_rule(alert_type="cost", threshold=0.05)
        events = evaluator.evaluate_rule(rule)
        assert len(events) == 1
        assert events[0].alert_type == "cost"
        assert "sess-expensive" in events[0].message
        assert events[0].details["total_cost"] == pytest.approx(0.06, abs=1e-6)

    def test_cost_no_trigger_below_threshold(self, exporter, evaluator):
        _insert_span(exporter, "s1", session_id="sess-cheap", attributes={"cost_usd": 0.01})
        rule = _make_rule(alert_type="cost", threshold=0.05)
        events = evaluator.evaluate_rule(rule)
        assert len(events) == 0

    def test_cost_no_cost_spans_returns_empty(self, exporter, evaluator):
        _insert_span(exporter, "s1", session_id="sess-1")  # no cost_usd
        rule = _make_rule(alert_type="cost", threshold=0.05)
        events = evaluator.evaluate_rule(rule)
        assert events == []


class TestRetrievalAlert:
    def test_retrieval_triggers_when_error_rate_exceeds_threshold(self, exporter, evaluator):
        _insert_span(exporter, "r1", operation="memory.read", status="error")
        _insert_span(exporter, "r2", operation="memory.read", status="error")
        _insert_span(exporter, "r3", operation="memory.read", status="ok")
        rule = _make_rule(alert_type="retrieval", threshold=0.10)
        events = evaluator.evaluate_rule(rule)
        assert len(events) == 1
        assert events[0].alert_type == "retrieval"
        assert events[0].details["failure_rate"] == pytest.approx(2 / 3, rel=1e-3)

    def test_retrieval_no_trigger_below_threshold(self, exporter, evaluator):
        _insert_span(exporter, "r1", operation="memory.read", status="ok")
        _insert_span(exporter, "r2", operation="memory.read", status="ok")
        rule = _make_rule(alert_type="retrieval", threshold=0.10)
        events = evaluator.evaluate_rule(rule)
        assert events == []

    def test_retrieval_low_score_counts_as_failure(self, exporter, evaluator):
        _insert_span(exporter, "r1", operation="memory.read", status="ok",
                     attributes={"retrieval_score": 0.3})
        _insert_span(exporter, "r2", operation="memory.read", status="ok",
                     attributes={"retrieval_score": 0.3})
        _insert_span(exporter, "r3", operation="memory.read", status="ok",
                     attributes={"retrieval_score": 0.9})
        rule = _make_rule(alert_type="retrieval", threshold=0.50)
        events = evaluator.evaluate_rule(rule)
        assert len(events) == 1

    def test_retrieval_no_spans_returns_empty(self, evaluator):
        rule = _make_rule(alert_type="retrieval", threshold=0.10)
        events = evaluator.evaluate_rule(rule)
        assert events == []


class TestCompressionLossAlert:
    def test_compression_loss_triggers_when_loss_exceeds_threshold(self, exporter, evaluator):
        # Insert a span first (audit needs span_id)
        _insert_span(exporter, "span-audit-1")
        from unittest.mock import MagicMock
        audit = MagicMock()
        audit.span_id = "span-audit-1"
        audit.semantic_loss_score = 0.75
        audit.compression_ratio = 0.4
        audit.pre_sentence_count = 10
        audit.post_sentence_count = 4
        audit.to_dict.return_value = {"sentences": []}
        audit.scorer_backend = "mock"
        exporter.save_audit(audit)

        rule = _make_rule(alert_type="compression_loss", threshold=0.6)
        events = evaluator.evaluate_rule(rule)
        assert len(events) == 1
        assert events[0].alert_type == "compression_loss"
        assert events[0].details["semantic_loss_score"] == pytest.approx(0.75, rel=1e-3)

    def test_compression_loss_no_trigger_below_threshold(self, exporter, evaluator):
        _insert_span(exporter, "span-audit-2")
        from unittest.mock import MagicMock
        audit = MagicMock()
        audit.span_id = "span-audit-2"
        audit.semantic_loss_score = 0.3
        audit.compression_ratio = 0.8
        audit.pre_sentence_count = 5
        audit.post_sentence_count = 4
        audit.to_dict.return_value = {"sentences": []}
        audit.scorer_backend = "mock"
        exporter.save_audit(audit)

        rule = _make_rule(alert_type="compression_loss", threshold=0.6)
        events = evaluator.evaluate_rule(rule)
        assert events == []

    def test_compression_loss_no_audits_returns_empty(self, evaluator):
        rule = _make_rule(alert_type="compression_loss", threshold=0.6)
        events = evaluator.evaluate_rule(rule)
        assert events == []


class TestErrorRateAlert:
    def test_error_rate_triggers_when_ratio_exceeds_threshold(self, exporter, evaluator):
        for i in range(6):
            _insert_span(exporter, f"e{i}", operation="memory.write", status="error")
        for i in range(4):
            _insert_span(exporter, f"ok{i}", operation="memory.write", status="ok")
        rule = _make_rule(alert_type="error_rate", threshold=0.05)
        events = evaluator.evaluate_rule(rule)
        assert len(events) == 1
        assert events[0].alert_type == "error_rate"
        assert events[0].details["error_rate"] == pytest.approx(0.6, rel=1e-3)

    def test_error_rate_no_trigger_below_threshold(self, exporter, evaluator):
        _insert_span(exporter, "ok1", operation="memory.write", status="ok")
        _insert_span(exporter, "ok2", operation="memory.write", status="ok")
        rule = _make_rule(alert_type="error_rate", threshold=0.05)
        events = evaluator.evaluate_rule(rule)
        assert events == []

    def test_error_rate_no_spans_returns_empty(self, evaluator):
        rule = _make_rule(alert_type="error_rate", threshold=0.05)
        events = evaluator.evaluate_rule(rule)
        assert events == []


class TestCooldown:
    def test_cooldown_suppresses_repeated_alerts(self, exporter, evaluator):
        exporter.save_alert_rule({
            "name": "drift-rule",
            "alert_type": "drift",
            "threshold": 4.0,
            "webhook_url": None,
            "enabled": 1,
            "created_at": time.time(),
        })
        rule = exporter.get_alert_rule("drift-rule")

        exporter.save_drift_report({
            "report_type": "entity",
            "key": "user_pref",
            "drift_score": 0.9,
            "contradiction_score": 0.6,
            "staleness_score": 0.4,
            "volatility_score": 0.7,
            "grade": "F",
            "details": {},
            "created_at": time.time(),
        })

        # First call: should fire
        events1 = evaluator.evaluate_rule(rule)
        assert len(events1) == 1

        # Simulate saving an alert event (as fire_alert would)
        exporter.save_alert_event({
            "rule_id": rule["id"],
            "alert_type": "drift",
            "message": events1[0].message,
            "details": events1[0].details,
            "fired_at": time.time(),
        })

        # Second call: should be suppressed by cooldown
        events2 = evaluator.evaluate_rule(rule)
        assert len(events2) == 0

    def test_unknown_alert_type_returns_empty(self, evaluator):
        rule = _make_rule(alert_type="unknown_type", threshold=1.0)
        events = evaluator.evaluate_rule(rule)
        assert events == []
