import { TracerProvider } from '../../tracer';
import type { Instrumentor } from '../index';

type AnyFn = (...args: unknown[]) => unknown;

interface BaseChatMemoryLike {
  saveContext: AnyFn;
  loadMemoryVariables: AnyFn;
}

// Original method store
const originals = new WeakMap<
  BaseChatMemoryLike,
  { saveContext: AnyFn; loadMemoryVariables: AnyFn }
>();

export class LangChainInstrumentor implements Instrumentor {
  private patched = false;

  instrument(_options?: Record<string, unknown>): void {
    if (this.patched) return;

    // Lazily require langchain/memory to avoid hard dependency
    let BaseChatMemory: { prototype: BaseChatMemoryLike } | undefined;
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const mod = require('langchain/memory') as { BaseChatMemory?: unknown };
      BaseChatMemory = mod.BaseChatMemory as { prototype: BaseChatMemoryLike } | undefined;
    } catch {
      console.warn('[memorylens] langchain/memory not found — LangChain instrumentation skipped');
      return;
    }

    if (!BaseChatMemory?.prototype) return;

    const proto = BaseChatMemory.prototype;
    const origSaveContext = proto.saveContext;
    const origLoadMemoryVariables = proto.loadMemoryVariables;

    proto.saveContext = async function (this: BaseChatMemoryLike, ...args: unknown[]) {
      const provider = TracerProvider.get();
      const tracer = provider.getTracer('memorylens.langchain');
      const span = tracer.startSpan('memory.write', { 'langchain.method': 'saveContext' });

      try {
        const result = await (origSaveContext as AnyFn).apply(this, args);
        tracer.endSpan(span);
        return result;
      } catch (error) {
        span.setError(error);
        tracer.endSpan(span);
        throw error;
      }
    };

    proto.loadMemoryVariables = async function (
      this: BaseChatMemoryLike,
      ...args: unknown[]
    ) {
      const provider = TracerProvider.get();
      const tracer = provider.getTracer('memorylens.langchain');
      const span = tracer.startSpan('memory.read', {
        'langchain.method': 'loadMemoryVariables',
      });

      try {
        const result = await (origLoadMemoryVariables as AnyFn).apply(this, args);
        tracer.endSpan(span);
        return result;
      } catch (error) {
        span.setError(error);
        tracer.endSpan(span);
        throw error;
      }
    };

    // Store originals on prototype (shared)
    originals.set(proto, { saveContext: origSaveContext, loadMemoryVariables: origLoadMemoryVariables });
    this.patched = true;
  }

  uninstrument(): void {
    if (!this.patched) return;

    let BaseChatMemory: { prototype: BaseChatMemoryLike } | undefined;
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const mod = require('langchain/memory') as { BaseChatMemory?: unknown };
      BaseChatMemory = mod.BaseChatMemory as { prototype: BaseChatMemoryLike } | undefined;
    } catch {
      return;
    }

    if (!BaseChatMemory?.prototype) return;

    const proto = BaseChatMemory.prototype;
    const orig = originals.get(proto);
    if (orig) {
      proto.saveContext = orig.saveContext;
      proto.loadMemoryVariables = orig.loadMemoryVariables;
      originals.delete(proto);
    }

    this.patched = false;
  }
}
