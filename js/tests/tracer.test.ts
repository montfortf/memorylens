import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { TracerProvider, MutableSpan } from '../src/tracer';
import { runWithContext } from '../src/context';
import { ExportResult } from '../src/types';
import type { SpanExporter, MemorySpan, SpanProcessor } from '../src/types';

class CollectingExporter implements SpanExporter {
  spans: MemorySpan[] = [];
  async export(spans: MemorySpan[]): Promise<ExportResult> {
    this.spans.push(...spans);
    return ExportResult.SUCCESS;
  }
  async shutdown(): Promise<void> {}
}

class CollectingProcessor implements SpanProcessor {
  started: MemorySpan[] = [];
  ended: MemorySpan[] = [];
  onStart(span: MemorySpan): void { this.started.push(span); }
  onEnd(span: MemorySpan): void { this.ended.push(span); }
  async shutdown(): Promise<void> {}
  async forceFlush(): Promise<boolean> { return true; }
}

beforeEach(() => {
  TracerProvider.reset();
});

afterEach(() => {
  TracerProvider.reset();
});

describe('TracerProvider', () => {
  it('is a singleton — get() returns same instance', () => {
    const a = TracerProvider.get();
    const b = TracerProvider.get();
    expect(a).toBe(b);
  });

  it('reset() creates a fresh instance', () => {
    const a = TracerProvider.get();
    TracerProvider.reset();
    const b = TracerProvider.get();
    expect(a).not.toBe(b);
  });

  it('addProcessor adds to processors list', () => {
    const p = TracerProvider.get();
    const proc = new CollectingProcessor();
    p.addProcessor(proc);
    expect(p.processors).toContain(proc);
  });

  it('getTracer returns a Tracer with correct name', () => {
    const p = TracerProvider.get();
    const tracer = p.getTracer('my-lib');
    expect(tracer.getName()).toBe('my-lib');
  });

  it('shutdown calls shutdown on all processors', async () => {
    const p = TracerProvider.get();
    let shutdownCalled = false;
    const mockProc: SpanProcessor = {
      onStart: () => {},
      onEnd: () => {},
      shutdown: async () => { shutdownCalled = true; },
      forceFlush: async () => true,
    };
    p.addProcessor(mockProc);
    await p.shutdown();
    expect(shutdownCalled).toBe(true);
  });
});

describe('MutableSpan', () => {
  it('generates unique spanId and traceId', () => {
    const s1 = new MutableSpan({ operation: 'memory.write' });
    const s2 = new MutableSpan({ operation: 'memory.write' });
    expect(s1.spanId).not.toBe(s2.spanId);
    expect(s1.traceId).not.toBe(s2.traceId);
  });

  it('end() returns a MemorySpan with durationMs', () => {
    const span = new MutableSpan({ operation: 'memory.read' });
    const finished = span.end();
    expect(finished.durationMs).toBeGreaterThanOrEqual(0);
    expect(finished.operation).toBe('memory.read');
    expect(finished.status).toBe('ok');
  });

  it('setAttribute sets a custom attribute', () => {
    const span = new MutableSpan({ operation: 'memory.write' });
    span.setAttribute('backend', 'redis');
    const finished = span.end();
    expect(finished.attributes['backend']).toBe('redis');
  });

  it('setContent sets input and output', () => {
    const span = new MutableSpan({ operation: 'memory.write' });
    span.setContent('hello', 'world');
    const finished = span.end();
    expect(finished.inputContent).toBe('hello');
    expect(finished.outputContent).toBe('world');
  });

  it('setError sets status to error and stores message', () => {
    const span = new MutableSpan({ operation: 'memory.compress' });
    span.setError(new Error('oops'));
    const finished = span.end();
    expect(finished.status).toBe('error');
    expect(finished.attributes['error.message']).toBe('oops');
    expect(finished.attributes['error.type']).toBe('Error');
  });

  it('setError handles non-Error values', () => {
    const span = new MutableSpan({ operation: 'memory.update' });
    span.setError('string error');
    const finished = span.end();
    expect(finished.attributes['error.message']).toBe('string error');
  });

  it('picks up context from AsyncLocalStorage', () => {
    runWithContext({ agentId: 'ctx-agent', sessionId: 'sess99', userId: 'user1' }, () => {
      const span = new MutableSpan({ operation: 'memory.write' });
      expect(span.agentId).toBe('ctx-agent');
      expect(span.sessionId).toBe('sess99');
      expect(span.userId).toBe('user1');
    });
  });
});

describe('Tracer', () => {
  it('startSpan creates a MutableSpan', () => {
    const provider = TracerProvider.get();
    const tracer = provider.getTracer('test');
    const span = tracer.startSpan('memory.read');
    expect(span).toBeInstanceOf(MutableSpan);
    expect(span.operation).toBe('memory.read');
  });

  it('endSpan sends finished span to all processors', () => {
    const provider = TracerProvider.get();
    const proc = new CollectingProcessor();
    provider.addProcessor(proc);

    const tracer = provider.getTracer('test');
    const span = tracer.startSpan('memory.write', { source: 'test' });
    tracer.endSpan(span);

    expect(proc.ended).toHaveLength(1);
    expect(proc.ended[0].operation).toBe('memory.write');
    expect(proc.ended[0].attributes['source']).toBe('test');
  });

  it('startSpan inherits context values', () => {
    const provider = TracerProvider.get();
    const proc = new CollectingProcessor();
    provider.addProcessor(proc);
    const tracer = provider.getTracer('test');

    runWithContext({ agentId: 'mybot', sessionId: 's1' }, () => {
      const span = tracer.startSpan('memory.compress');
      tracer.endSpan(span);
    });

    expect(proc.ended[0].agentId).toBe('mybot');
    expect(proc.ended[0].sessionId).toBe('s1');
  });
});
