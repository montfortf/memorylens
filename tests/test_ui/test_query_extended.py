from __future__ import annotations

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter


def _make_span(
    span_id: str = "s1",
    trace_id: str = "t1",
    operation: MemoryOperation = MemoryOperation.WRITE,
    status: SpanStatus = SpanStatus.OK,
    agent_id: str = "bot",
    input_content: str = "test input",
    output_content: str = "test output",
) -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=None,
        operation=operation,
        status=status,
        start_time=1000000000000.0,
        end_time=1000012000000.0,
        duration_ms=12.0,
        agent_id=agent_id,
        session_id="sess-1",
        user_id="user-1",
        input_content=input_content,
        output_content=output_content,
        attributes={"backend": "test"},
    )


def _seed_db(exporter: SQLiteExporter) -> None:
    exporter.export([
        _make_span("s1", "t1", MemoryOperation.WRITE, input_content="user prefers jazz"),
        _make_span("s2", "t2", MemoryOperation.READ, input_content="music preferences"),
        _make_span("s3", "t3", MemoryOperation.WRITE, status=SpanStatus.ERROR, input_content="failed write"),
        _make_span("s4", "t4", MemoryOperation.WRITE, input_content="user likes pizza"),
        _make_span("s5", "t5", MemoryOperation.READ, input_content="food preferences"),
    ])


class TestQueryExtended:
    def test_basic_query(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        _seed_db(exporter)
        rows, total = exporter.query_extended()
        assert total == 5
        assert len(rows) == 5
        exporter.shutdown()

    def test_fulltext_search(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        _seed_db(exporter)
        rows, total = exporter.query_extended(q="jazz")
        assert total == 1
        assert rows[0]["span_id"] == "s1"
        exporter.shutdown()

    def test_fulltext_search_output(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        _seed_db(exporter)
        rows, total = exporter.query_extended(q="test output")
        assert total == 5
        exporter.shutdown()

    def test_pagination_offset(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        _seed_db(exporter)
        rows, total = exporter.query_extended(limit=2, offset=0)
        assert len(rows) == 2
        assert total == 5
        rows2, total2 = exporter.query_extended(limit=2, offset=2)
        assert len(rows2) == 2
        assert total2 == 5
        assert rows[0]["span_id"] != rows2[0]["span_id"]
        exporter.shutdown()

    def test_filter_with_search(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        _seed_db(exporter)
        rows, total = exporter.query_extended(operation="memory.read", q="preferences")
        assert total == 2
        for row in rows:
            assert row["operation"] == "memory.read"
        exporter.shutdown()

    def test_total_count_independent_of_limit(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        _seed_db(exporter)
        rows, total = exporter.query_extended(limit=1)
        assert len(rows) == 1
        assert total == 5
        exporter.shutdown()
