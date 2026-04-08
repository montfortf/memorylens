from __future__ import annotations

import json

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.base import ExportResult
from memorylens._exporters.jsonl import JSONLExporter


def _make_span(span_id: str = "s1") -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id="t1",
        parent_span_id=None,
        operation=MemoryOperation.WRITE,
        status=SpanStatus.OK,
        start_time=1000.0,
        end_time=1012.0,
        duration_ms=12.0,
        agent_id="bot",
        session_id="sess-1",
        user_id="user-1",
        input_content="data",
        output_content="stored",
        attributes={"backend": "test"},
    )


class TestJSONLExporter:
    def test_export_to_file(self, tmp_path):
        path = str(tmp_path / "traces.jsonl")
        exporter = JSONLExporter(file_path=path)
        result = exporter.export([_make_span("s1"), _make_span("s2")])
        assert result == ExportResult.SUCCESS

        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        obj = json.loads(lines[0])
        assert obj["span_id"] == "s1"
        assert obj["operation"] == "memory.write"
        exporter.shutdown()

    def test_export_to_stdout(self, capsys):
        exporter = JSONLExporter()  # defaults to stdout
        exporter.export([_make_span()])
        captured = capsys.readouterr()
        obj = json.loads(captured.out.strip())
        assert obj["span_id"] == "s1"
        exporter.shutdown()

    def test_append_mode(self, tmp_path):
        path = str(tmp_path / "traces.jsonl")
        exporter = JSONLExporter(file_path=path)
        exporter.export([_make_span("s1")])
        exporter.export([_make_span("s2")])

        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        exporter.shutdown()
