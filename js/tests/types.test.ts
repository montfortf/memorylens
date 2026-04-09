import { describe, it, expect } from 'vitest';
import { ExportResult } from '../src/types';
import type { MemorySpan, MemoryOperation, SpanStatus } from '../src/types';

describe('types', () => {
  it('ExportResult has SUCCESS and FAILURE', () => {
    expect(ExportResult.SUCCESS).toBe(0);
    expect(ExportResult.FAILURE).toBe(1);
  });

  it('MemorySpan can be constructed', () => {
    const span: MemorySpan = {
      spanId: 's1',
      traceId: 't1',
      parentSpanId: null,
      operation: 'memory.write',
      status: 'ok',
      startTime: 1000,
      endTime: 1012,
      durationMs: 12,
      agentId: 'bot',
      sessionId: 's1',
      userId: 'u1',
      inputContent: 'data',
      outputContent: 'stored',
      attributes: { backend: 'test' },
    };
    expect(span.operation).toBe('memory.write');
    expect(span.attributes.backend).toBe('test');
  });

  it('operations are string literals', () => {
    const ops: MemoryOperation[] = ['memory.write', 'memory.read', 'memory.compress', 'memory.update'];
    expect(ops).toHaveLength(4);
  });

  it('statuses are string literals', () => {
    const statuses: SpanStatus[] = ['ok', 'error', 'dropped'];
    expect(statuses).toHaveLength(3);
  });

  it('MemorySpan allows null fields', () => {
    const span: MemorySpan = {
      spanId: 's2',
      traceId: 't2',
      parentSpanId: null,
      operation: 'memory.read',
      status: 'error',
      startTime: 2000,
      endTime: 2050,
      durationMs: 50,
      agentId: null,
      sessionId: null,
      userId: null,
      inputContent: null,
      outputContent: null,
      attributes: {},
    };
    expect(span.agentId).toBeNull();
    expect(span.parentSpanId).toBeNull();
  });
});
