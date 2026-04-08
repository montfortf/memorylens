# MemoryLens Instrumentation Spec v1

**Status:** Published  
**Date:** 2026-04-08  
**Scope:** Community integration developers

---

## 1. Introduction

This document defines the contract that community-built MemoryLens integrations must satisfy. It is intended for developers who want to add auto-instrumentation support for a new memory framework (e.g., ChromaDB, Zep, custom vector stores).

MemoryLens auto-instrumentation works by monkey-patching the target framework at runtime so that every memory operation emits a `MemorySpan`. Users enable an integration with a single call — no changes to their application code.

**Who should read this:** Anyone building or validating a `memorylens-{framework}` integration package.

---

## 2. Instrumentor Protocol

Every integration must expose a class that satisfies the `Instrumentor` protocol:

```python
from typing import Any, Protocol

class Instrumentor(Protocol):
    def instrument(self, **kwargs: Any) -> None:
        """Activate instrumentation. Monkey-patch the target framework."""
        ...

    def uninstrument(self) -> None:
        """Deactivate instrumentation. Restore original methods."""
        ...
```

The full protocol is defined in `memorylens.integrations` and can be imported:

```python
from memorylens.integrations import Instrumentor
```

### Contract

- `instrument()` must be idempotent — calling it twice must not double-patch.
- `uninstrument()` must fully restore the original behaviour. After calling it, no spans should be emitted.
- Both methods must raise `ImportError` with a clear install message if the target framework is not installed, rather than a generic `ModuleNotFoundError`.

---

## 3. Required Span Attributes

Each operation type has required and optional attributes. Required attributes must appear on every span.

| Operation | Required Attributes | Optional Attributes |
|---|---|---|
| `memory.write` | `backend`, `framework` | `memory_key`, `embedding_model`, `vector_dim`, `drop_reason`, `drop_policy` |
| `memory.read` | `backend`, `framework` | `query`, `results_count`, `scores`, `threshold`, `top_k` |
| `memory.compress` | `framework` | `model`, `pre_content`, `post_content`, `compression_ratio` |
| `memory.update` | `backend`, `framework` | `memory_key`, `memory_id`, `update_type` |

**Attribute definitions:**

- `backend` — the concrete class name being patched (e.g., `"ConversationBufferMemory"`)
- `framework` — the framework name in lowercase (e.g., `"langchain"`, `"mem0"`)
- `memory_key` — key under which the memory is stored (if applicable)
- `results_count` — number of results returned by a read operation
- `compression_ratio` — float representing `len(post) / len(pre)`

---

## 4. Implementation Pattern

### 4.1 Getter Function

Define a getter that imports the class to patch. This defers the import so MemoryLens itself does not require the framework as a hard dependency.

```python
def _get_base_memory_class() -> type:
    """Import and return the target class. Raises ImportError with install hint."""
    try:
        from my_framework import BaseMemory
        return BaseMemory
    except ImportError:
        raise ImportError(
            "MyFramework not found. Install with: pip install memorylens[myframework]"
        )
```

### 4.2 Instrumentor Class

```python
from typing import Any
from memorylens._core.schema import MemoryOperation
from memorylens._core.tracer import TracerProvider


class MyFrameworkInstrumentor:
    """Auto-instruments MyFramework memory operations."""

    def __init__(self) -> None:
        self._original_save: Any = None
        self._original_load: Any = None
        self._base_class: type | None = None

    def instrument(self, **kwargs: Any) -> None:
        if self._base_class is not None:
            return  # Already instrumented — idempotent guard

        cls = _get_base_memory_class()
        self._base_class = cls

        # Save originals before patching
        self._original_save = cls.save
        self._original_load = cls.load

        original_save = self._original_save
        original_load = self._original_load

        def patched_save(self_mem: Any, content: str) -> None:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.myframework")
            with tracer.start_span(
                operation=MemoryOperation.WRITE,
                attributes={
                    "backend": type(self_mem).__name__,
                    "framework": "myframework",
                },
            ) as span:
                span.set_content(input_content=content)
                return original_save(self_mem, content)

        def patched_load(self_mem: Any, query: str) -> list[str]:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.myframework")
            with tracer.start_span(
                operation=MemoryOperation.READ,
                attributes={
                    "backend": type(self_mem).__name__,
                    "framework": "myframework",
                },
            ) as span:
                span.set_content(input_content=query)
                result = original_load(self_mem, query)
                span.set_attribute("results_count", len(result))
                span.set_content(output_content=repr(result))
                return result

        cls.save = patched_save
        cls.load = patched_load

    def uninstrument(self) -> None:
        if self._base_class is not None:
            self._base_class.save = self._original_save
            self._base_class.load = self._original_load
            self._base_class = None
            self._original_save = None
            self._original_load = None
```

### 4.3 Key Patterns

- **Save originals before patching.** Always capture `cls.method` before replacing it.
- **Capture in closure.** Assign originals to local variables (`original_save = self._original_save`) before defining the wrapper, so the closure captures the right reference even if `instrument()` is somehow called again.
- **Restore in `uninstrument()`** by assigning back to the class attribute, then set `self._base_class = None`.
- **Idempotent guard.** Check `if self._base_class is not None: return` at the start of `instrument()`.

---

## 5. Naming Conventions

| Artifact | Convention | Example |
|---|---|---|
| PyPI package | `memorylens-{framework}` | `memorylens-chromadb` |
| Python module | `memorylens_{framework}` | `memorylens_chromadb` |
| Instrumentor class | `{Framework}Instrumentor` | `ChromaDBInstrumentor` |
| pip extra | `memorylens[{framework}]` | `memorylens[chromadb]` |
| Tracer name | `memorylens.{framework}` | `memorylens.chromadb` |

Framework names should be lowercase, no hyphens in the module name (use underscores).

---

## 6. Registration

Built-in integrations are registered in `memorylens/integrations/__init__.py` via `register_instrumentor()`. Community packages can register themselves too:

```python
from memorylens.integrations import register_instrumentor
from memorylens_chromadb.instrumentor import ChromaDBInstrumentor

register_instrumentor("chromadb", ChromaDBInstrumentor)
```

Registration makes the instrumentor available to `memorylens.init(instrument=["chromadb"])`.

For built-in integrations, add to `_register_builtins()` in `memorylens/integrations/__init__.py`:

```python
try:
    from memorylens.integrations.chromadb import ChromaDBInstrumentor
    register_instrumentor("chromadb", ChromaDBInstrumentor)
except Exception:
    pass
```

The `except Exception: pass` ensures that if the framework is not installed, registration is silently skipped.

---

## 7. Complete Example

A full integration for a hypothetical `MemoryDB` framework. This is the pattern to follow when building your own.

### 7.1 The Fake Framework (for illustration)

```python
# Imagine this is the third-party package: memorydb

class MemoryDB:
    """A simple in-process memory store."""

    def __init__(self):
        self._store: dict[str, str] = {}

    def save(self, key: str, content: str) -> None:
        self._store[key] = content

    def load(self, query: str) -> list[str]:
        return [v for k, v in self._store.items() if query.lower() in v.lower()]

    def update(self, key: str, content: str) -> None:
        self._store[key] = content
```

### 7.2 The Integration Package

**`memorylens_memorydb/instrumentor.py`**:

```python
from __future__ import annotations

from typing import Any

from memorylens._core.schema import MemoryOperation
from memorylens._core.tracer import TracerProvider


def _get_memory_db_class() -> type:
    """Import and return the MemoryDB class."""
    try:
        from memorydb import MemoryDB
        return MemoryDB
    except ImportError:
        raise ImportError(
            "MemoryDB not found. Install with: pip install memorylens[memorydb]"
        )


class MemoryDBInstrumentor:
    """Auto-instruments MemoryDB memory operations."""

    def __init__(self) -> None:
        self._original_save: Any = None
        self._original_load: Any = None
        self._original_update: Any = None
        self._base_class: type | None = None

    def instrument(self, **kwargs: Any) -> None:
        if self._base_class is not None:
            return  # idempotent

        cls = _get_memory_db_class()
        self._base_class = cls
        self._original_save = cls.save
        self._original_load = cls.load
        self._original_update = cls.update

        original_save = self._original_save
        original_load = self._original_load
        original_update = self._original_update

        def patched_save(self_mem: Any, key: str, content: str) -> None:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.memorydb")
            with tracer.start_span(
                operation=MemoryOperation.WRITE,
                attributes={
                    "backend": type(self_mem).__name__,
                    "framework": "memorydb",
                    "memory_key": key,
                },
            ) as span:
                span.set_content(input_content=content)
                return original_save(self_mem, key, content)

        def patched_load(self_mem: Any, query: str) -> list[str]:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.memorydb")
            with tracer.start_span(
                operation=MemoryOperation.READ,
                attributes={
                    "backend": type(self_mem).__name__,
                    "framework": "memorydb",
                    "query": query,
                },
            ) as span:
                result = original_load(self_mem, query)
                span.set_attribute("results_count", len(result))
                span.set_content(output_content=repr(result))
                return result

        def patched_update(self_mem: Any, key: str, content: str) -> None:
            provider = TracerProvider.get()
            tracer = provider.get_tracer("memorylens.memorydb")
            with tracer.start_span(
                operation=MemoryOperation.UPDATE,
                attributes={
                    "backend": type(self_mem).__name__,
                    "framework": "memorydb",
                    "memory_key": key,
                },
            ) as span:
                span.set_content(input_content=content)
                return original_update(self_mem, key, content)

        cls.save = patched_save
        cls.load = patched_load
        cls.update = patched_update

    def uninstrument(self) -> None:
        if self._base_class is not None:
            self._base_class.save = self._original_save
            self._base_class.load = self._original_load
            self._base_class.update = self._original_update
            self._base_class = None
            self._original_save = None
            self._original_load = None
            self._original_update = None
```

**`memorylens_memorydb/__init__.py`**:

```python
from memorylens_memorydb.instrumentor import MemoryDBInstrumentor

__all__ = ["MemoryDBInstrumentor"]

# Auto-register with MemoryLens
try:
    from memorylens.integrations import register_instrumentor
    register_instrumentor("memorydb", MemoryDBInstrumentor)
except Exception:
    pass
```

---

## 8. Testing

Use `IntegrationTestHelper` from `memorylens.testing` to write tests for your integration.

```python
from memorylens.testing import IntegrationTestHelper
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens_memorydb.instrumentor import MemoryDBInstrumentor


def test_write_emits_span():
    helper = IntegrationTestHelper()
    instrumentor = MemoryDBInstrumentor()
    instrumentor.instrument()

    db = MemoryDB()
    db.save("key1", "user prefers vegetarian meals")

    helper.assert_span_count(1)
    helper.assert_operation(0, MemoryOperation.WRITE)
    helper.assert_attribute(0, "framework", "memorydb")
    helper.assert_attribute(0, "backend", "MemoryDB")
    helper.assert_status(0, SpanStatus.OK)

    instrumentor.uninstrument()
    helper.reset()


def test_read_emits_span():
    helper = IntegrationTestHelper()
    instrumentor = MemoryDBInstrumentor()
    instrumentor.instrument()

    db = MemoryDB()
    db.save("key1", "user prefers vegetarian meals")
    helper.reset()  # clear the write span

    helper = IntegrationTestHelper()
    results = db.load("vegetarian")

    helper.assert_span_count(1)
    helper.assert_operation(0, MemoryOperation.READ)
    helper.assert_attribute(0, "results_count", 1)

    instrumentor.uninstrument()
    helper.reset()
```

### IntegrationTestHelper API

| Method | Description |
|---|---|
| `IntegrationTestHelper()` | Creates a fresh TracerProvider with a collecting exporter |
| `helper.spans` | List of `MemorySpan` objects collected so far |
| `helper.assert_span_count(n)` | Fails if span count != n |
| `helper.assert_operation(i, op)` | Fails if span[i].operation != op |
| `helper.assert_attribute(i, key, value?)` | Fails if attribute missing or value mismatch |
| `helper.assert_status(i, status)` | Fails if span[i].status != status |
| `helper.reset()` | Clears collected spans and resets TracerProvider |

---

## 9. Validation

Run the built-in validator to check your integration before publishing:

```bash
memorylens validate integration memorylens_memorydb.instrumentor
```

The validator will:
1. Import your module
2. Find classes with `instrument` and `uninstrument` methods
3. Instantiate each instrumentor
4. Call `instrument()` — must not raise
5. Call `uninstrument()` — must not raise
6. Report PASS/FAIL with per-check details

### Example Output

```
Validating: memorylens_memorydb.instrumentor

  ✓ Import successful
  ✓ Found instrumentor: MemoryDBInstrumentor
  ✓ MemoryDBInstrumentor() instantiated
  ✓ MemoryDBInstrumentor.instrument() completed
  ✓ MemoryDBInstrumentor.uninstrument() completed

PASSED: memorylens_memorydb.instrumentor (5/5 checks)
```

If the target framework is not installed, `instrument()` will raise `ImportError` — the validator will report this as a failed check. This is expected when validating in an environment without the framework. Install the framework first, then run the validator.
