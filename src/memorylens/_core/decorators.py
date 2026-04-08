from __future__ import annotations

import functools
import os
from typing import Any, Callable, TypeVar

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider

F = TypeVar("F", bound=Callable[..., Any])


def _get_capture_content(explicit: bool | None) -> bool:
    """Resolve capture_content: explicit arg > env var > default True."""
    if explicit is not None:
        return explicit
    env = os.environ.get("MEMORYLENS_CAPTURE_CONTENT", "").lower()
    if env in ("false", "0", "no"):
        return False
    return True


def _make_decorator(
    operation: MemoryOperation,
    **decorator_kwargs: Any,
) -> Callable[[F], F]:
    capture_content = _get_capture_content(decorator_kwargs.pop("capture_content", None))
    static_attrs = {k: v for k, v in decorator_kwargs.items() if v is not None}

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer(func.__module__)

            with tracer.start_span(
                operation=operation,
                attributes=dict(static_attrs),
            ) as span:
                if capture_content:
                    span.set_content(input_content=repr(args) if args else repr(kwargs))

                result = func(*args, **kwargs)

                if capture_content:
                    span.set_content(output_content=repr(result))

                return result

        return wrapper  # type: ignore[return-value]

    return decorator


def instrument_write(
    backend: str | None = None,
    capture_content: bool | None = None,
    **kwargs: Any,
) -> Callable[[F], F]:
    """Decorator to trace memory write operations."""
    return _make_decorator(
        MemoryOperation.WRITE,
        backend=backend,
        capture_content=capture_content,
        **kwargs,
    )


def instrument_read(
    backend: str | None = None,
    capture_content: bool | None = None,
    **kwargs: Any,
) -> Callable[[F], F]:
    """Decorator to trace memory read operations."""
    return _make_decorator(
        MemoryOperation.READ,
        backend=backend,
        capture_content=capture_content,
        **kwargs,
    )


def instrument_compress(
    model: str | None = None,
    capture_content: bool | None = None,
    **kwargs: Any,
) -> Callable[[F], F]:
    """Decorator to trace memory compression operations."""
    return _make_decorator(
        MemoryOperation.COMPRESS,
        model=model,
        capture_content=capture_content,
        **kwargs,
    )


def instrument_update(
    backend: str | None = None,
    capture_content: bool | None = None,
    **kwargs: Any,
) -> Callable[[F], F]:
    """Decorator to trace memory update operations."""
    return _make_decorator(
        MemoryOperation.UPDATE,
        backend=backend,
        capture_content=capture_content,
        **kwargs,
    )
