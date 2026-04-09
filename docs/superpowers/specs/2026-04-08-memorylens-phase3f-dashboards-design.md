# MemoryLens Phase 3f — Datadog/Grafana Dashboard Packages Design

**Date:** 2026-04-08
**Scope:** Pre-built dashboard JSON configs for Grafana and Datadog
**Status:** Approved
**Depends on:** Phase 1 SDK (OTLP export), Phase 2c (cost attributes), Phase 3a (drift attributes)

---

## Overview

Ship 8 pre-built dashboard JSON files (4 Grafana, 4 Datadog) that visualize MemoryLens OTLP span data. Bundled in the package, exported via CLI command. Zero code — just configuration.

---

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Plugin type | Dashboard JSON configs | OTLP traces already carry all data; configs give immediate value |
| Dashboards | 4 per platform: Operations, Retrieval, Cost, Drift | Covers all MemoryLens data in OTLP spans |
| Delivery | Bundled in package + CLI export | Always available, no network needed |

---

## Dashboards

### Operations Dashboard
- Span count by operation type (bar chart)
- Error rate over time (line chart)
- Latency p50/p95/p99 by operation (bar chart)
- Throughput — spans per minute (line chart)
- Top agents by span count (table)
- Queries: filter on `memorylens.operation`, `memorylens.status`, span duration

### Retrieval Dashboard
- Score distribution histogram (from `memorylens.scores`)
- Threshold hit/miss ratio (pie chart: returned vs filtered)
- Low-score queries — READ spans where min score < threshold (table)
- Average retrieval score by agent (bar chart)
- Queries: filter on `memorylens.operation = memory.read`, `memorylens.scores`, `memorylens.threshold`

### Cost Dashboard
- Total cost by agent (bar chart)
- Cost by session over time (line chart)
- Cost by operation type (pie chart)
- Token usage — tokens_in + tokens_out over time (stacked area)
- Top spenders — sessions sorted by cost (table)
- Queries: `memorylens.cost_usd`, `memorylens.tokens_in`, `memorylens.tokens_out`

### Drift Dashboard
- Drift events over time — spans with `drift_detected=true` (line chart)
- Drift score distribution (histogram)
- Top drifting entities by drift_score (table)
- Drift rate by agent (bar chart)
- Queries: `memorylens.drift_score`, `memorylens.drift_detected`, `memorylens.memory_key`

---

## File Structure

```
src/memorylens/dashboards/
├── __init__.py              # get_dashboard_path(), list_dashboards()
├── grafana/
│   ├── operations.json
│   ├── retrieval.json
│   ├── cost.json
│   └── drift.json
└── datadog/
    ├── operations.json
    ├── retrieval.json
    ├── cost.json
    └── drift.json
```

### Helper Functions

```python
def get_dashboard_path(platform: str, name: str) -> Path: ...
def list_dashboards(platform: str) -> list[str]: ...
def export_dashboards(platform: str, output_dir: Path, name: str | None = None) -> list[Path]: ...
```

---

## CLI Command

```bash
memorylens export dashboard --format grafana
memorylens export dashboard --format datadog
memorylens export dashboard --format grafana --output /path/to/dir
memorylens export dashboard --format grafana --name operations
```

Registered as `memorylens export` command group in `cli/main.py`.

---

## Testing

```
tests/
├── test_dashboards/
│   ├── __init__.py
│   ├── test_dashboard_json.py   # validate all 8 JSONs are valid
│   └── test_export.py           # CLI export command tests
```

- Verify all JSON files parse without error
- Verify Grafana JSONs have `panels` key
- Verify Datadog JSONs have `widgets` key  
- Verify CLI copies files to output directory
- Verify `--name` filter works

---

## Modified Files

| File | Change |
|---|---|
| `src/memorylens/cli/main.py` | Register export command group |
