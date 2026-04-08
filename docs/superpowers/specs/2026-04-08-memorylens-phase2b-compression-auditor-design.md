# MemoryLens Phase 2b — Compression Auditor Design

**Date:** 2026-04-08
**Scope:** Compression audit with semantic diff and loss scoring
**Status:** Approved
**Depends on:** Phase 1 SDK (complete), Phase 2a Web UI (complete)

---

## Overview

The Compression Auditor analyzes COMPRESS spans to determine what information was lost during memory summarization. It runs as an **offline analysis** — zero runtime overhead during instrumentation. The SDK already captures `pre_content` and `post_content` in COMPRESS spans; this feature computes semantic similarity at the sentence level to produce a loss score and a detailed diff showing which facts survived and which were dropped.

Accessible via CLI (`memorylens audit compress`) and a dedicated UI view at `/traces/{trace_id}/compression`.

---

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Scoring timing | Offline analysis (not at instrumentation time) | Zero runtime overhead, maintains <2ms p99 |
| Embedding model | Pluggable with local `sentence-transformers` default | Works offline, no API key needed, users can switch to OpenAI |
| Output | Score + sentence-level text diff | Answers "what was lost" not just "how much" |
| Access | CLI + UI | CLI for scripting/CI, UI for visual debugging |
| Storage | Separate `compression_audits` table | Immutable traces, re-runnable audits |

---

## Scorer Backend Protocol

```python
class ScorerBackend(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a list of texts."""
        ...
```

### Built-in Backends

**LocalScorer** (default) — uses `sentence-transformers` `all-MiniLM-L6-v2`. No API key needed. ~80MB model download on first use.

```python
class LocalScorer:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts).tolist()
```

**OpenAIScorer** — uses `text-embedding-3-small`. Requires `OPENAI_API_KEY` env var and user-installed `openai` package.

```python
class OpenAIScorer:
    def __init__(self, model: str = "text-embedding-3-small"):
        import openai
        self._client = openai.OpenAI()
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in response.data]
```

### New Dependency

```toml
[project.optional-dependencies]
audit = ["sentence-transformers>=2.0", "numpy>=1.24"]
```

OpenAI backend requires user to install `openai` separately.

---

## Compression Analyzer

### Data Model

```python
@dataclass(frozen=True)
class SentenceAnalysis:
    """Analysis of a single sentence from pre-compression content."""
    text: str                    # the original sentence
    best_match_score: float      # highest cosine similarity to any post-content sentence
    status: str                  # "preserved" (>= 0.7) or "lost" (< 0.7)

@dataclass(frozen=True)
class CompressionAudit:
    """Complete audit result for a single COMPRESS span."""
    span_id: str
    semantic_loss_score: float   # 1.0 - mean(best_match_scores). 0.0 = no loss, 1.0 = total loss
    compression_ratio: float     # len(post) / len(pre)
    pre_sentence_count: int
    post_sentence_count: int
    sentences: list[SentenceAnalysis]
    scorer_backend: str          # "local" or "openai"
```

### Algorithm

1. Split `pre_content` into sentences (regex: split on `.!?` followed by space/newline)
2. Split `post_content` into sentences
3. Embed all sentences in one batch call to the scorer backend
4. For each pre-sentence, compute cosine similarity against every post-sentence
5. Take the max similarity as `best_match_score`
6. Classify: `>= 0.7` → "preserved", `< 0.7` → "lost"
7. `semantic_loss_score` = 1.0 - mean of all best_match_scores
8. `compression_ratio` = len(post_content) / len(pre_content)
9. Return `CompressionAudit`

### Sentence Splitter

Simple regex-based splitter in `_audit/splitter.py`:

```python
def split_sentences(text: str) -> list[str]:
    """Split text into sentences. Handles common abbreviations."""
    ...
```

Splits on `.!?` followed by whitespace or end-of-string. Filters out empty strings and strips whitespace.

---

## Storage

### New Table: `compression_audits`

```sql
CREATE TABLE IF NOT EXISTS compression_audits (
    span_id TEXT PRIMARY KEY,
    semantic_loss_score REAL NOT NULL,
    compression_ratio REAL NOT NULL,
    pre_sentence_count INTEGER NOT NULL,
    post_sentence_count INTEGER NOT NULL,
    sentences TEXT NOT NULL,
    scorer_backend TEXT NOT NULL,
    created_at REAL NOT NULL
)
```

Created lazily on first `save_audit()` call, not at SQLiteExporter init.

### New Methods on SQLiteExporter

```python
class SQLiteExporter:
    def save_audit(self, audit: CompressionAudit) -> None:
        """Save a compression audit result. Creates table if needed."""
        ...

    def get_audit(self, span_id: str) -> dict | None:
        """Get audit result for a span, or None if not audited."""
        ...

    def list_audits(self, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        """List all audits with pagination. Returns (rows, total_count)."""
        ...
```

---

## CLI Commands

New `audit` command group registered in `cli/main.py`:

```bash
memorylens audit compress                          # audit all unaudited COMPRESS spans
memorylens audit compress --trace-id abc123        # audit specific trace
memorylens audit compress --scorer openai           # use OpenAI backend
memorylens audit compress --force                   # re-audit already-audited spans
memorylens audit show <span_id>                     # show detailed audit for a span
memorylens audit list                               # list all audit results
memorylens audit list --min-loss 0.3                # filter by minimum loss score
```

### Output: `memorylens audit compress`

```
Analyzing 12 COMPRESS spans...
[████████████████████████████████] 12/12

Results:
SPAN ID      LOSS SCORE   RATIO   PRESERVED   LOST    STATUS
a1b2c3d4     0.12         0.35    8/9         1/9     ✓ low loss
e5f6g7h8     0.45         0.28    4/7         3/7     ⚠ moderate loss
i9j0k1l2     0.78         0.15    2/8         6/8     ✗ high loss

Summary: 12 spans audited. 2 with moderate loss, 1 with high loss.
```

### Output: `memorylens audit show <span_id>`

```
Compression Audit: e5f6g7h8

Loss Score:    0.45 (moderate)
Ratio:         0.28 (72% reduction)
Sentences:     4/7 preserved, 3/7 lost
Scorer:        local (all-MiniLM-L6-v2)

Pre-compression (7 sentences):
  ✓ [0.92] "User prefers vegetarian meals"
  ✓ [0.88] "No dairy products due to allergy"
  ✗ [0.45] "Mentioned this during Feb 14 conversation"
  ...

Post-compression:
  "User is vegetarian with dairy allergy, enjoys Italian and Thai food."
```

### Loss Score Classification

- `< 0.3` → "low loss" (green, checkmark)
- `0.3 - 0.6` → "moderate loss" (amber, warning)
- `> 0.6` → "high loss" (red, X)

---

## UI View

### Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/traces/{trace_id}/compression` | Full page: compression audit view |
| POST | `/api/traces/{trace_id}/audit?scorer=local` | Run audit for a span (scorer: `local` or `openai`), redirect back |

### Trace Detail Integration

The trace detail template (`traces_detail.html`) shows a "Debug Compression →" button for COMPRESS spans, linking to `/traces/{trace_id}/compression`. Same pattern as "Debug Retrieval →" for READ spans.

### Compression Audit Page Layout

**Header** — breadcrumb (← Traces / {trace_id} / Compression Audit), span metadata

**Summary card** — loss score with color coding (green/amber/red), compression ratio, preserved/lost sentence counts

**Sentence diff** — list of all pre-compression sentences:
- Green checkmark + score bar for preserved sentences (score >= 0.7)
- Red X + score bar for lost sentences (score < 0.7)
- Score bars use the same visual style as the Retrieval Debugger
- Preserved sentences show the best-matching post-content sentence below in subtle text

**Post-compression content** — full compressed text in a box below the diff

**"Run Audit" state** — if no audit exists for this span:
- Message: "This span has not been audited yet"
- "Run Audit" button fires `POST /api/traces/{trace_id}/audit`
- If `[audit]` extra not installed, show: "Install audit dependencies: pip install memorylens[audit]"

---

## File Structure

### New Files

```
src/memorylens/
├── _audit/
│   ├── __init__.py
│   ├── analyzer.py           # CompressionAnalyzer, CompressionAudit, SentenceAnalysis
│   ├── scorer.py             # ScorerBackend protocol, LocalScorer, OpenAIScorer
│   └── splitter.py           # sentence splitting utility
├── _ui/
│   ├── api/
│   │   └── compression.py    # compression audit routes
│   └── templates/
│       ├── compression_audit.html
│       └── partials/
│           └── sentence_diff.html
├── cli/
│   └── commands/
│       └── audit.py           # memorylens audit compress/show/list
```

### Modified Files

| File | Change |
|---|---|
| `pyproject.toml` | Add `[audit]` extra |
| `src/memorylens/_exporters/sqlite.py` | Add `save_audit()`, `get_audit()`, `list_audits()`, lazy table creation |
| `src/memorylens/_ui/server.py` | Register compression routes |
| `src/memorylens/_ui/templates/traces_detail.html` | Add "Debug Compression" button for COMPRESS spans |
| `src/memorylens/cli/main.py` | Register `audit` command group |

---

## Testing Strategy

### Test Structure

```
tests/
├── test_audit/
│   ├── __init__.py
│   ├── test_splitter.py       # sentence splitting edge cases
│   ├── test_analyzer.py       # audit generation with mock scorer
│   ├── test_scorer.py         # scorer backends
│   └── test_storage.py        # save/get/list audits in SQLite
├── test_ui/
│   └── test_api_compression.py  # compression audit UI endpoints
├── test_cli/
│   └── test_audit_commands.py   # CLI audit commands
```

### Mock Scorer

Tests use a `MockScorer` that returns predictable embeddings so tests are fast and deterministic — no model download required. Example:

```python
class MockScorer:
    """Returns embeddings where similar texts get similar vectors."""
    def embed(self, texts: list[str]) -> list[list[float]]:
        # Simple hash-based embedding for testing
        ...
```

### Slow Test Marker

One integration test with the real `LocalScorer` runs behind `@pytest.mark.slow`:

```bash
uv run pytest tests/ -v                    # skips slow tests
uv run pytest tests/ -v -m slow            # runs slow tests only
```
