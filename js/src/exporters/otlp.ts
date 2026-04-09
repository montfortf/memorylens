import { ExportResult } from '../types';
import type { SpanExporter, MemorySpan } from '../types';

/**
 * OTLP HTTP exporter — maps MemorySpan to OpenTelemetry protobuf-JSON format
 * and ships to the MemoryLens ingest endpoint (or any OTLP-compatible backend).
 */
export class OTLPExporter implements SpanExporter {
  private endpoint: string;

  constructor(options?: { endpoint?: string }) {
    this.endpoint =
      options?.endpoint ??
      process.env['OTEL_EXPORTER_OTLP_ENDPOINT'] ??
      'http://localhost:8000/v1/traces';
  }

  async export(spans: MemorySpan[]): Promise<ExportResult> {
    if (spans.length === 0) return ExportResult.SUCCESS;

    const body = this.buildOTLPPayload(spans);

    try {
      const response = await fetch(this.endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        return ExportResult.FAILURE;
      }
      return ExportResult.SUCCESS;
    } catch {
      return ExportResult.FAILURE;
    }
  }

  async shutdown(): Promise<void> {}

  private buildOTLPPayload(spans: MemorySpan[]): object {
    return {
      resourceSpans: [
        {
          resource: {
            attributes: [
              {
                key: 'service.name',
                value: {
                  stringValue: process.env['OTEL_SERVICE_NAME'] ?? 'memorylens',
                },
              },
            ],
          },
          scopeSpans: [
            {
              scope: { name: 'memorylens', version: '0.1.0' },
              spans: spans.map((span) => this.spanToOTLP(span)),
            },
          ],
        },
      ],
    };
  }

  private spanToOTLP(span: MemorySpan): object {
    const startTimeUnixNano = String(span.startTime * 1_000_000);
    const endTimeUnixNano = String(span.endTime * 1_000_000);

    const attributes: Array<{ key: string; value: { stringValue?: string; intValue?: string } }> =
      [{ key: 'memory.operation', value: { stringValue: span.operation } }];

    if (span.agentId) attributes.push({ key: 'agent.id', value: { stringValue: span.agentId } });
    if (span.sessionId)
      attributes.push({ key: 'session.id', value: { stringValue: span.sessionId } });
    if (span.userId) attributes.push({ key: 'user.id', value: { stringValue: span.userId } });
    if (span.inputContent)
      attributes.push({ key: 'memory.input', value: { stringValue: span.inputContent } });
    if (span.outputContent)
      attributes.push({ key: 'memory.output', value: { stringValue: span.outputContent } });

    for (const [key, val] of Object.entries(span.attributes)) {
      attributes.push({ key, value: { stringValue: String(val) } });
    }

    return {
      traceId: span.traceId,
      spanId: span.spanId,
      parentSpanId: span.parentSpanId ?? undefined,
      name: span.operation,
      kind: 1, // SPAN_KIND_INTERNAL
      startTimeUnixNano,
      endTimeUnixNano,
      attributes,
      status: {
        code: span.status === 'ok' ? 1 : span.status === 'error' ? 2 : 0,
      },
    };
  }
}
