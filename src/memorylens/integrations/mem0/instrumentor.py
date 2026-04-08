from __future__ import annotations

from typing import Any

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider


def _get_memory_class() -> type:
    """Import and return Mem0's Memory class."""
    try:
        from mem0 import Memory

        return Memory
    except ImportError:
        raise ImportError("Mem0 not found. Install with: pip install memorylens[mem0]")


class Mem0Instrumentor:
    """Auto-instruments Mem0's Memory class."""

    def __init__(self) -> None:
        self._original_add: Any = None
        self._original_search: Any = None
        self._original_update: Any = None
        self._original_delete: Any = None
        self._memory_class: type | None = None

    def instrument(self, **kwargs: Any) -> None:
        cls = _get_memory_class()
        self._memory_class = cls
        self._original_add = cls.add
        self._original_search = cls.search
        self._original_update = cls.update
        self._original_delete = cls.delete

        original_add = self._original_add
        original_search = self._original_search
        original_update = self._original_update
        original_delete = self._original_delete

        def patched_add(self_mem: Any, content: str, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.mem0")
            with tracer.start_span(
                operation=MemoryOperation.WRITE,
                attributes={"backend": "mem0", "framework": "mem0"},
            ) as span:
                span.set_content(input_content=content)
                result = original_add(self_mem, content, **kw)
                span.set_content(output_content=repr(result))
                return result

        def patched_search(self_mem: Any, query: str, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.mem0")
            with tracer.start_span(
                operation=MemoryOperation.READ,
                attributes={"backend": "mem0", "framework": "mem0"},
            ) as span:
                span.set_content(input_content=query)
                result = original_search(self_mem, query, **kw)
                if isinstance(result, list):
                    scores = [r.get("score", 0.0) for r in result if isinstance(r, dict)]
                    span.set_attribute("results_count", len(result))
                    span.set_attribute("scores", scores)
                span.set_content(output_content=repr(result))
                return result

        def patched_update(self_mem: Any, memory_id: str, content: str, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.mem0")
            with tracer.start_span(
                operation=MemoryOperation.UPDATE,
                attributes={
                    "backend": "mem0",
                    "framework": "mem0",
                    "memory_id": memory_id,
                },
            ) as span:
                span.set_content(input_content=content)
                result = original_update(self_mem, memory_id, content, **kw)
                span.set_content(output_content=repr(result))
                return result

        def patched_delete(self_mem: Any, memory_id: str, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.mem0")
            with tracer.start_span(
                operation=MemoryOperation.WRITE,
                attributes={
                    "backend": "mem0",
                    "framework": "mem0",
                    "drop_reason": "explicit_delete",
                    "memory_id": memory_id,
                },
            ) as span:
                span.set_status(SpanStatus.DROPPED)
                result = original_delete(self_mem, memory_id, **kw)
                return result

        cls.add = patched_add
        cls.search = patched_search
        cls.update = patched_update
        cls.delete = patched_delete

    def uninstrument(self) -> None:
        if self._memory_class is not None:
            self._memory_class.add = self._original_add
            self._memory_class.search = self._original_search
            self._memory_class.update = self._original_update
            self._memory_class.delete = self._original_delete
            self._memory_class = None
