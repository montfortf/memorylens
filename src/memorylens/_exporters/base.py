from __future__ import annotations

from enum import Enum
from typing import Protocol

from memorylens._core.span import MemorySpan


class ExportResult(Enum):
    SUCCESS = 0
    FAILURE = 1


class SpanExporter(Protocol):
    """Interface for span exporters."""

    def export(self, spans: list[MemorySpan]) -> ExportResult: ...

    def shutdown(self) -> None: ...
