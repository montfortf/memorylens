from __future__ import annotations

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider, Tracer
from memorylens._core.context import MemoryContext
from memorylens._core.processor import SimpleSpanProcessor

# Reuse CollectingExporter from test_processor
from tests.test_core.test_processor import CollectingExporter


class TestTracerProvider:
    def test_singleton(self):
        TracerProvider.reset()
        p1 = TracerProvider.get()
        p2 = TracerProvider.get()
        assert p1 is p2

    def test_reset_clears_singleton(self):
        p1 = TracerProvider.get()
        TracerProvider.reset()
        p2 = TracerProvider.get()
        assert p1 is not p2

    def test_get_tracer(self):
        TracerProvider.reset()
        provider = TracerProvider.get()
        tracer = provider.get_tracer("test")
        assert isinstance(tracer, Tracer)

    def test_add_processor(self):
        TracerProvider.reset()
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        processor = SimpleSpanProcessor(exporter)
        provider.add_processor(processor)
        assert processor in provider.processors


class TestTracer:
    def test_start_span_creates_memory_span(self):
        TracerProvider.reset()
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")

        with tracer.start_span(
            operation=MemoryOperation.WRITE,
            attributes={"backend": "test"},
        ) as span:
            span.set_attribute("memory_key", "k1")

        assert len(exporter.spans) == 1
        exported = exporter.spans[0]
        assert exported.operation == MemoryOperation.WRITE
        assert exported.status == SpanStatus.OK
        assert exported.attributes["backend"] == "test"
        assert exported.attributes["memory_key"] == "k1"
        assert exported.duration_ms >= 0

    def test_span_captures_error(self):
        TracerProvider.reset()
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")

        try:
            with tracer.start_span(operation=MemoryOperation.READ) as span:
                raise ValueError("test error")
        except ValueError:
            pass

        assert len(exporter.spans) == 1
        exported = exporter.spans[0]
        assert exported.status == SpanStatus.ERROR
        assert "test error" in exported.attributes.get("error.message", "")

    def test_span_inherits_context(self):
        TracerProvider.reset()
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")

        with MemoryContext(agent_id="bot", session_id="s1", user_id="u1"):
            with tracer.start_span(operation=MemoryOperation.WRITE):
                pass

        exported = exporter.spans[0]
        assert exported.agent_id == "bot"
        assert exported.session_id == "s1"
        assert exported.user_id == "u1"

    def test_span_without_context(self):
        TracerProvider.reset()
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")

        with tracer.start_span(operation=MemoryOperation.READ):
            pass

        exported = exporter.spans[0]
        assert exported.agent_id is None
        assert exported.session_id is None
