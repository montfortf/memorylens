from __future__ import annotations

from typing import Any

from memorylens._core.schema import MemoryOperation
from memorylens._core.tracer import TracerProvider


def _get_base_memory_class() -> type:
    """Import and return LangChain's BaseMemory class."""
    try:
        from langchain_core.memory import BaseMemory
        return BaseMemory
    except ImportError:
        raise ImportError(
            "LangChain not found. Install with: pip install memorylens[langchain]"
        )


class LangChainInstrumentor:
    """Auto-instruments LangChain BaseMemory subclasses."""

    def __init__(self) -> None:
        self._original_save_context: Any = None
        self._original_load_memory_variables: Any = None
        self._base_class: type | None = None

    def instrument(self, **kwargs: Any) -> None:
        cls = _get_base_memory_class()
        self._base_class = cls
        self._original_save_context = cls.save_context
        self._original_load_memory_variables = cls.load_memory_variables

        original_save = self._original_save_context
        original_load = self._original_load_memory_variables

        def patched_save_context(self_mem: Any, inputs: dict, outputs: dict) -> None:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.langchain")
            with tracer.start_span(
                operation=MemoryOperation.WRITE,
                attributes={
                    "backend": type(self_mem).__name__,
                    "framework": "langchain",
                },
            ) as span:
                span.set_content(
                    input_content=repr(inputs),
                    output_content=repr(outputs),
                )
                return original_save(self_mem, inputs, outputs)

        def patched_load_memory_variables(self_mem: Any, inputs: dict) -> dict:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.langchain")
            with tracer.start_span(
                operation=MemoryOperation.READ,
                attributes={
                    "backend": type(self_mem).__name__,
                    "framework": "langchain",
                },
            ) as span:
                span.set_content(input_content=repr(inputs))
                result = original_load(self_mem, inputs)
                span.set_content(output_content=repr(result))
                return result

        cls.save_context = patched_save_context
        cls.load_memory_variables = patched_load_memory_variables

    def uninstrument(self) -> None:
        if self._base_class is not None:
            self._base_class.save_context = self._original_save_context
            self._base_class.load_memory_variables = self._original_load_memory_variables
            self._base_class = None
