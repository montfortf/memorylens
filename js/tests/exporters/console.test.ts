import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ConsoleExporter } from '../../src/exporters/console';
import { ExportResult } from '../../src/types';
import type { MemorySpan } from '../../src/types';

function makeSpan(override: Partial<MemorySpan> = {}): MemorySpan {
  return {
    spanId: 'cs1',
    traceId: 'ct1',
    parentSpanId: null,
    operation: 'memory.write',
    status: 'ok',
    startTime: 1000,
    endTime: 1012,
    durationMs: 12,
    agentId: 'bot',
    sessionId: 's1',
    userId: 'u1',
    inputContent: 'hello',
    outputContent: 'stored',
    attributes: { backend: 'mem0' },
    ...override,
  };
}

describe('ConsoleExporter', () => {
  let consoleSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleSpy.mockRestore();
  });

  it('returns SUCCESS', async () => {
    const exp = new ConsoleExporter();
    const result = await exp.export([makeSpan()]);
    expect(result).toBe(ExportResult.SUCCESS);
  });

  it('logs once per span', async () => {
    const exp = new ConsoleExporter();
    await exp.export([makeSpan(), makeSpan({ spanId: 'cs2' })]);
    expect(consoleSpy).toHaveBeenCalledTimes(2);
  });

  it('logs valid JSON containing spanId', async () => {
    const exp = new ConsoleExporter();
    await exp.export([makeSpan()]);
    const logged = consoleSpy.mock.calls[0][0] as string;
    const parsed = JSON.parse(logged) as Record<string, unknown>;
    expect(parsed.spanId).toBe('cs1');
    expect(parsed.operation).toBe('memory.write');
  });

  it('returns SUCCESS for empty array', async () => {
    const exp = new ConsoleExporter();
    const result = await exp.export([]);
    expect(result).toBe(ExportResult.SUCCESS);
    expect(consoleSpy).not.toHaveBeenCalled();
  });

  it('shutdown is a no-op', async () => {
    const exp = new ConsoleExporter();
    await expect(exp.shutdown()).resolves.toBeUndefined();
  });
});
