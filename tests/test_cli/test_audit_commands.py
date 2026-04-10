from __future__ import annotations

from typer.testing import CliRunner

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.main import app

runner = CliRunner()


def _make_compress_span(
    span_id: str = "s1",
    trace_id: str = "t1",
    pre: str = "User prefers jazz. Also likes classical music. Plays piano.",
    post: str = "User likes jazz and classical, plays piano.",
) -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=None,
        operation=MemoryOperation.COMPRESS,
        status=SpanStatus.OK,
        start_time=1000000000000.0,
        end_time=1000100000000.0,
        duration_ms=100.0,
        agent_id="bot",
        session_id="sess-1",
        user_id="user-1",
        input_content=pre,
        output_content=post,
        attributes={"model": "gpt-4o-mini"},
    )


def _seed_db(db_path: str) -> None:
    exporter = SQLiteExporter(db_path=db_path)
    exporter.export(
        [
            _make_compress_span("s1", "t1"),
            _make_compress_span(
                "s2",
                "t2",
                pre="Meeting on Thursday. Weather was nice. Budget discussion.",
                post="Budget was discussed.",
            ),
        ]
    )
    exporter.shutdown()


class TestAuditCompress:
    def test_audit_compress_runs(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, ["audit", "compress", "--db-path", db_path, "--scorer", "mock"])
        assert result.exit_code == 0
        assert "2" in result.stdout  # 2 spans analyzed

    def test_audit_compress_specific_trace(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(
            app,
            [
                "audit",
                "compress",
                "--db-path",
                db_path,
                "--scorer",
                "mock",
                "--trace-id",
                "t1",
            ],
        )
        assert result.exit_code == 0


class TestAuditShow:
    def test_show_after_audit(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        # First audit
        runner.invoke(app, ["audit", "compress", "--db-path", db_path, "--scorer", "mock"])
        # Then show
        result = runner.invoke(app, ["audit", "show", "s1", "--db-path", db_path])
        assert result.exit_code == 0
        assert "s1" in result.stdout

    def test_show_not_found(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, ["audit", "show", "nonexistent", "--db-path", db_path])
        assert result.exit_code == 0
        assert "not found" in result.stdout.lower() or "No audit" in result.stdout


class TestAuditList:
    def test_list_after_audit(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        runner.invoke(app, ["audit", "compress", "--db-path", db_path, "--scorer", "mock"])
        result = runner.invoke(app, ["audit", "list", "--db-path", db_path])
        assert result.exit_code == 0
