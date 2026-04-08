from __future__ import annotations

from typing import Any

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider


def _get_blocks_class() -> type:
    """Import and return Letta's blocks resource class."""
    try:
        from letta_client import Letta

        client = Letta.__new__(Letta)
        return type(client.agents.blocks)
    except (ImportError, Exception):
        raise ImportError("Letta not found. Install with: pip install memorylens[letta]")


class LettaInstrumentor:
    """Auto-instruments Letta memory blocks resource."""

    def __init__(self) -> None:
        self._original_retrieve: Any = None
        self._original_update: Any = None
        self._original_delete: Any = None
        self._original_list: Any = None
        self._blocks_class: type | None = None

    def instrument(self, **kwargs: Any) -> None:
        cls = _get_blocks_class()
        self._blocks_class = cls
        self._original_retrieve = cls.retrieve
        self._original_update = cls.update
        self._original_delete = cls.delete
        self._original_list = cls.list

        original_retrieve = self._original_retrieve
        original_update = self._original_update
        original_delete = self._original_delete
        original_list = self._original_list

        def patched_retrieve(self_blocks: Any, agent_id: str, block_label: str, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.letta")
            with tracer.start_span(
                operation=MemoryOperation.READ,
                attributes={
                    "backend": "letta",
                    "framework": "letta",
                    "agent_id": agent_id,
                    "block_label": block_label,
                },
            ) as span:
                span.set_content(input_content=block_label)
                result = original_retrieve(self_blocks, agent_id, block_label, **kw)
                span.set_content(output_content=repr(result))
                return result

        def patched_update(
            self_blocks: Any, agent_id: str, block_label: str, value: Any, **kw: Any
        ) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.letta")
            with tracer.start_span(
                operation=MemoryOperation.UPDATE,
                attributes={
                    "backend": "letta",
                    "framework": "letta",
                    "agent_id": agent_id,
                    "block_label": block_label,
                },
            ) as span:
                span.set_content(input_content=repr(value))
                result = original_update(self_blocks, agent_id, block_label, value, **kw)
                span.set_content(output_content=repr(result))
                return result

        def patched_delete(self_blocks: Any, agent_id: str, block_label: str, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.letta")
            with tracer.start_span(
                operation=MemoryOperation.WRITE,
                attributes={
                    "backend": "letta",
                    "framework": "letta",
                    "agent_id": agent_id,
                    "block_label": block_label,
                    "drop_reason": "explicit_delete",
                },
            ) as span:
                span.set_status(SpanStatus.DROPPED)
                result = original_delete(self_blocks, agent_id, block_label, **kw)
                return result

        def patched_list(self_blocks: Any, agent_id: str, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.letta")
            with tracer.start_span(
                operation=MemoryOperation.READ,
                attributes={
                    "backend": "letta",
                    "framework": "letta",
                    "agent_id": agent_id,
                },
            ) as span:
                result = original_list(self_blocks, agent_id, **kw)
                span.set_content(output_content=repr(result))
                return result

        cls.retrieve = patched_retrieve
        cls.update = patched_update
        cls.delete = patched_delete
        cls.list = patched_list

    def uninstrument(self) -> None:
        if self._blocks_class is not None:
            self._blocks_class.retrieve = self._original_retrieve
            self._blocks_class.update = self._original_update
            self._blocks_class.delete = self._original_delete
            self._blocks_class.list = self._original_list
            self._blocks_class = None
