from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True, slots=True)
class MemoryContext:
    """Carries agent/session/user metadata through the call stack.

    Usage::

        with MemoryContext(agent_id="bot", session_id="s1", user_id="u1"):
            # all spans created here inherit these attributes
            ...
    """

    agent_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None

    _token: Token | None = None

    def __enter__(self) -> Self:
        object.__setattr__(self, "_token", _current_context.set(self))
        return self

    def __exit__(self, *exc) -> None:
        _current_context.reset(self._token)


_current_context: ContextVar[MemoryContext | None] = ContextVar(
    "memorylens_context", default=None
)


def get_current_context() -> MemoryContext | None:
    """Return the active MemoryContext, or None if outside a context block."""
    return _current_context.get()
