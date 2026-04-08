from __future__ import annotations

import json

from typer.testing import CliRunner

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.main import app

runner = CliRunner()


def _make_span(span_id: str = "s1", trace_id: str = "t1", tokens_in: int = 100, tokens_out: int = 50) -> MemorySpan:
    return MemorySpan(
        span_id=span_id, trace_id=trace_id, parent_span_id=None,
        operation=MemoryOperation.WRITE, status=SpanStatus.OK,
        start_time=1000.0, end_time=1010.0, duration_ms=10.0,
        agent_id="bot", session_id="sess-1", user_id="user-1",
        input_content="data", output_content="stored",
        attributes={"backend": "test", "tokens_in": tokens_in, "tokens_out": tokens_out, "model": "gpt-4o-mini"},
    )


def _seed_db(db_path: str) -> None:
    exporter = SQLiteExporter(db_path=db_path)
    exporter.export([
        _make_span("s1", "t1", 100, 50),
        _make_span("s2", "t2", 200, 100),
        _make_span("s3", "t3", 0, 0),  # no tokens
    ])
    exporter.shutdown()


class TestCostEnrichCommand:
    def test_enrich_runs(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, ["cost", "enrich", "--db-path", db_path])
        assert result.exit_code == 0
        assert "Enriched: 2" in result.stdout

    def test_enrich_skips_already_enriched(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        runner.invoke(app, ["cost", "enrich", "--db-path", db_path])
        result = runner.invoke(app, ["cost", "enrich", "--db-path", db_path])
        assert "Skipped: 3" in result.stdout or "Enriched: 0" in result.stdout


class TestCostReportCommand:
    def test_report_runs(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        runner.invoke(app, ["cost", "enrich", "--db-path", db_path])
        result = runner.invoke(app, ["cost", "report", "--db-path", db_path])
        assert result.exit_code == 0
        assert "memory.write" in result.stdout or "OPERATION" in result.stdout


class TestCostPricingCommand:
    def test_pricing_shows_table(self, tmp_path):
        result = runner.invoke(app, ["cost", "pricing"])
        assert result.exit_code == 0
        assert "gpt-4o" in result.stdout
