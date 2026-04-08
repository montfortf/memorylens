from __future__ import annotations

from typing import Any, Protocol


class Instrumentor(Protocol):
    def instrument(self, **kwargs: Any) -> None: ...
    def uninstrument(self) -> None: ...


_INSTRUMENTOR_FACTORIES: dict[str, type] = {}


def register_instrumentor(name: str, cls: type) -> None:
    _INSTRUMENTOR_FACTORIES[name] = cls


def create_instrumentor(name: str) -> Instrumentor:
    if name not in _INSTRUMENTOR_FACTORIES:
        available = ", ".join(sorted(_INSTRUMENTOR_FACTORIES.keys()))
        raise ValueError(
            f"Unknown instrumentor '{name}'. Available: {available}. "
            f"Install with: pip install memorylens[{name}]"
        )
    return _INSTRUMENTOR_FACTORIES[name]()
