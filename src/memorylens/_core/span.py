from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from memorylens._core.schema import MemoryOperation, SpanStatus


@dataclass(frozen=True, slots=True)
class MemorySpan:
    """A single traced memory operation."""

    # Identity
    span_id: str
    trace_id: str
    parent_span_id: str | None

    # Classification
    operation: MemoryOperation
    status: SpanStatus

    # Timing
    start_time: float
    end_time: float
    duration_ms: float

    # Context
    agent_id: str | None
    session_id: str | None
    user_id: str | None

    # Memory content (redactable)
    input_content: str | None
    output_content: str | None

    # Operation-specific attributes
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict. Enum values become their string values."""
        d = asdict(self)
        d["operation"] = self.operation.value
        d["status"] = self.status.value
        return d
