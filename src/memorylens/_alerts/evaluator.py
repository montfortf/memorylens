from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memorylens._exporters.sqlite import SQLiteExporter

_GRADE_TO_NUM = {"A": 1, "B": 2, "C": 3, "D": 4, "F": 5}
_COOLDOWN_SECONDS = 3600


@dataclass(frozen=True)
class AlertEvent:
    rule_name: str
    alert_type: str
    message: str
    details: dict


class AlertEvaluator:
    """Evaluates alert rules against stored data and fires alerts."""

    def __init__(self, exporter: SQLiteExporter) -> None:
        self._exporter = exporter

    def evaluate_rule(self, rule: dict) -> list[AlertEvent]:
        """Dispatch to the appropriate check method for this rule's type."""
        alert_type = rule["alert_type"]
        dispatch = {
            "drift": self._check_drift,
            "cost": self._check_cost,
            "retrieval": self._check_retrieval,
            "compression_loss": self._check_compression_loss,
            "error_rate": self._check_error_rate,
        }
        check_fn = dispatch.get(alert_type)
        if check_fn is None:
            return []
        return check_fn(rule)

    def fire_alert(self, event: AlertEvent, rule: dict) -> None:
        """Send webhook (if configured) and save to alert_history."""
        from memorylens._alerts.webhook import send_webhook

        rule_id = rule.get("id", 0)
        fired_at = time.time()

        # Save to history first
        self._exporter.save_alert_event(
            {
                "rule_id": rule_id,
                "alert_type": event.alert_type,
                "message": event.message,
                "details": event.details,
                "fired_at": fired_at,
            }
        )

        # Send webhook if configured
        webhook_url = rule.get("webhook_url")
        if webhook_url:
            import datetime

            payload = {
                "alert": f"{event.alert_type}_threshold_exceeded",
                "rule_name": event.rule_name,
                "message": event.message,
                "details": event.details,
                "timestamp": datetime.datetime.utcfromtimestamp(fired_at).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
            }
            send_webhook(webhook_url, payload)

    def _is_on_cooldown(self, rule: dict) -> bool:
        """Return True if this rule fired within the last COOLDOWN_SECONDS."""
        rule_id = rule.get("id")
        if rule_id is None:
            return False
        last_time = self._exporter.get_last_alert_time(rule_id)
        if last_time is None:
            return False
        return (time.time() - last_time) < _COOLDOWN_SECONDS

    def _check_drift(self, rule: dict) -> list[AlertEvent]:
        """Alert when any drift report grade >= threshold (A=1..F=5)."""
        if self._is_on_cooldown(rule):
            return []

        threshold = rule["threshold"]
        reports, _ = self._exporter.list_drift_reports(limit=1000)
        events: list[AlertEvent] = []
        for report in reports:
            grade = report.get("grade", "A")
            grade_num = _GRADE_TO_NUM.get(grade, 1)
            if grade_num >= threshold:
                events.append(
                    AlertEvent(
                        rule_name=rule["name"],
                        alert_type="drift",
                        message=(
                            f"Entity {report['key']} has grade {grade} "
                            f"(drift: {report.get('drift_score', 0):.2f})"
                        ),
                        details={
                            "memory_key": report["key"],
                            "grade": grade,
                            "drift_score": report.get("drift_score", 0),
                        },
                    )
                )
        return events

    def _check_cost(self, rule: dict) -> list[AlertEvent]:
        """Alert when any session's total cost_usd exceeds threshold."""
        if self._is_on_cooldown(rule):
            return []

        threshold = rule["threshold"]
        spans = self._exporter.query(limit=10000)
        session_costs: dict[str, float] = {}
        for span in spans:
            attrs_raw = span.get("attributes", "{}")
            if isinstance(attrs_raw, str):
                try:
                    attrs = json.loads(attrs_raw)
                except Exception:
                    attrs = {}
            else:
                attrs = attrs_raw or {}
            cost = attrs.get("cost_usd")
            if cost is not None:
                try:
                    cost = float(cost)
                except (TypeError, ValueError):
                    continue
                session_id = span.get("session_id") or "unknown"
                session_costs[session_id] = session_costs.get(session_id, 0.0) + cost

        events: list[AlertEvent] = []
        for session_id, total_cost in session_costs.items():
            if total_cost > threshold:
                events.append(
                    AlertEvent(
                        rule_name=rule["name"],
                        alert_type="cost",
                        message=(
                            f"Session {session_id} cost ${total_cost:.4f} "
                            f"exceeds threshold ${threshold:.4f}"
                        ),
                        details={
                            "session_id": session_id,
                            "total_cost": total_cost,
                            "threshold": threshold,
                        },
                    )
                )
        return events

    def _check_retrieval(self, rule: dict) -> list[AlertEvent]:
        """Alert when ratio of failed reads exceeds threshold."""
        if self._is_on_cooldown(rule):
            return []

        threshold = rule["threshold"]
        # Query READ spans
        spans = self._exporter.query(operation="memory.read", limit=10000)
        if not spans:
            return []

        total = len(spans)
        failed = 0
        for span in spans:
            status = span.get("status", "")
            if status == "error":
                failed += 1
                continue
            # Check if all retrieval scores are below 0.5
            attrs_raw = span.get("attributes", "{}")
            if isinstance(attrs_raw, str):
                try:
                    attrs = json.loads(attrs_raw)
                except Exception:
                    attrs = {}
            else:
                attrs = attrs_raw or {}
            score = attrs.get("retrieval_score") or attrs.get("score")
            if score is not None:
                try:
                    if float(score) < 0.5:
                        failed += 1
                except (TypeError, ValueError):
                    pass

        ratio = failed / total if total > 0 else 0.0
        if ratio > threshold:
            return [
                AlertEvent(
                    rule_name=rule["name"],
                    alert_type="retrieval",
                    message=(
                        f"Retrieval failure rate {ratio:.1%} exceeds threshold {threshold:.1%} "
                        f"({failed}/{total} reads failed)"
                    ),
                    details={
                        "failure_rate": ratio,
                        "failed_reads": failed,
                        "total_reads": total,
                        "threshold": threshold,
                    },
                )
            ]
        return []

    def _check_compression_loss(self, rule: dict) -> list[AlertEvent]:
        """Alert when any compression audit has semantic_loss_score >= threshold."""
        if self._is_on_cooldown(rule):
            return []

        threshold = rule["threshold"]
        audits, _ = self._exporter.list_audits(limit=1000)
        events: list[AlertEvent] = []
        for audit in audits:
            loss = audit.get("semantic_loss_score", 0.0)
            if loss >= threshold:
                events.append(
                    AlertEvent(
                        rule_name=rule["name"],
                        alert_type="compression_loss",
                        message=(
                            f"Compression audit for span {audit['span_id']} "
                            f"has high semantic loss {loss:.2f} (threshold: {threshold:.2f})"
                        ),
                        details={
                            "span_id": audit["span_id"],
                            "semantic_loss_score": loss,
                            "compression_ratio": audit.get("compression_ratio", 0),
                            "threshold": threshold,
                        },
                    )
                )
        return events

    def _check_error_rate(self, rule: dict) -> list[AlertEvent]:
        """Alert when proportion of spans with status=error exceeds threshold."""
        if self._is_on_cooldown(rule):
            return []

        threshold = rule["threshold"]
        spans = self._exporter.query(limit=10000)
        if not spans:
            return []

        total = len(spans)
        errors = sum(1 for s in spans if s.get("status") == "error")
        ratio = errors / total if total > 0 else 0.0

        if ratio > threshold:
            return [
                AlertEvent(
                    rule_name=rule["name"],
                    alert_type="error_rate",
                    message=(
                        f"Error rate {ratio:.1%} exceeds threshold {threshold:.1%} "
                        f"({errors}/{total} spans errored)"
                    ),
                    details={
                        "error_rate": ratio,
                        "error_count": errors,
                        "total_spans": total,
                        "threshold": threshold,
                    },
                )
            ]
        return []
