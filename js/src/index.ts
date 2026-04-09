// Core types
export type { MemorySpan, MemoryOperation, SpanStatus, SpanProcessor, SpanExporter, MemoryContext } from './types';
export { ExportResult } from './types';

// Context
export { runWithContext, getCurrentContext } from './context';

// Tracer
export { TracerProvider, Tracer, MutableSpan } from './tracer';

// Sampler
export { Sampler } from './sampler';

// Processors
export { SimpleSpanProcessor, BatchSpanProcessor } from './processor';

// Exporters
export { ConsoleExporter } from './exporters/console';
export { OTLPExporter } from './exporters/otlp';

// Wrappers
export { instrumentWrite, instrumentRead, instrumentCompress, instrumentUpdate } from './wrappers';

// Instrumentor interface
export type { Instrumentor } from './integrations/index';

// ── Public convenience API ──────────────────────────────────────────────────

import { TracerProvider } from './tracer';
import { Sampler } from './sampler';
import { SimpleSpanProcessor, BatchSpanProcessor } from './processor';
import { OTLPExporter } from './exporters/otlp';
import { ConsoleExporter } from './exporters/console';
import { runWithContext } from './context';
import type { MemoryContext } from './types';

export interface InitOptions {
  serviceName?: string;
  exporter?: 'otlp' | 'console';
  endpoint?: string;
  captureContent?: boolean;
  sampleRate?: number;
  batch?: boolean;
}

export function init(options: InitOptions = {}): void {
  const {
    serviceName = process.env['OTEL_SERVICE_NAME'] ?? 'memorylens',
    exporter: exporterType =
      (process.env['MEMORYLENS_EXPORTER'] as 'otlp' | 'console' | undefined) ?? 'otlp',
    endpoint,
    sampleRate = parseFloat(process.env['MEMORYLENS_SAMPLE_RATE'] ?? '1.0'),
    batch = true,
  } = options;

  const provider = TracerProvider.get();
  provider.serviceName = serviceName;
  provider.sampler = new Sampler(sampleRate);

  const exp =
    exporterType === 'console'
      ? new ConsoleExporter()
      : new OTLPExporter({ endpoint });

  const processor = batch ? new BatchSpanProcessor(exp) : new SimpleSpanProcessor(exp);
  provider.addProcessor(processor);
}

export async function shutdown(): Promise<void> {
  const provider = TracerProvider.get();
  await provider.shutdown();
  TracerProvider.reset();
}

export async function context<T>(ctx: MemoryContext, fn: () => Promise<T>): Promise<T> {
  return runWithContext(ctx, fn);
}

export function getTracer(name: string) {
  return TracerProvider.get().getTracer(name);
}
