# MemoryLens

**Observability and debugging for AI agent memory systems.**

MemoryLens instruments the memory pipeline in your AI agents — write, read, compress, update — and gives you full visibility into what's happening. No more guessing why your agent "forgot" something.

## Install

```bash
pip install memorylens

# With framework integrations
pip install memorylens[langchain]
pip install memorylens[mem0]
```

## Quick Start

```python
import memorylens
from memorylens import instrument_write, instrument_read, context

# Initialize (defaults to local SQLite storage)
memorylens.init()

# Decorate your memory functions
@instrument_write(backend="my_db")
def store(content: str) -> bool:
    # your existing code
    return True

@instrument_read(backend="my_db")
def search(query: str) -> list[str]:
    # your existing code
    return ["result"]

# Add context for session tracking
with context(agent_id="support-bot", session_id="sess-123", user_id="user-456"):
    store("user prefers vegetarian meals")
    results = search("dietary preferences")

# Inspect with the CLI
# memorylens traces list
# memorylens traces show <trace-id>
```

## Auto-Instrumentation

For supported frameworks, zero code changes required:

```python
import memorylens

memorylens.init(instrument=["langchain", "mem0"])
# All memory operations are now traced automatically
```

## CLI

```bash
memorylens init                          # Set up local storage
memorylens traces list                   # List recent traces
memorylens traces list --status error    # Filter by status
memorylens traces show <trace-id>        # Inspect a trace
memorylens traces export -o traces.jsonl # Export as JSONL
memorylens stats                         # Summary statistics
```

## OTLP Export

Send traces to any OpenTelemetry-compatible backend:

```python
memorylens.init(
    exporter="otlp",
    otlp_endpoint="http://localhost:4317",
)
```

Or use environment variables:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_SERVICE_NAME=my-agent
```

## License

Apache 2.0
