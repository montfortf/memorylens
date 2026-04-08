from __future__ import annotations

import sqlite3
import json

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.base import ExportResult
from memorylens._exporters.sqlite import SQLiteExporter


def _make_span(
    span_id: str = "s1",
    operation: MemoryOperation = MemoryOperation.WRITE,
    status: SpanStatus = SpanStatus.OK,
    attributes: dict | None = None,
) -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id="t1",
        parent_span_id=None,
        operation=operation,
        status=status,
        start_time=1000000000000.0,
        end_time=1000012000000.0,
        duration_ms=12.0,
        agent_id="bot",
        session_id="sess-1",
        user_id="user-1",
        input_content="input data",
        output_content="output data",
        attributes=attributes or {"backend": "test"},
    )


class TestSQLiteExporter:
    def test_export_and_query(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        span = _make_span()
        result = exporter.export([span])
        assert result == ExportResult.SUCCESS

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM spans").fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["span_id"] == "s1"
        assert row["trace_id"] == "t1"
        assert row["operation"] == "memory.write"
        assert row["status"] == "ok"
        assert row["agent_id"] == "bot"
        assert row["input_content"] == "input data"
        attrs = json.loads(row["attributes"])
        assert attrs["backend"] == "test"
        conn.close()
        exporter.shutdown()

    def test_export_multiple_spans(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        spans = [_make_span(f"s{i}") for i in range(5)]
        result = exporter.export(spans)
        assert result == ExportResult.SUCCESS

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
        assert count == 5
        conn.close()
        exporter.shutdown()

    def test_auto_creates_db(self, tmp_path):
        db_path = str(tmp_path / "subdir" / "traces.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.export([_make_span()])

        conn = sqlite3.connect(db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "spans" in table_names
        conn.close()
        exporter.shutdown()

    def test_query_by_operation(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.export([
            _make_span("s1", operation=MemoryOperation.WRITE),
            _make_span("s2", operation=MemoryOperation.READ),
            _make_span("s3", operation=MemoryOperation.WRITE),
        ])

        rows = exporter.query(operation="memory.write")
        assert len(rows) == 2
        exporter.shutdown()

    def test_query_by_status(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.export([
            _make_span("s1", status=SpanStatus.OK),
            _make_span("s2", status=SpanStatus.ERROR),
            _make_span("s3", status=SpanStatus.DROPPED),
        ])

        rows = exporter.query(status="error")
        assert len(rows) == 1
        assert rows[0]["span_id"] == "s2"
        exporter.shutdown()

    def test_query_by_trace_id(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.export([_make_span("s1")])

        rows = exporter.query(trace_id="t1")
        assert len(rows) == 1
        exporter.shutdown()
