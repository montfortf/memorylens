import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { OTLPExporter } from '../../src/exporters/otlp';
import { ExportResult } from '../../src/types';
import type { MemorySpan } from '../../src/types';

function makeSpan(override: Partial<MemorySpan> = {}): MemorySpan {
  return {
    spanId: 'os1',
    traceId: 'ot1',
    parentSpanId: null,
    operation: 'memory.read',
    status: 'ok',
    startTime: 1000,
    endTime: 1020,
    durationMs: 20,
    agentId: 'ag1',
    sessionId: 'se1',
    userId: 'u1',
    inputContent: 'query',
    outputContent: 'results',
    attributes: { model: 'gpt-4' },
    ...override,
  };
}

describe('OTLPExporter', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env['OTEL_EXPORTER_OTLP_ENDPOINT'];
  });

  it('returns SUCCESS on 200 response', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true });
    const exp = new OTLPExporter({ endpoint: 'http://localhost:8000/v1/traces' });
    const result = await exp.export([makeSpan()]);
    expect(result).toBe(ExportResult.SUCCESS);
  });

  it('returns FAILURE on non-ok response', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 500 });
    const exp = new OTLPExporter({ endpoint: 'http://localhost:8000/v1/traces' });
    const result = await exp.export([makeSpan()]);
    expect(result).toBe(ExportResult.FAILURE);
  });

  it('returns FAILURE on network error', async () => {
    fetchMock.mockRejectedValueOnce(new Error('Network error'));
    const exp = new OTLPExporter({ endpoint: 'http://localhost:8000/v1/traces' });
    const result = await exp.export([makeSpan()]);
    expect(result).toBe(ExportResult.FAILURE);
  });

  it('returns SUCCESS for empty spans without calling fetch', async () => {
    const exp = new OTLPExporter({ endpoint: 'http://localhost:8000/v1/traces' });
    const result = await exp.export([]);
    expect(result).toBe(ExportResult.SUCCESS);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('uses OTEL_EXPORTER_OTLP_ENDPOINT env var as default', async () => {
    process.env['OTEL_EXPORTER_OTLP_ENDPOINT'] = 'http://custom:9000/v1/traces';
    fetchMock.mockResolvedValueOnce({ ok: true });
    const exp = new OTLPExporter();
    await exp.export([makeSpan()]);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://custom:9000/v1/traces',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('sends JSON body with resourceSpans', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true });
    const exp = new OTLPExporter({ endpoint: 'http://localhost:8000/v1/traces' });
    await exp.export([makeSpan()]);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string) as { resourceSpans: unknown[] };
    expect(body.resourceSpans).toHaveLength(1);
  });

  it('shutdown is a no-op', async () => {
    const exp = new OTLPExporter();
    await expect(exp.shutdown()).resolves.toBeUndefined();
  });
});
