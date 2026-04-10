from __future__ import annotations

import json

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter


def _make_span(span_id: str = "s1", attributes: dict | None = None) -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id="t1",
        parent_span_id=None,
        operation=MemoryOperation.WRITE,
        status=SpanStatus.OK,
        start_time=1000.0,
        end_time=1010.0,
        duration_ms=10.0,
        agent_id="bot",
        session_id="sess-1",
        user_id="user-1",
        input_content="data",
        output_content="stored",
        attributes=attributes or {"backend": "test"},
    )


class TestUpdateSpanAttributes:
    def test_merge_new_attributes(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.export([_make_span("s1", {"backend": "test", "tokens_in": 100})])

        exporter.update_span_attributes("s1", {"cost_usd": 0.0015})

        rows = exporter.query(trace_id="t1")
        attrs = json.loads(rows[0]["attributes"])
        assert attrs["cost_usd"] == 0.0015
        assert attrs["backend"] == "test"  # original preserved
        assert attrs["tokens_in"] == 100  # original preserved
        exporter.shutdown()

    def test_update_nonexistent_span(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.update_span_attributes("nonexistent", {"cost_usd": 0.0})  # should not raise
        exporter.shutdown()

    def test_overwrite_existing_attribute(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.export([_make_span("s1", {"cost_usd": 0.001})])

        exporter.update_span_attributes("s1", {"cost_usd": 0.002})

        rows = exporter.query(trace_id="t1")
        attrs = json.loads(rows[0]["attributes"])
        assert attrs["cost_usd"] == 0.002
        exporter.shutdown()
