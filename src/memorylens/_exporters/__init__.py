from __future__ import annotations

from typing import Any

from memorylens._exporters.base import ExportResult as ExportResult
from memorylens._exporters.base import SpanExporter

_EXPORTER_FACTORIES: dict[str, type] = {}


def register_exporter(name: str, cls: type) -> None:
    _EXPORTER_FACTORIES[name] = cls


def create_exporter(name: str, **kwargs: Any) -> SpanExporter:
    if name not in _EXPORTER_FACTORIES:
        available = ", ".join(sorted(_EXPORTER_FACTORIES.keys()))
        raise ValueError(f"Unknown exporter '{name}'. Available: {available}")
    return _EXPORTER_FACTORIES[name](**kwargs)


def get_available_exporters() -> list[str]:
    return sorted(_EXPORTER_FACTORIES.keys())


# Register built-in exporters
from memorylens._exporters.sqlite import SQLiteExporter  # noqa: E402

register_exporter("sqlite", SQLiteExporter)

from memorylens._exporters.jsonl import JSONLExporter  # noqa: E402

register_exporter("jsonl", JSONLExporter)

from memorylens._exporters.otlp import OTLPExporter  # noqa: E402

register_exporter("otlp", OTLPExporter)
