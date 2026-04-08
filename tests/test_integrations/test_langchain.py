from __future__ import annotations

from unittest.mock import patch

from memorylens._core.processor import SimpleSpanProcessor
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider
from memorylens.integrations.langchain.instrumentor import LangChainInstrumentor
from tests.test_core.test_processor import CollectingExporter


class FakeBaseMemory:
    """Simulates langchain_core.memory.BaseMemory interface."""

    def save_context(self, inputs: dict, outputs: dict) -> None:
        pass

    def load_memory_variables(self, inputs: dict) -> dict:
        return {"history": "User likes jazz"}


class TestLangChainInstrumentor:
    def _setup(self):
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        return exporter

    @patch(
        "memorylens.integrations.langchain.instrumentor._get_base_memory_class",
        return_value=FakeBaseMemory,
    )
    def test_instrument_save_context(self, mock_cls):
        exporter = self._setup()
        instrumentor = LangChainInstrumentor()
        instrumentor.instrument()

        mem = FakeBaseMemory()
        mem.save_context({"input": "hi"}, {"output": "hello"})

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.OK

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.langchain.instrumentor._get_base_memory_class",
        return_value=FakeBaseMemory,
    )
    def test_instrument_load_memory_variables(self, mock_cls):
        exporter = self._setup()
        instrumentor = LangChainInstrumentor()
        instrumentor.instrument()

        mem = FakeBaseMemory()
        result = mem.load_memory_variables({"input": "what does user like?"})
        assert result == {"history": "User likes jazz"}

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.READ

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.langchain.instrumentor._get_base_memory_class",
        return_value=FakeBaseMemory,
    )
    def test_uninstrument_restores_original(self, mock_cls):
        exporter = self._setup()
        instrumentor = LangChainInstrumentor()
        instrumentor.instrument()
        instrumentor.uninstrument()

        mem = FakeBaseMemory()
        mem.save_context({"input": "hi"}, {"output": "hello"})

        assert len(exporter.spans) == 0
