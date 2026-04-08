from __future__ import annotations

from unittest.mock import patch

from memorylens._core.processor import SimpleSpanProcessor
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider
from memorylens.integrations.llamaindex.instrumentor import LlamaIndexInstrumentor
from tests.test_core.test_processor import CollectingExporter


class FakeChatMemoryBuffer:
    """Simulates llama_index.core.memory.ChatMemoryBuffer interface."""

    def put(self, message):
        pass

    def put_messages(self, messages):
        pass

    def get(self, input=None):
        return [{"role": "user", "content": "hello"}]

    def get_all(self):
        return [{"role": "user", "content": "hello"}]

    def reset(self):
        pass


class TestLlamaIndexInstrumentor:
    def _setup(self):
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        return exporter

    @patch(
        "memorylens.integrations.llamaindex.instrumentor._get_chat_memory_class",
        return_value=FakeChatMemoryBuffer,
    )
    def test_instrument_put(self, mock_cls):
        exporter = self._setup()
        instrumentor = LlamaIndexInstrumentor()
        instrumentor.instrument()

        mem = FakeChatMemoryBuffer()
        mem.put({"role": "user", "content": "hello"})

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.OK

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.llamaindex.instrumentor._get_chat_memory_class",
        return_value=FakeChatMemoryBuffer,
    )
    def test_instrument_put_messages(self, mock_cls):
        exporter = self._setup()
        instrumentor = LlamaIndexInstrumentor()
        instrumentor.instrument()

        mem = FakeChatMemoryBuffer()
        mem.put_messages([{"role": "user", "content": "hello"}])

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.OK

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.llamaindex.instrumentor._get_chat_memory_class",
        return_value=FakeChatMemoryBuffer,
    )
    def test_instrument_get(self, mock_cls):
        exporter = self._setup()
        instrumentor = LlamaIndexInstrumentor()
        instrumentor.instrument()

        mem = FakeChatMemoryBuffer()
        result = mem.get(input="what did the user say?")
        assert result == [{"role": "user", "content": "hello"}]

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.READ

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.llamaindex.instrumentor._get_chat_memory_class",
        return_value=FakeChatMemoryBuffer,
    )
    def test_instrument_get_all(self, mock_cls):
        exporter = self._setup()
        instrumentor = LlamaIndexInstrumentor()
        instrumentor.instrument()

        mem = FakeChatMemoryBuffer()
        result = mem.get_all()
        assert result == [{"role": "user", "content": "hello"}]

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.READ

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.llamaindex.instrumentor._get_chat_memory_class",
        return_value=FakeChatMemoryBuffer,
    )
    def test_instrument_reset(self, mock_cls):
        exporter = self._setup()
        instrumentor = LlamaIndexInstrumentor()
        instrumentor.instrument()

        mem = FakeChatMemoryBuffer()
        mem.reset()

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.DROPPED
        assert span.attributes["drop_reason"] == "reset"

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.llamaindex.instrumentor._get_chat_memory_class",
        return_value=FakeChatMemoryBuffer,
    )
    def test_uninstrument_restores_original(self, mock_cls):
        exporter = self._setup()
        instrumentor = LlamaIndexInstrumentor()
        instrumentor.instrument()
        instrumentor.uninstrument()

        mem = FakeChatMemoryBuffer()
        mem.put({"role": "user", "content": "hello"})

        assert len(exporter.spans) == 0
