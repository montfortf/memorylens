# MemoryLens Phase 2a — Web UI Design

**Date:** 2026-04-07
**Scope:** Phase 2 Beta — Web Dashboard (Trace List, Trace Detail, Retrieval Debugger)
**Status:** Approved
**Depends on:** Phase 1 SDK (complete)

---

## Overview

The MemoryLens Web UI is a local developer dashboard for visualizing and debugging agent memory traces. It reads from the same SQLite store that the Phase 1 SDK writes to, providing a browser-based interface for trace inspection, timeline visualization, and retrieval debugging.

The dashboard launches via `memorylens ui` and optionally accepts live OTLP HTTP traces with `--ingest`, making it a lightweight trace collector + viewer in one.

---

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Tech stack | FastAPI + htmx + Jinja2 | Python-native, no Node.js dependency, no JS build step |
| Launch mode | `memorylens ui` + optional `--ingest` | Default reads SQLite, ingest adds live OTLP receiver |
| Views | Trace List, Trace Detail, Retrieval Debugger | Maps to PRD's "timeline view + retrieval debugger" |
| Distribution | `pip install memorylens[ui]` optional extra | Keeps core SDK lean, UI is opt-in |
| Styling | TailwindCSS via CDN | Flexibility without build step, dark theme |
| OTLP ingest | HTTP/JSON only (no gRPC) | Simpler, no protobuf compilation, sufficient for local dev |

---

## File Structure

```
src/memorylens/
├── _ui/
│   ├── __init__.py
│   ├── server.py                 # FastAPI app factory + uvicorn launcher
│   ├── api/
│   │   ├── __init__.py
│   │   ├── traces.py             # Page routes + JSON API endpoints
│   │   └── ingest.py             # OTLP HTTP/JSON receiver (optional)
│   ├── templates/
│   │   ├── base.html             # layout: nav, Tailwind CDN, htmx script
│   │   ├── traces_list.html      # trace list page
│   │   ├── traces_detail.html    # single trace timeline view
│   │   ├── retrieval_debug.html  # retrieval debugger view
│   │   └── partials/
│   │       ├── trace_table.html  # htmx partial: filterable trace rows
│   │       ├── span_timeline.html # htmx partial: span timeline
│   │       └── score_chart.html  # htmx partial: similarity score viz
│   └── static/
│       └── app.css               # custom styles (minimal, on top of Tailwind)
```

### New Dependencies (gated behind `[ui]` extra)

```toml
[project.optional-dependencies]
ui = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "jinja2>=3.1",
]
```

htmx and TailwindCSS are loaded via CDN `<script>` tags — no Python dependencies.

---

## FastAPI Server

### App Factory (`_ui/server.py`)

```python
def create_app(db_path: str, ingest: bool = False) -> FastAPI:
    """Create the FastAPI app with all routes and middleware."""
    app = FastAPI(title="MemoryLens")
    # Mount static files at /static
    # Configure Jinja2 templates directory
    # Register trace page routes and API routes
    # If ingest=True, register OTLP HTTP receiver routes
    return app

def run(db_path: str, port: int = 8000, ingest: bool = False):
    """Start the uvicorn server. Called by `memorylens ui` CLI command."""
    app = create_app(db_path, ingest)
    uvicorn.run(app, host="127.0.0.1", port=port)
```

### CLI Command

New command added to `cli/main.py`:

```bash
memorylens ui                              # reads from ~/.memorylens/traces.db, port 8000
memorylens ui --port 8080                  # custom port
memorylens ui --db-path ./my-traces.db     # custom DB
memorylens ui --ingest                     # also accept OTLP HTTP at /v1/traces on same port
```

The command checks for the `[ui]` extra at runtime. If missing, raises: `"UI dependencies not found. Install with: pip install memorylens[ui]"`.

---

## API Endpoints

### Page Routes (return full HTML)

| Method | Path | Template | Purpose |
|---|---|---|---|
| GET | `/` | redirect | Redirects to `/traces` |
| GET | `/traces` | `traces_list.html` | Trace list view |
| GET | `/traces/{trace_id}` | `traces_detail.html` | Trace detail with timeline |
| GET | `/traces/{trace_id}/retrieval` | `retrieval_debug.html` | Retrieval debugger for READ spans |

### API Routes (return HTML partials or JSON)

| Method | Path | Returns | Purpose |
|---|---|---|---|
| GET | `/api/traces` | HTML partial | Filtered trace table rows (htmx target) |
| GET | `/api/traces/{trace_id}/spans` | HTML partial | Span timeline (htmx target) |
| GET | `/api/traces/{trace_id}/retrieval` | HTML partial | Score chart + candidate list |

### Content Negotiation

If the request has `HX-Request: true` header (sent automatically by htmx), return the HTML partial. Otherwise return the full page. Same URL works for both initial page load and htmx partial updates.

### Query Parameters (`/api/traces`)

```
?operation=memory.write    # filter by operation type
&status=error              # filter by status
&agent_id=support-bot      # filter by agent
&session_id=sess-123       # filter by session
&q=user+preferences        # full-text search on input_content/output_content
&limit=50                  # page size
&offset=0                  # pagination offset
```

### OTLP Ingest (optional, only when `--ingest` is passed)

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/traces` | Accept OTLP HTTP/JSON trace data |

---

## Views

### Trace List (`/traces`)

The main landing page — a filterable, searchable table of all traces.

**Layout:**
- Top nav bar with "MemoryLens" branding and view navigation (Traces, Retrieval Debugger)
- Filter bar: search input, operation dropdown, status dropdown, agent ID input
- Trace table columns: Trace ID, Operation (color-coded badge), Status (dot indicator), Duration, Agent, Session, Content Preview, Time (relative)
- Error rows get subtle red background tint
- Pagination footer: "Showing 1-50 of 247" with Prev/Next

**htmx interactions:**
- Filter/search changes fire `hx-get="/api/traces"` with `hx-trigger="change"` (dropdowns) or `hx-trigger="keyup changed delay:300ms"` (search input). Swaps the table body partial.
- Row click navigates to `/traces/{trace_id}`
- Pagination uses `hx-get` with offset parameter
- Live tail (with `--ingest`): `hx-trigger="every 2s"` polls for new traces

### Trace Detail (`/traces/{trace_id}`)

Deep-dive into a single trace with timeline and attribute inspector.

**Two-column layout:**

**Left column:**
- Span timeline bar — visual duration bar with time axis, stacks vertically for parent/child spans. Each bar is colored by operation type, shows operation name and duration.
- Input content block — monospace code display of `input_content`
- Output content block — monospace code display of `output_content`
- Error block (red-tinted, only shown for error/dropped spans) — shows `error.type` and `error.message` from attributes

**Right column:**
- Attributes panel — key-value table split into two sections:
  - Standard fields: span_id, trace_id, operation (badge), status, duration, agent_id, session_id, user_id
  - Custom attributes: all entries from the `attributes` JSON field
- Action buttons:
  - "Export JSON" — downloads span data as JSON file
  - "Debug Retrieval →" — only visible for READ spans, links to `/traces/{trace_id}/retrieval`

**Header:** Breadcrumb (← Traces / {trace_id}), operation badge, status indicator, metadata line (agent, session, duration, timestamp).

### Retrieval Debugger (`/traces/{trace_id}/retrieval`)

The flagship debugging view — shows exactly why a retrieval returned or missed specific memories. Only accessible for READ operation spans.

**Query section** (top, two-column):
- Left: the search query text in a monospace box
- Right: parameters panel showing `backend`, `top_k`, `threshold`, `results_count` (returned/requested)

**Score visualization:**
- Horizontal bars for every candidate memory, scaled proportionally by similarity score (0.0 to 1.0)
- Green bars with "RETURNED" badge for candidates above the threshold
- Red bars with "FILTERED" badge for candidates below the threshold (shown dimmed)
- Dashed yellow vertical threshold line running through all bars at the threshold position
- Each bar shows: rank number, memory content preview, similarity score, and status badge

**Threshold insight callout:**
- Amber box that appears when there are near-miss candidates (scored within 0.10 of threshold)
- Text explains which candidates were close and suggests actions (lower threshold, improve query)

**Ranking diff section:**
- Side-by-side comparison of adjacent ranked results
- Highlights matching terms in each memory
- Shows why the higher-ranked result was semantically closer to the query

**Data source:** All data comes from existing READ span attributes: `scores` (list of floats), `threshold`, `top_k`, `results_count`, `query`, and `input_content`/`output_content`. No new SDK changes needed.

---

## SQLiteExporter Extensions

The UI needs richer querying than the existing `query()` method. We add a new method without modifying the existing one.

### New Method: `query_extended()`

```python
class SQLiteExporter:
    # Existing method — unchanged, backwards compatible
    def query(self, trace_id, operation, status, agent_id, session_id, limit) -> list[dict]: ...

    # New method for the UI
    def query_extended(
        self,
        trace_id: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        q: str | None = None,              # full-text search on input_content/output_content
        limit: int = 50,
        offset: int = 0,                   # pagination
    ) -> tuple[list[dict], int]:            # returns (rows, total_count)
```

**New capabilities:**
- `q` parameter — `WHERE input_content LIKE '%?%' OR output_content LIKE '%?%'`
- `offset` parameter — `OFFSET ?` for pagination
- Returns `(rows, total_count)` — total count powers the pagination footer

**No new database tables or schema changes.** The existing `spans` table and indexes are sufficient.

---

## OTLP Ingest Endpoint

The optional `--ingest` flag adds an HTTP endpoint that accepts OpenTelemetry trace data.

### How It Works

```
Agent App
    → OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8000
    → OTEL_EXPORTER_OTLP_PROTOCOL=http/json
    → POST /v1/traces (OTLP HTTP/JSON payload, same server)
    → MemoryLens parses, extracts memorylens.* attributes
    → Writes MemorySpan to SQLite
    → UI renders live
```

### Ingest Handler Logic

1. Parse OTLP HTTP/JSON payload (standard `ExportTraceServiceRequest` JSON format)
2. Iterate over `resource_spans[].scope_spans[].spans[]`
3. For each span, check for `memorylens.operation` attribute — skip non-MemoryLens spans
4. Map OTel attributes back to `MemorySpan` fields:
   - `memorylens.operation` → `operation`
   - `memorylens.status` → `status`
   - `memorylens.agent_id` → `agent_id`
   - `memorylens.session_id` → `session_id`
   - `memorylens.user_id` → `user_id`
   - `memorylens.input_content` → `input_content`
   - `memorylens.output_content` → `output_content`
   - All other `memorylens.*` attributes → `attributes` dict
5. Write `MemorySpan` objects to SQLite via `SQLiteExporter.export()`
6. Return 200 with empty JSON body (OTLP success response)

### Why HTTP/JSON Only

gRPC requires protobuf compilation and adds `grpcio` as a server-side dependency. HTTP/JSON is simpler, and the OTel SDK supports it with `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`. For a local dev tool, the performance difference is negligible.

---

## Testing Strategy

### Test Structure

```
tests/
├── test_ui/
│   ├── test_api_traces.py      # trace list/detail/retrieval endpoints
│   ├── test_api_ingest.py      # OTLP ingest endpoint
│   ├── test_templates.py       # template rendering with various data
│   └── test_query_extended.py  # SQLiteExporter extension tests
```

### API Tests (`test_api_traces.py`)

Using `httpx.AsyncClient` with FastAPI's `TestClient`:
- Each endpoint returns correct HTML (full page) vs HTML partial (htmx request with `HX-Request: true` header)
- Query parameter filtering passes through to `query_extended()` correctly
- Pagination (offset/limit) works
- Retrieval debugger returns 404 for non-READ spans

### Template Tests (`test_templates.py`)

Verify Jinja2 templates render without errors for:
- Normal spans (all fields populated)
- Minimal spans (optional fields as None)
- Error spans (with error.type and error.message attributes)
- Dropped spans (with drop_reason attribute)
- READ spans with scores data (for retrieval debugger)

### Ingest Tests (`test_api_ingest.py`)

- Valid OTLP JSON payload gets parsed and stored in SQLite
- Non-MemoryLens spans (without `memorylens.operation` attribute) are silently ignored
- Malformed payloads return 400
- Empty payload returns 200 (no-op)

### Query Extension Tests (`test_query_extended.py`)

- Full-text search (`q` parameter) matches input_content and output_content
- Offset/limit pagination returns correct slices
- Total count is correct regardless of limit
- All existing filter parameters still work

### No Browser Tests

htmx interactions are server-driven — testing the API responses covers the behavior. Visual testing is manual for Phase 2.
