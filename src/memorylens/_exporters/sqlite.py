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

    def shutdown(self) -> None:
        self._conn.close()
