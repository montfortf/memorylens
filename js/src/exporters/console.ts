import { ExportResult } from '../types';
import type { SpanExporter, MemorySpan } from '../types';

export class ConsoleExporter implements SpanExporter {
  async export(spans: MemorySpan[]): Promise<ExportResult> {
    for (const span of spans) {
      console.log(
        JSON.stringify(
          {
            spanId: span.spanId,
            traceId: span.traceId,
            parentSpanId: span.parentSpanId,
            operation: span.operation,
            status: span.status,
            startTime: span.startTime,
            endTime: span.endTime,
            durationMs: span.durationMs,
            agentId: span.agentId,
            sessionId: span.sessionId,
            userId: span.userId,
            inputContent: span.inputContent,
            outputContent: span.outputContent,
            attributes: span.attributes,
          },
          null,
          2,
        ),
      );
    }
    return ExportResult.SUCCESS;
  }

  async shutdown(): Promise<void> {}
}
