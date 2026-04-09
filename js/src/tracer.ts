import { randomUUID } from 'node:crypto';
import { getCurrentContext } from './context';
import { Sampler } from './sampler';
import type { MemorySpan, MemoryOperation, SpanStatus, SpanProcessor } from './types';

export class MutableSpan {
  readonly traceId: string;
  readonly spanId: string;
  readonly operation: MemoryOperation;
  readonly parentSpanId: string | null;
  status: SpanStatus = 'ok';
  readonly startTime: number;
  endTime: number = 0;
  agentId: string | null;
  sessionId: string | null;
  userId: string | null;
  inputContent: string | null = null;
  outputContent: string | null = null;
  attributes: Record<string, unknown>;

  constructor(options: {
    operation: MemoryOperation;
    parentSpanId?: string | null;
    agentId?: string | null;
    sessionId?: string | null;
    userId?: string | null;
    attributes?: Record<string, unknown>;
  }) {
    this.traceId = randomUUID().replace(/-/g, '');
    this.spanId = randomUUID().replace(/-/g, '').substring(0, 16);
    this.operation = options.operation;
    this.parentSpanId = options.parentSpanId ?? null;
    // Context values: explicit options override, then fall back to AsyncLocalStorage context
    const ctx = getCurrentContext();
    this.agentId = options.agentId !== undefined ? options.agentId : (ctx?.agentId ?? null);
    this.sessionId = options.sessionId !== undefined ? options.sessionId : (ctx?.sessionId ?? null);
    this.userId = options.userId !== undefined ? options.userId : (ctx?.userId ?? null);
    this.attributes = { ...options.attributes };
    this.startTime = Date.now();
  }

  setAttribute(key: string, value: unknown): void {
    this.attributes[key] = value;
  }

  setContent(input?: string | null, output?: string | null): void {
    if (input !== undefined) this.inputContent = input;
    if (output !== undefined) this.outputContent = output;
  }

  setStatus(status: SpanStatus): void {
    this.status = status;
  }

  setError(error: unknown): void {
    this.status = 'error';
    if (error instanceof Error) {
      this.attributes['error.type'] = error.constructor.name;
      this.attributes['error.message'] = error.message;
    } else {
      this.attributes['error.type'] = 'Error';
      this.attributes['error.message'] = String(error);
    }
  }

  end(): MemorySpan {
    this.endTime = Date.now();
    return {
      spanId: this.spanId,
      traceId: this.traceId,
      parentSpanId: this.parentSpanId,
      operation: this.operation,
      status: this.status,
      startTime: this.startTime,
      endTime: this.endTime,
      durationMs: this.endTime - this.startTime,
      agentId: this.agentId,
      sessionId: this.sessionId,
      userId: this.userId,
      inputContent: this.inputContent,
      outputContent: this.outputContent,
      attributes: { ...this.attributes },
    };
  }
}

export class Tracer {
  private name: string;
  private provider: TracerProvider;

  constructor(name: string, provider: TracerProvider) {
    this.name = name;
    this.provider = provider;
  }

  getName(): string {
    return this.name;
  }

  startSpan(operation: MemoryOperation, attributes?: Record<string, unknown>): MutableSpan {
    const ctx = getCurrentContext();
    return new MutableSpan({
      operation,
      agentId: ctx?.agentId ?? null,
      sessionId: ctx?.sessionId ?? null,
      userId: ctx?.userId ?? null,
      attributes,
    });
  }

  endSpan(span: MutableSpan): void {
    const finished = span.end();
    for (const processor of this.provider.processors) {
      processor.onEnd(finished);
    }
  }
}

export class TracerProvider {
  private static instance: TracerProvider | null = null;
  processors: SpanProcessor[] = [];
  sampler: Sampler = new Sampler(1.0);
  serviceName: string = 'memorylens';

  static get(): TracerProvider {
    if (!TracerProvider.instance) {
      TracerProvider.instance = new TracerProvider();
    }
    return TracerProvider.instance;
  }

  static reset(): void {
    if (TracerProvider.instance) {
      // Synchronous cleanup — don't await
      for (const p of TracerProvider.instance.processors) {
        p.shutdown().catch(() => {});
      }
    }
    TracerProvider.instance = null;
  }

  addProcessor(processor: SpanProcessor): void {
    this.processors.push(processor);
  }

  getTracer(name: string): Tracer {
    return new Tracer(name, this);
  }

  async shutdown(): Promise<void> {
    for (const p of this.processors) {
      await p.shutdown();
    }
  }
}
