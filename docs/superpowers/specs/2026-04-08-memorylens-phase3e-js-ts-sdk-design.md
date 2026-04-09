# MemoryLens Phase 3e — JavaScript/TypeScript SDK Design

**Date:** 2026-04-08
**Scope:** TypeScript SDK with core instrumentation, OTLP export, and LangChain.js integration
**Status:** Approved
**Depends on:** Phase 1 SDK (API design reference), Instrumentation Spec v1

---

## Overview

A TypeScript npm package that provides the same core instrumentation capabilities as the Python SDK Phase 1. JS agent developers can instrument memory operations, export traces via OTLP to the MemoryLens UI, and auto-instrument LangChain.js. Lives in `js/` directory of the same repo.

---

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Location | `js/` directory in same repo | Shared docs/spec, independent tooling |
| Scope | Core + LangChain.js integration | Minimum viable "instrument → see traces" story |
| Tooling | TypeScript + tsup + vitest + npm | Modern standard for TS libraries |
| API style | Wrapper functions | Most idiomatic for JS functional code |
| OTLP export | Official `@opentelemetry/exporter-trace-otlp-http` | Same approach as Python SDK |

---

## Public API

```typescript
import { 
  init, shutdown, 
  instrumentWrite, instrumentRead, instrumentCompress, instrumentUpdate,
  context, getTracer 
} from 'memorylens';
```

### init()

```typescript
init({
  serviceName?: string,           // default: 'memorylens'
  exporter?: 'otlp' | 'console', // default: 'otlp'
  endpoint?: string,              // default: 'http://localhost:8000/v1/traces'
  captureContent?: boolean,       // default: true
  sampleRate?: number,            // 0.0-1.0, default: 1.0
});
```

Default endpoint is the MemoryLens UI ingest — zero config sends traces to the local dashboard.

### Wrapper Functions

```typescript
const store = instrumentWrite(async (content: string) => {
  return await db.save(content);
}, { backend: 'mem0', captureContent: true });

const search = instrumentRead(async (query: string) => {
  return await db.search(query);
}, { backend: 'mem0' });

const summarize = instrumentCompress(async (texts: string[]) => {
  return await llm.summarize(texts);
}, { model: 'gpt-4o-mini' });

const update = instrumentUpdate(async (key: string, value: string) => {
  return await db.update(key, value);
}, { backend: 'mem0' });
```

Each wrapper:
1. Creates a MemorySpan with correct operation
2. Records start time
3. Calls the wrapped function (async)
4. Captures return value/error, sets status
5. Passes completed span to processors

### Context

Uses `AsyncLocalStorage` (Node.js built-in):

```typescript
await context({ agentId: 'bot', sessionId: 's1', userId: 'u1' }, async () => {
  await store('user likes jazz');
  const results = await search('music prefs');
});
```

### getTracer()

```typescript
const tracer = getTracer('my-component');
const span = tracer.startSpan('memory.write', { backend: 'custom' });
try {
  // manual instrumentation
  span.end();
} catch (e) {
  span.setError(e);
  span.end();
  throw e;
}
```

---

## Core Types

```typescript
interface MemorySpan {
  spanId: string;
  traceId: string;
  parentSpanId: string | null;
  operation: MemoryOperation;
  status: SpanStatus;
  startTime: number;
  endTime: number;
  durationMs: number;
  agentId: string | null;
  sessionId: string | null;
  userId: string | null;
  inputContent: string | null;
  outputContent: string | null;
  attributes: Record<string, unknown>;
}

type MemoryOperation = 'memory.write' | 'memory.read' | 'memory.compress' | 'memory.update';
type SpanStatus = 'ok' | 'error' | 'dropped';
```

### SpanProcessor

```typescript
interface SpanProcessor {
  onStart(span: MemorySpan): void;
  onEnd(span: MemorySpan): void;
  shutdown(): Promise<void>;
  forceFlush(timeoutMs?: number): Promise<boolean>;
}
```

### SpanExporter

```typescript
interface SpanExporter {
  export(spans: MemorySpan[]): Promise<ExportResult>;
  shutdown(): Promise<void>;
}

enum ExportResult { SUCCESS = 0, FAILURE = 1 }
```

---

## TracerProvider

Singleton, same pattern as Python:

```typescript
class TracerProvider {
  private static instance: TracerProvider | null = null;
  processors: SpanProcessor[] = [];
  sampler: Sampler = new Sampler(1.0);
  serviceName: string = 'memorylens';

  static get(): TracerProvider;
  static reset(): void;
  addProcessor(p: SpanProcessor): void;
  getTracer(name: string): Tracer;
  shutdown(): Promise<void>;
}
```

### BatchSpanProcessor

Same threading model as Python but using `setTimeout` for batch scheduling:

```typescript
class BatchSpanProcessor implements SpanProcessor {
  constructor(exporter: SpanExporter, options?: {
    maxBatchSize?: number,     // default: 512
    scheduleDelayMs?: number,  // default: 5000
    maxQueueSize?: number,     // default: 2048
  });
}
```

Uses a queue + `setTimeout` loop. `onEnd()` pushes to queue (non-blocking). Timer flushes batches to exporter.

---

## Exporters

### OTLP Exporter

Wraps `@opentelemetry/exporter-trace-otlp-http`:

```typescript
class OTLPExporter implements SpanExporter {
  constructor(options?: { endpoint?: string });
  export(spans: MemorySpan[]): Promise<ExportResult>;
  shutdown(): Promise<void>;
}
```

Default endpoint: `process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? 'http://localhost:8000/v1/traces'`

Includes `ReadableSpanAdapter` that maps MemorySpan to OTel span format (same as Python's adapter).

### Console Exporter

```typescript
class ConsoleExporter implements SpanExporter {
  export(spans: MemorySpan[]): Promise<ExportResult>;
  shutdown(): Promise<void>;
}
```

Logs formatted JSON to stdout. For local development.

---

## LangChain.js Integration

```typescript
import { LangChainInstrumentor } from 'memorylens/integrations/langchain';

const instrumentor = new LangChainInstrumentor();
instrumentor.instrument();
```

Patches `BaseChatMemory`:
- `saveContext()` → WRITE span
- `loadMemoryVariables()` → READ span

Same Instrumentor interface:

```typescript
interface Instrumentor {
  instrument(options?: Record<string, unknown>): void;
  uninstrument(): void;
}
```

LangChain is a peer dependency (optional).

---

## Environment Variables

| Variable | Effect |
|---|---|
| `MEMORYLENS_EXPORTER` | Override exporter ('otlp', 'console') |
| `MEMORYLENS_CAPTURE_CONTENT` | 'true'/'false' |
| `MEMORYLENS_SAMPLE_RATE` | 0.0-1.0 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP endpoint URL |
| `OTEL_SERVICE_NAME` | Service name |

---

## File Structure

```
js/
├── package.json
├── tsconfig.json
├── tsup.config.ts
├── vitest.config.ts
├── README.md
├── src/
│   ├── index.ts                  # public API re-exports
│   ├── types.ts                  # MemorySpan, MemoryOperation, SpanStatus
│   ├── tracer.ts                 # TracerProvider, Tracer, MutableSpan
│   ├── context.ts                # AsyncLocalStorage context
│   ├── wrappers.ts               # instrumentWrite/Read/Compress/Update
│   ├── processor.ts              # SpanProcessor, SimpleSpanProcessor, BatchSpanProcessor
│   ├── sampler.ts                # rate-based sampler
│   ├── exporters/
│   │   ├── index.ts              # exporter registry
│   │   ├── otlp.ts              # OTLP HTTP exporter
│   │   └── console.ts           # console exporter
│   └── integrations/
│       ├── index.ts              # Instrumentor interface + registry
│       └── langchain/
│           ├── index.ts
│           └── instrumentor.ts
├── tests/
│   ├── types.test.ts
│   ├── tracer.test.ts
│   ├── context.test.ts
│   ├── wrappers.test.ts
│   ├── processor.test.ts
│   ├── exporters/
│   │   ├── otlp.test.ts
│   │   └── console.test.ts
│   └── integrations/
│       └── langchain.test.ts
```

---

## Package Configuration

### Dependencies

```json
{
  "dependencies": {
    "@opentelemetry/api": "^1.7",
    "@opentelemetry/sdk-trace-base": "^1.20",
    "@opentelemetry/exporter-trace-otlp-http": "^0.48"
  },
  "peerDependencies": {
    "langchain": ">=0.1.0"
  },
  "peerDependenciesMeta": {
    "langchain": { "optional": true }
  },
  "devDependencies": {
    "typescript": "^5.3",
    "tsup": "^8.0",
    "vitest": "^1.2"
  }
}
```

### tsup Config

Dual CJS/ESM output, declaration files, external peer deps.

### Exports Map

```json
{
  ".": { "import": "./dist/index.js", "require": "./dist/index.cjs", "types": "./dist/index.d.ts" },
  "./integrations/langchain": { "import": "./dist/integrations/langchain/index.js", "require": "./dist/integrations/langchain/index.cjs" }
}
```

---

## Testing

vitest with a `CollectingExporter` test helper (mirrors Python pattern). Mock OTel exporter for OTLP tests. Mock `require('langchain/memory')` for LangChain tests using `vi.mock()`.

Target: ~40 tests covering types, tracer, context, wrappers, processors, both exporters, and LangChain integration.
