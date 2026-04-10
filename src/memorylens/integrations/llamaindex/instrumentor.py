from __future__ import annotations

from typing import Any

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider


def _get_chat_memory_class() -> type:
    """Import and return LlamaIndex's ChatMemoryBuffer class."""
    try:
        from llama_index.core.memory import ChatMemoryBuffer

        return ChatMemoryBuffer
    except ImportError:
        raise ImportError("LlamaIndex not found. Install with: pip install memorylens[llamaindex]")


class LlamaIndexInstrumentor:
    """Auto-instruments LlamaIndex ChatMemoryBuffer."""

    def __init__(self) -> None:
        self._original_put: Any = None
        self._original_put_messages: Any = None
        self._original_get: Any = None
        self._original_get_all: Any = None
        self._original_reset: Any = None
        self._chat_memory_class: type | None = None

    def instrument(self, **kwargs: Any) -> None:
        cls = _get_chat_memory_class()
        self._chat_memory_class = cls
        self._original_put = cls.put
        self._original_put_messages = cls.put_messages
        self._original_get = cls.get
        self._original_get_all = cls.get_all
        self._original_reset = cls.reset

        original_put = self._original_put
        original_put_messages = self._original_put_messages
        original_get = self._original_get
        original_get_all = self._original_get_all
        original_reset = self._original_reset

        def patched_put(self_mem: Any, message: Any) -> None:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.llamaindex")
            with tracer.start_span(
                operation=MemoryOperation.WRITE,
                attributes={"backend": type(self_mem).__name__, "framework": "llamaindex"},
            ) as span:
                span.set_content(input_content=repr(message))
                return original_put(self_mem, message)

        def patched_put_messages(self_mem: Any, messages: Any) -> None:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.llamaindex")
            with tracer.start_span(
                operation=MemoryOperation.WRITE,
                attributes={"backend": type(self_mem).__name__, "framework": "llamaindex"},
            ) as span:
                span.set_content(input_content=repr(messages))
                return original_put_messages(self_mem, messages)

        def patched_get(self_mem: Any, input: Any = None) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.llamaindex")
            with tracer.start_span(
                operation=MemoryOperation.READ,
                attributes={"backend": type(self_mem).__name__, "framework": "llamaindex"},
            ) as span:
                span.set_content(input_content=repr(input))
                result = original_get(self_mem, input)
                span.set_content(output_content=repr(result))
                return result

        def patched_get_all(self_mem: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.llamaindex")
            with tracer.start_span(
                operation=MemoryOperation.READ,
                attributes={"backend": type(self_mem).__name__, "framework": "llamaindex"},
            ) as span:
                result = original_get_all(self_mem)
                span.set_content(output_content=repr(result))
                return result

        def patched_reset(self_mem: Any) -> None:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.llamaindex")
            with tracer.start_span(
                operation=MemoryOperation.WRITE,
                attributes={
                    "backend": type(self_mem).__name__,
                    "framework": "llamaindex",
                    "drop_reason": "reset",
                },
            ) as span:
                span.set_status(SpanStatus.DROPPED)
                return original_reset(self_mem)

        cls.put = patched_put
        cls.put_messages = patched_put_messages
        cls.get = patched_get
        cls.get_all = patched_get_all
        cls.reset = patched_reset

    def uninstrument(self) -> None:
        if self._chat_memory_class is not None:
            self._chat_memory_class.put = self._original_put
            self._chat_memory_class.put_messages = self._original_put_messages
            self._chat_memory_class.get = self._original_get
            self._chat_memory_class.get_all = self._original_get_all
            self._chat_memory_class.reset = self._original_reset
            self._chat_memory_class = None
