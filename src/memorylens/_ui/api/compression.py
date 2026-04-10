from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse


def _parse_attributes(span: dict[str, Any]) -> dict[str, Any]:
    attrs = span.get("attributes", "{}")
    if isinstance(attrs, str):
        return json.loads(attrs)
    return attrs


def _operation_badge_class(operation: str) -> str:
    return {
        "memory.write": "badge-write",
        "memory.read": "badge-read",
        "memory.compress": "badge-compress",
        "memory.update": "badge-update",
    }.get(operation, "badge-write")


def create_compression_routes(app: FastAPI) -> None:
    templates = app.state.templates
    exporter = app.state.exporter

    @app.get("/traces/{trace_id}/compression", response_class=HTMLResponse)
    async def compression_audit_page(request: Request, trace_id: str):
        rows, _ = exporter.query_extended(trace_id=trace_id)
        if not rows:
            return HTMLResponse("<h2>Trace not found</h2>", status_code=404)
        span = rows[0]
        if span.get("operation") != "memory.compress":
            return HTMLResponse(
                "<h2>Compression audit is only available for COMPRESS operations</h2>",
                status_code=404,
            )
        span["_attrs"] = _parse_attributes(span)
        span["_badge"] = _operation_badge_class(span.get("operation", ""))

        # Check if audit exists
        audit_data = exporter.get_audit(span["span_id"])
        audit = None
        if audit_data:
            sentences = audit_data.get("sentences", "[]")
            if isinstance(sentences, str):
                sentences = json.loads(sentences)
            audit = {
                **audit_data,
                "sentences": sentences,
            }

        return templates.TemplateResponse(
            request,
            "compression_audit.html",
            {
                "span": span,
                "audit": audit,
                "active_nav": "traces",
            },
        )

    @app.post("/api/traces/{trace_id}/audit")
    async def run_audit(
        request: Request,
        trace_id: str,
        scorer: str = Query("mock"),
    ):
        rows, _ = exporter.query_extended(trace_id=trace_id)
        if not rows:
            return HTMLResponse("Trace not found", status_code=404)
        span = rows[0]
        if span.get("operation") != "memory.compress":
            return HTMLResponse("Not a COMPRESS span", status_code=400)

        try:
            from memorylens._audit.analyzer import CompressionAnalyzer
            from memorylens._audit.scorer import create_scorer

            scorer_backend = create_scorer(scorer)
            analyzer = CompressionAnalyzer(scorer_backend)
            audit = analyzer.analyze(
                span["span_id"],
                span.get("input_content", "") or "",
                span.get("output_content", "") or "",
            )
            exporter.save_audit(audit)
        except ImportError:
            return HTMLResponse(
                "Audit dependencies not found. Install with: pip install memorylens[audit]",
                status_code=500,
            )

        return RedirectResponse(url=f"/traces/{trace_id}/compression", status_code=303)
