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
        return None

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

    skip_keys = {
        "memorylens.operation", "memorylens.status",
        "memorylens.agent_id", "memorylens.session_id", "memorylens.user_id",
        "memorylens.input_content", "memorylens.output_content",
    }
    extra_attrs: dict[str, Any] = {}
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
