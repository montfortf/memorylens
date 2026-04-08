from __future__ import annotations

from memorylens._core.context import MemoryContext
from memorylens._core.decorators import (
    instrument_compress,
    instrument_read,
    instrument_update,
    instrument_write,
)
from memorylens._core.processor import SimpleSpanProcessor
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider
from tests.test_core.test_processor import CollectingExporter


def _setup_exporter() -> CollectingExporter:
    provider = TracerProvider.get()
    exporter = CollectingExporter()
    provider.add_processor(SimpleSpanProcessor(exporter))
    return exporter


class TestInstrumentWrite:
    def test_captures_write_span(self):
        exporter = _setup_exporter()

        @instrument_write(backend="test_db")
        def store(content: str) -> bool:
            return True

        result = store("hello world")
        assert result is True
        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.OK
        assert span.attributes["backend"] == "test_db"

    def test_captures_content_when_enabled(self):
        exporter = _setup_exporter()

        @instrument_write(backend="db", capture_content=True)
        def store(content: str) -> str:
            return "stored"

        store("save this")
        span = exporter.spans[0]
        assert span.input_content is not None
        assert span.output_content is not None

    def test_no_content_when_disabled(self):
        exporter = _setup_exporter()

        @instrument_write(backend="db", capture_content=False)
        def store(content: str) -> str:
            return "stored"

        store("secret")
        span = exporter.spans[0]
        assert span.input_content is None
        assert span.output_content is None

    def test_captures_exception(self):
        exporter = _setup_exporter()

        @instrument_write(backend="db")
        def store(content: str) -> bool:
            raise RuntimeError("db down")

        try:
            store("data")
        except RuntimeError:
            pass

        span = exporter.spans[0]
        assert span.status == SpanStatus.ERROR
        assert span.attributes["error.type"] == "RuntimeError"
        assert "db down" in span.attributes["error.message"]

    def test_inherits_context(self):
        exporter = _setup_exporter()

        @instrument_write(backend="db")
        def store(content: str) -> bool:
            return True

        with MemoryContext(agent_id="bot", session_id="s1", user_id="u1"):
            store("data")

        span = exporter.spans[0]
        assert span.agent_id == "bot"
        assert span.session_id == "s1"


class TestInstrumentRead:
    def test_captures_read_span(self):
        exporter = _setup_exporter()

        @instrument_read(backend="pinecone")
        def search(query: str, top_k: int = 5) -> list[str]:
            return ["result1", "result2"]

        results = search("music prefs", top_k=3)
        assert results == ["result1", "result2"]
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.READ
        assert span.attributes["backend"] == "pinecone"


class TestInstrumentCompress:
    def test_captures_compress_span(self):
        exporter = _setup_exporter()

        @instrument_compress(model="gpt-4o-mini")
        def summarize(texts: list[str]) -> str:
            return "summary"

        result = summarize(["a", "b", "c"])
        assert result == "summary"
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.COMPRESS
        assert span.attributes["model"] == "gpt-4o-mini"


class TestInstrumentUpdate:
    def test_captures_update_span(self):
        exporter = _setup_exporter()

        @instrument_update(backend="redis")
        def update_mem(key: str, value: str) -> bool:
            return True

        result = update_mem("k1", "new_val")
        assert result is True
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.UPDATE
        assert span.attributes["backend"] == "redis"
