"""MemoryLens — Observability and debugging for AI agent memory systems."""

from __future__ import annotations

import os
from typing import Any

from memorylens._core.context import MemoryContext
from memorylens._core.decorators import (
    instrument_compress,
    instrument_read,
    instrument_update,
    instrument_write,
)
from memorylens._core.processor import BatchSpanProcessor, SimpleSpanProcessor  # noqa: F401
from memorylens._core.sampler import Sampler
from memorylens._core.tracer import Tracer, TracerProvider

__all__ = [
    "init",
    "shutdown",
    "instrument_write",
    "instrument_read",
    "instrument_compress",
    "instrument_update",
    "context",
    "get_tracer",
]

__version__ = "0.1.0"


def context(
    agent_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> MemoryContext:
    """Create a context manager that attaches metadata to all spans within."""
    return MemoryContext(agent_id=agent_id, session_id=session_id, user_id=user_id)


def get_tracer(name: str) -> Tracer:
    """Get a Tracer for manual span creation."""
    return TracerProvider.get().get_tracer(name)


def init(
    service_name: str | None = None,
    exporter: str | None = None,
    exporters: list[str] | None = None,
    otlp_endpoint: str | None = None,
    instrument: list[str] | None = None,
    capture_content: bool | None = None,
    sample_rate: float | None = None,
    db_path: str | None = None,
    detect_drift: bool = False,
) -> None:
    """Initialize MemoryLens. Call once at application startup."""
    from memorylens._exporters import create_exporter

    # Resolve env var overrides
    service_name = service_name or os.environ.get("OTEL_SERVICE_NAME", "memorylens")
    sample_rate_val = sample_rate
    if sample_rate_val is None:
        env_rate = os.environ.get("MEMORYLENS_SAMPLE_RATE")
        sample_rate_val = float(env_rate) if env_rate else 1.0

    if capture_content is not None:
        os.environ["MEMORYLENS_CAPTURE_CONTENT"] = str(capture_content).lower()

    # Build exporter list
    exporter_names: list[str] = []
    env_exporter = os.environ.get("MEMORYLENS_EXPORTER")
    if env_exporter:
        exporter_names = [env_exporter]
    elif exporters:
        exporter_names = exporters
    elif exporter:
        exporter_names = [exporter]
    else:
        exporter_names = ["sqlite"]

    # Configure provider
    provider = TracerProvider.get()
    provider.service_name = service_name
    provider.sampler = Sampler(rate=sample_rate_val)

    # Build exporters and processors
    for name in exporter_names:
        kwargs: dict[str, Any] = {}
        if name == "otlp":
            endpoint = otlp_endpoint or os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
            )
            kwargs["endpoint"] = endpoint
        elif name == "sqlite":
            if db_path:
                kwargs["db_path"] = db_path
        exp = create_exporter(name, **kwargs)
        processor = BatchSpanProcessor(exp)
        provider.add_processor(processor)

    # Enable online drift detection
    if detect_drift:
        from memorylens._audit.scorer import CachedScorer, MockScorer
        from memorylens._drift.tracker import VersionTracker
        from memorylens._exporters.sqlite import SQLiteExporter

        # Re-use or create a SQLiteExporter for the tracker
        _db = db_path or os.path.expanduser("~/.memorylens/traces.db")
        _exporter = SQLiteExporter(db_path=_db)
        _scorer = CachedScorer(MockScorer())  # lightweight default; swap for LocalScorer in prod
        _tracker = VersionTracker(exporter=_exporter, scorer=_scorer)
        provider.add_processor(_tracker)

    # Auto-instrument frameworks
    if instrument:
        from memorylens.integrations import create_instrumentor

        for framework_name in instrument:
            inst = create_instrumentor(framework_name)
            inst.instrument()


def shutdown() -> None:
    """Flush pending spans and shut down all processors."""
    TracerProvider.get().shutdown()
