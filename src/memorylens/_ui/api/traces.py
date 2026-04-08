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
        return templates.TemplateResponse(request, "traces_list.html", {
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
        return templates.TemplateResponse(request, "partials/trace_table.html", {
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
        return templates.TemplateResponse(request, "traces_detail.html", {
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
        return templates.TemplateResponse(request, "retrieval_debug.html", {
            "span": span,
            "active_nav": "retrieval",
        })
