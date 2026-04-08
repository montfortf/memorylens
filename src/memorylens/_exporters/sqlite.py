from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from memorylens._core.span import MemorySpan
from memorylens._exporters.base import ExportResult

_DEFAULT_DB_PATH = os.path.expanduser("~/.memorylens/traces.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS spans (
    span_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    parent_span_id TEXT,
    operation TEXT NOT NULL,
    status TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    duration_ms REAL NOT NULL,
    agent_id TEXT,
    session_id TEXT,
    user_id TEXT,
    input_content TEXT,
    output_content TEXT,
    attributes TEXT NOT NULL DEFAULT '{}'
)
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans (trace_id)",
    "CREATE INDEX IF NOT EXISTS idx_spans_session_id ON spans (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_spans_operation ON spans (operation)",
    "CREATE INDEX IF NOT EXISTS idx_spans_start_time ON spans (start_time)",
]

_INSERT_SPAN = """
INSERT OR REPLACE INTO spans (
    span_id, trace_id, parent_span_id, operation, status,
    start_time, end_time, duration_ms,
    agent_id, session_id, user_id,
    input_content, output_content, attributes
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_CREATE_VERSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS memory_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    span_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    content TEXT,
    embedding TEXT,
    agent_id TEXT,
    session_id TEXT,
    timestamp REAL NOT NULL,
    UNIQUE(memory_key, version)
)
"""

_CREATE_VERSIONS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_versions_memory_key ON memory_versions (memory_key)",
    "CREATE INDEX IF NOT EXISTS idx_versions_session_id ON memory_versions (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_versions_timestamp ON memory_versions (timestamp)",
]

_CREATE_DRIFT_REPORTS_TABLE = """
CREATE TABLE IF NOT EXISTS drift_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT NOT NULL,
    key TEXT NOT NULL,
    drift_score REAL NOT NULL,
    contradiction_score REAL NOT NULL,
    staleness_score REAL NOT NULL,
    volatility_score REAL NOT NULL,
    grade TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(report_type, key)
)
"""

_CREATE_DRIFT_REPORTS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_drift_reports_type ON drift_reports (report_type)",
    "CREATE INDEX IF NOT EXISTS idx_drift_reports_grade ON drift_reports (grade)",
]

_INSERT_VERSION = """
INSERT OR REPLACE INTO memory_versions (
    memory_key, version, span_id, operation, content,
    embedding, agent_id, session_id, timestamp
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_DRIFT_REPORT = """
INSERT OR REPLACE INTO drift_reports (
    report_type, key, drift_score, contradiction_score,
    staleness_score, volatility_score, grade, details, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_CREATE_ALERT_RULES_TABLE = """
CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    alert_type TEXT NOT NULL,
    threshold REAL NOT NULL,
    webhook_url TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
)
"""

_CREATE_ALERT_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    alert_type TEXT NOT NULL,
    message TEXT NOT NULL,
    details TEXT NOT NULL,
    fired_at REAL NOT NULL
)
"""

_CREATE_AUDIT_TABLE = """
CREATE TABLE IF NOT EXISTS compression_audits (
    span_id TEXT PRIMARY KEY,
    semantic_loss_score REAL NOT NULL,
    compression_ratio REAL NOT NULL,
    pre_sentence_count INTEGER NOT NULL,
    post_sentence_count INTEGER NOT NULL,
    sentences TEXT NOT NULL,
    scorer_backend TEXT NOT NULL,
    created_at REAL NOT NULL
)
"""

_INSERT_AUDIT = """
INSERT OR REPLACE INTO compression_audits (
    span_id, semantic_loss_score, compression_ratio,
    pre_sentence_count, post_sentence_count,
    sentences, scorer_backend, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


class SQLiteExporter:
    """Exports spans to a local SQLite database."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE)
        for idx_sql in _CREATE_INDEXES:
            self._conn.execute(idx_sql)
        self._conn.commit()

    def export(self, spans: list[MemorySpan]) -> ExportResult:
        try:
            rows = [
                (
                    s.span_id,
                    s.trace_id,
                    s.parent_span_id,
                    s.operation.value if hasattr(s.operation, "value") else s.operation,
                    s.status.value if hasattr(s.status, "value") else s.status,
                    s.start_time,
                    s.end_time,
                    s.duration_ms,
                    s.agent_id,
                    s.session_id,
                    s.user_id,
                    s.input_content,
                    s.output_content,
                    json.dumps(s.attributes),
                )
                for s in spans
            ]
            self._conn.executemany(_INSERT_SPAN, rows)
            self._conn.commit()
            return ExportResult.SUCCESS
        except Exception:
            return ExportResult.FAILURE

    def query(
        self,
        trace_id: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query spans from the database. Returns list of dicts."""
        conditions: list[str] = []
        params: list[Any] = []

        if trace_id:
            conditions.append("trace_id = ?")
            params.append(trace_id)
        if operation:
            conditions.append("operation = ?")
            params.append(operation)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM spans WHERE {where} ORDER BY start_time DESC LIMIT ?"
        params.append(limit)

        cursor = self._conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def query_extended(
        self,
        trace_id: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query spans with full-text search, pagination, and total count."""
        conditions: list[str] = []
        params: list[Any] = []

        if trace_id:
            conditions.append("trace_id = ?")
            params.append(trace_id)
        if operation:
            conditions.append("operation = ?")
            params.append(operation)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if q:
            conditions.append("(input_content LIKE ? OR output_content LIKE ?)")
            q_param = f"%{q}%"
            params.extend([q_param, q_param])

        where = " AND ".join(conditions) if conditions else "1=1"

        count_sql = f"SELECT COUNT(*) FROM spans WHERE {where}"
        total = self._conn.execute(count_sql, params).fetchone()[0]

        sql = f"SELECT * FROM spans WHERE {where} ORDER BY start_time DESC LIMIT ? OFFSET ?"
        row_params = params + [limit, offset]
        cursor = self._conn.execute(sql, row_params)
        rows = [dict(row) for row in cursor.fetchall()]

        return rows, total

    def _ensure_audit_table(self) -> None:
        """Create the compression_audits table if it doesn't exist."""
        self._conn.execute(_CREATE_AUDIT_TABLE)
        self._conn.commit()

    def save_audit(self, audit: Any) -> None:
        """Save a compression audit result. Creates table if needed."""
        import time

        self._ensure_audit_table()
        self._conn.execute(
            _INSERT_AUDIT,
            (
                audit.span_id,
                audit.semantic_loss_score,
                audit.compression_ratio,
                audit.pre_sentence_count,
                audit.post_sentence_count,
                json.dumps(audit.to_dict()["sentences"]),
                audit.scorer_backend,
                time.time(),
            ),
        )
        self._conn.commit()

    def get_audit(self, span_id: str) -> dict[str, Any] | None:
        """Get audit result for a span, or None if not audited."""
        try:
            self._ensure_audit_table()
        except Exception:
            return None
        cursor = self._conn.execute(
            "SELECT * FROM compression_audits WHERE span_id = ?", (span_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_audits(self, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        """List all audits with pagination. Returns (rows, total_count)."""
        self._ensure_audit_table()
        total = self._conn.execute("SELECT COUNT(*) FROM compression_audits").fetchone()[0]
        cursor = self._conn.execute(
            "SELECT * FROM compression_audits ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        return rows, total

    def update_span_attributes(self, span_id: str, new_attrs: dict[str, Any]) -> None:
        """Merge new_attrs into existing span attributes JSON."""
        cursor = self._conn.execute("SELECT attributes FROM spans WHERE span_id = ?", (span_id,))
        row = cursor.fetchone()
        if row is None:
            return
        current = json.loads(row[0]) if row[0] else {}
        current.update(new_attrs)
        self._conn.execute(
            "UPDATE spans SET attributes = ? WHERE span_id = ?",
            (json.dumps(current), span_id),
        )
        self._conn.commit()

    # ── Version methods ──────────────────────────────────────────────────────

    def _ensure_versions_table(self) -> None:
        """Create memory_versions table and indexes if they don't exist."""
        self._conn.execute(_CREATE_VERSIONS_TABLE)
        for idx_sql in _CREATE_VERSIONS_INDEXES:
            self._conn.execute(idx_sql)
        self._conn.commit()

    def save_version(self, version: dict) -> None:
        """Save a memory version record. Creates table if needed."""
        self._ensure_versions_table()
        self._conn.execute(
            _INSERT_VERSION,
            (
                version["memory_key"],
                version["version"],
                version["span_id"],
                version["operation"],
                version.get("content"),
                json.dumps(version["embedding"]) if version.get("embedding") else None,
                version.get("agent_id"),
                version.get("session_id"),
                version["timestamp"],
            ),
        )
        self._conn.commit()

    def get_versions(self, memory_key: str) -> list[dict]:
        """Get all versions for a memory key, ordered by version number."""
        try:
            self._ensure_versions_table()
        except Exception:
            return []
        cursor = self._conn.execute(
            "SELECT * FROM memory_versions WHERE memory_key = ? ORDER BY version ASC",
            (memory_key,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            if row.get("embedding") and isinstance(row["embedding"], str):
                row["embedding"] = json.loads(row["embedding"])
        return rows

    def get_all_versions(self) -> list[dict]:
        """Get all memory versions, ordered by memory_key then version."""
        try:
            self._ensure_versions_table()
        except Exception:
            return []
        cursor = self._conn.execute(
            "SELECT * FROM memory_versions ORDER BY memory_key ASC, version ASC"
        )
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            if row.get("embedding") and isinstance(row["embedding"], str):
                row["embedding"] = json.loads(row["embedding"])
        return rows

    # ── Drift report methods ─────────────────────────────────────────────────

    def _ensure_drift_reports_table(self) -> None:
        """Create drift_reports table and indexes if they don't exist."""
        self._conn.execute(_CREATE_DRIFT_REPORTS_TABLE)
        for idx_sql in _CREATE_DRIFT_REPORTS_INDEXES:
            self._conn.execute(idx_sql)
        self._conn.commit()

    def save_drift_report(self, report: dict) -> None:
        """Save (upsert) a drift report. Creates table if needed."""
        import time

        self._ensure_drift_reports_table()
        self._conn.execute(
            _INSERT_DRIFT_REPORT,
            (
                report["report_type"],
                report["key"],
                report["drift_score"],
                report["contradiction_score"],
                report["staleness_score"],
                report["volatility_score"],
                report["grade"],
                json.dumps(report.get("details", {})),
                report.get("created_at", time.time()),
            ),
        )
        self._conn.commit()

    def get_drift_report(self, report_type: str, key: str) -> dict | None:
        """Get a single drift report by type + key, or None if not found."""
        try:
            self._ensure_drift_reports_table()
        except Exception:
            return None
        cursor = self._conn.execute(
            "SELECT * FROM drift_reports WHERE report_type = ? AND key = ?",
            (report_type, key),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        if isinstance(result.get("details"), str):
            result["details"] = json.loads(result["details"])
        return result

    def list_drift_reports(
        self,
        report_type: str | None = None,
        min_grade: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List drift reports with optional filters. Returns (rows, total_count).

        min_grade filters to grades >= that letter (F < D < C < B < A).
        E.g. min_grade="D" returns D and F reports.
        """
        self._ensure_drift_reports_table()

        _GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}

        conditions: list[str] = []
        params: list[Any] = []

        if report_type:
            conditions.append("report_type = ?")
            params.append(report_type)

        if min_grade and min_grade in _GRADE_ORDER:
            # Include grades with severity >= min_grade (lower score = worse)
            max_score = _GRADE_ORDER[min_grade]
            qualifying = [g for g, s in _GRADE_ORDER.items() if s <= max_score]
            placeholders = ",".join("?" * len(qualifying))
            conditions.append(f"grade IN ({placeholders})")
            params.extend(qualifying)

        where = " AND ".join(conditions) if conditions else "1=1"
        count_sql = f"SELECT COUNT(*) FROM drift_reports WHERE {where}"
        total = self._conn.execute(count_sql, params).fetchone()[0]

        sql = f"SELECT * FROM drift_reports WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        row_params = params + [limit, offset]
        cursor = self._conn.execute(sql, row_params)
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            if isinstance(row.get("details"), str):
                row["details"] = json.loads(row["details"])
        return rows, total

    # ── Alert rule methods ───────────────────────────────────────────────────

    def _ensure_alert_rules_table(self) -> None:
        """Create alert_rules table if it doesn't exist."""
        self._conn.execute(_CREATE_ALERT_RULES_TABLE)
        self._conn.commit()

    def _ensure_alert_history_table(self) -> None:
        """Create alert_history table if it doesn't exist."""
        self._conn.execute(_CREATE_ALERT_HISTORY_TABLE)
        self._conn.commit()

    def save_alert_rule(self, rule: dict) -> None:
        """Save (insert) an alert rule. Creates table if needed."""
        import time

        self._ensure_alert_rules_table()
        self._conn.execute(
            """
            INSERT INTO alert_rules (name, alert_type, threshold, webhook_url, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                rule["name"],
                rule["alert_type"],
                rule["threshold"],
                rule.get("webhook_url"),
                1 if rule.get("enabled", True) else 0,
                rule.get("created_at", time.time()),
            ),
        )
        self._conn.commit()

    def get_alert_rule(self, name: str) -> dict | None:
        """Get an alert rule by name, or None if not found."""
        try:
            self._ensure_alert_rules_table()
        except Exception:
            return None
        cursor = self._conn.execute(
            "SELECT * FROM alert_rules WHERE name = ?", (name,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_alert_rules(self, enabled_only: bool = False) -> list[dict]:
        """List all alert rules, optionally only enabled ones."""
        self._ensure_alert_rules_table()
        if enabled_only:
            cursor = self._conn.execute(
                "SELECT * FROM alert_rules WHERE enabled = 1 ORDER BY created_at ASC"
            )
        else:
            cursor = self._conn.execute(
                "SELECT * FROM alert_rules ORDER BY created_at ASC"
            )
        return [dict(row) for row in cursor.fetchall()]

    def delete_alert_rule(self, name: str) -> None:
        """Delete an alert rule by name."""
        self._ensure_alert_rules_table()
        self._conn.execute("DELETE FROM alert_rules WHERE name = ?", (name,))
        self._conn.commit()

    def update_alert_rule(self, name: str, updates: dict) -> None:
        """Update fields on an existing alert rule."""
        self._ensure_alert_rules_table()
        allowed = {"alert_type", "threshold", "webhook_url", "enabled"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [name]
        self._conn.execute(
            f"UPDATE alert_rules SET {set_clause} WHERE name = ?", values
        )
        self._conn.commit()

    # ── Alert history methods ────────────────────────────────────────────────

    def save_alert_event(self, event: dict) -> None:
        """Save an alert event to history. Creates table if needed."""
        import time

        self._ensure_alert_history_table()
        self._conn.execute(
            """
            INSERT INTO alert_history (rule_id, alert_type, message, details, fired_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event["rule_id"],
                event["alert_type"],
                event["message"],
                json.dumps(event.get("details", {})),
                event.get("fired_at", time.time()),
            ),
        )
        self._conn.commit()

    def list_alert_history(
        self, alert_type: str | None = None, limit: int = 50
    ) -> list[dict]:
        """List recent alert history, optionally filtered by type."""
        self._ensure_alert_history_table()
        if alert_type:
            cursor = self._conn.execute(
                "SELECT * FROM alert_history WHERE alert_type = ? ORDER BY fired_at DESC LIMIT ?",
                (alert_type, limit),
            )
        else:
            cursor = self._conn.execute(
                "SELECT * FROM alert_history ORDER BY fired_at DESC LIMIT ?",
                (limit,),
            )
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            if isinstance(row.get("details"), str):
                row["details"] = json.loads(row["details"])
        return rows

    def get_last_alert_time(self, rule_id: int) -> float | None:
        """Get the fired_at timestamp of the most recent alert for a rule, or None."""
        try:
            self._ensure_alert_history_table()
        except Exception:
            return None
        cursor = self._conn.execute(
            "SELECT fired_at FROM alert_history WHERE rule_id = ? ORDER BY fired_at DESC LIMIT 1",
            (rule_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def shutdown(self) -> None:
        self._conn.close()
