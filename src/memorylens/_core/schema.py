from __future__ import annotations

from enum import Enum


class MemoryOperation(str, Enum):
    """The type of memory operation being traced."""

    WRITE = "memory.write"
    READ = "memory.read"
    COMPRESS = "memory.compress"
    UPDATE = "memory.update"


class SpanStatus(str, Enum):
    """The outcome status of a memory operation."""

    OK = "ok"
    ERROR = "error"
    DROPPED = "dropped"
