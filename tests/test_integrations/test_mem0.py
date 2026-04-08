from __future__ import annotations

from unittest.mock import patch

from memorylens._core.processor import SimpleSpanProcessor
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider
from memorylens.integrations.mem0.instrumentor import Mem0Instrumentor
from tests.test_core.test_processor import CollectingExporter


class FakeMemory:
    """Simulates mem0.Memory interface."""

    def add(self, content: str, user_id: str | None = None, **kwargs) -> dict:
        return {"id": "mem_abc", "status": "ok"}

    def search(self, query: str, user_id: str | None = None, **kwargs) -> list[dict]:
        return [
            {"id": "mem_1", "text": "likes jazz", "score": 0.92},
            {"id": "mem_2", "text": "plays piano", "score": 0.78},
        ]

    def update(self, memory_id: str, content: str, **kwargs) -> dict:
        return {"id": memory_id, "status": "updated"}

    def delete(self, memory_id: str, **kwargs) -> dict:
        return {"id": memory_id, "status": "deleted"}


class TestMem0Instrumentor:
    def _setup(self):
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        return exporter

    @patch(
        "memorylens.integrations.mem0.instrumentor._get_memory_class",
        return_value=FakeMemory,
    )
    def test_instrument_add(self, mock_cls):
        exporter = self._setup()
        instrumentor = Mem0Instrumentor()
        instrumentor.instrument()

        mem = FakeMemory()
        result = mem.add("User likes jazz", user_id="u1")
        assert result["status"] == "ok"

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.OK
        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.mem0.instrumentor._get_memory_class",
        return_value=FakeMemory,
    )
    def test_instrument_search(self, mock_cls):
        exporter = self._setup()
        instrumentor = Mem0Instrumentor()
        instrumentor.instrument()

        mem = FakeMemory()
        results = mem.search("music preferences", user_id="u1")
        assert len(results) == 2

        span = exporter.spans[0]
        assert span.operation == MemoryOperation.READ
        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.mem0.instrumentor._get_memory_class",
        return_value=FakeMemory,
    )
    def test_instrument_update(self, mock_cls):
        exporter = self._setup()
        instrumentor = Mem0Instrumentor()
        instrumentor.instrument()

        mem = FakeMemory()
        mem.update("mem_1", "Now prefers classical")

        span = exporter.spans[0]
        assert span.operation == MemoryOperation.UPDATE
        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.mem0.instrumentor._get_memory_class",
        return_value=FakeMemory,
    )
    def test_instrument_delete(self, mock_cls):
        exporter = self._setup()
        instrumentor = Mem0Instrumentor()
        instrumentor.instrument()

        mem = FakeMemory()
        mem.delete("mem_1")

        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.DROPPED
        assert span.attributes["drop_reason"] == "explicit_delete"
        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.mem0.instrumentor._get_memory_class",
        return_value=FakeMemory,
    )
    def test_uninstrument_restores(self, mock_cls):
        exporter = self._setup()
        instrumentor = Mem0Instrumentor()
        instrumentor.instrument()
        instrumentor.uninstrument()

        mem = FakeMemory()
        mem.add("data", user_id="u1")
        assert len(exporter.spans) == 0
