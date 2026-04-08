from __future__ import annotations

import time

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._core.processor import SimpleSpanProcessor, BatchSpanProcessor
from memorylens._exporters.base import SpanExporter, ExportResult


def _make_span(span_id: str = "s1", operation: MemoryOperation = MemoryOperation.WRITE) -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id="t1",
        parent_span_id=None,
        operation=operation,
        status=SpanStatus.OK,
        start_time=1000.0,
        end_time=1010.0,
        duration_ms=10.0,
        agent_id=None,
        session_id=None,
        user_id=None,
        input_content=None,
        output_content=None,
        attributes={},
    )


class CollectingExporter:
    """Test exporter that collects spans in a list."""

    def __init__(self):
        self.spans: list[MemorySpan] = []

    def export(self, spans: list[MemorySpan]) -> ExportResult:
        self.spans.extend(spans)
        return ExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


class TestSimpleSpanProcessor:
    def test_on_end_exports_immediately(self):
        exporter = CollectingExporter()
        processor = SimpleSpanProcessor(exporter)
        span = _make_span()
        processor.on_end(span)
        assert len(exporter.spans) == 1
        assert exporter.spans[0].span_id == "s1"

    def test_multiple_spans(self):
        exporter = CollectingExporter()
        processor = SimpleSpanProcessor(exporter)
        processor.on_end(_make_span("s1"))
        processor.on_end(_make_span("s2"))
        assert len(exporter.spans) == 2


class TestBatchSpanProcessor:
    def test_flush_exports_all_queued(self):
        exporter = CollectingExporter()
        processor = BatchSpanProcessor(exporter, schedule_delay_ms=60000)
        processor.on_end(_make_span("s1"))
        processor.on_end(_make_span("s2"))
        processor.on_end(_make_span("s3"))
        assert processor.force_flush(timeout_ms=5000)
        assert len(exporter.spans) == 3

    def test_shutdown_flushes_remaining(self):
        exporter = CollectingExporter()
        processor = BatchSpanProcessor(exporter, schedule_delay_ms=60000)
        processor.on_end(_make_span("s1"))
        processor.shutdown()
        assert len(exporter.spans) == 1

    def test_auto_export_on_delay(self):
        exporter = CollectingExporter()
        processor = BatchSpanProcessor(exporter, schedule_delay_ms=100)
        processor.on_end(_make_span("s1"))
        time.sleep(0.3)
        assert len(exporter.spans) >= 1
        processor.shutdown()
