import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SimpleSpanProcessor, BatchSpanProcessor } from '../src/processor';
import { ExportResult } from '../src/types';
import type { SpanExporter, MemorySpan } from '../src/types';

function makeSpan(override: Partial<MemorySpan> = {}): MemorySpan {
  return {
    spanId: 'span1',
    traceId: 'trace1',
    parentSpanId: null,
    operation: 'memory.write',
    status: 'ok',
    startTime: Date.now() - 10,
    endTime: Date.now(),
    durationMs: 10,
    agentId: null,
    sessionId: null,
    userId: null,
    inputContent: null,
    outputContent: null,
    attributes: {},
    ...override,
  };
}

class CollectingExporter implements SpanExporter {
  exported: MemorySpan[][] = [];
  shutdownCalled = false;

  async export(spans: MemorySpan[]): Promise<ExportResult> {
    this.exported.push([...spans]);
    return ExportResult.SUCCESS;
  }

  async shutdown(): Promise<void> {
    this.shutdownCalled = true;
  }
}

describe('SimpleSpanProcessor', () => {
  it('calls exporter.export immediately on onEnd', async () => {
    const exp = new CollectingExporter();
    const proc = new SimpleSpanProcessor(exp);
    const span = makeSpan();
    proc.onEnd(span);
    // Give the fire-and-forget a tick
    await new Promise(r => setTimeout(r, 0));
    expect(exp.exported).toHaveLength(1);
    expect(exp.exported[0][0].spanId).toBe('span1');
  });

  it('onStart is a no-op', () => {
    const exp = new CollectingExporter();
    const proc = new SimpleSpanProcessor(exp);
    // Should not throw
    proc.onStart(makeSpan());
    expect(exp.exported).toHaveLength(0);
  });

  it('forceFlush returns true', async () => {
    const exp = new CollectingExporter();
    const proc = new SimpleSpanProcessor(exp);
    expect(await proc.forceFlush()).toBe(true);
  });

  it('shutdown calls exporter shutdown', async () => {
    const exp = new CollectingExporter();
    const proc = new SimpleSpanProcessor(exp);
    await proc.shutdown();
    expect(exp.shutdownCalled).toBe(true);
  });
});

describe('BatchSpanProcessor', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it('queues spans and flushes on forceFlush', async () => {
    const exp = new CollectingExporter();
    const proc = new BatchSpanProcessor(exp, { scheduleDelayMs: 60000, maxBatchSize: 512 });

    proc.onEnd(makeSpan({ spanId: 'a' }));
    proc.onEnd(makeSpan({ spanId: 'b' }));

    expect(exp.exported).toHaveLength(0);

    await proc.forceFlush();
    expect(exp.exported).toHaveLength(1);
    expect(exp.exported[0]).toHaveLength(2);

    await proc.shutdown();
  });

  it('auto-flushes when maxBatchSize is reached', async () => {
    vi.useRealTimers(); // avoid infinite loop with self-rescheduling timer
    const exp = new CollectingExporter();
    const proc = new BatchSpanProcessor(exp, { maxBatchSize: 2, scheduleDelayMs: 60000 });

    proc.onEnd(makeSpan({ spanId: 'x1' }));
    proc.onEnd(makeSpan({ spanId: 'x2' }));

    // flush() is fire-and-forget async — drain the microtask queue
    await new Promise(r => setImmediate(r));
    expect(exp.exported).toHaveLength(1);
    expect(exp.exported[0]).toHaveLength(2);

    await proc.shutdown();
  });

  it('drops spans when maxQueueSize exceeded', async () => {
    const exp = new CollectingExporter();
    const proc = new BatchSpanProcessor(exp, {
      maxQueueSize: 2,
      maxBatchSize: 512,
      scheduleDelayMs: 60000,
    });

    proc.onEnd(makeSpan({ spanId: '1' }));
    proc.onEnd(makeSpan({ spanId: '2' }));
    proc.onEnd(makeSpan({ spanId: '3' })); // should be dropped

    await proc.forceFlush();
    expect(exp.exported[0]).toHaveLength(2);

    await proc.shutdown();
  });

  it('does not accept spans after shutdown', async () => {
    const exp = new CollectingExporter();
    const proc = new BatchSpanProcessor(exp, { scheduleDelayMs: 60000 });
    await proc.shutdown();

    proc.onEnd(makeSpan({ spanId: 'late' }));
    await proc.forceFlush();
    expect(exp.exported.flat()).toHaveLength(0);
  });

  it('forceFlush returns true', async () => {
    const exp = new CollectingExporter();
    const proc = new BatchSpanProcessor(exp, { scheduleDelayMs: 60000 });
    expect(await proc.forceFlush()).toBe(true);
    await proc.shutdown();
  });
});
