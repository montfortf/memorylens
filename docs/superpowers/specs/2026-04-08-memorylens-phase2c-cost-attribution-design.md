# MemoryLens Phase 2c — Cost Attribution Design

**Date:** 2026-04-08
**Scope:** Token/dollar cost tracking per memory operation
**Status:** Approved
**Depends on:** Phase 1 SDK (complete), Phase 2a Web UI (complete)

---

## Overview

Cost attribution tracks token counts and dollar costs per memory operation. It works as **offline enrichment** — users set `tokens_in`/`tokens_out`/`model` as span attributes during instrumentation, and a CLI command computes `cost_usd` using a configurable pricing model. Costs appear in existing CLI and UI views.

---

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Cost capture | Offline enrichment via CLI | Zero runtime overhead, same pattern as compression auditor |
| Pricing model | Built-in defaults + user config override | Works out of the box, customizable |
| Aggregation | CLI report + cost in existing UI views | Contextual — see cost next to the trace |
| Storage | Update span attributes in-place | Cost is 3 numbers, not complex analysis; avoids new table |

---

## Pricing Model

### Default Pricing Table

```python
DEFAULT_PRICING = {
    "gpt-4o": {"input": 0.0000025, "output": 0.00001},
    "gpt-4o-mini": {"input": 0.00000015, "output": 0.0000006},
    "gpt-4-turbo": {"input": 0.00001, "output": 0.00003},
    "claude-3-opus": {"input": 0.000015, "output": 0.000075},
    "claude-3-sonnet": {"input": 0.000003, "output": 0.000015},
    "claude-3-haiku": {"input": 0.00000025, "output": 0.00000125},
    "text-embedding-3-small": {"input": 0.00000002, "output": 0.0},
    "text-embedding-3-large": {"input": 0.00000013, "output": 0.0},
}
```

### User Override

Users override via `~/.memorylens/pricing.json`:

```json
{
    "my-fine-tuned-model": {"input": 0.00001, "output": 0.00003}
}
```

The enricher merges user pricing over defaults. User entries take precedence.

### Loading

```python
def load_pricing() -> dict[str, dict[str, float]]:
    """Load DEFAULT_PRICING merged with user pricing.json if it exists."""
```

---

## Cost Enricher

### How Users Add Token Data

Via decorator kwargs (stored as span attributes):

```python
@instrument_write(backend="mem0", tokens_in=150, tokens_out=0, model="gpt-4o-mini")
def store(...): ...
```

Or manually:

```python
with tracer.start_span(...) as span:
    span.set_attribute("tokens_in", 150)
    span.set_attribute("tokens_out", 50)
    span.set_attribute("model", "gpt-4o-mini")
```

### Enrichment Logic

```python
class CostEnricher:
    def __init__(self, pricing: dict[str, dict[str, float]]): ...

    def enrich_span(self, span: dict) -> dict | None:
        """Compute cost from tokens_in/tokens_out/model. Returns updated attributes or None."""
        tokens_in = attrs.get("tokens_in", 0)
        tokens_out = attrs.get("tokens_out", 0)
        model = attrs.get("model")
        # If no token data, skip
        # Look up model in pricing
        # cost = tokens_in * pricing[model]["input"] + tokens_out * pricing[model]["output"]
        # Return {"cost_usd": cost} to merge into attributes
```

Spans without `tokens_in` or `tokens_out` are skipped. Spans with tokens but unknown model get a warning in CLI output.

### SQLiteExporter Extension

New method:

```python
def update_span_attributes(self, span_id: str, new_attrs: dict) -> None:
    """Merge new_attrs into existing span attributes JSON."""
    # Read current attributes, json.loads, dict.update, json.dumps, UPDATE spans SET attributes=?
```

---

## CLI Commands

```bash
memorylens cost enrich                         # enrich all spans with token data but no cost_usd
memorylens cost enrich --trace-id abc123       # specific trace
memorylens cost enrich --force                 # recalculate all (e.g. after pricing update)

memorylens cost report                         # aggregated cost report
memorylens cost report --group-by agent_id     # group by agent
memorylens cost report --group-by session_id   # group by session
memorylens cost report --group-by operation    # group by operation type

memorylens cost pricing                        # show current pricing table
memorylens cost pricing --set gpt-4o-mini.input=0.0000002  # update pricing
```

### Report Output

```
Cost Report (grouped by operation)

OPERATION         SPANS   TOKENS IN   TOKENS OUT   TOTAL COST
memory.write        45      12,300        0          $0.0018
memory.read         38       8,400      2,100        $0.0031
memory.compress     12       6,800      1,200        $0.0015

Total: 95 spans, 27,500 tokens in, 3,300 tokens out, $0.0064
```

---

## UI Integration

No new pages. Cost data appears in existing views:

1. **Trace list** — add "Cost" column showing `$0.0012` or `-` if no cost data. Read from `span.attributes.cost_usd`.
2. **Trace detail header** — show cost after duration: `12ms · $0.0012`. Only if `cost_usd` exists in attributes.
3. No new routes or templates beyond modifying `trace_table.html` and `traces_detail.html`.

---

## File Structure

### New Files

```
src/memorylens/
├── _cost/
│   ├── __init__.py
│   ├── pricing.py        # DEFAULT_PRICING, load_pricing(), save_user_pricing()
│   └── enricher.py       # CostEnricher
├── cli/commands/
│   └── cost.py           # memorylens cost enrich/report/pricing
```

### Modified Files

| File | Change |
|---|---|
| `pyproject.toml` | No new deps — cost uses only stdlib |
| `src/memorylens/_exporters/sqlite.py` | Add `update_span_attributes()` |
| `src/memorylens/_ui/templates/partials/trace_table.html` | Add Cost column |
| `src/memorylens/_ui/templates/traces_detail.html` | Add cost in header line |
| `src/memorylens/cli/main.py` | Register cost command group |

### Tests

```
tests/
├── test_cost/
│   ├── __init__.py
│   ├── test_pricing.py     # pricing load/merge/save
│   ├── test_enricher.py    # cost computation, skip logic
│   └── test_storage.py     # update_span_attributes
├── test_cli/
│   └── test_cost_commands.py  # CLI cost commands
```
