# MemoryLens Phase 1 — Core Instrumentation SDK Design

**Date:** 2026-04-07
**Scope:** Phase 1 Alpha (Weeks 1–8 of PRD roadmap)
**Status:** Approved

---

## Overview

MemoryLens is an observability/debugging tool for AI agent memory systems. It instruments the memory pipeline (write, retrieve, compress, update) across frameworks like LangChain, Mem0, Letta, and LlamaIndex — exposing failures that are currently invisible to developers.

Phase 1 delivers the **Core Instrumentation SDK**: a Python package with decorator-based manual instrumentation, auto-instrumentation for LangChain and Mem0, OpenTelemetry-native trace export, local SQLite storage, and a CLI for trace inspection. Open-source under Apache 2.0.

---

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Distribution | Core + optional extras (`memorylens[langchain]`, `memorylens[mem0]`) | Keeps core lean, integrations opt-in |
| Python version | 3.10+ | Modern type syntax, `match/case`, covers vast majority of agent developers |
| Async strategy | Sync API, async trace export in background thread | Small API surface, <2ms p99 overhead via `BatchSpanProcessor` |
| Local storage | SQLite (primary) + JSONL export | Structured queries for CLI + portable file export |
| Instrumentation | Decorators (core) + auto-instrumentation (integrations) | Manual for custom backends, "3 lines of code" for supported frameworks |
| CLI style | Subcommand-based (Typer) | Scriptable, lean, web UI deferred to Phase 2 |
| Architecture | Layered single package with internal boundaries | Clean separation without monorepo overhead |
| Tooling | uv + pyproject.toml | Fast, modern, signals contemporary project |

---

## Trace Schema & Core Data Model

### MemorySpan

The core data structure for every memory operation:

```python
@dataclass
class MemorySpan:
    # Identity
    span_id: str                # unique span ID (UUID)
    trace_id: str               # groups spans in one logical operation
    parent_span_id: str | None

    # Classification
    operation: MemoryOperation  # WRITE, READ, COMPRESS, UPDATE
    status: SpanStatus          # OK, ERROR, DROPPED

    # Timing
    start_time: float           # epoch nanoseconds
    end_time: float
    duration_ms: float

    # Context
    agent_id: str | None        # which agent
    session_id: str | None      # which session
    user_id: str | None         # which end-user

    # Memory content (redactable)
    input_content: str | None   # what was sent (query or content to store)
    output_content: str | None  # what was returned or stored

    # Operation-specific attributes
    attributes: dict[str, Any]
```

### Enums

```python
class MemoryOperation(str, Enum):
    WRITE = "memory.write"
    READ = "memory.read"
    COMPRESS = "memory.compress"
    UPDATE = "memory.update"

class SpanStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    DROPPED = "dropped"
```

### Operation-Specific Attributes

| Operation | Key Attributes |
|---|---|
| WRITE | `memory_key`, `backend`, `drop_reason`, `drop_policy`, `embedding_model`, `vector_dim` |
| READ | `query`, `results_count`, `scores` (list of floats), `threshold`, `backend`, `top_k` |
| COMPRESS | `pre_content`, `post_content`, `compression_ratio`, `semantic_loss_score`, `model_used` |
| UPDATE | `memory_key`, `previous_version`, `new_version`, `update_type` (merge/replace/append) |

The schema maps directly to OpenTelemetry span attributes — OTLP export is a 1:1 mapping.

---

## Core Layer (`_core/`)

### TracerProvider

Singleton that manages configuration and span processing:

```python
class TracerProvider:
    _instance: TracerProvider | None = None

    def __init__(self):
        self.processors: list[SpanProcessor] = []
        self.resource: Resource   # agent_id, service_name, sdk_version
        self.sampler: Sampler     # controls trace sampling rate

    def add_processor(self, processor: SpanProcessor) -> None: ...
    def get_tracer(self, name: str) -> Tracer: ...

    @classmethod
    def get(cls) -> TracerProvider: ...  # singleton access
```

### SpanProcessor

Interface for anything that receives completed spans:

```python
class SpanProcessor(Protocol):
    def on_start(self, span: MemorySpan) -> None: ...
    def on_end(self, span: MemorySpan) -> None: ...
    def shutdown(self) -> None: ...
    def force_flush(self, timeout_ms: int = 30000) -> bool: ...
```

### BatchSpanProcessor

Non-blocking async exporter — `on_end()` enqueues to a queue, background thread batches and exports:

```python
class BatchSpanProcessor(SpanProcessor):
    def __init__(self, exporter: SpanExporter,
                 max_batch_size: int = 512,
                 schedule_delay_ms: int = 5000,
                 max_queue_size: int = 2048): ...
```

### Decorators

Four primitives that create spans around existing functions:

```python
@instrument_write(backend="mem0", capture_content=True)
def store_memory(user_id: str, content: str) -> bool: ...

@instrument_read(backend="mem0", capture_content=True)
def search_memories(query: str, top_k: int = 5) -> list[Memory]: ...

@instrument_compress(model="gpt-4o-mini")
def summarize_memories(memories: list[str]) -> str: ...

@instrument_update(backend="mem0")
def update_memory(memory_id: str, new_content: str) -> bool: ...
```

Each decorator:
1. Creates a `MemorySpan` with the correct `MemoryOperation`
2. Records `start_time`
3. Calls the wrapped function
4. Captures return value, exceptions, sets `status`
5. Passes completed span to all registered `SpanProcessor`s

`capture_content` controls whether input/output is recorded (defaults to `True`). In production, set `MEMORYLENS_CAPTURE_CONTENT=false` to disable. This is the PII safety lever.

### Context Propagation

`ContextVar`-based system for attaching session/agent metadata:

```python
with memorylens.context(agent_id="support-bot", session_id="sess-123", user_id="user-456"):
    # all spans inside inherit these attributes
    result = search_memories("user preferences")
```

---

## Exporters (`_exporters/`)

### SpanExporter Protocol

```python
class SpanExporter(Protocol):
    def export(self, spans: list[MemorySpan]) -> ExportResult: ...
    def shutdown(self) -> None: ...
```

### OTLP Exporter

- Translates `MemorySpan` → OTel `Span` (1:1 mapping)
- Supports gRPC and HTTP (`OTEL_EXPORTER_OTLP_PROTOCOL`)
- Configured via standard OTel env vars (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`)
- Required dependency of core package (OTLP is the primary production export path)

### SQLite Exporter

- Writes to `~/.memorylens/traces.db` (configurable)
- `spans` table with columns matching `MemorySpan`, `attributes` as JSON
- Indexes on `trace_id`, `session_id`, `operation`, `start_time`
- Auto-creates DB and runs migrations on first use
- Auto-prunes spans older than 7 days (configurable)

### JSONL Exporter

- One JSON object per span per line
- Defaults to stdout, configurable to file path
- Used by `memorylens traces export` CLI command
- Stateless — simplest exporter

### Default Configuration

```python
# Minimal — SQLite for local dev
memorylens.init()

# Production — OTLP to collector
memorylens.init(exporter="otlp", endpoint="http://localhost:4317")

# Both — local + remote
memorylens.init(exporters=["sqlite", "otlp"], otlp_endpoint="http://localhost:4317")
```

`memorylens.init()` with no args defaults to SQLite so traces are always captured locally.

---

## Integrations (`integrations/`)

### Instrumentor Protocol

```python
class Instrumentor(Protocol):
    def instrument(self, **kwargs) -> None: ...
    def uninstrument(self) -> None: ...
```

### LangChain Integration (`memorylens[langchain]`)

Patches `BaseMemory`:

```python
from memorylens.integrations.langchain import LangChainInstrumentor
LangChainInstrumentor().instrument()
```

- `save_context()` → WRITE span (input/output keys, memory key, backend type)
- `load_memory_variables()` → READ span (query, returned memories)
- `ConversationSummaryMemory` summarization → COMPRESS spans
- Captures memory backend class name as `backend` attribute

### Mem0 Integration (`memorylens[mem0]`)

Patches Mem0's `Memory` class:

```python
from memorylens.integrations.mem0 import Mem0Instrumentor
Mem0Instrumentor().instrument()
```

- `add()` → WRITE span (user_id, content, metadata)
- `search()` → READ span (query, results, similarity scores, threshold)
- `update()` → UPDATE span (memory_id, old/new content)
- `delete()` → WRITE span with status=DROPPED, drop_reason="explicit_delete"

### Auto-Instrumentation Shorthand

```python
memorylens.init(instrument=["langchain", "mem0"])
```

Looks up registered instrumentors by name. If framework not installed, raises: `"LangChain not found. Install with: pip install memorylens[langchain]"`.

---

## CLI (`cli/`)

Built with Typer. Reads from SQLite store.

### Commands

```bash
memorylens init                                    # create ~/.memorylens/
memorylens traces list [--operation X] [--status X] [--last 1h] [--agent-id X] [--session-id X]
memorylens traces show <trace-id>                  # full span detail
memorylens traces tail [--operation X] [--min-duration 100ms]  # live tail
memorylens traces export [--last 24h] [--format jsonl]         # JSONL export
memorylens stats [--last 7d] [--group-by operation]            # summary stats
memorylens config show
memorylens config set <key> <value>
```

### Output Formatting

- Default: human-readable tables via `rich`
- `--json` flag on any command for machine-readable output
- `traces show` renders structured view: timing, attributes, content

---

## Public API Surface

**8 public symbols** from `memorylens`:

| Symbol | Purpose |
|---|---|
| `init()` | Configure TracerProvider, exporters, auto-instrumentation |
| `shutdown()` | Flush pending spans + cleanup |
| `instrument_write` | Decorator for write operations |
| `instrument_read` | Decorator for read operations |
| `instrument_compress` | Decorator for compression operations |
| `instrument_update` | Decorator for update operations |
| `context()` | Context manager for session/agent/user metadata |
| `get_tracer()` | Escape hatch for manual span creation |

### Environment Variable Overrides

| Env Var | Effect |
|---|---|
| `MEMORYLENS_EXPORTER` | Override exporter (`sqlite`, `otlp`, `jsonl`) |
| `MEMORYLENS_CAPTURE_CONTENT` | `true`/`false` — PII toggle |
| `MEMORYLENS_SAMPLE_RATE` | `0.0`–`1.0` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector URL |
| `OTEL_EXPORTER_OTLP_HEADERS` | Auth headers for collector |
| `OTEL_SERVICE_NAME` | Service name in traces |

Env vars take precedence over `init()` kwargs.

---

## Project Structure

```
memorylens/
├── pyproject.toml
├── uv.lock
├── LICENSE                      # Apache 2.0
├── README.md
├── src/
│   └── memorylens/
│       ├── __init__.py          # public API re-exports
│       ├── _core/
│       │   ├── __init__.py
│       │   ├── tracer.py        # TracerProvider, Tracer
│       │   ├── span.py          # MemorySpan dataclass
│       │   ├── decorators.py    # 4 instrument_* decorators
│       │   ├── schema.py        # MemoryOperation, SpanStatus enums
│       │   ├── context.py       # ContextVar-based context propagation
│       │   ├── processor.py     # SpanProcessor, BatchSpanProcessor
│       │   └── sampler.py       # Sampler (rate-based)
│       ├── _exporters/
│       │   ├── __init__.py      # exporter registry + factory
│       │   ├── base.py          # SpanExporter protocol, ExportResult
│       │   ├── otlp.py          # OTLP gRPC/HTTP exporter
│       │   ├── sqlite.py        # SQLite local store
│       │   └── jsonl.py         # JSONL file exporter
│       ├── integrations/
│       │   ├── __init__.py      # Instrumentor protocol + registry
│       │   ├── langchain/
│       │   │   ├── __init__.py
│       │   │   └── instrumentor.py
│       │   └── mem0/
│       │       ├── __init__.py
│       │       └── instrumentor.py
│       └── cli/
│           ├── __init__.py
│           ├── main.py          # Typer app entry point
│           ├── commands/
│           │   ├── __init__.py
│           │   ├── traces.py    # list, show, tail, export
│           │   ├── stats.py     # summary statistics
│           │   └── config.py    # config management
│           └── formatters.py    # rich table + JSON output
├── tests/
│   ├── conftest.py
│   ├── test_core/
│   │   ├── test_tracer.py
│   │   ├── test_decorators.py
│   │   ├── test_span.py
│   │   ├── test_context.py
│   │   └── test_processor.py
│   ├── test_exporters/
│   │   ├── test_otlp.py
│   │   ├── test_sqlite.py
│   │   └── test_jsonl.py
│   ├── test_integrations/
│   │   ├── test_langchain.py
│   │   └── test_mem0.py
│   └── test_cli/
│       └── test_commands.py
└── docs/
```

### pyproject.toml Dependencies

```toml
[project]
name = "memorylens"
requires-python = ">=3.10"
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
dev = ["pytest>=8.0", "pytest-asyncio", "ruff", "mypy"]

[project.scripts]
memorylens = "memorylens.cli.main:app"
```

### Testing Strategy

- pytest with fixtures for each exporter
- Integration tests for LangChain/Mem0 use lightweight mocks of framework classes
- Separate `tests/test_integrations/` with optional markers for full integration tests
- `ruff` for linting, `mypy` for type checking
