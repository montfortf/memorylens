# MemoryLens Phase 3a — Memory Drift Detection Design

**Date:** 2026-04-08
**Scope:** Memory drift detection, contradiction detection, staleness tracking, health scoring
**Status:** Approved
**Depends on:** Phase 1 SDK, Phase 2a Web UI, Phase 2b Compression Auditor (for ScorerBackend)

---

## Overview

Memory Drift Detection tracks how stored memories evolve across sessions, detects semantic drift, contradictions, and staleness, and generates a multi-dimensional health score per entity, session, and topic. It operates in three modes: offline CLI analysis, online real-time detection (opt-in), and a scheduled watcher for continuous monitoring.

This is the most differentiated feature in the MemoryLens platform — no competitor offers memory-specific drift detection. Grounded in arxiv 2603.07670 which empirically demonstrates memory drift and contradiction accumulation over extended agent runs.

---

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Drift types | Entity + Session + Topic (all three) | Comprehensive coverage of drift patterns |
| Trigger modes | Offline + Online (opt-in) + Scheduled watcher | Flexibility from dev to production |
| Online performance | In-memory cache for last-known versions | Maintains low overhead for opt-in mode |
| Health score | 4 dimension scores + letter grade (A-F) | Actionable detail + quick scanning |
| Embedding backend | Reuse ScorerBackend with new CachedScorer wrapper | No new abstractions, cache prevents redundant calls |
| Storage | Two tables: memory_versions + drift_reports | Versions are foundation, reports are computed results |

---

## Memory Versions Table

```sql
CREATE TABLE IF NOT EXISTS memory_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    span_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    content TEXT,
    embedding TEXT,
    agent_id TEXT,
    session_id TEXT,
    timestamp REAL NOT NULL,
    UNIQUE(memory_key, version)
)
```

Indexes on `memory_key`, `session_id`, `timestamp`. Created lazily on first `save_version()` call.

### How Versions Get Created

- **Offline** — `memorylens drift analyze` scans WRITE/UPDATE spans, extracts `memory_key` from attributes, builds version chains
- **Online** — `VersionTracker` SpanProcessor writes to `memory_versions` on every WRITE/UPDATE `on_end()`
- **Key extraction** — `memory_key` from span attributes. Fallback: hash of input content. Spans without identifiable key are skipped.

---

## Drift Reports Table

```sql
CREATE TABLE IF NOT EXISTS drift_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT NOT NULL,
    key TEXT NOT NULL,
    drift_score REAL NOT NULL,
    contradiction_score REAL NOT NULL,
    staleness_score REAL NOT NULL,
    volatility_score REAL NOT NULL,
    grade TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(report_type, key)
)
```

Created lazily. One report per entity/session/topic (upserted on re-analysis).

---

## SQLiteExporter Extensions

```python
class SQLiteExporter:
    # Version methods
    def save_version(self, version: dict) -> None: ...
    def get_versions(self, memory_key: str) -> list[dict]: ...
    def get_all_versions(self) -> list[dict]: ...

    # Drift report methods
    def save_drift_report(self, report: dict) -> None: ...
    def get_drift_report(self, report_type: str, key: str) -> dict | None: ...
    def list_drift_reports(self, report_type: str | None = None,
                           min_grade: str | None = None,
                           limit: int = 50, offset: int = 0) -> tuple[list[dict], int]: ...
```

Both tables created lazily with `_ensure_*_table()` pattern (same as compression audits).

---

## CachedScorer

Added to `src/memorylens/_audit/scorer.py`:

```python
class CachedScorer:
    """Wraps a ScorerBackend with a text→embedding cache."""

    def __init__(self, scorer: ScorerBackend):
        self._scorer = scorer
        self._cache: dict[str, list[float]] = {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings, using cache for already-seen texts."""
        # Check cache for each text (keyed by MD5 hash)
        # Batch-embed only uncached texts
        # Store results in cache
        # Return all embeddings in order
        ...

    def clear_cache(self) -> None:
        self._cache.clear()
```

---

## Drift Analyzer

Three analysis methods, each producing a typed result.

### Entity-Level Drift

For each `memory_key`:
1. Get all versions ordered by time
2. Embed all version contents (via CachedScorer)
3. Compute cosine similarity between consecutive versions
4. `drift_score` = 1.0 - mean(consecutive similarities)
5. `contradiction_score` = proportion of version pairs with similarity < 0.5
6. `staleness_score` = min(1.0, days_since_last_update / 7.0)
7. `volatility_score` = sessions_with_changes / total_sessions

### Session-Level Drift

For each `session_id`:
1. Collect all WRITE/UPDATE spans in the session
2. For each modified memory_key, compare the version created in this session against its prior version
3. Aggregate drift scores across all keys modified in the session
4. Produces a per-session report of how much this session changed memory state

### Topic-Level Drift

1. Embed all memory versions
2. Cluster by similarity (group versions with pairwise similarity > 0.7 into same topic)
3. For each cluster, compute centroid at each time window
4. Track centroid movement over time
5. Flag clusters whose centroid has drifted significantly

### DriftAnalyzer Class

```python
class DriftAnalyzer:
    def __init__(self, scorer: CachedScorer): ...

    def analyze_entity(self, versions: list[dict]) -> EntityDriftResult: ...
    def analyze_session(self, session_id: str, versions: list[dict]) -> SessionDriftResult: ...
    def analyze_topics(self, all_versions: list[dict]) -> list[TopicDriftResult]: ...
    def compute_health(self, entity_result: EntityDriftResult) -> HealthScore: ...
```

---

## Health Score Model

```python
@dataclass(frozen=True)
class HealthScore:
    memory_key: str
    drift_score: float          # 0.0 = stable, 1.0 = total rewrite every time
    contradiction_score: float  # 0.0 = no contradictions, 1.0 = all pairs contradict
    staleness_score: float      # 0.0 = just updated, 1.0 = very stale
    volatility_score: float     # 0.0 = stable, 1.0 = changes every session
    grade: str                  # A/B/C/D/F
```

### Grade Computation

```
composite = 0.35 * drift + 0.30 * contradiction + 0.20 * staleness + 0.15 * volatility

A = composite < 0.15   (healthy)
B = composite < 0.30   (minor concerns)
C = composite < 0.50   (moderate issues)
D = composite < 0.70   (significant problems)
F = composite >= 0.70  (critical)
```

---

## VersionTracker (Online Mode)

Enabled via `memorylens.init(detect_drift=True)`. Implements `SpanProcessor` interface.

```python
class VersionTracker:
    def __init__(self, exporter: SQLiteExporter, scorer: CachedScorer):
        self._exporter = exporter
        self._scorer = scorer
        self._cache: dict[str, list[float]] = {}  # memory_key → last embedding

    def on_start(self, span: MemorySpan) -> None:
        pass

    def on_end(self, span: MemorySpan) -> None:
        # Only process WRITE and UPDATE operations
        # Extract memory_key from attributes
        # Save version to memory_versions table
        # Compute drift against cached previous embedding
        # If drift > 0.3, set drift_score and drift_detected on span attributes
        ...

    def shutdown(self) -> None: ...
    def force_flush(self, timeout_ms: int = 30000) -> bool: ...
```

Performance: cache hit = one cosine similarity computation (~0.01ms). Cache miss = one embed call (depends on backend). The in-memory `_cache` dict holds `{memory_key: last_embedding}` — populated lazily.

---

## Scheduled Watcher

`memorylens drift watch` runs the offline analyzer in a loop.

```python
def watch(db_path: str, interval: int = 300, scorer_name: str = "local") -> None:
    """Run drift analysis every `interval` seconds. Ctrl+C to stop."""
    while True:
        # Run full analysis
        # Save reports
        # Print summary
        # Sleep interval
```

---

## CLI Commands

```bash
# Offline analysis
memorylens drift analyze                            # all types
memorylens drift analyze --type entity              # entity only
memorylens drift analyze --type session             # session only
memorylens drift analyze --type topic               # topic only
memorylens drift analyze --scorer local             # scorer choice

# View results
memorylens drift report                             # list all reports
memorylens drift report --type entity --grade D,F   # filter by type and grade
memorylens drift show <memory_key>                  # entity detail

# Scheduled watcher
memorylens drift watch                              # every 5 minutes
memorylens drift watch --interval 60                # custom interval
```

### Report Output

```
Drift Report — Entities

KEY                    GRADE  DRIFT  CONTRADICTION  STALENESS  VOLATILITY
user_42_diet_prefs       F    0.82       0.90          0.10       0.45
user_42_music_prefs      B    0.15       0.00          0.30       0.20
user_99_location         C    0.40       0.35          0.55       0.10

3 entities analyzed. 1 critical, 0 significant, 1 moderate, 1 minor.
```

---

## UI Integration

### New Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/drift` | Drift dashboard with entity/session/topic tabs |
| GET | `/drift/{memory_key}` | Entity detail with version history and contradictions |

### Drift Dashboard (`/drift`)

- Nav bar gets "Drift" link
- Three htmx tabs: Entities / Sessions / Topics
- Sortable table: Key, Grade (color badge), Drift, Contradiction, Staleness, Volatility
- Grade colors: A=green, B=blue, C=amber, D=orange, F=red
- Click row → entity detail

### Entity Detail (`/drift/{memory_key}`)

- Health score breakdown (4 dimension bars + grade badge)
- Version timeline — vertical list of all versions with timestamps, content diffs
- Contradiction highlights — conflicting version pairs shown side-by-side
- Drift chart — horizontal bars showing drift between consecutive versions

### Trace Detail Integration

- WRITE/UPDATE spans with `drift_score` in attributes show drift indicator in header
- Link to entity's drift detail page if `memory_key` present

### Modified Templates

- `base.html` — add "Drift" nav link
- `traces_detail.html` — add drift indicator for WRITE/UPDATE spans

---

## File Structure

### New Files

```
src/memorylens/
├── _drift/
│   ├── __init__.py
│   ├── tracker.py              # VersionTracker (online mode SpanProcessor)
│   ├── analyzer.py             # DriftAnalyzer (entity/session/topic)
│   ├── health.py               # HealthScore model + grade computation
│   └── watcher.py              # Scheduled watcher loop
├── _ui/api/
│   └── drift.py                # drift dashboard + detail routes
├── _ui/templates/
│   ├── drift_dashboard.html
│   ├── drift_detail.html
│   └── partials/
│       ├── drift_table.html
│       └── version_timeline.html
├── cli/commands/
│   └── drift.py                # CLI drift commands
```

### Modified Files

| File | Change |
|---|---|
| `src/memorylens/_exporters/sqlite.py` | Add version + drift report CRUD, lazy tables |
| `src/memorylens/_audit/scorer.py` | Add CachedScorer class |
| `src/memorylens/__init__.py` | Add `detect_drift` param to `init()` |
| `src/memorylens/_ui/server.py` | Register drift routes |
| `src/memorylens/_ui/templates/base.html` | Add "Drift" nav link |
| `src/memorylens/_ui/templates/traces_detail.html` | Add drift indicator |
| `src/memorylens/cli/main.py` | Register drift command group |

---

## Testing

```
tests/
├── test_drift/
│   ├── __init__.py
│   ├── test_tracker.py           # version tracking, online drift detection
│   ├── test_analyzer.py          # entity/session/topic analysis (mock scorer)
│   ├── test_health.py            # health score computation, grade mapping
│   ├── test_cached_scorer.py     # cache hit/miss behavior
│   └── test_storage.py           # version + drift report CRUD
├── test_ui/
│   └── test_api_drift.py         # drift dashboard + detail routes
├── test_cli/
│   └── test_drift_commands.py    # CLI drift commands
```

All analyzer tests use `MockScorer` wrapped in `CachedScorer`. Controlled version histories with known drift patterns to verify correct score computation and grade assignment.
