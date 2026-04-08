# MemoryLens Phase 1 — Core Instrumentation SDK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MemoryLens Python SDK — an observability layer for AI agent memory systems that instruments write, read, compress, and update operations, exports traces via OpenTelemetry, stores locally in SQLite, and provides a CLI for inspection.

**Architecture:** Layered single package (`memorylens`) with internal boundaries: `_core/` (tracer, spans, decorators, context), `_exporters/` (OTLP, SQLite, JSONL), `integrations/` (LangChain, Mem0 auto-instrumentation), and `cli/` (Typer subcommands). Sync API surface with async background trace export via `BatchSpanProcessor`.

**Tech Stack:** Python 3.10+, uv, OpenTelemetry SDK, Typer, Rich, SQLite, pytest, ruff, mypy

**Spec:** `docs/superpowers/specs/2026-04-07-memorylens-phase1-sdk-design.md`

---

## File Map

### New Files (Create)

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, deps, extras, scripts |
| `LICENSE` | Apache 2.0 |
| `README.md` | Usage quickstart |
| `src/memorylens/__init__.py` | Public API: 8 symbols re-exported |
| `src/memorylens/_core/__init__.py` | Core layer exports |
| `src/memorylens/_core/schema.py` | `MemoryOperation`, `SpanStatus` enums |
| `src/memorylens/_core/span.py` | `MemorySpan` dataclass |
| `src/memorylens/_core/context.py` | `ContextVar`-based context propagation |
| `src/memorylens/_core/processor.py` | `SpanProcessor` protocol, `BatchSpanProcessor` |
| `src/memorylens/_core/sampler.py` | `Sampler` (rate-based) |
| `src/memorylens/_core/tracer.py` | `TracerProvider`, `Tracer` |
| `src/memorylens/_core/decorators.py` | 4 `instrument_*` decorators |
| `src/memorylens/_exporters/__init__.py` | Exporter registry + factory |
| `src/memorylens/_exporters/base.py` | `SpanExporter` protocol, `ExportResult` |
| `src/memorylens/_exporters/otlp.py` | OTLP gRPC/HTTP exporter |
| `src/memorylens/_exporters/sqlite.py` | SQLite local store |
| `src/memorylens/_exporters/jsonl.py` | JSONL file/stdout exporter |
| `src/memorylens/integrations/__init__.py` | `Instrumentor` protocol + registry |
| `src/memorylens/integrations/langchain/__init__.py` | LangChain integration exports |
| `src/memorylens/integrations/langchain/instrumentor.py` | LangChain auto-instrumentation |
| `src/memorylens/integrations/mem0/__init__.py` | Mem0 integration exports |
| `src/memorylens/integrations/mem0/instrumentor.py` | Mem0 auto-instrumentation |
| `src/memorylens/cli/__init__.py` | CLI package |
| `src/memorylens/cli/main.py` | Typer app entry point |
| `src/memorylens/cli/commands/__init__.py` | Commands package |
| `src/memorylens/cli/commands/traces.py` | list, show, tail, export |
| `src/memorylens/cli/commands/stats.py` | Summary statistics |
| `src/memorylens/cli/commands/config.py` | Config management |
| `src/memorylens/cli/formatters.py` | Rich table + JSON output helpers |
| `tests/conftest.py` | Shared fixtures |
| `tests/test_core/test_schema.py` | Schema enum tests |
| `tests/test_core/test_span.py` | MemorySpan tests |
| `tests/test_core/test_context.py` | Context propagation tests |
| `tests/test_core/test_processor.py` | Processor tests |
| `tests/test_core/test_tracer.py` | TracerProvider tests |
| `tests/test_core/test_decorators.py` | Decorator tests |
| `tests/test_exporters/test_sqlite.py` | SQLite exporter tests |
| `tests/test_exporters/test_jsonl.py` | JSONL exporter tests |
| `tests/test_exporters/test_otlp.py` | OTLP exporter tests |
| `tests/test_integrations/test_langchain.py` | LangChain integration tests |
| `tests/test_integrations/test_mem0.py` | Mem0 integration tests |
| `tests/test_cli/test_commands.py` | CLI command tests |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `src/memorylens/__init__.py`, `.gitignore`
- Create: All `__init__.py` files for subpackages

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "memorylens"
version = "0.1.0"
description = "Observability and debugging for AI agent memory systems"
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.10"
authors = [
    { name = "MemoryLens Contributors" },
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Topic :: System :: Monitoring",
]
dependencies = [
    "opentelemetry-api>=1.20",
    "opentelemetry-sdk>=1.20",
    "opentelemetry-exporter-otlp-proto-grpc>=1.20",
    "opentelemetry-exporter-otlp-proto-http>=1.20",
    "typer>=0.9",
    "rich>=13.0",
]

[project.optional-dependencies]
langchain = ["langchain-core>=0.1"]
mem0 = ["mem0ai>=0.1"]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "mypy>=1.10",
]

[project.scripts]
memorylens = "memorylens.cli.main:app"

[tool.hatch.build.targets.wheel]
packages = ["src/memorylens"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
target-version = "py310"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.mypy]
python_version = "3.10"
strict = true
warn_return_any = true
warn_unused_configs = true
```

- [ ] **Step 2: Create LICENSE (Apache 2.0)**

Create `LICENSE` with the standard Apache 2.0 text. Set copyright to `2026 MemoryLens Contributors`.

- [ ] **Step 3: Create all package __init__.py files**

Create these empty files to establish the package structure:

```
src/memorylens/__init__.py          (leave empty for now — populated in Task 7)
src/memorylens/_core/__init__.py
src/memorylens/_exporters/__init__.py
src/memorylens/integrations/__init__.py
src/memorylens/integrations/langchain/__init__.py
src/memorylens/integrations/mem0/__init__.py
src/memorylens/cli/__init__.py
src/memorylens/cli/commands/__init__.py
```

Also create empty test directories:

```
tests/__init__.py
tests/test_core/__init__.py
tests/test_exporters/__init__.py
tests/test_integrations/__init__.py
tests/test_cli/__init__.py
```

- [ ] **Step 4: Create conftest.py with basic fixture**

File: `tests/conftest.py`

```python
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_tracer_provider():
    """Reset the global TracerProvider between tests."""
    yield
    # Will be updated in Task 6 once TracerProvider exists
```

- [ ] **Step 5: Initialize uv and verify**

```bash
cd /Users/montfortfernando/Dropbox/Montfort/Dev2026/MemoryLens
uv venv
uv pip install -e ".[dev]"
uv run pytest --co -q
```

Expected: pytest collects 0 tests, no errors. Verifies the package is installable and pytest can find the test directory.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml LICENSE .gitignore src/ tests/
git commit -m "feat: scaffold memorylens package with pyproject.toml and directory structure"
```

---

## Task 2: Schema Enums

**Files:**
- Create: `src/memorylens/_core/schema.py`
- Test: `tests/test_core/test_schema.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_core/test_schema.py`

```python
from __future__ import annotations

from memorylens._core.schema import MemoryOperation, SpanStatus


class TestMemoryOperation:
    def test_write_value(self):
        assert MemoryOperation.WRITE == "memory.write"
        assert MemoryOperation.WRITE.value == "memory.write"

    def test_read_value(self):
        assert MemoryOperation.READ == "memory.read"

    def test_compress_value(self):
        assert MemoryOperation.COMPRESS == "memory.compress"

    def test_update_value(self):
        assert MemoryOperation.UPDATE == "memory.update"

    def test_is_string(self):
        assert isinstance(MemoryOperation.WRITE, str)

    def test_all_members(self):
        members = {m.value for m in MemoryOperation}
        assert members == {"memory.write", "memory.read", "memory.compress", "memory.update"}


class TestSpanStatus:
    def test_ok_value(self):
        assert SpanStatus.OK == "ok"

    def test_error_value(self):
        assert SpanStatus.ERROR == "error"

    def test_dropped_value(self):
        assert SpanStatus.DROPPED == "dropped"

    def test_is_string(self):
        assert isinstance(SpanStatus.OK, str)

    def test_all_members(self):
        members = {m.value for m in SpanStatus}
        assert members == {"ok", "error", "dropped"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_core/test_schema.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'memorylens._core.schema'`

- [ ] **Step 3: Write the implementation**

File: `src/memorylens/_core/schema.py`

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_core/test_schema.py -v
```

Expected: All 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memorylens/_core/schema.py tests/test_core/test_schema.py
git commit -m "feat: add MemoryOperation and SpanStatus enums"
```

---

## Task 3: MemorySpan Dataclass

**Files:**
- Create: `src/memorylens/_core/span.py`
- Test: `tests/test_core/test_span.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_core/test_span.py`

```python
from __future__ import annotations

import time
from typing import Any

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan


class TestMemorySpan:
    def test_create_write_span(self):
        span = MemorySpan(
            span_id="span-1",
            trace_id="trace-1",
            parent_span_id=None,
            operation=MemoryOperation.WRITE,
            status=SpanStatus.OK,
            start_time=1000.0,
            end_time=1012.0,
            duration_ms=12.0,
            agent_id="test-agent",
            session_id="sess-1",
            user_id="user-1",
            input_content="Store this fact",
            output_content="Stored successfully",
            attributes={"backend": "mem0", "memory_key": "pref_diet"},
        )
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.OK
        assert span.duration_ms == 12.0
        assert span.attributes["backend"] == "mem0"

    def test_create_read_span_with_scores(self):
        span = MemorySpan(
            span_id="span-2",
            trace_id="trace-1",
            parent_span_id="span-1",
            operation=MemoryOperation.READ,
            status=SpanStatus.OK,
            start_time=1000.0,
            end_time=1045.0,
            duration_ms=45.0,
            agent_id=None,
            session_id=None,
            user_id=None,
            input_content="music preferences",
            output_content=None,
            attributes={
                "query": "music preferences",
                "results_count": 3,
                "scores": [0.92, 0.87, 0.65],
                "threshold": 0.7,
                "backend": "pinecone",
                "top_k": 5,
            },
        )
        assert span.parent_span_id == "span-1"
        assert span.attributes["scores"] == [0.92, 0.87, 0.65]

    def test_optional_fields_default_none(self):
        span = MemorySpan(
            span_id="span-3",
            trace_id="trace-2",
            parent_span_id=None,
            operation=MemoryOperation.COMPRESS,
            status=SpanStatus.OK,
            start_time=1000.0,
            end_time=1100.0,
            duration_ms=100.0,
            agent_id=None,
            session_id=None,
            user_id=None,
            input_content=None,
            output_content=None,
            attributes={},
        )
        assert span.agent_id is None
        assert span.input_content is None
        assert span.attributes == {}

    def test_to_dict(self):
        span = MemorySpan(
            span_id="span-4",
            trace_id="trace-3",
            parent_span_id=None,
            operation=MemoryOperation.UPDATE,
            status=SpanStatus.OK,
            start_time=1000.0,
            end_time=1008.0,
            duration_ms=8.0,
            agent_id="bot",
            session_id=None,
            user_id=None,
            input_content="new value",
            output_content="updated",
            attributes={"memory_key": "k1", "update_type": "replace"},
        )
        d = span.to_dict()
        assert isinstance(d, dict)
        assert d["span_id"] == "span-4"
        assert d["operation"] == "memory.update"
        assert d["status"] == "ok"
        assert d["attributes"]["update_type"] == "replace"

    def test_dropped_span(self):
        span = MemorySpan(
            span_id="span-5",
            trace_id="trace-4",
            parent_span_id=None,
            operation=MemoryOperation.WRITE,
            status=SpanStatus.DROPPED,
            start_time=1000.0,
            end_time=1005.0,
            duration_ms=5.0,
            agent_id=None,
            session_id=None,
            user_id=None,
            input_content="something",
            output_content=None,
            attributes={"drop_reason": "duplicate", "drop_policy": "dedup_filter"},
        )
        assert span.status == SpanStatus.DROPPED
        assert span.attributes["drop_reason"] == "duplicate"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_core/test_span.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'memorylens._core.span'`

- [ ] **Step 3: Write the implementation**

File: `src/memorylens/_core/span.py`

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_core/test_span.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memorylens/_core/span.py tests/test_core/test_span.py
git commit -m "feat: add MemorySpan dataclass with serialization"
```

---

## Task 4: Context Propagation

**Files:**
- Create: `src/memorylens/_core/context.py`
- Test: `tests/test_core/test_context.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_core/test_context.py`

```python
from __future__ import annotations

from memorylens._core.context import MemoryContext, get_current_context


class TestMemoryContext:
    def test_context_sets_and_clears(self):
        assert get_current_context() is None
        with MemoryContext(agent_id="bot", session_id="s1", user_id="u1"):
            ctx = get_current_context()
            assert ctx is not None
            assert ctx.agent_id == "bot"
            assert ctx.session_id == "s1"
            assert ctx.user_id == "u1"
        assert get_current_context() is None

    def test_nested_context_overrides(self):
        with MemoryContext(agent_id="outer", session_id="s1", user_id="u1"):
            assert get_current_context().agent_id == "outer"
            with MemoryContext(agent_id="inner", session_id="s2", user_id="u2"):
                assert get_current_context().agent_id == "inner"
                assert get_current_context().session_id == "s2"
            assert get_current_context().agent_id == "outer"

    def test_partial_context(self):
        with MemoryContext(agent_id="bot"):
            ctx = get_current_context()
            assert ctx.agent_id == "bot"
            assert ctx.session_id is None
            assert ctx.user_id is None

    def test_context_outside_block_is_none(self):
        assert get_current_context() is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_core/test_context.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

File: `src/memorylens/_core/context.py`

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_core/test_context.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memorylens/_core/context.py tests/test_core/test_context.py
git commit -m "feat: add ContextVar-based context propagation"
```

---

## Task 5: SpanProcessor and BatchSpanProcessor

**Files:**
- Create: `src/memorylens/_core/processor.py`, `src/memorylens/_core/sampler.py`
- Test: `tests/test_core/test_processor.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_core/test_processor.py`

```python
from __future__ import annotations

import time

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._core.processor import SimpleSpanProcessor, BatchSpanProcessor
from memorylens._exporters.base import SpanExporter, ExportResult


def _make_span(span_id: str = "s1", operation: MemoryOperation = MemoryOperation.WRITE) -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id="t1",
        parent_span_id=None,
        operation=operation,
        status=SpanStatus.OK,
        start_time=1000.0,
        end_time=1010.0,
        duration_ms=10.0,
        agent_id=None,
        session_id=None,
        user_id=None,
        input_content=None,
        output_content=None,
        attributes={},
    )


class CollectingExporter:
    """Test exporter that collects spans in a list."""

    def __init__(self):
        self.spans: list[MemorySpan] = []

    def export(self, spans: list[MemorySpan]) -> ExportResult:
        self.spans.extend(spans)
        return ExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


class TestSimpleSpanProcessor:
    def test_on_end_exports_immediately(self):
        exporter = CollectingExporter()
        processor = SimpleSpanProcessor(exporter)
        span = _make_span()
        processor.on_end(span)
        assert len(exporter.spans) == 1
        assert exporter.spans[0].span_id == "s1"

    def test_multiple_spans(self):
        exporter = CollectingExporter()
        processor = SimpleSpanProcessor(exporter)
        processor.on_end(_make_span("s1"))
        processor.on_end(_make_span("s2"))
        assert len(exporter.spans) == 2


class TestBatchSpanProcessor:
    def test_flush_exports_all_queued(self):
        exporter = CollectingExporter()
        processor = BatchSpanProcessor(exporter, schedule_delay_ms=60000)
        processor.on_end(_make_span("s1"))
        processor.on_end(_make_span("s2"))
        processor.on_end(_make_span("s3"))
        assert processor.force_flush(timeout_ms=5000)
        assert len(exporter.spans) == 3

    def test_shutdown_flushes_remaining(self):
        exporter = CollectingExporter()
        processor = BatchSpanProcessor(exporter, schedule_delay_ms=60000)
        processor.on_end(_make_span("s1"))
        processor.shutdown()
        assert len(exporter.spans) == 1

    def test_auto_export_on_delay(self):
        exporter = CollectingExporter()
        processor = BatchSpanProcessor(exporter, schedule_delay_ms=100)
        processor.on_end(_make_span("s1"))
        time.sleep(0.3)
        assert len(exporter.spans) >= 1
        processor.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_core/test_processor.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the exporter base first**

File: `src/memorylens/_exporters/base.py`

```python
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
```

- [ ] **Step 4: Write the processor implementation**

File: `src/memorylens/_core/processor.py`

```python
from __future__ import annotations

import threading
from collections import deque
from typing import Protocol

from memorylens._core.span import MemorySpan
from memorylens._exporters.base import SpanExporter


class SpanProcessor(Protocol):
    """Interface for span processors."""

    def on_start(self, span: MemorySpan) -> None: ...
    def on_end(self, span: MemorySpan) -> None: ...
    def shutdown(self) -> None: ...
    def force_flush(self, timeout_ms: int = 30000) -> bool: ...


class SimpleSpanProcessor:
    """Exports each span synchronously on on_end(). For debugging/testing."""

    def __init__(self, exporter: SpanExporter) -> None:
        self._exporter = exporter

    def on_start(self, span: MemorySpan) -> None:
        pass

    def on_end(self, span: MemorySpan) -> None:
        self._exporter.export([span])

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_ms: int = 30000) -> bool:
        return True


class BatchSpanProcessor:
    """Batches spans and exports in a background thread. Non-blocking."""

    def __init__(
        self,
        exporter: SpanExporter,
        max_batch_size: int = 512,
        schedule_delay_ms: int = 5000,
        max_queue_size: int = 2048,
    ) -> None:
        self._exporter = exporter
        self._max_batch_size = max_batch_size
        self._schedule_delay_s = schedule_delay_ms / 1000.0
        self._max_queue_size = max_queue_size
        self._queue: deque[MemorySpan] = deque(maxlen=max_queue_size)
        self._lock = threading.Lock()
        self._flush_event = threading.Event()
        self._shutdown_event = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def on_start(self, span: MemorySpan) -> None:
        pass

    def on_end(self, span: MemorySpan) -> None:
        with self._lock:
            self._queue.append(span)
            if len(self._queue) >= self._max_batch_size:
                self._flush_event.set()

    def shutdown(self) -> None:
        self._shutdown_event.set()
        self._flush_event.set()
        self._worker.join(timeout=10)
        self._flush_batch()
        self._exporter.shutdown()

    def force_flush(self, timeout_ms: int = 30000) -> bool:
        self._flush_event.set()
        self._worker.join(timeout=timeout_ms / 1000.0)
        if self._worker.is_alive():
            # Worker is still running — just flush inline
            self._flush_batch()
        return True

    def _run(self) -> None:
        while not self._shutdown_event.is_set():
            self._flush_event.wait(timeout=self._schedule_delay_s)
            self._flush_event.clear()
            self._flush_batch()

    def _flush_batch(self) -> None:
        with self._lock:
            batch = list(self._queue)
            self._queue.clear()
        if batch:
            # Export in chunks of max_batch_size
            for i in range(0, len(batch), self._max_batch_size):
                chunk = batch[i : i + self._max_batch_size]
                self._exporter.export(chunk)
```

- [ ] **Step 5: Write the sampler**

File: `src/memorylens/_core/sampler.py`

```python
from __future__ import annotations

import random


class Sampler:
    """Rate-based sampler. Returns True if the span should be recorded."""

    def __init__(self, rate: float = 1.0) -> None:
        if not 0.0 <= rate <= 1.0:
            raise ValueError(f"Sample rate must be between 0.0 and 1.0, got {rate}")
        self._rate = rate

    @property
    def rate(self) -> float:
        return self._rate

    def should_sample(self) -> bool:
        if self._rate == 1.0:
            return True
        if self._rate == 0.0:
            return False
        return random.random() < self._rate
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/test_core/test_processor.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/memorylens/_core/processor.py src/memorylens/_core/sampler.py src/memorylens/_exporters/base.py tests/test_core/test_processor.py
git commit -m "feat: add SpanProcessor, BatchSpanProcessor, Sampler, and SpanExporter protocol"
```

---

## Task 6: TracerProvider and Tracer

**Files:**
- Create: `src/memorylens/_core/tracer.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_core/test_tracer.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_core/test_tracer.py`

```python
from __future__ import annotations

import uuid

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._core.tracer import TracerProvider, Tracer
from memorylens._core.context import MemoryContext
from tests.test_core.test_processor import CollectingExporter, _make_span
from memorylens._core.processor import SimpleSpanProcessor


class TestTracerProvider:
    def test_singleton(self):
        TracerProvider.reset()
        p1 = TracerProvider.get()
        p2 = TracerProvider.get()
        assert p1 is p2

    def test_reset_clears_singleton(self):
        p1 = TracerProvider.get()
        TracerProvider.reset()
        p2 = TracerProvider.get()
        assert p1 is not p2

    def test_get_tracer(self):
        TracerProvider.reset()
        provider = TracerProvider.get()
        tracer = provider.get_tracer("test")
        assert isinstance(tracer, Tracer)

    def test_add_processor(self):
        TracerProvider.reset()
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        processor = SimpleSpanProcessor(exporter)
        provider.add_processor(processor)
        assert processor in provider.processors


class TestTracer:
    def test_start_span_creates_memory_span(self):
        TracerProvider.reset()
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")

        with tracer.start_span(
            operation=MemoryOperation.WRITE,
            attributes={"backend": "test"},
        ) as span:
            span.set_attribute("memory_key", "k1")

        assert len(exporter.spans) == 1
        exported = exporter.spans[0]
        assert exported.operation == MemoryOperation.WRITE
        assert exported.status == SpanStatus.OK
        assert exported.attributes["backend"] == "test"
        assert exported.attributes["memory_key"] == "k1"
        assert exported.duration_ms >= 0

    def test_span_captures_error(self):
        TracerProvider.reset()
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")

        try:
            with tracer.start_span(operation=MemoryOperation.READ) as span:
                raise ValueError("test error")
        except ValueError:
            pass

        assert len(exporter.spans) == 1
        exported = exporter.spans[0]
        assert exported.status == SpanStatus.ERROR
        assert "test error" in exported.attributes.get("error.message", "")

    def test_span_inherits_context(self):
        TracerProvider.reset()
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")

        with MemoryContext(agent_id="bot", session_id="s1", user_id="u1"):
            with tracer.start_span(operation=MemoryOperation.WRITE):
                pass

        exported = exporter.spans[0]
        assert exported.agent_id == "bot"
        assert exported.session_id == "s1"
        assert exported.user_id == "u1"

    def test_span_without_context(self):
        TracerProvider.reset()
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")

        with tracer.start_span(operation=MemoryOperation.READ):
            pass

        exported = exporter.spans[0]
        assert exported.agent_id is None
        assert exported.session_id is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_core/test_tracer.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

File: `src/memorylens/_core/tracer.py`

```python
from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from typing import Any, Generator

from memorylens._core.context import get_current_context
from memorylens._core.processor import SpanProcessor
from memorylens._core.sampler import Sampler
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan


class _MutableSpan:
    """Internal mutable span builder. Finalized into a frozen MemorySpan."""

    def __init__(
        self,
        trace_id: str,
        span_id: str,
        operation: MemoryOperation,
        parent_span_id: str | None,
        agent_id: str | None,
        session_id: str | None,
        user_id: str | None,
        attributes: dict[str, Any],
    ) -> None:
        self.trace_id = trace_id
        self.span_id = span_id
        self.operation = operation
        self.parent_span_id = parent_span_id
        self.status = SpanStatus.OK
        self.start_time = time.time_ns()
        self.end_time: float = 0
        self.agent_id = agent_id
        self.session_id = session_id
        self.user_id = user_id
        self.input_content: str | None = None
        self.output_content: str | None = None
        self.attributes = dict(attributes)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_status(self, status: SpanStatus) -> None:
        self.status = status

    def set_content(self, input_content: str | None = None, output_content: str | None = None) -> None:
        if input_content is not None:
            self.input_content = input_content
        if output_content is not None:
            self.output_content = output_content

    def finalize(self) -> MemorySpan:
        self.end_time = time.time_ns()
        duration_ms = (self.end_time - self.start_time) / 1_000_000
        return MemorySpan(
            span_id=self.span_id,
            trace_id=self.trace_id,
            parent_span_id=self.parent_span_id,
            operation=self.operation,
            status=self.status,
            start_time=self.start_time,
            end_time=self.end_time,
            duration_ms=duration_ms,
            agent_id=self.agent_id,
            session_id=self.session_id,
            user_id=self.user_id,
            input_content=self.input_content,
            output_content=self.output_content,
            attributes=self.attributes,
        )


class Tracer:
    """Creates spans for memory operations."""

    def __init__(self, name: str, provider: TracerProvider) -> None:
        self._name = name
        self._provider = provider

    @contextmanager
    def start_span(
        self,
        operation: MemoryOperation,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[_MutableSpan, None, None]:
        if not self._provider.sampler.should_sample():
            yield _MutableSpan(
                trace_id="",
                span_id="",
                operation=operation,
                parent_span_id=None,
                agent_id=None,
                session_id=None,
                user_id=None,
                attributes=attributes or {},
            )
            return

        ctx = get_current_context()
        span = _MutableSpan(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex,
            operation=operation,
            parent_span_id=parent_span_id,
            agent_id=ctx.agent_id if ctx else None,
            session_id=ctx.session_id if ctx else None,
            user_id=ctx.user_id if ctx else None,
            attributes=attributes or {},
        )

        for processor in self._provider.processors:
            processor.on_start(span.finalize())

        try:
            yield span
        except Exception as exc:
            span.set_status(SpanStatus.ERROR)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            raise
        finally:
            finished = span.finalize()
            for processor in self._provider.processors:
                processor.on_end(finished)


class TracerProvider:
    """Singleton that manages tracers, processors, and sampling."""

    _instance: TracerProvider | None = None

    def __init__(self) -> None:
        self.processors: list[SpanProcessor] = []
        self.sampler = Sampler(rate=1.0)
        self.service_name: str = "memorylens"

    def add_processor(self, processor: SpanProcessor) -> None:
        self.processors.append(processor)

    def get_tracer(self, name: str) -> Tracer:
        return Tracer(name=name, provider=self)

    def shutdown(self) -> None:
        for processor in self.processors:
            processor.shutdown()

    @classmethod
    def get(cls) -> TracerProvider:
        if cls._instance is None:
            cls._instance = TracerProvider()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        if cls._instance is not None:
            cls._instance.shutdown()
        cls._instance = None
```

- [ ] **Step 4: Update conftest.py to reset provider between tests**

File: `tests/conftest.py`

```python
from __future__ import annotations

import pytest

from memorylens._core.tracer import TracerProvider


@pytest.fixture(autouse=True)
def _reset_tracer_provider():
    """Reset the global TracerProvider between tests."""
    TracerProvider.reset()
    yield
    TracerProvider.reset()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_core/test_tracer.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 6: Run all tests to check nothing broke**

```bash
uv run pytest tests/ -v
```

Expected: All tests across all files PASS.

- [ ] **Step 7: Commit**

```bash
git add src/memorylens/_core/tracer.py tests/test_core/test_tracer.py tests/conftest.py
git commit -m "feat: add TracerProvider, Tracer, and MutableSpan with context inheritance"
```

---

## Task 7: Decorators

**Files:**
- Create: `src/memorylens/_core/decorators.py`
- Test: `tests/test_core/test_decorators.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_core/test_decorators.py`

```python
from __future__ import annotations

from memorylens._core.decorators import (
    instrument_compress,
    instrument_read,
    instrument_update,
    instrument_write,
)
from memorylens._core.context import MemoryContext
from memorylens._core.processor import SimpleSpanProcessor
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider
from tests.test_core.test_processor import CollectingExporter


def _setup_exporter() -> CollectingExporter:
    provider = TracerProvider.get()
    exporter = CollectingExporter()
    provider.add_processor(SimpleSpanProcessor(exporter))
    return exporter


class TestInstrumentWrite:
    def test_captures_write_span(self):
        exporter = _setup_exporter()

        @instrument_write(backend="test_db")
        def store(content: str) -> bool:
            return True

        result = store("hello world")
        assert result is True
        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.OK
        assert span.attributes["backend"] == "test_db"

    def test_captures_content_when_enabled(self):
        exporter = _setup_exporter()

        @instrument_write(backend="db", capture_content=True)
        def store(content: str) -> str:
            return "stored"

        store("save this")
        span = exporter.spans[0]
        assert span.input_content is not None
        assert span.output_content is not None

    def test_no_content_when_disabled(self):
        exporter = _setup_exporter()

        @instrument_write(backend="db", capture_content=False)
        def store(content: str) -> str:
            return "stored"

        store("secret")
        span = exporter.spans[0]
        assert span.input_content is None
        assert span.output_content is None

    def test_captures_exception(self):
        exporter = _setup_exporter()

        @instrument_write(backend="db")
        def store(content: str) -> bool:
            raise RuntimeError("db down")

        try:
            store("data")
        except RuntimeError:
            pass

        span = exporter.spans[0]
        assert span.status == SpanStatus.ERROR
        assert span.attributes["error.type"] == "RuntimeError"
        assert "db down" in span.attributes["error.message"]

    def test_inherits_context(self):
        exporter = _setup_exporter()

        @instrument_write(backend="db")
        def store(content: str) -> bool:
            return True

        with MemoryContext(agent_id="bot", session_id="s1", user_id="u1"):
            store("data")

        span = exporter.spans[0]
        assert span.agent_id == "bot"
        assert span.session_id == "s1"


class TestInstrumentRead:
    def test_captures_read_span(self):
        exporter = _setup_exporter()

        @instrument_read(backend="pinecone")
        def search(query: str, top_k: int = 5) -> list[str]:
            return ["result1", "result2"]

        results = search("music prefs", top_k=3)
        assert results == ["result1", "result2"]
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.READ
        assert span.attributes["backend"] == "pinecone"


class TestInstrumentCompress:
    def test_captures_compress_span(self):
        exporter = _setup_exporter()

        @instrument_compress(model="gpt-4o-mini")
        def summarize(texts: list[str]) -> str:
            return "summary"

        result = summarize(["a", "b", "c"])
        assert result == "summary"
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.COMPRESS
        assert span.attributes["model"] == "gpt-4o-mini"


class TestInstrumentUpdate:
    def test_captures_update_span(self):
        exporter = _setup_exporter()

        @instrument_update(backend="redis")
        def update_mem(key: str, value: str) -> bool:
            return True

        result = update_mem("k1", "new_val")
        assert result is True
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.UPDATE
        assert span.attributes["backend"] == "redis"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_core/test_decorators.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

File: `src/memorylens/_core/decorators.py`

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_core/test_decorators.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memorylens/_core/decorators.py tests/test_core/test_decorators.py
git commit -m "feat: add instrument_write, instrument_read, instrument_compress, instrument_update decorators"
```

---

## Task 8: Public API and init()

**Files:**
- Create: `src/memorylens/__init__.py` (populate with public API)
- Modify: `src/memorylens/_exporters/__init__.py` (exporter registry)

- [ ] **Step 1: Write the exporter registry**

File: `src/memorylens/_exporters/__init__.py`

```python
from __future__ import annotations

from typing import Any

from memorylens._exporters.base import ExportResult, SpanExporter

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
```

- [ ] **Step 2: Write the integrations registry**

File: `src/memorylens/integrations/__init__.py`

```python
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
```

- [ ] **Step 3: Write the public API**

File: `src/memorylens/__init__.py`

```python
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
from memorylens._core.processor import BatchSpanProcessor, SimpleSpanProcessor
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
) -> None:
    """Initialize MemoryLens. Call once at application startup.

    Args:
        service_name: Identifies this service in traces.
        exporter: Single exporter name ("sqlite", "otlp", "jsonl").
        exporters: Multiple exporter names.
        otlp_endpoint: OTLP collector URL.
        instrument: List of framework names to auto-instrument.
        capture_content: Whether to record input/output content.
        sample_rate: Sampling rate 0.0-1.0.
        db_path: SQLite database path.
    """
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

    # Auto-instrument frameworks
    if instrument:
        from memorylens.integrations import create_instrumentor

        for framework_name in instrument:
            inst = create_instrumentor(framework_name)
            inst.instrument()


def shutdown() -> None:
    """Flush pending spans and shut down all processors."""
    TracerProvider.get().shutdown()
```

- [ ] **Step 4: Run all tests to verify nothing broke**

```bash
uv run pytest tests/ -v
```

Expected: All existing tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memorylens/__init__.py src/memorylens/_exporters/__init__.py src/memorylens/integrations/__init__.py
git commit -m "feat: add public API (init, shutdown, context, get_tracer) and exporter/instrumentor registries"
```

---

## Task 9: SQLite Exporter

**Files:**
- Create: `src/memorylens/_exporters/sqlite.py`
- Test: `tests/test_exporters/test_sqlite.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_exporters/test_sqlite.py`

```python
from __future__ import annotations

import sqlite3
import json

import pytest

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.base import ExportResult
from memorylens._exporters.sqlite import SQLiteExporter


def _make_span(
    span_id: str = "s1",
    operation: MemoryOperation = MemoryOperation.WRITE,
    status: SpanStatus = SpanStatus.OK,
    attributes: dict | None = None,
) -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id="t1",
        parent_span_id=None,
        operation=operation,
        status=status,
        start_time=1000000000000.0,
        end_time=1000012000000.0,
        duration_ms=12.0,
        agent_id="bot",
        session_id="sess-1",
        user_id="user-1",
        input_content="input data",
        output_content="output data",
        attributes=attributes or {"backend": "test"},
    )


class TestSQLiteExporter:
    def test_export_and_query(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        span = _make_span()
        result = exporter.export([span])
        assert result == ExportResult.SUCCESS

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM spans").fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["span_id"] == "s1"
        assert row["trace_id"] == "t1"
        assert row["operation"] == "memory.write"
        assert row["status"] == "ok"
        assert row["agent_id"] == "bot"
        assert row["input_content"] == "input data"
        attrs = json.loads(row["attributes"])
        assert attrs["backend"] == "test"
        conn.close()
        exporter.shutdown()

    def test_export_multiple_spans(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        spans = [_make_span(f"s{i}") for i in range(5)]
        result = exporter.export(spans)
        assert result == ExportResult.SUCCESS

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
        assert count == 5
        conn.close()
        exporter.shutdown()

    def test_auto_creates_db(self, tmp_path):
        db_path = str(tmp_path / "subdir" / "traces.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.export([_make_span()])

        conn = sqlite3.connect(db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "spans" in table_names
        conn.close()
        exporter.shutdown()

    def test_query_by_operation(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.export([
            _make_span("s1", operation=MemoryOperation.WRITE),
            _make_span("s2", operation=MemoryOperation.READ),
            _make_span("s3", operation=MemoryOperation.WRITE),
        ])

        rows = exporter.query(operation="memory.write")
        assert len(rows) == 2
        exporter.shutdown()

    def test_query_by_status(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.export([
            _make_span("s1", status=SpanStatus.OK),
            _make_span("s2", status=SpanStatus.ERROR),
            _make_span("s3", status=SpanStatus.DROPPED),
        ])

        rows = exporter.query(status="error")
        assert len(rows) == 1
        assert rows[0]["span_id"] == "s2"
        exporter.shutdown()

    def test_query_by_trace_id(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.export([_make_span("s1")])

        rows = exporter.query(trace_id="t1")
        assert len(rows) == 1
        exporter.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_exporters/test_sqlite.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

File: `src/memorylens/_exporters/sqlite.py`

```python
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from memorylens._core.span import MemorySpan
from memorylens._exporters.base import ExportResult

_DEFAULT_DB_PATH = os.path.expanduser("~/.memorylens/traces.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS spans (
    span_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    parent_span_id TEXT,
    operation TEXT NOT NULL,
    status TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    duration_ms REAL NOT NULL,
    agent_id TEXT,
    session_id TEXT,
    user_id TEXT,
    input_content TEXT,
    output_content TEXT,
    attributes TEXT NOT NULL DEFAULT '{}'
)
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans (trace_id)",
    "CREATE INDEX IF NOT EXISTS idx_spans_session_id ON spans (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_spans_operation ON spans (operation)",
    "CREATE INDEX IF NOT EXISTS idx_spans_start_time ON spans (start_time)",
]

_INSERT_SPAN = """
INSERT OR REPLACE INTO spans (
    span_id, trace_id, parent_span_id, operation, status,
    start_time, end_time, duration_ms,
    agent_id, session_id, user_id,
    input_content, output_content, attributes
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class SQLiteExporter:
    """Exports spans to a local SQLite database."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE)
        for idx_sql in _CREATE_INDEXES:
            self._conn.execute(idx_sql)
        self._conn.commit()

    def export(self, spans: list[MemorySpan]) -> ExportResult:
        try:
            rows = [
                (
                    s.span_id,
                    s.trace_id,
                    s.parent_span_id,
                    s.operation.value if hasattr(s.operation, "value") else s.operation,
                    s.status.value if hasattr(s.status, "value") else s.status,
                    s.start_time,
                    s.end_time,
                    s.duration_ms,
                    s.agent_id,
                    s.session_id,
                    s.user_id,
                    s.input_content,
                    s.output_content,
                    json.dumps(s.attributes),
                )
                for s in spans
            ]
            self._conn.executemany(_INSERT_SPAN, rows)
            self._conn.commit()
            return ExportResult.SUCCESS
        except Exception:
            return ExportResult.FAILURE

    def query(
        self,
        trace_id: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query spans from the database. Returns list of dicts."""
        conditions: list[str] = []
        params: list[Any] = []

        if trace_id:
            conditions.append("trace_id = ?")
            params.append(trace_id)
        if operation:
            conditions.append("operation = ?")
            params.append(operation)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM spans WHERE {where} ORDER BY start_time DESC LIMIT ?"
        params.append(limit)

        cursor = self._conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def shutdown(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Register the SQLite exporter**

Add to the bottom of `src/memorylens/_exporters/__init__.py`:

```python
# Register built-in exporters
from memorylens._exporters.sqlite import SQLiteExporter

register_exporter("sqlite", SQLiteExporter)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_exporters/test_sqlite.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memorylens/_exporters/sqlite.py src/memorylens/_exporters/__init__.py tests/test_exporters/test_sqlite.py
git commit -m "feat: add SQLite exporter with query support"
```

---

## Task 10: JSONL Exporter

**Files:**
- Create: `src/memorylens/_exporters/jsonl.py`
- Test: `tests/test_exporters/test_jsonl.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_exporters/test_jsonl.py`

```python
from __future__ import annotations

import json

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.base import ExportResult
from memorylens._exporters.jsonl import JSONLExporter


def _make_span(span_id: str = "s1") -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id="t1",
        parent_span_id=None,
        operation=MemoryOperation.WRITE,
        status=SpanStatus.OK,
        start_time=1000.0,
        end_time=1012.0,
        duration_ms=12.0,
        agent_id="bot",
        session_id="sess-1",
        user_id="user-1",
        input_content="data",
        output_content="stored",
        attributes={"backend": "test"},
    )


class TestJSONLExporter:
    def test_export_to_file(self, tmp_path):
        path = str(tmp_path / "traces.jsonl")
        exporter = JSONLExporter(file_path=path)
        result = exporter.export([_make_span("s1"), _make_span("s2")])
        assert result == ExportResult.SUCCESS

        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        obj = json.loads(lines[0])
        assert obj["span_id"] == "s1"
        assert obj["operation"] == "memory.write"
        exporter.shutdown()

    def test_export_to_stdout(self, capsys):
        exporter = JSONLExporter()  # defaults to stdout
        exporter.export([_make_span()])
        captured = capsys.readouterr()
        obj = json.loads(captured.out.strip())
        assert obj["span_id"] == "s1"
        exporter.shutdown()

    def test_append_mode(self, tmp_path):
        path = str(tmp_path / "traces.jsonl")
        exporter = JSONLExporter(file_path=path)
        exporter.export([_make_span("s1")])
        exporter.export([_make_span("s2")])

        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        exporter.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_exporters/test_jsonl.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

File: `src/memorylens/_exporters/jsonl.py`

```python
from __future__ import annotations

import json
import sys
from typing import IO

from memorylens._core.span import MemorySpan
from memorylens._exporters.base import ExportResult


class JSONLExporter:
    """Exports spans as JSON Lines to a file or stdout."""

    def __init__(self, file_path: str | None = None) -> None:
        self._file_path = file_path
        self._file_handle: IO[str] | None = None

    def _get_output(self) -> IO[str]:
        if self._file_path is None:
            return sys.stdout
        if self._file_handle is None:
            self._file_handle = open(self._file_path, "a")
        return self._file_handle

    def export(self, spans: list[MemorySpan]) -> ExportResult:
        try:
            output = self._get_output()
            for span in spans:
                line = json.dumps(span.to_dict(), default=str)
                output.write(line + "\n")
            if self._file_handle is not None:
                self._file_handle.flush()
            return ExportResult.SUCCESS
        except Exception:
            return ExportResult.FAILURE

    def shutdown(self) -> None:
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None
```

- [ ] **Step 4: Register the JSONL exporter**

Add to `src/memorylens/_exporters/__init__.py` (after the sqlite import):

```python
from memorylens._exporters.jsonl import JSONLExporter

register_exporter("jsonl", JSONLExporter)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_exporters/test_jsonl.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memorylens/_exporters/jsonl.py src/memorylens/_exporters/__init__.py tests/test_exporters/test_jsonl.py
git commit -m "feat: add JSONL exporter with file and stdout support"
```

---

## Task 11: OTLP Exporter

**Files:**
- Create: `src/memorylens/_exporters/otlp.py`
- Test: `tests/test_exporters/test_otlp.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_exporters/test_otlp.py`

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.base import ExportResult
from memorylens._exporters.otlp import OTLPExporter


def _make_span(span_id: str = "s1") -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id="abc123",
        parent_span_id=None,
        operation=MemoryOperation.WRITE,
        status=SpanStatus.OK,
        start_time=1000000000000.0,
        end_time=1000012000000.0,
        duration_ms=12.0,
        agent_id="bot",
        session_id="sess-1",
        user_id="user-1",
        input_content="data",
        output_content="stored",
        attributes={"backend": "test", "memory_key": "k1"},
    )


class TestOTLPExporter:
    def test_converts_span_to_otel_format(self):
        """Verify the exporter translates MemorySpan fields to OTel attributes."""
        exporter = OTLPExporter.__new__(OTLPExporter)
        otel_span = exporter._to_otel_span(_make_span())
        attrs = dict(otel_span.attributes)
        assert attrs["memorylens.operation"] == "memory.write"
        assert attrs["memorylens.status"] == "ok"
        assert attrs["memorylens.agent_id"] == "bot"
        assert attrs["memorylens.session_id"] == "sess-1"
        assert attrs["memorylens.backend"] == "test"

    @patch("memorylens._exporters.otlp.OTLPSpanExporter")
    def test_export_calls_underlying_exporter(self, mock_otlp_cls):
        mock_instance = MagicMock()
        mock_otlp_cls.return_value = mock_instance
        mock_instance.export.return_value = MagicMock(name="SUCCESS")

        exporter = OTLPExporter(endpoint="http://localhost:4317")
        result = exporter.export([_make_span()])

        mock_instance.export.assert_called_once()
        args = mock_instance.export.call_args[0][0]
        assert len(args) == 1

    @patch("memorylens._exporters.otlp.OTLPSpanExporter")
    def test_shutdown_delegates(self, mock_otlp_cls):
        mock_instance = MagicMock()
        mock_otlp_cls.return_value = mock_instance

        exporter = OTLPExporter(endpoint="http://localhost:4317")
        exporter.shutdown()
        mock_instance.shutdown.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_exporters/test_otlp.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

File: `src/memorylens/_exporters/otlp.py`

```python
from __future__ import annotations

import os
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.trace import StatusCode
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)

from memorylens._core.span import MemorySpan
from memorylens._exporters.base import ExportResult


class _ReadableSpanAdapter:
    """Adapts a MemorySpan to look like an OTel ReadableSpan for the OTLP exporter."""

    def __init__(self, span: MemorySpan, resource: Resource) -> None:
        self._span = span
        self._resource = resource

    @property
    def name(self) -> str:
        return self._span.operation.value

    @property
    def context(self):
        from opentelemetry.trace import SpanContext, TraceFlags

        # Convert hex string to int for trace_id and span_id
        trace_id = int(self._span.trace_id[:32].ljust(32, "0"), 16)
        span_id = int(self._span.span_id[:16].ljust(16, "0"), 16)
        return SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )

    @property
    def parent(self):
        return None

    @property
    def start_time(self) -> int:
        return int(self._span.start_time)

    @property
    def end_time(self) -> int:
        return int(self._span.end_time)

    @property
    def attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "memorylens.operation": self._span.operation.value,
            "memorylens.status": self._span.status.value,
        }
        if self._span.agent_id:
            attrs["memorylens.agent_id"] = self._span.agent_id
        if self._span.session_id:
            attrs["memorylens.session_id"] = self._span.session_id
        if self._span.user_id:
            attrs["memorylens.user_id"] = self._span.user_id
        if self._span.input_content:
            attrs["memorylens.input_content"] = self._span.input_content
        if self._span.output_content:
            attrs["memorylens.output_content"] = self._span.output_content
        # Flatten operation-specific attributes with prefix
        for k, v in self._span.attributes.items():
            if isinstance(v, (str, int, float, bool)):
                attrs[f"memorylens.{k}"] = v
            else:
                import json
                attrs[f"memorylens.{k}"] = json.dumps(v, default=str)
        return attrs

    @property
    def events(self) -> list:
        return []

    @property
    def links(self) -> list:
        return []

    @property
    def status(self):
        from opentelemetry.trace import Status

        if self._span.status.value == "error":
            return Status(StatusCode.ERROR, self._span.attributes.get("error.message", ""))
        return Status(StatusCode.OK)

    @property
    def kind(self):
        from opentelemetry.trace import SpanKind

        return SpanKind.INTERNAL

    @property
    def resource(self) -> Resource:
        return self._resource

    @property
    def instrumentation_info(self):
        from opentelemetry.sdk.util.instrumentation import InstrumentationInfo

        return InstrumentationInfo("memorylens", "0.1.0")

    @property
    def instrumentation_scope(self):
        from opentelemetry.sdk.util.instrumentation import InstrumentationScope

        return InstrumentationScope("memorylens", "0.1.0")


class OTLPExporter:
    """Exports MemorySpans via OpenTelemetry OTLP protocol."""

    def __init__(
        self,
        endpoint: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        endpoint = endpoint or os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
        )
        self._resource = Resource.create({"service.name": "memorylens"})
        self._exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)

    def _to_otel_span(self, span: MemorySpan) -> _ReadableSpanAdapter:
        return _ReadableSpanAdapter(span, self._resource)

    def export(self, spans: list[MemorySpan]) -> ExportResult:
        try:
            otel_spans = [self._to_otel_span(s) for s in spans]
            self._exporter.export(otel_spans)  # type: ignore[arg-type]
            return ExportResult.SUCCESS
        except Exception:
            return ExportResult.FAILURE

    def shutdown(self) -> None:
        self._exporter.shutdown()
```

- [ ] **Step 4: Register the OTLP exporter**

Add to `src/memorylens/_exporters/__init__.py` (after jsonl import):

```python
from memorylens._exporters.otlp import OTLPExporter

register_exporter("otlp", OTLPExporter)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_exporters/test_otlp.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memorylens/_exporters/otlp.py src/memorylens/_exporters/__init__.py tests/test_exporters/test_otlp.py
git commit -m "feat: add OTLP exporter with MemorySpan-to-OTel span translation"
```

---

## Task 12: LangChain Integration

**Files:**
- Create: `src/memorylens/integrations/langchain/instrumentor.py`
- Modify: `src/memorylens/integrations/langchain/__init__.py`
- Test: `tests/test_integrations/test_langchain.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_integrations/test_langchain.py`

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from memorylens._core.processor import SimpleSpanProcessor
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider
from memorylens.integrations.langchain.instrumentor import LangChainInstrumentor
from tests.test_core.test_processor import CollectingExporter


class FakeBaseMemory:
    """Simulates langchain_core.memory.BaseMemory interface."""

    def save_context(self, inputs: dict, outputs: dict) -> None:
        pass

    def load_memory_variables(self, inputs: dict) -> dict:
        return {"history": "User likes jazz"}


class TestLangChainInstrumentor:
    def _setup(self):
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        return exporter

    @patch(
        "memorylens.integrations.langchain.instrumentor._get_base_memory_class",
        return_value=FakeBaseMemory,
    )
    def test_instrument_save_context(self, mock_cls):
        exporter = self._setup()
        instrumentor = LangChainInstrumentor()
        instrumentor.instrument()

        mem = FakeBaseMemory()
        mem.save_context({"input": "hi"}, {"output": "hello"})

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.OK

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.langchain.instrumentor._get_base_memory_class",
        return_value=FakeBaseMemory,
    )
    def test_instrument_load_memory_variables(self, mock_cls):
        exporter = self._setup()
        instrumentor = LangChainInstrumentor()
        instrumentor.instrument()

        mem = FakeBaseMemory()
        result = mem.load_memory_variables({"input": "what does user like?"})
        assert result == {"history": "User likes jazz"}

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.READ

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.langchain.instrumentor._get_base_memory_class",
        return_value=FakeBaseMemory,
    )
    def test_uninstrument_restores_original(self, mock_cls):
        exporter = self._setup()
        instrumentor = LangChainInstrumentor()
        instrumentor.instrument()
        instrumentor.uninstrument()

        mem = FakeBaseMemory()
        mem.save_context({"input": "hi"}, {"output": "hello"})

        # No spans after uninstrument
        assert len(exporter.spans) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_integrations/test_langchain.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

File: `src/memorylens/integrations/langchain/instrumentor.py`

```python
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
```

- [ ] **Step 4: Update the langchain __init__.py**

File: `src/memorylens/integrations/langchain/__init__.py`

```python
from memorylens.integrations.langchain.instrumentor import LangChainInstrumentor

__all__ = ["LangChainInstrumentor"]
```

- [ ] **Step 5: Register the instrumentor**

Add to `src/memorylens/integrations/__init__.py` (at the bottom):

```python
# Register built-in instrumentors (lazy — import only registers the name)
register_instrumentor("langchain", LangChainInstrumentor)
```

But we need a lazy import to avoid importing LangChain at module level. Change the registration to:

```python
# Lazy registration — actual class imported only when used
def _register_builtins() -> None:
    try:
        from memorylens.integrations.langchain import LangChainInstrumentor
        register_instrumentor("langchain", LangChainInstrumentor)
    except Exception:
        pass
    try:
        from memorylens.integrations.mem0 import Mem0Instrumentor
        register_instrumentor("mem0", Mem0Instrumentor)
    except Exception:
        pass

_register_builtins()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/test_integrations/test_langchain.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/memorylens/integrations/ tests/test_integrations/test_langchain.py
git commit -m "feat: add LangChain auto-instrumentation for BaseMemory"
```

---

## Task 13: Mem0 Integration

**Files:**
- Create: `src/memorylens/integrations/mem0/instrumentor.py`
- Modify: `src/memorylens/integrations/mem0/__init__.py`
- Test: `tests/test_integrations/test_mem0.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_integrations/test_mem0.py`

```python
from __future__ import annotations

from unittest.mock import patch

from memorylens._core.processor import SimpleSpanProcessor
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider
from memorylens.integrations.mem0.instrumentor import Mem0Instrumentor
from tests.test_core.test_processor import CollectingExporter


class FakeMemory:
    """Simulates mem0.Memory interface."""

    def add(self, content: str, user_id: str | None = None, **kwargs) -> dict:
        return {"id": "mem_abc", "status": "ok"}

    def search(self, query: str, user_id: str | None = None, **kwargs) -> list[dict]:
        return [
            {"id": "mem_1", "text": "likes jazz", "score": 0.92},
            {"id": "mem_2", "text": "plays piano", "score": 0.78},
        ]

    def update(self, memory_id: str, content: str, **kwargs) -> dict:
        return {"id": memory_id, "status": "updated"}

    def delete(self, memory_id: str, **kwargs) -> dict:
        return {"id": memory_id, "status": "deleted"}


class TestMem0Instrumentor:
    def _setup(self):
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        return exporter

    @patch(
        "memorylens.integrations.mem0.instrumentor._get_memory_class",
        return_value=FakeMemory,
    )
    def test_instrument_add(self, mock_cls):
        exporter = self._setup()
        instrumentor = Mem0Instrumentor()
        instrumentor.instrument()

        mem = FakeMemory()
        result = mem.add("User likes jazz", user_id="u1")
        assert result["status"] == "ok"

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.OK
        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.mem0.instrumentor._get_memory_class",
        return_value=FakeMemory,
    )
    def test_instrument_search(self, mock_cls):
        exporter = self._setup()
        instrumentor = Mem0Instrumentor()
        instrumentor.instrument()

        mem = FakeMemory()
        results = mem.search("music preferences", user_id="u1")
        assert len(results) == 2

        span = exporter.spans[0]
        assert span.operation == MemoryOperation.READ
        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.mem0.instrumentor._get_memory_class",
        return_value=FakeMemory,
    )
    def test_instrument_update(self, mock_cls):
        exporter = self._setup()
        instrumentor = Mem0Instrumentor()
        instrumentor.instrument()

        mem = FakeMemory()
        mem.update("mem_1", "Now prefers classical")

        span = exporter.spans[0]
        assert span.operation == MemoryOperation.UPDATE
        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.mem0.instrumentor._get_memory_class",
        return_value=FakeMemory,
    )
    def test_instrument_delete(self, mock_cls):
        exporter = self._setup()
        instrumentor = Mem0Instrumentor()
        instrumentor.instrument()

        mem = FakeMemory()
        mem.delete("mem_1")

        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.DROPPED
        assert span.attributes["drop_reason"] == "explicit_delete"
        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.mem0.instrumentor._get_memory_class",
        return_value=FakeMemory,
    )
    def test_uninstrument_restores(self, mock_cls):
        exporter = self._setup()
        instrumentor = Mem0Instrumentor()
        instrumentor.instrument()
        instrumentor.uninstrument()

        mem = FakeMemory()
        mem.add("data", user_id="u1")
        assert len(exporter.spans) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_integrations/test_mem0.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

File: `src/memorylens/integrations/mem0/instrumentor.py`

```python
from __future__ import annotations

from typing import Any

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider


def _get_memory_class() -> type:
    """Import and return Mem0's Memory class."""
    try:
        from mem0 import Memory
        return Memory
    except ImportError:
        raise ImportError(
            "Mem0 not found. Install with: pip install memorylens[mem0]"
        )


class Mem0Instrumentor:
    """Auto-instruments Mem0's Memory class."""

    def __init__(self) -> None:
        self._original_add: Any = None
        self._original_search: Any = None
        self._original_update: Any = None
        self._original_delete: Any = None
        self._memory_class: type | None = None

    def instrument(self, **kwargs: Any) -> None:
        cls = _get_memory_class()
        self._memory_class = cls
        self._original_add = cls.add
        self._original_search = cls.search
        self._original_update = cls.update
        self._original_delete = cls.delete

        original_add = self._original_add
        original_search = self._original_search
        original_update = self._original_update
        original_delete = self._original_delete

        def patched_add(self_mem: Any, content: str, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.mem0")
            with tracer.start_span(
                operation=MemoryOperation.WRITE,
                attributes={"backend": "mem0", "framework": "mem0"},
            ) as span:
                span.set_content(input_content=content)
                result = original_add(self_mem, content, **kw)
                span.set_content(output_content=repr(result))
                return result

        def patched_search(self_mem: Any, query: str, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.mem0")
            with tracer.start_span(
                operation=MemoryOperation.READ,
                attributes={"backend": "mem0", "framework": "mem0"},
            ) as span:
                span.set_content(input_content=query)
                result = original_search(self_mem, query, **kw)
                if isinstance(result, list):
                    scores = [r.get("score", 0.0) for r in result if isinstance(r, dict)]
                    span.set_attribute("results_count", len(result))
                    span.set_attribute("scores", scores)
                span.set_content(output_content=repr(result))
                return result

        def patched_update(self_mem: Any, memory_id: str, content: str, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.mem0")
            with tracer.start_span(
                operation=MemoryOperation.UPDATE,
                attributes={
                    "backend": "mem0",
                    "framework": "mem0",
                    "memory_id": memory_id,
                },
            ) as span:
                span.set_content(input_content=content)
                result = original_update(self_mem, memory_id, content, **kw)
                span.set_content(output_content=repr(result))
                return result

        def patched_delete(self_mem: Any, memory_id: str, **kw: Any) -> Any:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.mem0")
            with tracer.start_span(
                operation=MemoryOperation.WRITE,
                attributes={
                    "backend": "mem0",
                    "framework": "mem0",
                    "drop_reason": "explicit_delete",
                    "memory_id": memory_id,
                },
            ) as span:
                span.set_status(SpanStatus.DROPPED)
                result = original_delete(self_mem, memory_id, **kw)
                return result

        cls.add = patched_add
        cls.search = patched_search
        cls.update = patched_update
        cls.delete = patched_delete

    def uninstrument(self) -> None:
        if self._memory_class is not None:
            self._memory_class.add = self._original_add
            self._memory_class.search = self._original_search
            self._memory_class.update = self._original_update
            self._memory_class.delete = self._original_delete
            self._memory_class = None
```

- [ ] **Step 4: Update the mem0 __init__.py**

File: `src/memorylens/integrations/mem0/__init__.py`

```python
from memorylens.integrations.mem0.instrumentor import Mem0Instrumentor

__all__ = ["Mem0Instrumentor"]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_integrations/test_mem0.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memorylens/integrations/mem0/ tests/test_integrations/test_mem0.py
git commit -m "feat: add Mem0 auto-instrumentation for Memory class"
```

---

## Task 14: CLI — Formatters and Core App

**Files:**
- Create: `src/memorylens/cli/formatters.py`, `src/memorylens/cli/main.py`
- Test: (tested via CLI commands in Task 15)

- [ ] **Step 1: Write the formatters**

File: `src/memorylens/cli/formatters.py`

```python
from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table


console = Console()


def print_spans_table(spans: list[dict[str, Any]]) -> None:
    """Print spans as a rich table."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("SPAN ID", style="dim", max_width=12)
    table.add_column("OPERATION")
    table.add_column("STATUS")
    table.add_column("DURATION")
    table.add_column("AGENT")
    table.add_column("SESSION", style="dim")

    for span in spans:
        status_style = {
            "ok": "green",
            "error": "red",
            "dropped": "yellow",
        }.get(span.get("status", ""), "")

        table.add_row(
            span.get("span_id", "")[:12],
            span.get("operation", ""),
            f"[{status_style}]{span.get('status', '')}[/{status_style}]",
            f"{span.get('duration_ms', 0):.1f}ms",
            span.get("agent_id", "-") or "-",
            span.get("session_id", "-") or "-",
        )

    console.print(table)


def print_span_detail(span: dict[str, Any]) -> None:
    """Print detailed view of a single span."""
    console.print(f"\n[bold]Trace: {span.get('span_id', '')} — {span.get('operation', '')}[/bold]\n")
    console.print(f"  Status:     {span.get('status', '')}")
    console.print(f"  Duration:   {span.get('duration_ms', 0):.1f}ms")
    console.print(f"  Agent:      {span.get('agent_id', '-') or '-'}")
    console.print(f"  Session:    {span.get('session_id', '-') or '-'}")
    console.print(f"  User:       {span.get('user_id', '-') or '-'}")

    attrs = span.get("attributes", "{}")
    if isinstance(attrs, str):
        attrs = json.loads(attrs)
    if attrs:
        console.print("\n  [bold]Attributes:[/bold]")
        for k, v in attrs.items():
            console.print(f"    {k}: {v}")

    if span.get("input_content"):
        console.print(f"\n  [bold]Input:[/bold]\n    {span['input_content']}")
    if span.get("output_content"):
        console.print(f"\n  [bold]Output:[/bold]\n    {span['output_content']}")
    console.print()


def print_json(data: Any) -> None:
    """Print data as formatted JSON."""
    console.print_json(json.dumps(data, default=str))
```

- [ ] **Step 2: Write the main CLI app**

File: `src/memorylens/cli/main.py`

```python
from __future__ import annotations

import typer

app = typer.Typer(
    name="memorylens",
    help="Observability and debugging for AI agent memory systems.",
    no_args_is_help=True,
)


def _register_commands() -> None:
    from memorylens.cli.commands.traces import traces_app
    from memorylens.cli.commands.stats import stats_app
    from memorylens.cli.commands.config import config_app

    app.add_typer(traces_app, name="traces", help="Inspect and manage traces")
    app.command(name="stats")(stats_app)
    app.add_typer(config_app, name="config", help="Manage configuration")


_register_commands()


@app.command()
def init() -> None:
    """Initialize MemoryLens local storage."""
    import os
    from pathlib import Path

    ml_dir = Path.home() / ".memorylens"
    ml_dir.mkdir(exist_ok=True)
    typer.echo(f"Initialized MemoryLens at {ml_dir}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 3: Commit**

```bash
git add src/memorylens/cli/formatters.py src/memorylens/cli/main.py
git commit -m "feat: add CLI formatters and Typer app skeleton"
```

---

## Task 15: CLI — Traces Commands

**Files:**
- Create: `src/memorylens/cli/commands/traces.py`
- Test: `tests/test_cli/test_commands.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_cli/test_commands.py`

```python
from __future__ import annotations

import json

from typer.testing import CliRunner

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.main import app

runner = CliRunner()


def _make_span(
    span_id: str = "s1",
    trace_id: str = "t1",
    operation: MemoryOperation = MemoryOperation.WRITE,
    status: SpanStatus = SpanStatus.OK,
    agent_id: str = "bot",
    session_id: str = "sess-1",
) -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=None,
        operation=operation,
        status=status,
        start_time=1000000000000.0,
        end_time=1000012000000.0,
        duration_ms=12.0,
        agent_id=agent_id,
        session_id=session_id,
        user_id="user-1",
        input_content="test input",
        output_content="test output",
        attributes={"backend": "test"},
    )


def _seed_db(db_path: str) -> None:
    exporter = SQLiteExporter(db_path=db_path)
    exporter.export([
        _make_span("s1", "t1", MemoryOperation.WRITE, SpanStatus.OK),
        _make_span("s2", "t2", MemoryOperation.READ, SpanStatus.OK),
        _make_span("s3", "t3", MemoryOperation.WRITE, SpanStatus.ERROR),
        _make_span("s4", "t4", MemoryOperation.WRITE, SpanStatus.DROPPED),
    ])
    exporter.shutdown()


class TestTracesListCommand:
    def test_list_all(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, ["traces", "list", "--db-path", db_path])
        assert result.exit_code == 0
        assert "s1" in result.stdout or "s2" in result.stdout

    def test_list_filter_operation(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(
            app, ["traces", "list", "--db-path", db_path, "--operation", "memory.read"]
        )
        assert result.exit_code == 0

    def test_list_json_output(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, ["traces", "list", "--db-path", db_path, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)


class TestTracesShowCommand:
    def test_show_by_trace_id(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, ["traces", "show", "t1", "--db-path", db_path])
        assert result.exit_code == 0
        assert "s1" in result.stdout or "t1" in result.stdout

    def test_show_not_found(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, ["traces", "show", "nonexistent", "--db-path", db_path])
        assert result.exit_code == 0
        assert "No trace found" in result.stdout or "not found" in result.stdout.lower()


class TestTracesExportCommand:
    def test_export_jsonl(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        out_path = str(tmp_path / "export.jsonl")
        result = runner.invoke(
            app, ["traces", "export", "--db-path", db_path, "--output", out_path]
        )
        assert result.exit_code == 0
        with open(out_path) as f:
            lines = f.readlines()
        assert len(lines) >= 1
        obj = json.loads(lines[0])
        assert "span_id" in obj


class TestInitCommand:
    def test_init_creates_directory(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / ".memorylens").is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_cli/test_commands.py -v
```

Expected: FAIL — `ModuleNotFoundError` for traces commands

- [ ] **Step 3: Write the traces commands**

File: `src/memorylens/cli/commands/traces.py`

```python
from __future__ import annotations

import json
import os
from typing import Optional

import typer

from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.formatters import console, print_json, print_span_detail, print_spans_table

traces_app = typer.Typer(no_args_is_help=True)

_DEFAULT_DB = os.path.expanduser("~/.memorylens/traces.db")


def _get_exporter(db_path: str) -> SQLiteExporter:
    return SQLiteExporter(db_path=db_path)


@traces_app.command("list")
def traces_list(
    operation: Optional[str] = typer.Option(None, help="Filter by operation (e.g. memory.write)"),
    status: Optional[str] = typer.Option(None, help="Filter by status (ok, error, dropped)"),
    agent_id: Optional[str] = typer.Option(None, "--agent-id", help="Filter by agent ID"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Filter by session ID"),
    limit: int = typer.Option(50, help="Max results"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    use_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List recent traces."""
    exporter = _get_exporter(db_path)
    spans = exporter.query(
        operation=operation,
        status=status,
        agent_id=agent_id,
        session_id=session_id,
        limit=limit,
    )
    exporter.shutdown()

    if use_json:
        for s in spans:
            if isinstance(s.get("attributes"), str):
                s["attributes"] = json.loads(s["attributes"])
        print_json(spans)
    else:
        print_spans_table(spans)


@traces_app.command("show")
def traces_show(
    trace_id: str = typer.Argument(..., help="Trace ID to inspect"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    use_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show detailed view of a trace."""
    exporter = _get_exporter(db_path)
    spans = exporter.query(trace_id=trace_id)
    exporter.shutdown()

    if not spans:
        console.print(f"No trace found with ID: {trace_id}")
        return

    if use_json:
        for s in spans:
            if isinstance(s.get("attributes"), str):
                s["attributes"] = json.loads(s["attributes"])
        print_json(spans)
    else:
        for span in spans:
            print_span_detail(span)


@traces_app.command("export")
def traces_export(
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    limit: int = typer.Option(1000, help="Max spans to export"),
) -> None:
    """Export traces as JSONL."""
    exporter = _get_exporter(db_path)
    spans = exporter.query(limit=limit)
    exporter.shutdown()

    lines = []
    for span in spans:
        if isinstance(span.get("attributes"), str):
            span["attributes"] = json.loads(span["attributes"])
        lines.append(json.dumps(span, default=str))

    if output:
        with open(output, "w") as f:
            f.write("\n".join(lines) + "\n")
        console.print(f"Exported {len(lines)} spans to {output}")
    else:
        for line in lines:
            typer.echo(line)
```

- [ ] **Step 4: Write the stats command**

File: `src/memorylens/cli/commands/stats.py`

```python
from __future__ import annotations

import json
import os
from collections import Counter

import typer

from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.formatters import console, print_json

from rich.table import Table

_DEFAULT_DB = os.path.expanduser("~/.memorylens/traces.db")


def stats_app(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    group_by: str = typer.Option("operation", help="Group by: operation, status, agent_id"),
    use_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show summary statistics."""
    exporter = SQLiteExporter(db_path=db_path)
    spans = exporter.query(limit=10000)
    exporter.shutdown()

    if not spans:
        console.print("No spans found.")
        return

    counts: Counter = Counter()
    durations: dict[str, list[float]] = {}
    for span in spans:
        key = span.get(group_by, "unknown") or "unknown"
        counts[key] += 1
        durations.setdefault(key, []).append(span.get("duration_ms", 0))

    if use_json:
        data = [
            {
                group_by: key,
                "count": count,
                "avg_duration_ms": round(sum(durations[key]) / len(durations[key]), 1),
            }
            for key, count in counts.most_common()
        ]
        print_json(data)
    else:
        table = Table(show_header=True, header_style="bold")
        table.add_column(group_by.upper())
        table.add_column("COUNT", justify="right")
        table.add_column("AVG DURATION", justify="right")

        for key, count in counts.most_common():
            avg = sum(durations[key]) / len(durations[key])
            table.add_row(str(key), str(count), f"{avg:.1f}ms")

        console.print(table)
```

- [ ] **Step 5: Write the config command**

File: `src/memorylens/cli/commands/config.py`

```python
from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from memorylens.cli.formatters import console

config_app = typer.Typer(no_args_is_help=True)

_CONFIG_PATH = Path.home() / ".memorylens" / "config.json"


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        return json.loads(_CONFIG_PATH.read_text())
    return {}


def _save_config(config: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")


@config_app.command("show")
def config_show() -> None:
    """Show current configuration."""
    config = _load_config()
    if not config:
        console.print("No configuration set. Using defaults.")
        return
    console.print_json(json.dumps(config, indent=2))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key (e.g. exporter)"),
    value: str = typer.Argument(..., help="Config value"),
) -> None:
    """Set a configuration value."""
    config = _load_config()
    # Support dotted keys: "otlp.endpoint" -> {"otlp": {"endpoint": "..."}}
    parts = key.split(".")
    current = config
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value
    _save_config(config)
    console.print(f"Set {key} = {value}")
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli/test_commands.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 7: Run the full test suite**

```bash
uv run pytest tests/ -v
```

Expected: All tests across all files PASS.

- [ ] **Step 8: Commit**

```bash
git add src/memorylens/cli/ tests/test_cli/
git commit -m "feat: add CLI commands — traces list/show/export, stats, config, init"
```

---

## Task 16: Integration Test — End-to-End Flow

**Files:**
- Test: `tests/test_e2e.py`

- [ ] **Step 1: Write the end-to-end test**

File: `tests/test_e2e.py`

```python
from __future__ import annotations

import memorylens
from memorylens import instrument_write, instrument_read, context
from memorylens._core.tracer import TracerProvider
from memorylens._exporters.sqlite import SQLiteExporter


class TestEndToEnd:
    def test_full_flow_with_sqlite(self, tmp_path):
        """Test: init → decorate → context → call → query traces."""
        db_path = str(tmp_path / "e2e.db")

        memorylens.init(
            service_name="test-agent",
            exporter="sqlite",
            db_path=db_path,
            capture_content=True,
            sample_rate=1.0,
        )

        @instrument_write(backend="test_db")
        def store_memory(content: str) -> str:
            return f"stored: {content}"

        @instrument_read(backend="test_db")
        def search_memory(query: str) -> list[str]:
            return ["result1", "result2"]

        with context(agent_id="support-bot", session_id="sess-001", user_id="user-42"):
            store_memory("user prefers dark mode")
            results = search_memory("user preferences")

        assert results == ["result1", "result2"]

        # Flush all pending spans
        memorylens.shutdown()

        # Query the SQLite store directly
        exporter = SQLiteExporter(db_path=db_path)
        spans = exporter.query(limit=10)
        exporter.shutdown()

        assert len(spans) == 2

        write_spans = [s for s in spans if s["operation"] == "memory.write"]
        read_spans = [s for s in spans if s["operation"] == "memory.read"]
        assert len(write_spans) == 1
        assert len(read_spans) == 1

        write_span = write_spans[0]
        assert write_span["agent_id"] == "support-bot"
        assert write_span["session_id"] == "sess-001"
        assert write_span["user_id"] == "user-42"
        assert write_span["status"] == "ok"

    def test_error_flow(self, tmp_path):
        """Test: decorated function that raises an exception."""
        db_path = str(tmp_path / "e2e_err.db")

        memorylens.init(
            service_name="test-agent",
            exporter="sqlite",
            db_path=db_path,
        )

        @instrument_write(backend="flaky_db")
        def store_memory(content: str) -> str:
            raise ConnectionError("database unreachable")

        try:
            store_memory("important data")
        except ConnectionError:
            pass

        memorylens.shutdown()

        exporter = SQLiteExporter(db_path=db_path)
        spans = exporter.query(limit=10)
        exporter.shutdown()

        assert len(spans) == 1
        assert spans[0]["status"] == "error"
```

- [ ] **Step 2: Run the test**

```bash
uv run pytest tests/test_e2e.py -v
```

Expected: All 2 tests PASS.

- [ ] **Step 3: Run the complete test suite one final time**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: All tests across all files PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add end-to-end integration tests for full SDK flow"
```

---

## Task 17: README and Final Polish

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

File: `README.md`

````markdown
# MemoryLens

**Observability and debugging for AI agent memory systems.**

MemoryLens instruments the memory pipeline in your AI agents — write, read, compress, update — and gives you full visibility into what's happening. No more guessing why your agent "forgot" something.

## Install

```bash
pip install memorylens

# With framework integrations
pip install memorylens[langchain]
pip install memorylens[mem0]
```

## Quick Start

```python
import memorylens
from memorylens import instrument_write, instrument_read, context

# Initialize (defaults to local SQLite storage)
memorylens.init()

# Decorate your memory functions
@instrument_write(backend="my_db")
def store(content: str) -> bool:
    # your existing code
    return True

@instrument_read(backend="my_db")
def search(query: str) -> list[str]:
    # your existing code
    return ["result"]

# Add context for session tracking
with context(agent_id="support-bot", session_id="sess-123", user_id="user-456"):
    store("user prefers vegetarian meals")
    results = search("dietary preferences")

# Inspect with the CLI
# memorylens traces list
# memorylens traces show <trace-id>
```

## Auto-Instrumentation

For supported frameworks, zero code changes required:

```python
import memorylens

memorylens.init(instrument=["langchain", "mem0"])
# All memory operations are now traced automatically
```

## CLI

```bash
memorylens init                          # Set up local storage
memorylens traces list                   # List recent traces
memorylens traces list --status error    # Filter by status
memorylens traces show <trace-id>        # Inspect a trace
memorylens traces export -o traces.jsonl # Export as JSONL
memorylens stats                         # Summary statistics
```

## OTLP Export

Send traces to any OpenTelemetry-compatible backend:

```python
memorylens.init(
    exporter="otlp",
    otlp_endpoint="http://localhost:4317",
)
```

Or use environment variables:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_SERVICE_NAME=my-agent
```

## License

Apache 2.0
````

- [ ] **Step 2: Run linting**

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

Fix any issues reported.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README with quickstart, CLI, and OTLP examples"
```

- [ ] **Step 4: Final full test suite run**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: All tests PASS. This is the verification that the complete Phase 1 SDK is working.

---

## Summary

| Task | Component | Tests |
|------|-----------|-------|
| 1 | Project scaffolding | — |
| 2 | Schema enums | 11 |
| 3 | MemorySpan dataclass | 5 |
| 4 | Context propagation | 4 |
| 5 | SpanProcessor + BatchSpanProcessor | 5 |
| 6 | TracerProvider + Tracer | 8 |
| 7 | Decorators | 9 |
| 8 | Public API + init() | — |
| 9 | SQLite exporter | 6 |
| 10 | JSONL exporter | 3 |
| 11 | OTLP exporter | 3 |
| 12 | LangChain integration | 3 |
| 13 | Mem0 integration | 5 |
| 14 | CLI formatters + app | — |
| 15 | CLI commands | 6 |
| 16 | End-to-end tests | 2 |
| 17 | README + polish | — |

**Total: 17 tasks, ~70 tests, 30+ files**
