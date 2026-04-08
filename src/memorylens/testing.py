from __future__ import annotations

from typing import Any

from memorylens._core.processor import SimpleSpanProcessor
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._core.tracer import TracerProvider


class _CollectingExporter:
    """Internal exporter that collects spans for testing."""

    def __init__(self):
        self.spans: list[MemorySpan] = []

    def export(self, spans: list[MemorySpan]):
        self.spans.extend(spans)
        return 0  # SUCCESS

    def shutdown(self) -> None:
        pass


class IntegrationTestHelper:
    """Reusable test helper for community integration developers.

    Usage::

        helper = IntegrationTestHelper()
        instrumentor = MyInstrumentor()
        instrumentor.instrument()

        # call patched methods...

        helper.assert_span_count(2)
        helper.assert_operation(0, MemoryOperation.WRITE)
        helper.assert_attribute(0, "framework", "my_framework")

        instrumentor.uninstrument()
        helper.reset()
    """

    def __init__(self) -> None:
        TracerProvider.reset()
        self._exporter = _CollectingExporter()
        provider = TracerProvider.get()
        provider.add_processor(SimpleSpanProcessor(self._exporter))

    @property
    def spans(self) -> list[MemorySpan]:
        return list(self._exporter.spans)

    def assert_span_count(self, expected: int) -> None:
        actual = len(self._exporter.spans)
        assert actual == expected, f"Expected {expected} spans, got {actual}"

    def assert_operation(self, index: int, operation: MemoryOperation) -> None:
        span = self._exporter.spans[index]
        assert span.operation == operation, (
            f"Span {index}: expected operation {operation.value}, got {span.operation.value}"
        )

    def assert_attribute(self, index: int, key: str, value: Any = None) -> None:
        span = self._exporter.spans[index]
        assert key in span.attributes, (
            f"Span {index}: missing attribute '{key}'. Present: {list(span.attributes.keys())}"
        )
        if value is not None:
            assert span.attributes[key] == value, (
                f"Span {index}: attribute '{key}' expected {value!r}, got {span.attributes[key]!r}"
            )

    def assert_status(self, index: int, status: SpanStatus) -> None:
        span = self._exporter.spans[index]
        assert span.status == status, (
            f"Span {index}: expected status {status.value}, got {span.status.value}"
        )

    def reset(self) -> None:
        self._exporter.spans.clear()
        TracerProvider.reset()
