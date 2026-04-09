import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { TracerProvider } from '../src/tracer';
import { instrumentWrite, instrumentRead, instrumentCompress, instrumentUpdate } from '../src/wrappers';
import { SimpleSpanProcessor } from '../src/processor';
import { ExportResult } from '../src/types';
import { runWithContext } from '../src/context';
import type { MemorySpan, SpanExporter } from '../src/types';

class CollectingExporter implements SpanExporter {
  spans: MemorySpan[] = [];
  async export(spans: MemorySpan[]): Promise<ExportResult> {
    this.spans.push(...spans);
    return ExportResult.SUCCESS;
  }
  async shutdown(): Promise<void> {}
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

describe('instrumentWrite', () => {
  it('creates a memory.write span on success', async () => {
    const fn = instrumentWrite(async (s: string) => `saved:${s}`);
    const result = await fn('hello');
    await new Promise(r => setTimeout(r, 0));
    expect(result).toBe('saved:hello');
    expect(collector.spans).toHaveLength(1);
    expect(collector.spans[0].operation).toBe('memory.write');
    expect(collector.spans[0].status).toBe('ok');
  });

  it('captures input content by default', async () => {
    const fn = instrumentWrite(async (s: string) => s);
    await fn('my data');
    await new Promise(r => setTimeout(r, 0));
    expect(collector.spans[0].inputContent).toBe('my data');
  });

  it('does not capture content when captureContent=false', async () => {
    const fn = instrumentWrite(async (s: string) => s, { captureContent: false });
    await fn('secret');
    await new Promise(r => setTimeout(r, 0));
    expect(collector.spans[0].inputContent).toBeNull();
  });

  it('sets status to error on throw', async () => {
    const fn = instrumentWrite(async () => { throw new Error('write fail'); });
    await expect(fn()).rejects.toThrow('write fail');
    await new Promise(r => setTimeout(r, 0));
    expect(collector.spans[0].status).toBe('error');
    expect(collector.spans[0].attributes['error.message']).toBe('write fail');
  });

  it('passes custom attributes to span', async () => {
    const fn = instrumentWrite(async () => 'ok', { backend: 'redis' });
    await fn();
    await new Promise(r => setTimeout(r, 0));
    expect(collector.spans[0].attributes['backend']).toBe('redis');
  });

  it('picks up context agentId', async () => {
    const fn = instrumentWrite(async () => 'ok');
    await runWithContext({ agentId: 'ctx-agent' }, () => fn());
    await new Promise(r => setTimeout(r, 0));
    expect(collector.spans[0].agentId).toBe('ctx-agent');
  });
});

describe('instrumentRead', () => {
  it('creates a memory.read span', async () => {
    const fn = instrumentRead(async (q: string) => `results for ${q}`);
    await fn('jazz');
    await new Promise(r => setTimeout(r, 0));
    expect(collector.spans[0].operation).toBe('memory.read');
  });
});

describe('instrumentCompress', () => {
  it('creates a memory.compress span', async () => {
    const fn = instrumentCompress(async (texts: string[]) => texts.join(' '));
    await fn(['a', 'b']);
    await new Promise(r => setTimeout(r, 0));
    expect(collector.spans[0].operation).toBe('memory.compress');
  });
});

describe('instrumentUpdate', () => {
  it('creates a memory.update span', async () => {
    const fn = instrumentUpdate(async (k: string, v: string) => `${k}=${v}`);
    await fn('key', 'val');
    await new Promise(r => setTimeout(r, 0));
    expect(collector.spans[0].operation).toBe('memory.update');
  });
});
