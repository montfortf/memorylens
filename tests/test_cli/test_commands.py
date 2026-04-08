from __future__ import annotations

import json

from typer.testing import CliRunner

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.main import app

runner = CliRunner()


def _make_span(
    span_id: str = "s1",
    trace_id: str = "t1",
    operation: MemoryOperation = MemoryOperation.WRITE,
    status: SpanStatus = SpanStatus.OK,
    agent_id: str = "bot",
    session_id: str = "sess-1",
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
        session_id=session_id,
        user_id="user-1",
        input_content="test input",
        output_content="test output",
        attributes={"backend": "test"},
    )


def _seed_db(db_path: str) -> None:
    exporter = SQLiteExporter(db_path=db_path)
    exporter.export(
        [
            _make_span("s1", "t1", MemoryOperation.WRITE, SpanStatus.OK),
            _make_span("s2", "t2", MemoryOperation.READ, SpanStatus.OK),
            _make_span("s3", "t3", MemoryOperation.WRITE, SpanStatus.ERROR),
            _make_span("s4", "t4", MemoryOperation.WRITE, SpanStatus.DROPPED),
        ]
    )
    exporter.shutdown()


class TestTracesListCommand:
    def test_list_all(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, ["traces", "list", "--db-path", db_path])
        assert result.exit_code == 0

    def test_list_filter_operation(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(
            app, ["traces", "list", "--db-path", db_path, "--operation", "memory.read"]
        )
        assert result.exit_code == 0

    def test_list_json_output(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, ["traces", "list", "--db-path", db_path, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)


class TestTracesShowCommand:
    def test_show_by_trace_id(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, ["traces", "show", "t1", "--db-path", db_path])
        assert result.exit_code == 0

    def test_show_not_found(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, ["traces", "show", "nonexistent", "--db-path", db_path])
        assert result.exit_code == 0
        assert "not found" in result.stdout.lower() or "no trace" in result.stdout.lower()


class TestTracesExportCommand:
    def test_export_jsonl(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        out_path = str(tmp_path / "export.jsonl")
        result = runner.invoke(
            app, ["traces", "export", "--db-path", db_path, "--output", out_path]
        )
        assert result.exit_code == 0
        with open(out_path) as f:
            lines = f.readlines()
        assert len(lines) >= 1
        obj = json.loads(lines[0])
        assert "span_id" in obj


class TestInitCommand:
    def test_init_creates_directory(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / ".memorylens").is_dir()
