import type { MemorySpan, SpanProcessor, SpanExporter } from './types';

export class SimpleSpanProcessor implements SpanProcessor {
  private exporter: SpanExporter;

  constructor(exporter: SpanExporter) {
    this.exporter = exporter;
  }

  onStart(_span: MemorySpan): void {}

  onEnd(span: MemorySpan): void {
    this.exporter.export([span]);
  }

  async shutdown(): Promise<void> {
    await this.exporter.shutdown();
  }

  async forceFlush(_timeoutMs?: number): Promise<boolean> {
    return true;
  }
}

export class BatchSpanProcessor implements SpanProcessor {
  private exporter: SpanExporter;
  private queue: MemorySpan[] = [];
  private maxBatchSize: number;
  private scheduleDelayMs: number;
  private maxQueueSize: number;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private isShutdown = false;

  constructor(
    exporter: SpanExporter,
    options?: {
      maxBatchSize?: number;
      scheduleDelayMs?: number;
      maxQueueSize?: number;
    },
  ) {
    this.exporter = exporter;
    this.maxBatchSize = options?.maxBatchSize ?? 512;
    this.scheduleDelayMs = options?.scheduleDelayMs ?? 5000;
    this.maxQueueSize = options?.maxQueueSize ?? 2048;
    this.scheduleFlush();
  }

  onStart(_span: MemorySpan): void {}

  onEnd(span: MemorySpan): void {
    if (this.isShutdown) return;
    if (this.queue.length < this.maxQueueSize) {
      this.queue.push(span);
    }
    if (this.queue.length >= this.maxBatchSize) {
      this.flush();
    }
  }

  async shutdown(): Promise<void> {
    this.isShutdown = true;
    if (this.timer) clearTimeout(this.timer);
    await this.flush();
    await this.exporter.shutdown();
  }

  async forceFlush(_timeoutMs?: number): Promise<boolean> {
    await this.flush();
    return true;
  }

  private async flush(): Promise<void> {
    if (this.queue.length === 0) return;
    const batch = this.queue.splice(0, this.maxBatchSize);
    await this.exporter.export(batch);
  }

  private scheduleFlush(): void {
    this.timer = setTimeout(async () => {
      await this.flush();
      if (!this.isShutdown) this.scheduleFlush();
    }, this.scheduleDelayMs);
    // Don't block Node process exit
    if (this.timer && typeof this.timer === 'object' && 'unref' in this.timer) {
      (this.timer as NodeJS.Timeout).unref();
    }
  }
}
