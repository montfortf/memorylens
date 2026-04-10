from __future__ import annotations

from typing import Any

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider


def _get_memory_client_class() -> type:
    """Import and return Zep's memory client class."""
    try:
        from zep_python import Zep

        client = Zep.__new__(Zep)
        return type(client.memory)
    except (ImportError, Exception):
        raise ImportError("Zep not found. Install with: pip install memorylens[zep]")


class ZepInstrumentor:
    """Auto-instruments Zep memory client."""

    def __init__(self) -> None:
        self._original_add: Any = None
        self._original_get: Any = None
        self._original_search: Any = None
        self._original_delete: Any = None
        self._memory_client_class: type | None = None

    def instrument(self, **kwargs: Any) -> None:
        cls = _get_memory_client_class()
        self._memory_client_class = cls
        self._original_add = cls.add
        self._original_get = cls.get
        self._original_search = cls.search
        self._original_delete = cls.delete

        original_add = self._original_add
        original_get = self._original_get
        original_search = self._original_search
        original_delete = self._original_delete

        def patched_add(self_mem: Any, session_id: str, messages: Any, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.zep")
            with tracer.start_span(
                operation=MemoryOperation.WRITE,
                attributes={
                    "backend": "zep",
                    "framework": "zep",
                    "session_id": session_id,
                },
            ) as span:
                span.set_content(input_content=repr(messages))
                result = original_add(self_mem, session_id, messages, **kw)
                span.set_content(output_content=repr(result))
                return result

        def patched_get(self_mem: Any, session_id: str, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.zep")
            with tracer.start_span(
                operation=MemoryOperation.READ,
                attributes={
                    "backend": "zep",
                    "framework": "zep",
                    "session_id": session_id,
                },
            ) as span:
                result = original_get(self_mem, session_id, **kw)
                span.set_content(output_content=repr(result))
                return result

        def patched_search(
            self_mem: Any, session_id: str, query: str, limit: int = 5, **kw: Any
        ) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.zep")
            with tracer.start_span(
                operation=MemoryOperation.READ,
                attributes={
                    "backend": "zep",
                    "framework": "zep",
                    "session_id": session_id,
                },
            ) as span:
                span.set_content(input_content=query)
                result = original_search(self_mem, session_id, query, limit, **kw)
                if isinstance(result, list):
                    scores = [r.get("score", 0.0) for r in result if isinstance(r, dict)]
                    span.set_attribute("results_count", len(result))
                    span.set_attribute("scores", scores)
                span.set_content(output_content=repr(result))
                return result

        def patched_delete(self_mem: Any, session_id: str, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.zep")
            with tracer.start_span(
                operation=MemoryOperation.WRITE,
                attributes={
                    "backend": "zep",
                    "framework": "zep",
                    "session_id": session_id,
                    "drop_reason": "session_delete",
                },
            ) as span:
                span.set_status(SpanStatus.DROPPED)
                result = original_delete(self_mem, session_id, **kw)
                return result

        cls.add = patched_add
        cls.get = patched_get
        cls.search = patched_search
        cls.delete = patched_delete

    def uninstrument(self) -> None:
        if self._memory_client_class is not None:
            self._memory_client_class.add = self._original_add
            self._memory_client_class.get = self._original_get
            self._memory_client_class.search = self._original_search
            self._memory_client_class.delete = self._original_delete
            self._memory_client_class = None
