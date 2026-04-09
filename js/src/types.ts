export type MemoryOperation = 'memory.write' | 'memory.read' | 'memory.compress' | 'memory.update';

export type SpanStatus = 'ok' | 'error' | 'dropped';

export enum ExportResult {
  SUCCESS = 0,
  FAILURE = 1,
}

export interface MemorySpan {
  spanId: string;
  traceId: string;
  parentSpanId: string | null;
  operation: MemoryOperation;
  status: SpanStatus;
  startTime: number;
  endTime: number;
  durationMs: number;
  agentId: string | null;
  sessionId: string | null;
  userId: string | null;
  inputContent: string | null;
  outputContent: string | null;
  attributes: Record<string, unknown>;
}

export interface SpanProcessor {
  onStart(span: MemorySpan): void;
  onEnd(span: MemorySpan): void;
  shutdown(): Promise<void>;
  forceFlush(timeoutMs?: number): Promise<boolean>;
}

export interface SpanExporter {
  export(spans: MemorySpan[]): Promise<ExportResult>;
  shutdown(): Promise<void>;
}

export interface MemoryContext {
  agentId?: string | null;
  sessionId?: string | null;
  userId?: string | null;
}
