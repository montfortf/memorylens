# MemoryLens JS/TS SDK

**Observability and debugging for AI agent memory systems.**

TypeScript SDK for instrumenting memory operations in JavaScript/TypeScript AI agents. Sends traces to the [MemoryLens](https://github.com/memorylens/memorylens) dashboard via OTLP.

## Install

```bash
npm install memorylens
```

## Quick Start

```typescript
import { init, instrumentWrite, instrumentRead, context } from 'memorylens';

// Initialize — sends traces to MemoryLens UI by default
init();

// Wrap your memory functions
const store = instrumentWrite(async (content: string) => {
  return await db.save(content);
}, { backend: 'my_db' });

const search = instrumentRead(async (query: string) => {
  return await db.search(query);
}, { backend: 'my_db' });

// Add context for session tracking
await context({ agentId: 'support-bot', sessionId: 'sess-123' }, async () => {
  await store('user prefers dark mode');
  const results = await search('user preferences');
});
```

## Auto-Instrumentation (LangChain.js)

```typescript
import { init } from 'memorylens';
import { LangChainInstrumentor } from 'memorylens/integrations/langchain';

init();
new LangChainInstrumentor().instrument();
// All LangChain memory operations are now traced
```

## Configuration

```typescript
init({
  serviceName: 'my-agent',
  exporter: 'otlp',                              // 'otlp' or 'console'
  endpoint: 'http://localhost:8000/v1/traces',    // MemoryLens UI ingest
  captureContent: true,
  sampleRate: 1.0,
});
```

Or via environment variables:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8000/v1/traces
export OTEL_SERVICE_NAME=my-agent
```

## View Traces

Start the MemoryLens dashboard (Python):

```bash
pip install memorylens[ui]
memorylens ui --ingest
# Open http://localhost:8000
```

## License

Apache 2.0
