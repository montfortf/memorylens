# MemoryLens Phase 2d — Additional Integrations Design

**Date:** 2026-04-08
**Scope:** LlamaIndex, Letta, and Zep auto-instrumentation
**Status:** Approved
**Depends on:** Phase 1 SDK (complete)

---

## Overview

Three new framework integrations following the exact same `Instrumentor` pattern as LangChain and Mem0. Each patches the framework's memory class methods to emit MemoryLens spans.

---

## LlamaIndex Integration (`memorylens[llamaindex]`)

**Package:** `llama-index-core`
**Class:** `ChatMemoryBuffer` from `llama_index.core.memory`

| Method | Operation | Span Type |
|---|---|---|
| `put(message)` | WRITE | Captures message content |
| `put_messages(messages)` | WRITE | Captures message list |
| `get(input)` | READ | Captures input query, returned messages |
| `get_all()` | READ | Captures all returned messages |
| `reset()` | WRITE (DROPPED) | drop_reason="reset" |

**Extra:** `pip install memorylens[llamaindex]` adds `llama-index-core>=0.10` dependency.

---

## Letta Integration (`memorylens[letta]`)

**Package:** `letta-client`
**Class:** Memory block operations via `client.agents.blocks`

Since Letta uses a client-server model, we patch the `Letta` client's agent block methods:

| Method | Operation | Span Type |
|---|---|---|
| `agents.blocks.retrieve(agent_id, block_label)` | READ | Captures block label, returned value |
| `agents.blocks.update(agent_id, block_label, value)` | UPDATE | Captures block label, old/new value |
| `agents.blocks.delete(agent_id, block_label)` | WRITE (DROPPED) | drop_reason="explicit_delete" |
| `agents.blocks.list(agent_id)` | READ | Captures agent_id, returned blocks |

**Extra:** `pip install memorylens[letta]` adds `letta-client>=0.1` dependency.

---

## Zep Integration (`memorylens[zep]`)

**Package:** `zep-python`
**Class:** `Zep` client from `zep_python`

| Method | Operation | Span Type |
|---|---|---|
| `memory.add(session_id, messages)` | WRITE | Captures session_id, message count |
| `memory.get(session_id)` | READ | Captures session_id, returned memories |
| `memory.search(session_id, search_payload)` | READ | Captures query, results, scores |
| `memory.delete(session_id)` | WRITE (DROPPED) | drop_reason="session_delete" |

**Extra:** `pip install memorylens[zep]` adds `zep-python>=2.0` dependency.

---

## File Structure

Each integration follows the identical pattern:

```
src/memorylens/integrations/
├── llamaindex/
│   ├── __init__.py           # exports LlamaIndexInstrumentor
│   └── instrumentor.py       # patches ChatMemoryBuffer
├── letta/
│   ├── __init__.py           # exports LettaInstrumentor
│   └── instrumentor.py       # patches Letta client blocks
└── zep/
    ├── __init__.py           # exports ZepInstrumentor
    └── instrumentor.py       # patches Zep memory client
```

All three registered in `integrations/__init__.py` via `_register_builtins()`.

---

## Testing

Same pattern as existing integration tests — fake framework classes, mock the `_get_*_class()` function, verify spans are emitted with correct operation types.

```
tests/test_integrations/
├── test_llamaindex.py
├── test_letta.py
└── test_zep.py
```
