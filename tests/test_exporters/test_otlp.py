from __future__ import annotations

from unittest.mock import MagicMock, patch

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.base import ExportResult
from memorylens._exporters.otlp import OTLPExporter, _ReadableSpanAdapter
from opentelemetry.sdk.resources import Resource


def _make_span(span_id: str = "s1") -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id="abc123",
        parent_span_id=None,
        operation=MemoryOperation.WRITE,
        status=SpanStatus.OK,
        start_time=1000000000000.0,
        end_time=1000012000000.0,
        duration_ms=12.0,
        agent_id="bot",
        session_id="sess-1",
        user_id="user-1",
        input_content="data",
        output_content="stored",
        attributes={"backend": "test", "memory_key": "k1"},
    )


class TestReadableSpanAdapter:
    def test_converts_span_to_otel_format(self):
        resource = Resource.create({"service.name": "test"})
        adapter = _ReadableSpanAdapter(_make_span(), resource)
        attrs = adapter.attributes
        assert attrs["memorylens.operation"] == "memory.write"
        assert attrs["memorylens.status"] == "ok"
        assert attrs["memorylens.agent_id"] == "bot"
        assert attrs["memorylens.session_id"] == "sess-1"
        assert attrs["memorylens.backend"] == "test"


class TestOTLPExporter:
    @patch("memorylens._exporters.otlp.OTLPSpanExporter")
    def test_export_calls_underlying_exporter(self, mock_otlp_cls):
        mock_instance = MagicMock()
        mock_otlp_cls.return_value = mock_instance
        mock_instance.export.return_value = MagicMock(name="SUCCESS")

        exporter = OTLPExporter(endpoint="http://localhost:4317")
        result = exporter.export([_make_span()])

        mock_instance.export.assert_called_once()
        args = mock_instance.export.call_args[0][0]
        assert len(args) == 1

    @patch("memorylens._exporters.otlp.OTLPSpanExporter")
    def test_shutdown_delegates(self, mock_otlp_cls):
        mock_instance = MagicMock()
        mock_otlp_cls.return_value = mock_instance

        exporter = OTLPExporter(endpoint="http://localhost:4317")
        exporter.shutdown()
        mock_instance.shutdown.assert_called_once()
