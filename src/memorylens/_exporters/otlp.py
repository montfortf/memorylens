from __future__ import annotations

import json
import os
from typing import Any

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import SpanContext, SpanKind, Status, StatusCode, TraceFlags

from memorylens._core.span import MemorySpan
from memorylens._exporters.base import ExportResult


class _ReadableSpanAdapter:
    """Adapts a MemorySpan to look like an OTel ReadableSpan for the OTLP exporter."""

    def __init__(self, span: MemorySpan, resource: Resource) -> None:
        self._span = span
        self._resource = resource

    @property
    def name(self) -> str:
        return self._span.operation.value

    @property
    def context(self) -> SpanContext:
        trace_id = int(self._span.trace_id[:32].ljust(32, "0"), 16)
        span_id = int(self._span.span_id[:16].ljust(16, "0"), 16)
        return SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )

    @property
    def parent(self):
        return None

    @property
    def start_time(self) -> int:
        return int(self._span.start_time)

    @property
    def end_time(self) -> int:
        return int(self._span.end_time)

    @property
    def attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "memorylens.operation": self._span.operation.value,
            "memorylens.status": self._span.status.value,
        }
        if self._span.agent_id:
            attrs["memorylens.agent_id"] = self._span.agent_id
        if self._span.session_id:
            attrs["memorylens.session_id"] = self._span.session_id
        if self._span.user_id:
            attrs["memorylens.user_id"] = self._span.user_id
        if self._span.input_content:
            attrs["memorylens.input_content"] = self._span.input_content
        if self._span.output_content:
            attrs["memorylens.output_content"] = self._span.output_content
        for k, v in self._span.attributes.items():
            if isinstance(v, (str, int, float, bool)):
                attrs[f"memorylens.{k}"] = v
            else:
                attrs[f"memorylens.{k}"] = json.dumps(v, default=str)
        return attrs

    @property
    def events(self) -> list:
        return []

    @property
    def links(self) -> list:
        return []

    @property
    def status(self) -> Status:
        if self._span.status.value == "error":
            return Status(StatusCode.ERROR, self._span.attributes.get("error.message", ""))
        return Status(StatusCode.OK)

    @property
    def kind(self) -> SpanKind:
        return SpanKind.INTERNAL

    @property
    def resource(self) -> Resource:
        return self._resource

    @property
    def instrumentation_scope(self) -> InstrumentationScope:
        return InstrumentationScope("memorylens", "0.1.0")


class OTLPExporter:
    """Exports MemorySpans via OpenTelemetry OTLP protocol."""

    def __init__(
        self,
        endpoint: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        endpoint = endpoint or os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
        )
        self._resource = Resource.create({"service.name": "memorylens"})
        self._exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)

    def _to_otel_span(self, span: MemorySpan) -> _ReadableSpanAdapter:
        return _ReadableSpanAdapter(span, self._resource)

    def export(self, spans: list[MemorySpan]) -> ExportResult:
        try:
            otel_spans = [self._to_otel_span(s) for s in spans]
            self._exporter.export(otel_spans)  # type: ignore[arg-type]
            return ExportResult.SUCCESS
        except Exception:
            return ExportResult.FAILURE

    def shutdown(self) -> None:
        self._exporter.shutdown()
