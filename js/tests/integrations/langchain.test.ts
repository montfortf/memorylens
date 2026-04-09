import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TracerProvider, Tracer } from '../../src/tracer';
import { ExportResult } from '../../src/types';
import type { MemorySpan, SpanExporter, SpanProcessor } from '../../src/types';
import { SimpleSpanProcessor } from '../../src/processor';

/**
 * The LangChain instrumentor uses require('langchain/memory') which may not be
 * installed in the dev environment.  We therefore test the instrumentation
 * logic directly — i.e. the same pattern the instrumentor applies — without
 * going through the langchain module import.
 */

class CollectingExporter implements SpanExporter {
  spans: MemorySpan[] = [];
  async export(spans: MemorySpan[]): Promise<ExportResult> {
    this.spans.push(...spans);
    return ExportResult.SUCCESS;
  }
  async shutdown(): Promise<void> {}
}

// A stand-in for BaseChatMemory
class FakeMemory {
  async saveContext(..._args: unknown[]): Promise<void> {}
  async loadMemoryVariables(..._args: unknown[]): Promise<Record<string, string>> {
    return { history: 'test' };
  }
}

/** Apply the same monkey-patch the instrumentor would apply */
function patchMemoryClass(
  cls: { prototype: FakeMemory },
  provider: TracerProvider,
): () => void {
  const proto = cls.prototype;
  const origSave = proto.saveContext;
  const origLoad = proto.loadMemoryVariables;

  proto.saveContext = async function (...args: unknown[]) {
    const tracer = provider.getTracer('memorylens.langchain');
    const span = tracer.startSpan('memory.write', { 'langchain.method': 'saveContext' });
    try {
      const result = await origSave.apply(this, args as []);
      tracer.endSpan(span);
      return result;
    } catch (e) {
      span.setError(e);
      tracer.endSpan(span);
      throw e;
    }
  };

  proto.loadMemoryVariables = async function (...args: unknown[]) {
    const tracer = provider.getTracer('memorylens.langchain');
    const span = tracer.startSpan('memory.read', { 'langchain.method': 'loadMemoryVariables' });
    try {
      const result = await origLoad.apply(this, args as []);
      tracer.endSpan(span);
      return result;
    } catch (e) {
      span.setError(e);
      tracer.endSpan(span);
      throw e;
    }
  };

  return () => {
    proto.saveContext = origSave;
    proto.loadMemoryVariables = origLoad;
  };
}

let collector: CollectingExporter;

beforeEach(() => {
  TracerProvider.reset();
  collector = new CollectingExporter();
  TracerProvider.get().addProcessor(new SimpleSpanProcessor(collector));
});

afterEach(() => {
  TracerProvider.reset();
});

describe('LangChain instrumentation pattern', () => {
  it('saveContext creates a memory.write span', async () => {
    const provider = TracerProvider.get();
    const unpatch = patchMemoryClass(FakeMemory as unknown as { prototype: FakeMemory }, provider);

    const mem = new FakeMemory();
    await mem.saveContext({ input: 'hello' }, { output: 'hi' });
    await new Promise(r => setTimeout(r, 0));

    expect(collector.spans.length).toBeGreaterThanOrEqual(1);
    expect(collector.spans[0].operation).toBe('memory.write');
    expect(collector.spans[0].attributes['langchain.method']).toBe('saveContext');

    unpatch();
  });

  it('loadMemoryVariables creates a memory.read span', async () => {
    const provider = TracerProvider.get();
    const unpatch = patchMemoryClass(FakeMemory as unknown as { prototype: FakeMemory }, provider);

    const mem = new FakeMemory();
    await mem.loadMemoryVariables({});
    await new Promise(r => setTimeout(r, 0));

    const readSpans = collector.spans.filter(s => s.operation === 'memory.read');
    expect(readSpans.length).toBeGreaterThanOrEqual(1);
    expect(readSpans[0].attributes['langchain.method']).toBe('loadMemoryVariables');

    unpatch();
  });

  it('unpatch restores original methods — no new spans created', async () => {
    const provider = TracerProvider.get();
    const unpatch = patchMemoryClass(FakeMemory as unknown as { prototype: FakeMemory }, provider);
    unpatch();

    const mem = new FakeMemory();
    await mem.saveContext({}, {});
    await new Promise(r => setTimeout(r, 0));

    expect(collector.spans).toHaveLength(0);
  });

  it('span is ended even when original method throws', async () => {
    const provider = TracerProvider.get();

    class ThrowingMemory extends FakeMemory {
      async saveContext(): Promise<void> {
        throw new Error('storage down');
      }
    }

    const unpatch = patchMemoryClass(ThrowingMemory as unknown as { prototype: FakeMemory }, provider);

    const mem = new ThrowingMemory();
    await expect(mem.saveContext()).rejects.toThrow('storage down');
    await new Promise(r => setTimeout(r, 0));

    expect(collector.spans).toHaveLength(1);
    expect(collector.spans[0].status).toBe('error');
    expect(collector.spans[0].attributes['error.message']).toBe('storage down');

    unpatch();
  });
});

describe('LangChainInstrumentor class', () => {
  it('gracefully skips when langchain is not installed', async () => {
    // The real instrumentor catches the require() error and logs a warning.
    // We just verify it does not throw.
    const { LangChainInstrumentor } = await import('../../src/integrations/langchain/index');
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const instr = new LangChainInstrumentor();
    expect(() => instr.instrument()).not.toThrow();
    warnSpy.mockRestore();
  });

  it('uninstrument() on unpatched instance is a no-op', async () => {
    const { LangChainInstrumentor } = await import('../../src/integrations/langchain/index');
    const instr = new LangChainInstrumentor();
    expect(() => instr.uninstrument()).not.toThrow();
  });
});
