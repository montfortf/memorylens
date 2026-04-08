# MemoryLens Phase 2a — Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a browser-based dashboard for visualizing and debugging agent memory traces — Trace List, Trace Detail with span timeline, and Retrieval Debugger with score visualization.

**Architecture:** FastAPI server with Jinja2 templates and htmx for interactivity, reading from the existing SQLite trace store. TailwindCSS via CDN for styling. Optional OTLP HTTP/JSON ingest endpoint for live trace streaming. Distributed as `pip install memorylens[ui]`.

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, Jinja2, htmx (CDN), TailwindCSS (CDN), SQLite

**Spec:** `docs/superpowers/specs/2026-04-07-memorylens-phase2-web-ui-design.md`

---

## File Map

### New Files (Create)

| File | Responsibility |
|---|---|
| `src/memorylens/_ui/__init__.py` | UI package marker |
| `src/memorylens/_ui/server.py` | FastAPI app factory + uvicorn launcher |
| `src/memorylens/_ui/api/__init__.py` | API package marker |
| `src/memorylens/_ui/api/traces.py` | Page routes + API endpoints for traces |
| `src/memorylens/_ui/api/ingest.py` | OTLP HTTP/JSON receiver |
| `src/memorylens/_ui/templates/base.html` | Layout: nav, Tailwind CDN, htmx |
| `src/memorylens/_ui/templates/traces_list.html` | Trace list page |
| `src/memorylens/_ui/templates/traces_detail.html` | Trace detail with timeline |
| `src/memorylens/_ui/templates/retrieval_debug.html` | Retrieval debugger view |
| `src/memorylens/_ui/templates/partials/trace_table.html` | htmx partial: trace rows |
| `src/memorylens/_ui/templates/partials/span_timeline.html` | htmx partial: span timeline |
| `src/memorylens/_ui/templates/partials/score_chart.html` | htmx partial: score viz |
| `src/memorylens/_ui/static/app.css` | Custom styles |
| `tests/test_ui/__init__.py` | Test package marker |
| `tests/test_ui/test_query_extended.py` | SQLiteExporter extension tests |
| `tests/test_ui/test_api_traces.py` | Trace endpoint tests |
| `tests/test_ui/test_api_ingest.py` | OTLP ingest tests |

### Modified Files

| File | Change |
|---|---|
| `pyproject.toml` | Add `[ui]` optional extra, `httpx` to dev deps |
| `src/memorylens/_exporters/sqlite.py` | Add `query_extended()` method |
| `src/memorylens/cli/main.py` | Add `memorylens ui` command |

---

## Task 1: Package Setup and Dependencies

**Files:**
- Modify: `pyproject.toml`
- Create: `src/memorylens/_ui/__init__.py`, `src/memorylens/_ui/api/__init__.py`, `tests/test_ui/__init__.py`

- [ ] **Step 1: Update pyproject.toml**

Add the `ui` optional extra and `httpx` for testing. In `pyproject.toml`, add to `[project.optional-dependencies]`:

```toml
ui = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "jinja2>=3.1",
]
```

And add `httpx>=0.27` to the `dev` list (needed for FastAPI TestClient):

```toml
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "mypy>=1.10",
    "httpx>=0.27",
]
```

- [ ] **Step 2: Create package directories**

Create empty `__init__.py` files:

```
src/memorylens/_ui/__init__.py
src/memorylens/_ui/api/__init__.py
tests/test_ui/__init__.py
```

- [ ] **Step 3: Create static and template directories**

```bash
mkdir -p src/memorylens/_ui/templates/partials
mkdir -p src/memorylens/_ui/static
```

- [ ] **Step 4: Install new deps and verify**

```bash
uv pip install -e ".[dev,ui]"
uv run pytest tests/ -v --tb=short
```

Expected: all 70 existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/memorylens/_ui/ tests/test_ui/
git commit -m "feat: add UI package structure and [ui] optional extra"
```

---

## Task 2: SQLiteExporter.query_extended()

**Files:**
- Modify: `src/memorylens/_exporters/sqlite.py`
- Create: `tests/test_ui/test_query_extended.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_ui/test_query_extended.py`

```python
from __future__ import annotations

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter


def _make_span(
    span_id: str = "s1",
    trace_id: str = "t1",
    operation: MemoryOperation = MemoryOperation.WRITE,
    status: SpanStatus = SpanStatus.OK,
    agent_id: str = "bot",
    input_content: str = "test input",
    output_content: str = "test output",
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
        session_id="sess-1",
        user_id="user-1",
        input_content=input_content,
        output_content=output_content,
        attributes={"backend": "test"},
    )


def _seed_db(exporter: SQLiteExporter) -> None:
    exporter.export([
        _make_span("s1", "t1", MemoryOperation.WRITE, input_content="user prefers jazz"),
        _make_span("s2", "t2", MemoryOperation.READ, input_content="music preferences"),
        _make_span("s3", "t3", MemoryOperation.WRITE, status=SpanStatus.ERROR, input_content="failed write"),
        _make_span("s4", "t4", MemoryOperation.WRITE, input_content="user likes pizza"),
        _make_span("s5", "t5", MemoryOperation.READ, input_content="food preferences"),
    ])


class TestQueryExtended:
    def test_basic_query(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        _seed_db(exporter)

        rows, total = exporter.query_extended()
        assert total == 5
        assert len(rows) == 5
        exporter.shutdown()

    def test_fulltext_search(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        _seed_db(exporter)

        rows, total = exporter.query_extended(q="jazz")
        assert total == 1
        assert rows[0]["span_id"] == "s1"
        exporter.shutdown()

    def test_fulltext_search_output(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        _seed_db(exporter)

        rows, total = exporter.query_extended(q="test output")
        assert total == 5  # all spans have "test output" as output_content
        exporter.shutdown()

    def test_pagination_offset(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        _seed_db(exporter)

        rows, total = exporter.query_extended(limit=2, offset=0)
        assert len(rows) == 2
        assert total == 5

        rows2, total2 = exporter.query_extended(limit=2, offset=2)
        assert len(rows2) == 2
        assert total2 == 5
        assert rows[0]["span_id"] != rows2[0]["span_id"]
        exporter.shutdown()

    def test_filter_with_search(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        _seed_db(exporter)

        rows, total = exporter.query_extended(operation="memory.read", q="preferences")
        assert total == 2
        for row in rows:
            assert row["operation"] == "memory.read"
        exporter.shutdown()

    def test_total_count_independent_of_limit(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        _seed_db(exporter)

        rows, total = exporter.query_extended(limit=1)
        assert len(rows) == 1
        assert total == 5
        exporter.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_ui/test_query_extended.py -v
```

Expected: FAIL — `AttributeError: 'SQLiteExporter' object has no attribute 'query_extended'`

- [ ] **Step 3: Implement query_extended()**

Add to `src/memorylens/_exporters/sqlite.py`, after the existing `query()` method:

```python
    def query_extended(
        self,
        trace_id: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query spans with full-text search, pagination, and total count."""
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
        if q:
            conditions.append("(input_content LIKE ? OR output_content LIKE ?)")
            q_param = f"%{q}%"
            params.extend([q_param, q_param])

        where = " AND ".join(conditions) if conditions else "1=1"

        # Get total count
        count_sql = f"SELECT COUNT(*) FROM spans WHERE {where}"
        total = self._conn.execute(count_sql, params).fetchone()[0]

        # Get paginated rows
        sql = f"SELECT * FROM spans WHERE {where} ORDER BY start_time DESC LIMIT ? OFFSET ?"
        row_params = params + [limit, offset]
        cursor = self._conn.execute(sql, row_params)
        rows = [dict(row) for row in cursor.fetchall()]

        return rows, total
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_ui/test_query_extended.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: All tests pass (70 existing + 6 new = 76).

- [ ] **Step 6: Commit**

```bash
git add src/memorylens/_exporters/sqlite.py tests/test_ui/test_query_extended.py
git commit -m "feat: add query_extended() with full-text search and pagination"
```

---

## Task 3: FastAPI Server and Base Template

**Files:**
- Create: `src/memorylens/_ui/server.py`
- Create: `src/memorylens/_ui/templates/base.html`
- Create: `src/memorylens/_ui/static/app.css`

- [ ] **Step 1: Create the FastAPI app factory**

File: `src/memorylens/_ui/server.py`

```python
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from memorylens._exporters.sqlite import SQLiteExporter

_DEFAULT_DB = os.path.expanduser("~/.memorylens/traces.db")
_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"


def create_app(db_path: str = _DEFAULT_DB, ingest: bool = False) -> FastAPI:
    """Create the FastAPI app with all routes and middleware."""
    app = FastAPI(title="MemoryLens", docs_url=None, redoc_url=None)

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    exporter = SQLiteExporter(db_path=db_path)

    # Store on app state for access in route handlers
    app.state.templates = templates
    app.state.exporter = exporter

    @app.get("/")
    async def index():
        return RedirectResponse(url="/traces")

    # Register trace routes
    from memorylens._ui.api.traces import create_trace_routes

    create_trace_routes(app)

    # Optionally register ingest routes
    if ingest:
        from memorylens._ui.api.ingest import create_ingest_routes

        create_ingest_routes(app)

    return app


def run(db_path: str = _DEFAULT_DB, port: int = 8000, ingest: bool = False) -> None:
    """Start the uvicorn server."""
    import uvicorn

    app = create_app(db_path=db_path, ingest=ingest)
    print(f"MemoryLens UI running at http://127.0.0.1:{port}")
    if ingest:
        print(f"OTLP ingest accepting traces at http://127.0.0.1:{port}/v1/traces")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
```

- [ ] **Step 2: Create base.html template**

File: `src/memorylens/_ui/templates/base.html`

```html
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}MemoryLens{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        surface: { DEFAULT: '#0f172a', 2: '#1e293b', 3: '#334155' },
                    }
                }
            }
        }
    </script>
    <link rel="stylesheet" href="/static/app.css">
</head>
<body class="bg-surface text-slate-200 min-h-screen">
    <!-- Nav bar -->
    <nav class="flex items-center justify-between px-5 py-3 border-b border-white/[0.08] bg-surface-2">
        <div class="flex items-center gap-3">
            <span class="font-bold text-indigo-400 text-[15px]">◉ MemoryLens</span>
            <span class="px-2.5 py-0.5 rounded bg-indigo-500/15 text-indigo-400 text-[11px] font-semibold">BETA</span>
        </div>
        <div class="flex gap-5 text-xs">
            <a href="/traces" class="{% if active_nav == 'traces' %}text-indigo-400 border-b-2 border-indigo-400 pb-0.5{% else %}text-white/40 hover:text-white/60{% endif %}">Traces</a>
        </div>
    </nav>

    <!-- Content -->
    <main>
        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

- [ ] **Step 3: Create app.css**

File: `src/memorylens/_ui/static/app.css`

```css
/* Operation badge colors */
.badge-write { background: rgba(99,102,241,0.15); color: #a5b4fc; }
.badge-read { background: rgba(16,185,129,0.15); color: #6ee7b7; }
.badge-compress { background: rgba(245,158,11,0.15); color: #fbbf24; }
.badge-update { background: rgba(168,85,247,0.15); color: #c4b5fd; }

/* Status colors */
.status-ok { color: #4ade80; }
.status-error { color: #f87171; }
.status-dropped { color: #facc15; }

/* Error row tint */
.row-error { background: rgba(239,68,68,0.03); }
.row-error:hover { background: rgba(239,68,68,0.06) !important; }

/* Score bars */
.score-bar-returned { background: linear-gradient(90deg, rgba(16,185,129,0.3), rgba(16,185,129,0.5)); }
.score-bar-filtered { background: linear-gradient(90deg, rgba(239,68,68,0.15), rgba(239,68,68,0.25)); }

/* Threshold line */
.threshold-line { border-left: 2px dashed rgba(251,191,36,0.4); }
```

- [ ] **Step 4: Commit**

```bash
git add src/memorylens/_ui/server.py src/memorylens/_ui/templates/base.html src/memorylens/_ui/static/app.css
git commit -m "feat: add FastAPI server factory and base template with Tailwind/htmx"
```

---

## Task 4: Trace List View (Page + Partial)

**Files:**
- Create: `src/memorylens/_ui/api/traces.py`
- Create: `src/memorylens/_ui/templates/traces_list.html`
- Create: `src/memorylens/_ui/templates/partials/trace_table.html`
- Create: `tests/test_ui/test_api_traces.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_ui/test_api_traces.py`

```python
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter
from memorylens._ui.server import create_app


def _make_span(
    span_id: str = "s1",
    trace_id: str = "t1",
    operation: MemoryOperation = MemoryOperation.WRITE,
    status: SpanStatus = SpanStatus.OK,
    input_content: str = "test input",
    output_content: str = "test output",
    attributes: dict | None = None,
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
        agent_id="bot",
        session_id="sess-1",
        user_id="user-1",
        input_content=input_content,
        output_content=output_content,
        attributes=attributes or {"backend": "test"},
    )


def _create_seeded_client(tmp_path) -> TestClient:
    db_path = str(tmp_path / "test.db")
    exporter = SQLiteExporter(db_path=db_path)
    exporter.export([
        _make_span("s1", "t1", MemoryOperation.WRITE),
        _make_span("s2", "t2", MemoryOperation.READ, attributes={
            "backend": "pinecone", "query": "music prefs",
            "scores": [0.92, 0.87, 0.65], "threshold": 0.7,
            "top_k": 5, "results_count": 2,
        }),
        _make_span("s3", "t3", MemoryOperation.WRITE, status=SpanStatus.ERROR),
    ])
    exporter.shutdown()
    app = create_app(db_path=db_path)
    return TestClient(app)


class TestTraceListPage:
    def test_traces_page_returns_html(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "MemoryLens" in resp.text

    def test_traces_page_contains_spans(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces")
        assert "s1" in resp.text or "t1" in resp.text

    def test_index_redirects_to_traces(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == "/traces"


class TestTraceListAPI:
    def test_api_traces_returns_partial(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/api/traces", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        # Should NOT contain the full page layout (no <nav>)
        assert "<nav" not in resp.text

    def test_api_traces_filter_operation(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/api/traces?operation=memory.read", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "memory.read" in resp.text

    def test_api_traces_filter_status(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/api/traces?status=error", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "error" in resp.text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_ui/test_api_traces.py -v
```

Expected: FAIL — `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Create trace routes**

File: `src/memorylens/_ui/api/traces.py`

```python
from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse


def _operation_badge_class(operation: str) -> str:
    return {
        "memory.write": "badge-write",
        "memory.read": "badge-read",
        "memory.compress": "badge-compress",
        "memory.update": "badge-update",
    }.get(operation, "badge-write")


def _parse_attributes(span: dict[str, Any]) -> dict[str, Any]:
    attrs = span.get("attributes", "{}")
    if isinstance(attrs, str):
        return json.loads(attrs)
    return attrs


def create_trace_routes(app: FastAPI) -> None:
    templates = app.state.templates
    exporter = app.state.exporter

    @app.get("/traces", response_class=HTMLResponse)
    async def traces_list_page(request: Request):
        rows, total = exporter.query_extended(limit=50, offset=0)
        for row in rows:
            row["_attrs"] = _parse_attributes(row)
            row["_badge"] = _operation_badge_class(row.get("operation", ""))
        return templates.TemplateResponse("traces_list.html", {
            "request": request,
            "spans": rows,
            "total": total,
            "offset": 0,
            "limit": 50,
            "active_nav": "traces",
            "filters": {},
        })

    @app.get("/api/traces", response_class=HTMLResponse)
    async def traces_list_api(
        request: Request,
        operation: str | None = Query(None),
        status: str | None = Query(None),
        agent_id: str | None = Query(None, alias="agent_id"),
        session_id: str | None = Query(None, alias="session_id"),
        q: str | None = Query(None),
        limit: int = Query(50),
        offset: int = Query(0),
    ):
        rows, total = exporter.query_extended(
            operation=operation, status=status, agent_id=agent_id,
            session_id=session_id, q=q, limit=limit, offset=offset,
        )
        for row in rows:
            row["_attrs"] = _parse_attributes(row)
            row["_badge"] = _operation_badge_class(row.get("operation", ""))
        return templates.TemplateResponse("partials/trace_table.html", {
            "request": request,
            "spans": rows,
            "total": total,
            "offset": offset,
            "limit": limit,
            "filters": {
                "operation": operation or "",
                "status": status or "",
                "agent_id": agent_id or "",
                "session_id": session_id or "",
                "q": q or "",
            },
        })

    @app.get("/traces/{trace_id}", response_class=HTMLResponse)
    async def traces_detail_page(request: Request, trace_id: str):
        rows, _ = exporter.query_extended(trace_id=trace_id)
        if not rows:
            return HTMLResponse("<h2>Trace not found</h2>", status_code=404)
        span = rows[0]
        span["_attrs"] = _parse_attributes(span)
        span["_badge"] = _operation_badge_class(span.get("operation", ""))
        return templates.TemplateResponse("traces_detail.html", {
            "request": request,
            "span": span,
            "active_nav": "traces",
        })

    @app.get("/traces/{trace_id}/retrieval", response_class=HTMLResponse)
    async def retrieval_debug_page(request: Request, trace_id: str):
        rows, _ = exporter.query_extended(trace_id=trace_id)
        if not rows:
            return HTMLResponse("<h2>Trace not found</h2>", status_code=404)
        span = rows[0]
        if span.get("operation") != "memory.read":
            return HTMLResponse("<h2>Retrieval debugger is only available for READ operations</h2>", status_code=404)
        span["_attrs"] = _parse_attributes(span)
        span["_badge"] = _operation_badge_class(span.get("operation", ""))
        return templates.TemplateResponse("retrieval_debug.html", {
            "request": request,
            "span": span,
            "active_nav": "retrieval",
        })
```

- [ ] **Step 4: Create traces_list.html**

File: `src/memorylens/_ui/templates/traces_list.html`

```html
{% extends "base.html" %}
{% block title %}Traces — MemoryLens{% endblock %}
{% block content %}
<div class="px-5 py-3 border-b border-white/[0.06] flex gap-2 flex-wrap items-center">
    <input type="text" name="q" placeholder="Search content..."
        class="px-3 py-1.5 rounded-md border border-white/[0.12] bg-white/[0.05] text-slate-200 text-xs w-48 outline-none focus:border-indigo-400/50"
        hx-get="/api/traces" hx-trigger="keyup changed delay:300ms" hx-target="#trace-table" hx-include="[name]">
    <select name="operation"
        class="px-2.5 py-1.5 rounded-md border border-white/[0.12] bg-white/[0.05] text-slate-200 text-xs"
        hx-get="/api/traces" hx-trigger="change" hx-target="#trace-table" hx-include="[name]">
        <option value="">All Operations</option>
        <option value="memory.write">memory.write</option>
        <option value="memory.read">memory.read</option>
        <option value="memory.compress">memory.compress</option>
        <option value="memory.update">memory.update</option>
    </select>
    <select name="status"
        class="px-2.5 py-1.5 rounded-md border border-white/[0.12] bg-white/[0.05] text-slate-200 text-xs"
        hx-get="/api/traces" hx-trigger="change" hx-target="#trace-table" hx-include="[name]">
        <option value="">All Statuses</option>
        <option value="ok">ok</option>
        <option value="error">error</option>
        <option value="dropped">dropped</option>
    </select>
    <input type="text" name="agent_id" placeholder="Agent ID"
        class="px-3 py-1.5 rounded-md border border-white/[0.12] bg-white/[0.05] text-slate-200 text-xs w-28 outline-none"
        hx-get="/api/traces" hx-trigger="keyup changed delay:300ms" hx-target="#trace-table" hx-include="[name]">
    <div class="ml-auto text-[11px] text-white/30">{{ total }} traces</div>
</div>

<div id="trace-table">
    {% include "partials/trace_table.html" %}
</div>
{% endblock %}
```

- [ ] **Step 5: Create trace_table.html partial**

File: `src/memorylens/_ui/templates/partials/trace_table.html`

```html
<div class="overflow-x-auto">
<table class="w-full border-collapse">
    <thead>
        <tr class="border-b border-white/[0.08] text-left text-[11px] uppercase tracking-wider text-white/35">
            <th class="px-5 py-2.5">Trace ID</th>
            <th class="px-3 py-2.5">Operation</th>
            <th class="px-3 py-2.5">Status</th>
            <th class="px-3 py-2.5">Duration</th>
            <th class="px-3 py-2.5">Agent</th>
            <th class="px-3 py-2.5">Session</th>
            <th class="px-3 py-2.5">Content</th>
        </tr>
    </thead>
    <tbody>
    {% for span in spans %}
        <tr class="border-b border-white/[0.04] cursor-pointer hover:bg-white/[0.03] {% if span.status == 'error' %}row-error{% endif %}"
            onclick="window.location='/traces/{{ span.trace_id }}'">
            <td class="px-5 py-2.5 font-mono text-xs text-indigo-400">{{ span.trace_id[:12] }}</td>
            <td class="px-3 py-2.5"><span class="px-2 py-0.5 rounded text-[11px] {{ span._badge }}">{{ span.operation }}</span></td>
            <td class="px-3 py-2.5 text-xs status-{{ span.status }}">● {{ span.status }}</td>
            <td class="px-3 py-2.5 font-mono text-xs">{{ "%.1f"|format(span.duration_ms) }}ms</td>
            <td class="px-3 py-2.5 text-xs">{{ span.agent_id or '-' }}</td>
            <td class="px-3 py-2.5 font-mono text-[11px] text-white/40">{{ span.session_id or '-' }}</td>
            <td class="px-3 py-2.5 text-xs text-white/50 max-w-[200px] overflow-hidden text-ellipsis whitespace-nowrap">{{ (span.input_content or '')[:60] }}</td>
        </tr>
    {% endfor %}
    </tbody>
</table>
</div>
<div class="flex justify-between items-center px-5 py-2.5 border-t border-white/[0.06] text-[11px] text-white/30">
    <span>Showing {{ offset + 1 }}-{{ [offset + limit, total]|min }} of {{ total }}</span>
    <div class="flex gap-2">
        {% if offset > 0 %}
        <span class="px-2.5 py-1 rounded bg-white/[0.05] cursor-pointer"
              hx-get="/api/traces?offset={{ offset - limit }}&limit={{ limit }}" hx-target="#trace-table" hx-include="[name]">← Prev</span>
        {% endif %}
        {% if offset + limit < total %}
        <span class="px-2.5 py-1 rounded bg-indigo-500/20 text-indigo-400 cursor-pointer"
              hx-get="/api/traces?offset={{ offset + limit }}&limit={{ limit }}" hx-target="#trace-table" hx-include="[name]">Next →</span>
        {% endif %}
    </div>
</div>
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/test_ui/test_api_traces.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/memorylens/_ui/api/traces.py src/memorylens/_ui/templates/traces_list.html src/memorylens/_ui/templates/partials/trace_table.html tests/test_ui/test_api_traces.py
git commit -m "feat: add trace list view with filtering, search, and pagination"
```

---

## Task 5: Trace Detail View

**Files:**
- Create: `src/memorylens/_ui/templates/traces_detail.html`
- Create: `src/memorylens/_ui/templates/partials/span_timeline.html`

- [ ] **Step 1: Add detail page tests to test_api_traces.py**

Append to `tests/test_ui/test_api_traces.py`:

```python
class TestTraceDetailPage:
    def test_detail_returns_html(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t1")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "memory.write" in resp.text

    def test_detail_shows_attributes(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t1")
        assert "backend" in resp.text
        assert "test" in resp.text

    def test_detail_not_found(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/nonexistent")
        assert resp.status_code == 404

    def test_detail_error_span(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t3")
        assert resp.status_code == 200
        assert "error" in resp.text
```

- [ ] **Step 2: Create traces_detail.html**

File: `src/memorylens/_ui/templates/traces_detail.html`

```html
{% extends "base.html" %}
{% block title %}Trace {{ span.trace_id[:12] }} — MemoryLens{% endblock %}
{% block content %}
<div class="px-6 pt-4">
    <div class="text-[11px] text-white/30 mb-2">
        <a href="/traces" class="text-indigo-400 hover:text-indigo-300">← Traces</a> / {{ span.trace_id[:12] }}
    </div>
    <div class="flex items-center gap-3 mb-1">
        <h2 class="text-xl font-semibold">Trace {{ span.trace_id[:12] }}</h2>
        <span class="px-2 py-0.5 rounded text-[11px] {{ span._badge }}">{{ span.operation }}</span>
        <span class="text-xs status-{{ span.status }}">● {{ span.status }}</span>
    </div>
    <div class="text-xs text-white/35">{{ span.agent_id or '-' }} · {{ span.session_id or '-' }} · {{ "%.1f"|format(span.duration_ms) }}ms</div>
</div>

<div class="grid grid-cols-[1fr_340px] gap-0 px-6 py-4">
    <!-- Left: Timeline + Content -->
    <div class="pr-5 border-r border-white/[0.06]">
        {% include "partials/span_timeline.html" %}

        {% if span.input_content %}
        <div class="mb-4">
            <div class="text-[11px] uppercase tracking-wider text-white/30 mb-1.5">Input Content</div>
            <div class="px-4 py-3 bg-white/[0.03] rounded-md border border-white/[0.06] font-mono text-xs leading-relaxed text-slate-300">{{ span.input_content }}</div>
        </div>
        {% endif %}

        {% if span.output_content %}
        <div class="mb-4">
            <div class="text-[11px] uppercase tracking-wider text-white/30 mb-1.5">Output Content</div>
            <div class="px-4 py-3 bg-white/[0.03] rounded-md border border-white/[0.06] font-mono text-xs leading-relaxed text-slate-300">{{ span.output_content }}</div>
        </div>
        {% endif %}

        {% if span.status == 'error' and span._attrs.get('error.message') %}
        <div class="mb-4">
            <div class="text-[11px] uppercase tracking-wider text-red-400 mb-1.5">Error</div>
            <div class="px-4 py-3 bg-red-500/[0.05] rounded-md border border-red-500/20 font-mono text-xs text-red-300">
                {{ span._attrs.get('error.type', 'Error') }}: {{ span._attrs.get('error.message', '') }}
            </div>
        </div>
        {% endif %}
    </div>

    <!-- Right: Attributes -->
    <div class="pl-5">
        <div class="text-[11px] uppercase tracking-wider text-white/30 mb-2.5">Attributes</div>
        <div class="bg-white/[0.03] rounded-md border border-white/[0.06] overflow-hidden">
            <table class="w-full border-collapse text-xs">
                <tr class="border-b border-white/[0.04]"><td class="px-3 py-2 text-white/40">span_id</td><td class="px-3 py-2 font-mono">{{ span.span_id }}</td></tr>
                <tr class="border-b border-white/[0.04]"><td class="px-3 py-2 text-white/40">trace_id</td><td class="px-3 py-2 font-mono">{{ span.trace_id }}</td></tr>
                <tr class="border-b border-white/[0.04]"><td class="px-3 py-2 text-white/40">operation</td><td class="px-3 py-2"><span class="px-2 py-0.5 rounded text-[11px] {{ span._badge }}">{{ span.operation }}</span></td></tr>
                <tr class="border-b border-white/[0.04]"><td class="px-3 py-2 text-white/40">status</td><td class="px-3 py-2 status-{{ span.status }}">{{ span.status }}</td></tr>
                <tr class="border-b border-white/[0.04]"><td class="px-3 py-2 text-white/40">duration</td><td class="px-3 py-2 font-mono">{{ "%.1f"|format(span.duration_ms) }}ms</td></tr>
                <tr class="border-b border-white/[0.04]"><td class="px-3 py-2 text-white/40">agent_id</td><td class="px-3 py-2">{{ span.agent_id or '-' }}</td></tr>
                <tr class="border-b border-white/[0.04]"><td class="px-3 py-2 text-white/40">session_id</td><td class="px-3 py-2 font-mono text-white/50">{{ span.session_id or '-' }}</td></tr>
                <tr class="border-b border-white/[0.04]"><td class="px-3 py-2 text-white/40">user_id</td><td class="px-3 py-2">{{ span.user_id or '-' }}</td></tr>
                {% if span._attrs %}
                <tr class="border-b border-white/[0.04]"><td colspan="2" class="px-3 py-2 text-[11px] uppercase tracking-wider text-white/25 bg-white/[0.02]">Custom Attributes</td></tr>
                {% for key, value in span._attrs.items() %}
                {% if key not in ('error.type', 'error.message') %}
                <tr class="border-b border-white/[0.04]"><td class="px-3 py-2 text-white/40">{{ key }}</td><td class="px-3 py-2 font-mono">{{ value }}</td></tr>
                {% endif %}
                {% endfor %}
                {% endif %}
            </table>
        </div>

        <div class="mt-3 flex gap-2">
            {% if span.operation == 'memory.read' %}
            <a href="/traces/{{ span.trace_id }}/retrieval" class="px-3.5 py-1.5 rounded-md bg-indigo-500/15 border border-indigo-500/30 text-xs text-indigo-400 hover:bg-indigo-500/25">Debug Retrieval →</a>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Create span_timeline.html partial**

File: `src/memorylens/_ui/templates/partials/span_timeline.html`

```html
<div class="mb-5">
    <div class="text-[11px] uppercase tracking-wider text-white/30 mb-2.5">Span Timeline</div>
    <div class="bg-white/[0.03] rounded-md border border-white/[0.06] p-4">
        <div class="flex justify-between text-[10px] text-white/25 mb-2">
            <span>0ms</span>
            <span>{{ "%.0f"|format(span.duration_ms / 4) }}ms</span>
            <span>{{ "%.0f"|format(span.duration_ms / 2) }}ms</span>
            <span>{{ "%.0f"|format(span.duration_ms * 3 / 4) }}ms</span>
            <span>{{ "%.1f"|format(span.duration_ms) }}ms</span>
        </div>
        <div class="relative h-7 bg-white/[0.02] rounded overflow-hidden">
            <div class="absolute left-0 top-1 h-5 w-full rounded-sm flex items-center pl-2 text-[11px] text-indigo-200
                {% if span.operation == 'memory.write' %}bg-indigo-500/40
                {% elif span.operation == 'memory.read' %}bg-emerald-500/40
                {% elif span.operation == 'memory.compress' %}bg-amber-500/40
                {% else %}bg-purple-500/40{% endif %}">
                {{ span.operation }} — {{ "%.1f"|format(span.duration_ms) }}ms
            </div>
        </div>
    </div>
</div>
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_ui/test_api_traces.py -v
```

Expected: All 10 tests PASS (6 from Task 4 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add src/memorylens/_ui/templates/traces_detail.html src/memorylens/_ui/templates/partials/span_timeline.html tests/test_ui/test_api_traces.py
git commit -m "feat: add trace detail view with span timeline and attribute inspector"
```

---

## Task 6: Retrieval Debugger View

**Files:**
- Create: `src/memorylens/_ui/templates/retrieval_debug.html`
- Create: `src/memorylens/_ui/templates/partials/score_chart.html`

- [ ] **Step 1: Add retrieval debugger tests**

Append to `tests/test_ui/test_api_traces.py`:

```python
class TestRetrievalDebugger:
    def test_retrieval_page_returns_html(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t2/retrieval")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Retrieval" in resp.text

    def test_retrieval_shows_scores(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t2/retrieval")
        assert "0.92" in resp.text
        assert "0.87" in resp.text

    def test_retrieval_shows_threshold(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t2/retrieval")
        assert "0.7" in resp.text

    def test_retrieval_404_for_write_span(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t1/retrieval")
        assert resp.status_code == 404

    def test_retrieval_404_for_missing_trace(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/nonexistent/retrieval")
        assert resp.status_code == 404
```

- [ ] **Step 2: Create retrieval_debug.html**

File: `src/memorylens/_ui/templates/retrieval_debug.html`

```html
{% extends "base.html" %}
{% block title %}Retrieval Debugger — MemoryLens{% endblock %}
{% block content %}
{% set attrs = span._attrs %}
{% set scores = attrs.get('scores', []) %}
{% set threshold = attrs.get('threshold', 0) %}
{% set top_k = attrs.get('top_k', 0) %}
{% set results_count = attrs.get('results_count', 0) %}
{% set query = attrs.get('query', span.input_content or '') %}

<div class="px-6 pt-4">
    <div class="text-[11px] text-white/30 mb-2">
        <a href="/traces" class="text-indigo-400 hover:text-indigo-300">← Traces</a>
        / <a href="/traces/{{ span.trace_id }}" class="text-indigo-400 hover:text-indigo-300">{{ span.trace_id[:12] }}</a>
        / Retrieval Debugger
    </div>
    <div class="flex items-center gap-3 mb-1">
        <h2 class="text-xl font-semibold">Retrieval Debugger</h2>
        <span class="px-2 py-0.5 rounded text-[11px] {{ span._badge }}">{{ span.operation }}</span>
        <span class="text-xs status-{{ span.status }}">● {{ span.status }}</span>
    </div>
    <div class="text-xs text-white/35">{{ span.agent_id or '-' }} · {{ span.session_id or '-' }} · {{ "%.1f"|format(span.duration_ms) }}ms</div>
</div>

<div class="px-6 py-4">
    <!-- Query + Parameters -->
    <div class="grid grid-cols-2 gap-4 mb-5">
        <div>
            <div class="text-[11px] uppercase tracking-wider text-white/30 mb-1.5">Query</div>
            <div class="px-4 py-3 bg-white/[0.03] rounded-md border border-white/[0.06] font-mono text-[13px]">{{ query }}</div>
        </div>
        <div>
            <div class="text-[11px] uppercase tracking-wider text-white/30 mb-1.5">Parameters</div>
            <div class="px-4 py-3 bg-white/[0.03] rounded-md border border-white/[0.06] flex gap-5">
                <div><span class="text-white/40 text-[11px]">backend</span><br><span class="text-[13px]">{{ attrs.get('backend', '-') }}</span></div>
                <div><span class="text-white/40 text-[11px]">top_k</span><br><span class="font-mono text-[13px]">{{ top_k }}</span></div>
                <div><span class="text-white/40 text-[11px]">threshold</span><br><span class="font-mono text-[13px] text-amber-400">{{ threshold }}</span></div>
                <div><span class="text-white/40 text-[11px]">results</span><br><span class="font-mono text-[13px]">{{ results_count }} / {{ top_k }}</span></div>
            </div>
        </div>
    </div>

    <!-- Score Visualization -->
    {% include "partials/score_chart.html" %}

    <!-- Threshold insight -->
    {% set near_misses = [] %}
    {% for score in scores %}
        {% if score < threshold and score >= threshold - 0.10 %}
            {% if near_misses.append(score) %}{% endif %}
        {% endif %}
    {% endfor %}
    {% if near_misses %}
    <div class="bg-amber-500/[0.08] border border-amber-500/20 border-l-[3px] border-l-amber-500 rounded-md px-4 py-3 mb-5">
        <div class="text-[11px] font-semibold text-amber-400 mb-1">THRESHOLD INSIGHT</div>
        <div class="text-xs text-white/60">
            {{ near_misses|length }} candidate(s) scored within 0.10 of the <strong class="text-amber-400">{{ threshold }}</strong> threshold.
            If relevant memories are being filtered out, consider lowering the threshold or improving query specificity.
        </div>
    </div>
    {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 3: Create score_chart.html partial**

File: `src/memorylens/_ui/templates/partials/score_chart.html`

```html
<div class="mb-5">
    <div class="text-[11px] uppercase tracking-wider text-white/30 mb-2.5">Similarity Scores</div>
    <div class="bg-white/[0.03] rounded-md border border-white/[0.06] p-5">
        {% if threshold %}
        <div class="flex items-center gap-2 mb-3">
            <div class="w-3 border-t-2 border-dashed border-amber-400"></div>
            <span class="text-[10px] text-amber-400">Threshold: {{ threshold }}</span>
        </div>
        {% endif %}

        <div class="flex flex-col gap-2">
        {% for score in scores %}
            {% set pct = (score * 100)|int %}
            {% set threshold_pct = (threshold * 100)|int if threshold else 0 %}
            {% set above = score >= threshold if threshold else true %}
            <div class="flex items-center gap-3 {% if not above %}opacity-60{% endif %}">
                <div class="w-6 text-center text-[11px] text-white/30">#{{ loop.index }}</div>
                <div class="flex-1 relative h-7 bg-white/[0.02] rounded overflow-hidden">
                    <div class="absolute left-0 top-0 h-full rounded-sm flex items-center pl-2.5 text-[11px]
                        {% if above %}score-bar-returned text-emerald-200{% else %}score-bar-filtered text-red-300{% endif %}"
                        style="width:{{ pct }}%">
                    </div>
                    {% if threshold_pct > 0 %}
                    <div class="threshold-line absolute top-0 h-full" style="left:{{ threshold_pct }}%"></div>
                    {% endif %}
                </div>
                <div class="w-12 text-right font-mono text-[13px] {% if above %}text-emerald-400 font-semibold{% else %}text-red-400{% endif %}">{{ "%.2f"|format(score) }}</div>
                <div class="w-16">
                    {% if above %}
                    <span class="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 text-[10px]">RETURNED</span>
                    {% else %}
                    <span class="px-2 py-0.5 rounded bg-red-500/10 text-red-400 text-[10px] border border-red-500/20">FILTERED</span>
                    {% endif %}
                </div>
            </div>
        {% endfor %}
        </div>
    </div>
</div>
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_ui/test_api_traces.py -v
```

Expected: All 15 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memorylens/_ui/templates/retrieval_debug.html src/memorylens/_ui/templates/partials/score_chart.html tests/test_ui/test_api_traces.py
git commit -m "feat: add retrieval debugger with score visualization and threshold insights"
```

---

## Task 7: OTLP Ingest Endpoint

**Files:**
- Create: `src/memorylens/_ui/api/ingest.py`
- Create: `tests/test_ui/test_api_ingest.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_ui/test_api_ingest.py`

```python
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from memorylens._exporters.sqlite import SQLiteExporter
from memorylens._ui.server import create_app


def _create_ingest_client(tmp_path) -> tuple[TestClient, str]:
    db_path = str(tmp_path / "ingest.db")
    app = create_app(db_path=db_path, ingest=True)
    return TestClient(app), db_path


def _make_otlp_payload(
    operation: str = "memory.write",
    status: str = "ok",
    agent_id: str = "bot",
    span_id: str = "abc123",
    trace_id: str = "def456",
) -> dict:
    """Create a minimal OTLP HTTP/JSON payload."""
    return {
        "resourceSpans": [{
            "resource": {"attributes": []},
            "scopeSpans": [{
                "scope": {"name": "memorylens", "version": "0.1.0"},
                "spans": [{
                    "traceId": trace_id,
                    "spanId": span_id,
                    "name": operation,
                    "kind": 1,
                    "startTimeUnixNano": "1000000000000",
                    "endTimeUnixNano": "1000012000000",
                    "attributes": [
                        {"key": "memorylens.operation", "value": {"stringValue": operation}},
                        {"key": "memorylens.status", "value": {"stringValue": status}},
                        {"key": "memorylens.agent_id", "value": {"stringValue": agent_id}},
                        {"key": "memorylens.session_id", "value": {"stringValue": "sess-1"}},
                        {"key": "memorylens.user_id", "value": {"stringValue": "user-1"}},
                        {"key": "memorylens.input_content", "value": {"stringValue": "test data"}},
                        {"key": "memorylens.backend", "value": {"stringValue": "mem0"}},
                    ],
                    "status": {"code": 1},
                }],
            }],
        }],
    }


class TestOTLPIngest:
    def test_ingest_valid_payload(self, tmp_path):
        client, db_path = _create_ingest_client(tmp_path)
        payload = _make_otlp_payload()
        resp = client.post("/v1/traces", json=payload)
        assert resp.status_code == 200

        exporter = SQLiteExporter(db_path=db_path)
        rows = exporter.query(limit=10)
        assert len(rows) == 1
        assert rows[0]["operation"] == "memory.write"
        assert rows[0]["agent_id"] == "bot"
        exporter.shutdown()

    def test_ingest_ignores_non_memorylens_spans(self, tmp_path):
        client, db_path = _create_ingest_client(tmp_path)
        payload = {
            "resourceSpans": [{
                "resource": {"attributes": []},
                "scopeSpans": [{
                    "scope": {"name": "other"},
                    "spans": [{
                        "traceId": "t1",
                        "spanId": "s1",
                        "name": "http.request",
                        "kind": 1,
                        "startTimeUnixNano": "1000",
                        "endTimeUnixNano": "2000",
                        "attributes": [
                            {"key": "http.method", "value": {"stringValue": "GET"}},
                        ],
                        "status": {"code": 1},
                    }],
                }],
            }],
        }
        resp = client.post("/v1/traces", json=payload)
        assert resp.status_code == 200

        exporter = SQLiteExporter(db_path=db_path)
        rows = exporter.query(limit=10)
        assert len(rows) == 0
        exporter.shutdown()

    def test_ingest_empty_payload(self, tmp_path):
        client, _ = _create_ingest_client(tmp_path)
        resp = client.post("/v1/traces", json={"resourceSpans": []})
        assert resp.status_code == 200

    def test_ingest_malformed_payload(self, tmp_path):
        client, _ = _create_ingest_client(tmp_path)
        resp = client.post("/v1/traces", json={"bad": "data"})
        assert resp.status_code == 400

    def test_ingest_not_available_without_flag(self, tmp_path):
        db_path = str(tmp_path / "noingest.db")
        app = create_app(db_path=db_path, ingest=False)
        client = TestClient(app)
        resp = client.post("/v1/traces", json={})
        assert resp.status_code == 404 or resp.status_code == 405
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_ui/test_api_ingest.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement the ingest handler**

File: `src/memorylens/_ui/api/ingest.py`

```python
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan


def _extract_attr(attributes: list[dict], key: str) -> str | None:
    """Extract a string attribute value from OTLP attribute list."""
    for attr in attributes:
        if attr.get("key") == key:
            value = attr.get("value", {})
            return value.get("stringValue") or value.get("intValue") or value.get("doubleValue")
    return None


def _otlp_span_to_memory_span(otel_span: dict[str, Any]) -> MemorySpan | None:
    """Convert an OTLP JSON span to a MemorySpan. Returns None if not a MemoryLens span."""
    attributes = otel_span.get("attributes", [])

    operation_str = _extract_attr(attributes, "memorylens.operation")
    if not operation_str:
        return None  # Not a MemoryLens span

    status_str = _extract_attr(attributes, "memorylens.status") or "ok"

    try:
        operation = MemoryOperation(operation_str)
    except ValueError:
        return None

    try:
        status = SpanStatus(status_str)
    except ValueError:
        status = SpanStatus.OK

    start_ns = int(otel_span.get("startTimeUnixNano", "0"))
    end_ns = int(otel_span.get("endTimeUnixNano", "0"))
    duration_ms = (end_ns - start_ns) / 1_000_000

    # Collect remaining memorylens.* attributes
    extra_attrs: dict[str, Any] = {}
    skip_keys = {
        "memorylens.operation", "memorylens.status",
        "memorylens.agent_id", "memorylens.session_id", "memorylens.user_id",
        "memorylens.input_content", "memorylens.output_content",
    }
    for attr in attributes:
        key = attr.get("key", "")
        if key.startswith("memorylens.") and key not in skip_keys:
            short_key = key[len("memorylens."):]
            value = attr.get("value", {})
            extra_attrs[short_key] = (
                value.get("stringValue")
                or value.get("intValue")
                or value.get("doubleValue")
                or value.get("boolValue")
            )

    return MemorySpan(
        span_id=otel_span.get("spanId", ""),
        trace_id=otel_span.get("traceId", ""),
        parent_span_id=otel_span.get("parentSpanId"),
        operation=operation,
        status=status,
        start_time=float(start_ns),
        end_time=float(end_ns),
        duration_ms=duration_ms,
        agent_id=_extract_attr(attributes, "memorylens.agent_id"),
        session_id=_extract_attr(attributes, "memorylens.session_id"),
        user_id=_extract_attr(attributes, "memorylens.user_id"),
        input_content=_extract_attr(attributes, "memorylens.input_content"),
        output_content=_extract_attr(attributes, "memorylens.output_content"),
        attributes=extra_attrs,
    )


def create_ingest_routes(app: FastAPI) -> None:
    exporter = app.state.exporter

    @app.post("/v1/traces")
    async def ingest_traces(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        resource_spans = body.get("resourceSpans")
        if resource_spans is None:
            return JSONResponse({"error": "Missing resourceSpans"}, status_code=400)

        memory_spans: list[MemorySpan] = []
        for rs in resource_spans:
            for ss in rs.get("scopeSpans", []):
                for otel_span in ss.get("spans", []):
                    ms = _otlp_span_to_memory_span(otel_span)
                    if ms is not None:
                        memory_spans.append(ms)

        if memory_spans:
            exporter.export(memory_spans)

        return JSONResponse({})
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_ui/test_api_ingest.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memorylens/_ui/api/ingest.py tests/test_ui/test_api_ingest.py
git commit -m "feat: add OTLP HTTP/JSON ingest endpoint for live trace streaming"
```

---

## Task 8: CLI `memorylens ui` Command

**Files:**
- Modify: `src/memorylens/cli/main.py`

- [ ] **Step 1: Add the ui command**

Add to `src/memorylens/cli/main.py`, after the existing `init` command:

```python
@app.command()
def ui(
    port: int = typer.Option(8000, help="Port to serve on"),
    db_path: str = typer.Option(
        os.path.expanduser("~/.memorylens/traces.db"), "--db-path", help="SQLite database path"
    ),
    ingest: bool = typer.Option(False, "--ingest", help="Accept OTLP HTTP traces at /v1/traces"),
) -> None:
    """Launch the MemoryLens web dashboard."""
    try:
        from memorylens._ui.server import run as run_ui
    except ImportError:
        typer.echo(
            "UI dependencies not found. Install with: pip install memorylens[ui]",
            err=True,
        )
        raise typer.Exit(1)
    run_ui(db_path=db_path, port=port, ingest=ingest)
```

Also add `import os` at the top of the file if not already present.

- [ ] **Step 2: Test the CLI command is registered**

```bash
uv run memorylens ui --help
```

Expected: Shows help text with `--port`, `--db-path`, `--ingest` options.

- [ ] **Step 3: Commit**

```bash
git add src/memorylens/cli/main.py
git commit -m "feat: add memorylens ui CLI command"
```

---

## Task 9: End-to-End Integration Test

**Files:**
- Create: `tests/test_ui/test_e2e_ui.py`

- [ ] **Step 1: Write end-to-end test**

File: `tests/test_ui/test_e2e_ui.py`

```python
from __future__ import annotations

import memorylens
from memorylens import context, instrument_read, instrument_write
from memorylens._exporters.sqlite import SQLiteExporter
from memorylens._ui.server import create_app
from fastapi.testclient import TestClient


class TestEndToEndUI:
    def test_sdk_writes_ui_reads(self, tmp_path):
        """Full flow: SDK writes traces → UI serves them."""
        db_path = str(tmp_path / "e2e_ui.db")

        memorylens.init(
            service_name="test",
            exporter="sqlite",
            db_path=db_path,
            capture_content=True,
        )

        @instrument_write(backend="test_db")
        def store(content: str) -> str:
            return "stored"

        @instrument_read(backend="test_db")
        def search(query: str) -> list[str]:
            return ["r1", "r2"]

        with context(agent_id="e2e-bot", session_id="e2e-sess"):
            store("user likes jazz")
            search("music preferences")

        memorylens.shutdown()

        # Now start the UI and query
        app = create_app(db_path=db_path)
        client = TestClient(app)

        # Trace list should show both spans
        resp = client.get("/traces")
        assert resp.status_code == 200
        assert "e2e-bot" in resp.text

        # Get traces via API
        resp = client.get("/api/traces", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "memory.write" in resp.text
        assert "memory.read" in resp.text

    def test_ingest_and_view(self, tmp_path):
        """Ingest OTLP traces then view them in UI."""
        db_path = str(tmp_path / "e2e_ingest.db")
        app = create_app(db_path=db_path, ingest=True)
        client = TestClient(app)

        # Send OTLP payload
        payload = {
            "resourceSpans": [{
                "resource": {"attributes": []},
                "scopeSpans": [{
                    "scope": {"name": "memorylens"},
                    "spans": [{
                        "traceId": "e2etrace",
                        "spanId": "e2espan",
                        "name": "memory.write",
                        "kind": 1,
                        "startTimeUnixNano": "1000000000000",
                        "endTimeUnixNano": "1000012000000",
                        "attributes": [
                            {"key": "memorylens.operation", "value": {"stringValue": "memory.write"}},
                            {"key": "memorylens.status", "value": {"stringValue": "ok"}},
                            {"key": "memorylens.agent_id", "value": {"stringValue": "ingest-bot"}},
                            {"key": "memorylens.input_content", "value": {"stringValue": "ingested data"}},
                        ],
                        "status": {"code": 1},
                    }],
                }],
            }],
        }
        resp = client.post("/v1/traces", json=payload)
        assert resp.status_code == 200

        # View in UI
        resp = client.get("/traces")
        assert resp.status_code == 200
        assert "ingest-bot" in resp.text
```

- [ ] **Step 2: Run all tests**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: All tests pass (~95+ total).

- [ ] **Step 3: Run ruff**

```bash
uv run ruff check src/ tests/ --fix
uv run ruff format src/ tests/
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_ui/test_e2e_ui.py
git commit -m "test: add end-to-end UI integration tests"
```

If ruff made changes:
```bash
git add -u
git commit -m "style: format code with ruff"
```

---

## Summary

| Task | Component | Tests |
|------|-----------|-------|
| 1 | Package setup + deps | — |
| 2 | SQLiteExporter.query_extended() | 6 |
| 3 | FastAPI server + base template | — |
| 4 | Trace list view (page + partial) | 6 |
| 5 | Trace detail view | 4 |
| 6 | Retrieval debugger | 5 |
| 7 | OTLP ingest endpoint | 5 |
| 8 | CLI `memorylens ui` command | — |
| 9 | End-to-end integration test | 2 |

**Total: 9 tasks, ~28 new tests, ~17 new files**
