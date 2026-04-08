from __future__ import annotations

from unittest.mock import patch

from memorylens._core.processor import SimpleSpanProcessor
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider
from memorylens.integrations.zep.instrumentor import ZepInstrumentor
from tests.test_core.test_processor import CollectingExporter


class FakeMemoryClient:
    """Simulates Zep's memory client interface."""

    def add(self, session_id, messages):
        return {"status": "ok"}

    def get(self, session_id):
        return {"messages": [{"content": "hello"}], "summary": "conversation"}

    def search(self, session_id, query, limit=5):
        return [{"message": {"content": "result"}, "score": 0.92}]

    def delete(self, session_id):
        return None


class TestZepInstrumentor:
    def _setup(self):
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        return exporter

    @patch(
        "memorylens.integrations.zep.instrumentor._get_memory_client_class",
        return_value=FakeMemoryClient,
    )
    def test_instrument_add(self, mock_cls):
        exporter = self._setup()
        instrumentor = ZepInstrumentor()
        instrumentor.instrument()

        mem = FakeMemoryClient()
        result = mem.add("session_1", [{"content": "hello"}])
        assert result["status"] == "ok"

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.OK

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.zep.instrumentor._get_memory_client_class",
        return_value=FakeMemoryClient,
    )
    def test_instrument_get(self, mock_cls):
        exporter = self._setup()
        instrumentor = ZepInstrumentor()
        instrumentor.instrument()

        mem = FakeMemoryClient()
        result = mem.get("session_1")
        assert "messages" in result

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.READ

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.zep.instrumentor._get_memory_client_class",
        return_value=FakeMemoryClient,
    )
    def test_instrument_search(self, mock_cls):
        exporter = self._setup()
        instrumentor = ZepInstrumentor()
        instrumentor.instrument()

        mem = FakeMemoryClient()
        results = mem.search("session_1", "hello")
        assert len(results) == 1

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.READ
        assert span.attributes["results_count"] == 1
        assert span.attributes["scores"] == [0.92]

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.zep.instrumentor._get_memory_client_class",
        return_value=FakeMemoryClient,
    )
    def test_instrument_delete(self, mock_cls):
        exporter = self._setup()
        instrumentor = ZepInstrumentor()
        instrumentor.instrument()

        mem = FakeMemoryClient()
        mem.delete("session_1")

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.DROPPED
        assert span.attributes["drop_reason"] == "session_delete"

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.zep.instrumentor._get_memory_client_class",
        return_value=FakeMemoryClient,
    )
    def test_uninstrument_restores(self, mock_cls):
        exporter = self._setup()
        instrumentor = ZepInstrumentor()
        instrumentor.instrument()
        instrumentor.uninstrument()

        mem = FakeMemoryClient()
        mem.add("session_1", [{"content": "hello"}])

        assert len(exporter.spans) == 0
