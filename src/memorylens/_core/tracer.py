from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from typing import Any, Generator

from memorylens._core.context import get_current_context
from memorylens._core.processor import SpanProcessor
from memorylens._core.sampler import Sampler
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan


class _MutableSpan:
    """Internal mutable span builder. Finalized into a frozen MemorySpan."""

    def __init__(
        self,
        trace_id: str,
        span_id: str,
        operation: MemoryOperation,
        parent_span_id: str | None,
        agent_id: str | None,
        session_id: str | None,
        user_id: str | None,
        attributes: dict[str, Any],
    ) -> None:
        self.trace_id = trace_id
        self.span_id = span_id
        self.operation = operation
        self.parent_span_id = parent_span_id
        self.status = SpanStatus.OK
        self.start_time = time.time_ns()
        self.end_time: float = 0
        self.agent_id = agent_id
        self.session_id = session_id
        self.user_id = user_id
        self.input_content: str | None = None
        self.output_content: str | None = None
        self.attributes = dict(attributes)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_status(self, status: SpanStatus) -> None:
        self.status = status

    def set_content(self, input_content: str | None = None, output_content: str | None = None) -> None:
        if input_content is not None:
            self.input_content = input_content
        if output_content is not None:
            self.output_content = output_content

    def finalize(self) -> MemorySpan:
        self.end_time = time.time_ns()
        duration_ms = (self.end_time - self.start_time) / 1_000_000
        return MemorySpan(
            span_id=self.span_id,
            trace_id=self.trace_id,
            parent_span_id=self.parent_span_id,
            operation=self.operation,
            status=self.status,
            start_time=self.start_time,
            end_time=self.end_time,
            duration_ms=duration_ms,
            agent_id=self.agent_id,
            session_id=self.session_id,
            user_id=self.user_id,
            input_content=self.input_content,
            output_content=self.output_content,
            attributes=self.attributes,
        )


class Tracer:
    """Creates spans for memory operations."""

    def __init__(self, name: str, provider: TracerProvider) -> None:
        self._name = name
        self._provider = provider

    @contextmanager
    def start_span(
        self,
        operation: MemoryOperation,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[_MutableSpan, None, None]:
        if not self._provider.sampler.should_sample():
            yield _MutableSpan(
                trace_id="",
                span_id="",
                operation=operation,
                parent_span_id=None,
                agent_id=None,
                session_id=None,
                user_id=None,
                attributes=attributes or {},
            )
            return

        ctx = get_current_context()
        span = _MutableSpan(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex,
            operation=operation,
            parent_span_id=parent_span_id,
            agent_id=ctx.agent_id if ctx else None,
            session_id=ctx.session_id if ctx else None,
            user_id=ctx.user_id if ctx else None,
            attributes=attributes or {},
        )

        for processor in self._provider.processors:
            processor.on_start(span.finalize())

        try:
            yield span
        except Exception as exc:
            span.set_status(SpanStatus.ERROR)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            raise
        finally:
            finished = span.finalize()
            for processor in self._provider.processors:
                processor.on_end(finished)


class TracerProvider:
    """Singleton that manages tracers, processors, and sampling."""

    _instance: TracerProvider | None = None

    def __init__(self) -> None:
        self.processors: list[SpanProcessor] = []
        self.sampler = Sampler(rate=1.0)
        self.service_name: str = "memorylens"

    def add_processor(self, processor: SpanProcessor) -> None:
        self.processors.append(processor)

    def get_tracer(self, name: str) -> Tracer:
        return Tracer(name=name, provider=self)

    def shutdown(self) -> None:
        for processor in self.processors:
            processor.shutdown()

    @classmethod
    def get(cls) -> TracerProvider:
        if cls._instance is None:
            cls._instance = TracerProvider()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        if cls._instance is not None:
            cls._instance.shutdown()
        cls._instance = None
