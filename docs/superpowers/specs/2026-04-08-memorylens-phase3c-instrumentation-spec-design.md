# MemoryLens Phase 3c — Community Instrumentation Spec Design

**Date:** 2026-04-08
**Scope:** Published instrumentation spec v1, CLI validator, test helper
**Status:** Approved
**Depends on:** Phase 1 SDK (Instrumentor protocol)

---

## Overview

Formalizes the existing `Instrumentor` protocol as a published specification that community contributors can implement to add support for new memory frameworks. Includes a CLI validator tool and reusable test helper.

---

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Spec content | Protocol docs + validator tool | Validator is the real value for contributors |
| Spec location | `docs/instrumentation-spec-v1.md` | Technical spec, linked from README |
| Template | No cookiecutter | Integration code is ~50 lines, template adds overhead |

---

## Deliverable 1: Spec Document

`docs/instrumentation-spec-v1.md` covering:

### Instrumentor Protocol

```python
class Instrumentor(Protocol):
    def instrument(self, **kwargs: Any) -> None: ...
    def uninstrument(self) -> None: ...
```

### Required Span Attributes by Operation

| Operation | Required Attributes | Optional Attributes |
|---|---|---|
| `memory.write` | `backend`, `framework` | `memory_key`, `embedding_model`, `vector_dim`, `drop_reason`, `drop_policy` |
| `memory.read` | `backend`, `framework` | `query`, `results_count`, `scores`, `threshold`, `top_k` |
| `memory.compress` | `framework` | `model`, `pre_content`, `post_content`, `compression_ratio` |
| `memory.update` | `backend`, `framework` | `memory_key`, `memory_id`, `update_type` |

### Implementation Pattern

1. Getter function: `_get_{class}_class() -> type` with `ImportError` → clear install message
2. `instrument()`: save originals, replace with span-emitting wrappers
3. `uninstrument()`: restore originals
4. Registration: `register_instrumentor(name, cls)` in `integrations/__init__.py`

### Naming Conventions

- Package: `memorylens-{framework}` (e.g., `memorylens-chromadb`)
- Class: `{Framework}Instrumentor` (e.g., `ChromaDBInstrumentor`)
- Optional extra: `memorylens[{framework}]`

### Complete Example

A full ~50 line integration for a hypothetical framework.

---

## Deliverable 2: Validator CLI

`memorylens validate-integration <module_path>`

### How It Works

1. Import the module at `<module_path>` (e.g., `my_integration.instrumentor`)
2. Find classes that have `instrument` and `uninstrument` methods
3. Create a mock TracerProvider with CollectingExporter
4. Call `instrument()`
5. Verify: the class patched something (by checking that calling methods produces spans)
6. Check spans: valid MemoryOperation, `backend` or `framework` attribute present
7. Call `uninstrument()`
8. Verify: calling methods no longer produces spans
9. Report PASS/FAIL with details

### Validation Checks

| Check | Pass Condition |
|---|---|
| Import | Module imports without error |
| Instrumentor found | At least one class with instrument/uninstrument |
| instrument() | Doesn't raise |
| Spans produced | At least one span collected after instrument |
| Operation valid | All spans have valid MemoryOperation values |
| Attributes present | All spans have `framework` attribute |
| uninstrument() | Doesn't raise |
| Cleanup | No spans produced after uninstrument |

### Output

```
Validating: my_integration.instrumentor

  ✓ Import successful
  ✓ Found instrumentor: MyInstrumentor
  ✓ instrument() completed
  ✓ 3 spans produced
  ✓ All operations valid (memory.write, memory.read)
  ✓ All spans have required attributes
  ✓ uninstrument() completed
  ✓ No spans after uninstrument

PASSED: my_integration.instrumentor is a valid MemoryLens integration
```

---

## Deliverable 3: Integration Test Helper

`src/memorylens/testing.py` — importable by community devs for their test suites.

```python
class IntegrationTestHelper:
    def __init__(self):
        """Set up TracerProvider + CollectingExporter."""
        ...

    @property
    def spans(self) -> list[MemorySpan]: ...

    def assert_span_count(self, expected: int) -> None: ...
    def assert_operation(self, index: int, operation: MemoryOperation) -> None: ...
    def assert_attribute(self, index: int, key: str, value: Any = None) -> None: ...
    def assert_status(self, index: int, status: SpanStatus) -> None: ...
    def reset(self) -> None: ...
```

Usage by community devs:

```python
from memorylens.testing import IntegrationTestHelper

def test_my_integration():
    helper = IntegrationTestHelper()
    instrumentor = MyInstrumentor()
    instrumentor.instrument()

    # call patched methods...

    helper.assert_span_count(2)
    helper.assert_operation(0, MemoryOperation.WRITE)
    helper.assert_attribute(0, "framework", "my_framework")

    instrumentor.uninstrument()
    helper.reset()
```

---

## File Structure

### New Files

| File | Responsibility |
|---|---|
| `docs/instrumentation-spec-v1.md` | Published spec document |
| `src/memorylens/testing.py` | IntegrationTestHelper for community devs |
| `src/memorylens/cli/commands/validate.py` | validate-integration CLI command |
| `tests/test_cli/test_validate.py` | Validator tests |
| `tests/test_testing.py` | IntegrationTestHelper tests |

### Modified Files

| File | Change |
|---|---|
| `src/memorylens/cli/main.py` | Register validate-integration command |
| `README.md` | Add link to instrumentation spec |
