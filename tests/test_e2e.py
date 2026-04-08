from __future__ import annotations

import memorylens
from memorylens import context, instrument_read, instrument_write
from memorylens._exporters.sqlite import SQLiteExporter


class TestEndToEnd:
    def test_full_flow_with_sqlite(self, tmp_path):
        """Test: init → decorate → context → call → query traces."""
        db_path = str(tmp_path / "e2e.db")

        memorylens.init(
            service_name="test-agent",
            exporter="sqlite",
            db_path=db_path,
            capture_content=True,
            sample_rate=1.0,
        )

        @instrument_write(backend="test_db")
        def store_memory(content: str) -> str:
            return f"stored: {content}"

        @instrument_read(backend="test_db")
        def search_memory(query: str) -> list[str]:
            return ["result1", "result2"]

        with context(agent_id="support-bot", session_id="sess-001", user_id="user-42"):
            store_memory("user prefers dark mode")
            results = search_memory("user preferences")

        assert results == ["result1", "result2"]

        # Flush all pending spans
        memorylens.shutdown()

        # Query the SQLite store directly
        exporter = SQLiteExporter(db_path=db_path)
        spans = exporter.query(limit=10)
        exporter.shutdown()

        assert len(spans) == 2

        write_spans = [s for s in spans if s["operation"] == "memory.write"]
        read_spans = [s for s in spans if s["operation"] == "memory.read"]
        assert len(write_spans) == 1
        assert len(read_spans) == 1

        write_span = write_spans[0]
        assert write_span["agent_id"] == "support-bot"
        assert write_span["session_id"] == "sess-001"
        assert write_span["user_id"] == "user-42"
        assert write_span["status"] == "ok"

    def test_error_flow(self, tmp_path):
        """Test: decorated function that raises an exception."""
        db_path = str(tmp_path / "e2e_err.db")

        memorylens.init(
            service_name="test-agent",
            exporter="sqlite",
            db_path=db_path,
        )

        @instrument_write(backend="flaky_db")
        def store_memory(content: str) -> str:
            raise ConnectionError("database unreachable")

        try:
            store_memory("important data")
        except ConnectionError:
            pass

        memorylens.shutdown()

        exporter = SQLiteExporter(db_path=db_path)
        spans = exporter.query(limit=10)
        exporter.shutdown()

        assert len(spans) == 1
        assert spans[0]["status"] == "error"
