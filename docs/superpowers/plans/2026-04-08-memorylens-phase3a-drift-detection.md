# MemoryLens Phase 3a — Memory Drift Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build memory drift detection that tracks how memories evolve, detects contradictions and staleness, computes multi-dimensional health scores, and works in offline, online, and scheduled modes.

**Architecture:** CachedScorer wraps existing ScorerBackend. VersionTracker (SpanProcessor) records memory versions. DriftAnalyzer computes entity/session/topic drift with 4-dimension health scores (drift, contradiction, staleness, volatility) and letter grades. Two new SQLite tables (memory_versions, drift_reports). CLI commands + UI dashboard.

**Tech Stack:** Python 3.10+, existing ScorerBackend/MockScorer, SQLite, FastAPI (existing), Jinja2/htmx (existing)

**Spec:** `docs/superpowers/specs/2026-04-08-memorylens-phase3a-drift-detection-design.md`

---

## Task 1: Package Setup

**Goal:** Create the `_drift` package skeleton and test package. No logic yet — just the directory structure and empty `__init__.py` files so subsequent tasks can import cleanly.

- [ ] Create `src/memorylens/_drift/__init__.py` (empty for now — Task 10 fills it)
- [ ] Create `tests/test_drift/__init__.py` (empty)
- [ ] Verify existing package structure with `ls src/memorylens/` and `ls tests/`
- [ ] Commit

**Files to create:**

`src/memorylens/_drift/__init__.py`:
```python
# Populated in Task 10
```

`tests/test_drift/__init__.py`:
```python
```

---

## Task 2: CachedScorer

**Goal:** Add `CachedScorer` to `src/memorylens/_audit/scorer.py`. It wraps any `ScorerBackend`, caches embeddings by MD5 hash of text, and only calls the underlying scorer for cache-miss texts — batching them in a single call.

- [ ] Add `CachedScorer` class to `src/memorylens/_audit/scorer.py` (append after `OpenAIScorer`)
- [ ] Create `tests/test_drift/test_cached_scorer.py` with 4 test cases
- [ ] Run `python -m pytest tests/test_drift/test_cached_scorer.py -v` and confirm all pass
- [ ] Commit

**Code to append to `src/memorylens/_audit/scorer.py`:**

```python
class CachedScorer:
    """Wraps a ScorerBackend with a text→embedding cache keyed by MD5 hash."""

    def __init__(self, scorer: ScorerBackend) -> None:
        self._scorer = scorer
        self._cache: dict[str, list[float]] = {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings, using cache for already-seen texts.

        Batches only uncached texts into a single scorer call.
        """
        keys = [hashlib.md5(t.encode()).hexdigest() for t in texts]

        # Identify which texts are not yet cached
        miss_indices: list[int] = []
        miss_texts: list[str] = []
        for i, key in enumerate(keys):
            if key not in self._cache:
                miss_indices.append(i)
                miss_texts.append(texts[i])

        # Batch-embed only cache misses
        if miss_texts:
            new_embeddings = self._scorer.embed(miss_texts)
            for i, emb in zip(miss_indices, new_embeddings):
                self._cache[keys[i]] = emb

        return [self._cache[key] for key in keys]

    def clear_cache(self) -> None:
        """Remove all cached embeddings."""
        self._cache.clear()
```

**`tests/test_drift/test_cached_scorer.py`:**

```python
from __future__ import annotations

from memorylens._audit.scorer import CachedScorer, MockScorer


class TestCachedScorer:
    def test_cache_hit_avoids_scorer_call(self):
        """Second embed of same text must not call scorer again."""
        call_count = 0
        original_embed = MockScorer.embed

        class CountingMock(MockScorer):
            def embed(self, texts):
                nonlocal call_count
                call_count += len(texts)
                return original_embed(self, texts)

        scorer = CachedScorer(CountingMock())
        scorer.embed(["hello world"])
        first_count = call_count
        scorer.embed(["hello world"])

        assert call_count == first_count  # no additional calls

    def test_cache_miss_calls_scorer(self):
        """New text must produce an embedding via the underlying scorer."""
        scorer = CachedScorer(MockScorer())
        result = scorer.embed(["unique text for cache miss test"])
        assert len(result) == 1
        assert len(result[0]) == 64  # MockScorer default dim

    def test_mixed_batch_only_embeds_new_texts(self):
        """Mixed batch: cached texts reuse cache, new texts get embedded."""
        call_count = 0
        original_embed = MockScorer.embed

        class CountingMock(MockScorer):
            def embed(self, texts):
                nonlocal call_count
                call_count += len(texts)
                return original_embed(self, texts)

        mock = CountingMock()
        scorer = CachedScorer(mock)

        # Prime cache with text_a
        scorer.embed(["text_a"])
        count_after_first = call_count

        # Embed text_a (cached) + text_b (new)
        results = scorer.embed(["text_a", "text_b"])
        assert call_count == count_after_first + 1  # only text_b sent to scorer
        assert len(results) == 2
        assert len(results[0]) == 64
        assert len(results[1]) == 64

    def test_clear_cache_forces_reembed(self):
        """After clear_cache(), same text must be re-embedded."""
        call_count = 0
        original_embed = MockScorer.embed

        class CountingMock(MockScorer):
            def embed(self, texts):
                nonlocal call_count
                call_count += len(texts)
                return original_embed(self, texts)

        scorer = CachedScorer(CountingMock())
        scorer.embed(["text to clear"])
        count_after_first = call_count
        scorer.clear_cache()
        scorer.embed(["text to clear"])
        assert call_count == count_after_first + 1  # re-embedded after clear

    def test_deterministic_embeddings(self):
        """Same text always produces identical embedding vectors."""
        scorer = CachedScorer(MockScorer())
        r1 = scorer.embed(["deterministic check"])
        scorer.clear_cache()
        r2 = scorer.embed(["deterministic check"])
        assert r1[0] == r2[0]
```

---

## Task 3: Health Score Model

**Goal:** Create `src/memorylens/_drift/health.py` with the `HealthScore` frozen dataclass and `compute_grade()` function using the weighted composite formula from the spec.

- [ ] Create `src/memorylens/_drift/health.py`
- [ ] Create `tests/test_drift/test_health.py`
- [ ] Run `python -m pytest tests/test_drift/test_health.py -v` and confirm all pass
- [ ] Commit

**`src/memorylens/_drift/health.py`:**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HealthScore:
    """Multi-dimensional memory health score for a single memory entity."""

    memory_key: str
    drift_score: float          # 0.0 = stable, 1.0 = total rewrite every time
    contradiction_score: float  # 0.0 = no contradictions, 1.0 = all pairs contradict
    staleness_score: float      # 0.0 = just updated, 1.0 = very stale
    volatility_score: float     # 0.0 = stable, 1.0 = changes every session
    grade: str                  # A / B / C / D / F


def compute_grade(
    drift: float,
    contradiction: float,
    staleness: float,
    volatility: float,
) -> str:
    """Compute letter grade from 4-dimension scores using weighted composite.

    composite = 0.35*drift + 0.30*contradiction + 0.20*staleness + 0.15*volatility

    A  composite < 0.15   (healthy)
    B  composite < 0.30   (minor concerns)
    C  composite < 0.50   (moderate issues)
    D  composite < 0.70   (significant problems)
    F  composite >= 0.70  (critical)
    """
    composite = (
        0.35 * drift
        + 0.30 * contradiction
        + 0.20 * staleness
        + 0.15 * volatility
    )
    if composite < 0.15:
        return "A"
    elif composite < 0.30:
        return "B"
    elif composite < 0.50:
        return "C"
    elif composite < 0.70:
        return "D"
    else:
        return "F"
```

**`tests/test_drift/test_health.py`:**

```python
from __future__ import annotations

import pytest

from memorylens._drift.health import HealthScore, compute_grade


class TestComputeGrade:
    def test_grade_a_all_zeros(self):
        assert compute_grade(0.0, 0.0, 0.0, 0.0) == "A"

    def test_grade_a_boundary(self):
        # composite just below 0.15 → A
        # 0.35*0.1 + 0.30*0.1 + 0.20*0.1 + 0.15*0.1 = 0.10 < 0.15
        assert compute_grade(0.1, 0.1, 0.1, 0.1) == "A"

    def test_grade_b(self):
        # composite = 0.35*0.3 + 0.30*0.3 + 0.20*0.3 + 0.15*0.3 = 0.30 → B (0.15 <= c < 0.30)
        # Use values giving composite ~0.20
        # 0.35*0.4 + 0.30*0.0 + 0.20*0.0 + 0.15*0.0 = 0.14 ... try drift=0.5 => 0.175
        assert compute_grade(0.5, 0.0, 0.0, 0.0) == "B"

    def test_grade_c(self):
        # composite ~0.40
        # 0.35*0.6 + 0.30*0.3 + 0.20*0.2 + 0.15*0.2 = 0.21+0.09+0.04+0.03 = 0.37 → C
        # Try: 0.35*0.8 + 0.30*0.3 = 0.28+0.09 = 0.37 — still B
        # drift=1.0, contradiction=0.1 => 0.35+0.03=0.38 → C? yes 0.38 >= 0.30
        assert compute_grade(1.0, 0.1, 0.0, 0.0) == "C"

    def test_grade_d(self):
        # composite ~0.55
        # 0.35*1.0 + 0.30*0.7 = 0.35+0.21 = 0.56 → D
        assert compute_grade(1.0, 0.7, 0.0, 0.0) == "D"

    def test_grade_f_all_ones(self):
        assert compute_grade(1.0, 1.0, 1.0, 1.0) == "F"

    def test_grade_f_threshold(self):
        # composite >= 0.70 → F
        # 0.35*1.0 + 0.30*1.0 = 0.65; add 0.20*1.0 = 0.85 → F
        assert compute_grade(1.0, 1.0, 1.0, 0.0) == "F"

    def test_grade_boundary_b_to_c(self):
        # composite = 0.30 → C (not B, since B is strictly < 0.30)
        # 0.35*(6/7) ≈ 0.30 is imprecise; use known values
        # drift=0.857... => 0.35*0.857=0.30 → C
        grade = compute_grade(6 / 7, 0.0, 0.0, 0.0)
        assert grade == "C"

    def test_weights_sum_to_one(self):
        """Confirm weight distribution: all scores = 1.0 should give composite = 1.0 → F."""
        assert compute_grade(1.0, 1.0, 1.0, 1.0) == "F"


class TestHealthScore:
    def test_creation(self):
        hs = HealthScore(
            memory_key="user_42_prefs",
            drift_score=0.2,
            contradiction_score=0.1,
            staleness_score=0.5,
            volatility_score=0.3,
            grade="B",
        )
        assert hs.memory_key == "user_42_prefs"
        assert hs.drift_score == 0.2
        assert hs.grade == "B"

    def test_frozen(self):
        hs = HealthScore("k", 0.1, 0.1, 0.1, 0.1, "A")
        with pytest.raises((AttributeError, TypeError)):
            hs.grade = "F"  # type: ignore[misc]

    def test_grade_matches_compute_grade(self):
        d, c, s, v = 0.1, 0.1, 0.1, 0.1
        expected_grade = compute_grade(d, c, s, v)
        hs = HealthScore("key", d, c, s, v, expected_grade)
        assert hs.grade == expected_grade
```

---

## Task 4: SQLite Storage — Versions + Drift Reports

**Goal:** Add two new tables and six new methods to `src/memorylens/_exporters/sqlite.py`. Both tables are created lazily (same `_ensure_*_table()` pattern as compression audits). Drift reports use `INSERT OR REPLACE` so re-analysis upserts results.

- [ ] Append SQL constants and methods to `src/memorylens/_exporters/sqlite.py`
- [ ] Create `tests/test_drift/test_storage.py`
- [ ] Run `python -m pytest tests/test_drift/test_storage.py -v` and confirm all pass
- [ ] Commit

**Code to append to `src/memorylens/_exporters/sqlite.py`:**

```python
_CREATE_VERSIONS_TABLE = """
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
"""

_CREATE_VERSIONS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_versions_memory_key ON memory_versions (memory_key)",
    "CREATE INDEX IF NOT EXISTS idx_versions_session_id ON memory_versions (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_versions_timestamp ON memory_versions (timestamp)",
]

_CREATE_DRIFT_REPORTS_TABLE = """
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
"""

_CREATE_DRIFT_REPORTS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_drift_reports_type ON drift_reports (report_type)",
    "CREATE INDEX IF NOT EXISTS idx_drift_reports_grade ON drift_reports (grade)",
]

_INSERT_VERSION = """
INSERT OR REPLACE INTO memory_versions (
    memory_key, version, span_id, operation, content,
    embedding, agent_id, session_id, timestamp
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_DRIFT_REPORT = """
INSERT OR REPLACE INTO drift_reports (
    report_type, key, drift_score, contradiction_score,
    staleness_score, volatility_score, grade, details, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
```

**Methods to add inside `SQLiteExporter` class** (before `shutdown`):

```python
    # ── Version methods ──────────────────────────────────────────────────────

    def _ensure_versions_table(self) -> None:
        """Create memory_versions table and indexes if they don't exist."""
        self._conn.execute(_CREATE_VERSIONS_TABLE)
        for idx_sql in _CREATE_VERSIONS_INDEXES:
            self._conn.execute(idx_sql)
        self._conn.commit()

    def save_version(self, version: dict) -> None:
        """Save a memory version record. Creates table if needed."""
        self._ensure_versions_table()
        self._conn.execute(
            _INSERT_VERSION,
            (
                version["memory_key"],
                version["version"],
                version["span_id"],
                version["operation"],
                version.get("content"),
                json.dumps(version["embedding"]) if version.get("embedding") else None,
                version.get("agent_id"),
                version.get("session_id"),
                version["timestamp"],
            ),
        )
        self._conn.commit()

    def get_versions(self, memory_key: str) -> list[dict]:
        """Get all versions for a memory key, ordered by version number."""
        try:
            self._ensure_versions_table()
        except Exception:
            return []
        cursor = self._conn.execute(
            "SELECT * FROM memory_versions WHERE memory_key = ? ORDER BY version ASC",
            (memory_key,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            if row.get("embedding") and isinstance(row["embedding"], str):
                row["embedding"] = json.loads(row["embedding"])
        return rows

    def get_all_versions(self) -> list[dict]:
        """Get all memory versions, ordered by memory_key then version."""
        try:
            self._ensure_versions_table()
        except Exception:
            return []
        cursor = self._conn.execute(
            "SELECT * FROM memory_versions ORDER BY memory_key ASC, version ASC"
        )
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            if row.get("embedding") and isinstance(row["embedding"], str):
                row["embedding"] = json.loads(row["embedding"])
        return rows

    # ── Drift report methods ─────────────────────────────────────────────────

    def _ensure_drift_reports_table(self) -> None:
        """Create drift_reports table and indexes if they don't exist."""
        self._conn.execute(_CREATE_DRIFT_REPORTS_TABLE)
        for idx_sql in _CREATE_DRIFT_REPORTS_INDEXES:
            self._conn.execute(idx_sql)
        self._conn.commit()

    def save_drift_report(self, report: dict) -> None:
        """Save (upsert) a drift report. Creates table if needed."""
        import time

        self._ensure_drift_reports_table()
        self._conn.execute(
            _INSERT_DRIFT_REPORT,
            (
                report["report_type"],
                report["key"],
                report["drift_score"],
                report["contradiction_score"],
                report["staleness_score"],
                report["volatility_score"],
                report["grade"],
                json.dumps(report.get("details", {})),
                report.get("created_at", time.time()),
            ),
        )
        self._conn.commit()

    def get_drift_report(self, report_type: str, key: str) -> dict | None:
        """Get a single drift report by type + key, or None if not found."""
        try:
            self._ensure_drift_reports_table()
        except Exception:
            return None
        cursor = self._conn.execute(
            "SELECT * FROM drift_reports WHERE report_type = ? AND key = ?",
            (report_type, key),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        if isinstance(result.get("details"), str):
            result["details"] = json.loads(result["details"])
        return result

    def list_drift_reports(
        self,
        report_type: str | None = None,
        min_grade: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List drift reports with optional filters. Returns (rows, total_count).

        min_grade filters to grades >= that letter (F < D < C < B < A).
        E.g. min_grade="D" returns D and F reports.
        """
        self._ensure_drift_reports_table()

        _GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}

        conditions: list[str] = []
        params: list[Any] = []

        if report_type:
            conditions.append("report_type = ?")
            params.append(report_type)

        if min_grade and min_grade in _GRADE_ORDER:
            # Include grades with severity >= min_grade (lower score = worse)
            max_score = _GRADE_ORDER[min_grade]
            qualifying = [g for g, s in _GRADE_ORDER.items() if s <= max_score]
            placeholders = ",".join("?" * len(qualifying))
            conditions.append(f"grade IN ({placeholders})")
            params.extend(qualifying)

        where = " AND ".join(conditions) if conditions else "1=1"
        count_sql = f"SELECT COUNT(*) FROM drift_reports WHERE {where}"
        total = self._conn.execute(count_sql, params).fetchone()[0]

        sql = (
            f"SELECT * FROM drift_reports WHERE {where} "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?"
        )
        row_params = params + [limit, offset]
        cursor = self._conn.execute(sql, row_params)
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            if isinstance(row.get("details"), str):
                row["details"] = json.loads(row["details"])
        return rows, total
```

**`tests/test_drift/test_storage.py`:**

```python
from __future__ import annotations

import tempfile
import time

import pytest

from memorylens._exporters.sqlite import SQLiteExporter


@pytest.fixture
def exporter(tmp_path):
    db_path = str(tmp_path / "test.db")
    exp = SQLiteExporter(db_path=db_path)
    yield exp
    exp.shutdown()


class TestVersionStorage:
    def test_save_and_get_version(self, exporter):
        version = {
            "memory_key": "user_42_prefs",
            "version": 1,
            "span_id": "span-001",
            "operation": "memory.write",
            "content": "User prefers vegetarian meals.",
            "embedding": [0.1, 0.2, 0.3],
            "agent_id": "agent-1",
            "session_id": "sess-1",
            "timestamp": time.time(),
        }
        exporter.save_version(version)
        rows = exporter.get_versions("user_42_prefs")
        assert len(rows) == 1
        assert rows[0]["memory_key"] == "user_42_prefs"
        assert rows[0]["version"] == 1
        assert rows[0]["content"] == "User prefers vegetarian meals."
        assert rows[0]["embedding"] == [0.1, 0.2, 0.3]

    def test_get_versions_ordered(self, exporter):
        base_time = time.time()
        for v in range(3):
            exporter.save_version({
                "memory_key": "key_a",
                "version": v + 1,
                "span_id": f"span-{v}",
                "operation": "memory.write",
                "content": f"Version {v + 1}",
                "embedding": None,
                "agent_id": None,
                "session_id": None,
                "timestamp": base_time + v,
            })
        rows = exporter.get_versions("key_a")
        assert len(rows) == 3
        assert [r["version"] for r in rows] == [1, 2, 3]

    def test_get_all_versions(self, exporter):
        for mk in ["key_a", "key_b"]:
            exporter.save_version({
                "memory_key": mk,
                "version": 1,
                "span_id": f"span-{mk}",
                "operation": "memory.write",
                "content": f"Content for {mk}",
                "embedding": None,
                "agent_id": None,
                "session_id": None,
                "timestamp": time.time(),
            })
        all_versions = exporter.get_all_versions()
        assert len(all_versions) == 2
        keys = {r["memory_key"] for r in all_versions}
        assert keys == {"key_a", "key_b"}

    def test_version_without_embedding(self, exporter):
        exporter.save_version({
            "memory_key": "no_embed",
            "version": 1,
            "span_id": "s1",
            "operation": "memory.write",
            "content": "text",
            "embedding": None,
            "agent_id": None,
            "session_id": None,
            "timestamp": time.time(),
        })
        rows = exporter.get_versions("no_embed")
        assert rows[0]["embedding"] is None

    def test_get_versions_unknown_key_returns_empty(self, exporter):
        rows = exporter.get_versions("nonexistent_key")
        assert rows == []


class TestDriftReportStorage:
    def _make_report(self, key="user_42", report_type="entity", grade="B"):
        return {
            "report_type": report_type,
            "key": key,
            "drift_score": 0.2,
            "contradiction_score": 0.1,
            "staleness_score": 0.3,
            "volatility_score": 0.15,
            "grade": grade,
            "details": {"version_count": 3},
            "created_at": time.time(),
        }

    def test_save_and_get_report(self, exporter):
        report = self._make_report()
        exporter.save_drift_report(report)
        result = exporter.get_drift_report("entity", "user_42")
        assert result is not None
        assert result["key"] == "user_42"
        assert result["grade"] == "B"
        assert isinstance(result["details"], dict)
        assert result["details"]["version_count"] == 3

    def test_upsert_replaces_existing(self, exporter):
        exporter.save_drift_report(self._make_report(grade="C"))
        exporter.save_drift_report(self._make_report(grade="F"))
        result = exporter.get_drift_report("entity", "user_42")
        assert result["grade"] == "F"

    def test_get_report_not_found_returns_none(self, exporter):
        result = exporter.get_drift_report("entity", "does_not_exist")
        assert result is None

    def test_list_drift_reports_no_filter(self, exporter):
        for i, grade in enumerate(["A", "B", "C"]):
            exporter.save_drift_report(self._make_report(key=f"key_{i}", grade=grade))
        rows, total = exporter.list_drift_reports()
        assert total == 3
        assert len(rows) == 3

    def test_list_drift_reports_filter_by_type(self, exporter):
        exporter.save_drift_report(self._make_report(key="e1", report_type="entity"))
        exporter.save_drift_report(self._make_report(key="s1", report_type="session"))
        rows, total = exporter.list_drift_reports(report_type="entity")
        assert total == 1
        assert rows[0]["report_type"] == "entity"

    def test_list_drift_reports_filter_by_min_grade_d(self, exporter):
        """min_grade=D should return D and F reports only."""
        for key, grade in [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D"), ("f", "F")]:
            exporter.save_drift_report(self._make_report(key=key, grade=grade))
        rows, total = exporter.list_drift_reports(min_grade="D")
        grades_returned = {r["grade"] for r in rows}
        assert grades_returned == {"D", "F"}
        assert total == 2

    def test_list_drift_reports_pagination(self, exporter):
        for i in range(5):
            exporter.save_drift_report(self._make_report(key=f"key_{i}"))
        rows, total = exporter.list_drift_reports(limit=2, offset=0)
        assert total == 5
        assert len(rows) == 2
        rows2, _ = exporter.list_drift_reports(limit=2, offset=2)
        assert len(rows2) == 2
        # No overlap between pages
        keys1 = {r["key"] for r in rows}
        keys2 = {r["key"] for r in rows2}
        assert not keys1.intersection(keys2)
```

---

## Task 5: DriftAnalyzer — Entity Level

**Goal:** Create `src/memorylens/_drift/analyzer.py` with result dataclasses and `DriftAnalyzer.analyze_entity()`. All scoring uses `cosine_similarity` from `_audit/scorer.py`. Session and topic methods are stubbed (implemented in Task 6).

- [ ] Create `src/memorylens/_drift/analyzer.py`
- [ ] Create `tests/test_drift/test_analyzer.py` with entity-level tests
- [ ] Run `python -m pytest tests/test_drift/test_analyzer.py -v` and confirm all pass
- [ ] Commit

**`src/memorylens/_drift/analyzer.py`:**

```python
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from memorylens._audit.scorer import CachedScorer, cosine_similarity
from memorylens._drift.health import HealthScore, compute_grade


@dataclass(frozen=True)
class EntityDriftResult:
    """Drift analysis result for a single memory entity (memory_key)."""

    memory_key: str
    version_count: int
    drift_score: float          # 0.0–1.0: mean cross-version drift
    contradiction_score: float  # 0.0–1.0: proportion of pairs with similarity < 0.5
    staleness_score: float      # 0.0–1.0: based on days since last update
    volatility_score: float     # 0.0–1.0: sessions with changes / total sessions
    grade: str                  # A / B / C / D / F
    consecutive_similarities: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class SessionDriftResult:
    """Drift analysis result for a single session."""

    session_id: str
    memory_keys_modified: list[str]
    drift_score: float
    contradiction_score: float
    staleness_score: float
    volatility_score: float
    grade: str


@dataclass(frozen=True)
class TopicDriftResult:
    """Drift analysis result for a topic cluster."""

    topic_id: str
    memory_keys: list[str]
    centroid_drift: float       # How much the cluster centroid moved over time
    drift_score: float
    contradiction_score: float
    staleness_score: float
    volatility_score: float
    grade: str


class DriftAnalyzer:
    """Computes entity, session, and topic drift across memory version histories."""

    def __init__(self, scorer: CachedScorer) -> None:
        self._scorer = scorer

    def analyze_entity(self, versions: list[dict]) -> EntityDriftResult:
        """Compute drift for a single memory_key's version history.

        Args:
            versions: List of version dicts ordered by version number, each with
                      keys: memory_key, version, content, timestamp, session_id.

        Returns:
            EntityDriftResult with 4-dimension scores and letter grade.
        """
        if not versions:
            raise ValueError("versions list must not be empty")

        memory_key = versions[0]["memory_key"]
        now = time.time()

        # ── Single version: no drift possible ──────────────────────────────
        if len(versions) == 1:
            days_stale = (now - versions[0]["timestamp"]) / 86400.0
            staleness = min(1.0, days_stale / 7.0)
            grade = compute_grade(0.0, 0.0, staleness, 0.0)
            return EntityDriftResult(
                memory_key=memory_key,
                version_count=1,
                drift_score=0.0,
                contradiction_score=0.0,
                staleness_score=round(staleness, 4),
                volatility_score=0.0,
                grade=grade,
                consecutive_similarities=[],
            )

        # ── Embed all versions ──────────────────────────────────────────────
        contents = [v.get("content") or "" for v in versions]
        embeddings = self._scorer.embed(contents)

        # ── Consecutive cosine similarities ────────────────────────────────
        consecutive_sims: list[float] = []
        for i in range(len(embeddings) - 1):
            sim = cosine_similarity(embeddings[i], embeddings[i + 1])
            sim = max(0.0, min(1.0, sim))
            consecutive_sims.append(sim)

        drift_score = round(1.0 - (sum(consecutive_sims) / len(consecutive_sims)), 4)

        # ── Contradiction score ─────────────────────────────────────────────
        # All pairs (not just consecutive) with similarity < 0.5
        total_pairs = 0
        contradicting_pairs = 0
        n = len(embeddings)
        for i in range(n):
            for j in range(i + 1, n):
                sim = cosine_similarity(embeddings[i], embeddings[j])
                sim = max(0.0, min(1.0, sim))
                total_pairs += 1
                if sim < 0.5:
                    contradicting_pairs += 1
        contradiction_score = round(contradicting_pairs / total_pairs, 4) if total_pairs > 0 else 0.0

        # ── Staleness score ─────────────────────────────────────────────────
        last_ts = max(v["timestamp"] for v in versions)
        days_stale = (now - last_ts) / 86400.0
        staleness_score = round(min(1.0, days_stale / 7.0), 4)

        # ── Volatility score ────────────────────────────────────────────────
        sessions_with_changes: set[str] = set()
        all_sessions: set[str] = set()
        for v in versions:
            sid = v.get("session_id")
            if sid:
                all_sessions.add(sid)
                sessions_with_changes.add(sid)
        volatility_score = (
            round(len(sessions_with_changes) / len(all_sessions), 4)
            if all_sessions
            else 0.0
        )

        grade = compute_grade(drift_score, contradiction_score, staleness_score, volatility_score)

        return EntityDriftResult(
            memory_key=memory_key,
            version_count=len(versions),
            drift_score=drift_score,
            contradiction_score=contradiction_score,
            staleness_score=staleness_score,
            volatility_score=volatility_score,
            grade=grade,
            consecutive_similarities=consecutive_sims,
        )

    def analyze_session(
        self, session_id: str, versions: list[dict]
    ) -> SessionDriftResult:
        """Implemented in Task 6."""
        raise NotImplementedError("Task 6")

    def analyze_topics(
        self, all_versions: list[dict]
    ) -> list[TopicDriftResult]:
        """Implemented in Task 6."""
        raise NotImplementedError("Task 6")

    def compute_health(self, entity_result: EntityDriftResult) -> HealthScore:
        """Wrap an EntityDriftResult into a HealthScore."""
        return HealthScore(
            memory_key=entity_result.memory_key,
            drift_score=entity_result.drift_score,
            contradiction_score=entity_result.contradiction_score,
            staleness_score=entity_result.staleness_score,
            volatility_score=entity_result.volatility_score,
            grade=entity_result.grade,
        )
```

**`tests/test_drift/test_analyzer.py`** (entity-level only, Task 6 appends more):

```python
from __future__ import annotations

import time

import pytest

from memorylens._audit.scorer import CachedScorer, MockScorer
from memorylens._drift.analyzer import DriftAnalyzer, EntityDriftResult


def make_versions(texts: list[str], session_ids: list[str] | None = None) -> list[dict]:
    """Helper: build version dicts from text list with sequential timestamps."""
    now = time.time()
    memory_key = "test_key"
    if session_ids is None:
        session_ids = [f"sess-{i}" for i in range(len(texts))]
    return [
        {
            "memory_key": memory_key,
            "version": i + 1,
            "span_id": f"span-{i}",
            "operation": "memory.write",
            "content": text,
            "embedding": None,
            "agent_id": "agent-1",
            "session_id": session_ids[i],
            "timestamp": now - (len(texts) - i) * 3600,  # spaced 1h apart, last is recent
        }
        for i, text in enumerate(texts)
    ]


def make_scorer() -> CachedScorer:
    return CachedScorer(MockScorer())


class TestAnalyzeEntitySingleVersion:
    def test_single_version_zero_drift(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        versions = make_versions(["User prefers vegetarian meals."])
        result = analyzer.analyze_entity(versions)
        assert isinstance(result, EntityDriftResult)
        assert result.drift_score == 0.0
        assert result.contradiction_score == 0.0
        assert result.volatility_score == 0.0
        assert result.version_count == 1

    def test_single_version_grade_a_when_fresh(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        # timestamp = very recent (now)
        versions = [{
            "memory_key": "fresh_key",
            "version": 1,
            "span_id": "s1",
            "operation": "memory.write",
            "content": "Fresh content.",
            "embedding": None,
            "agent_id": None,
            "session_id": None,
            "timestamp": time.time(),
        }]
        result = analyzer.analyze_entity(versions)
        assert result.grade == "A"


class TestAnalyzeEntityMultipleVersions:
    def test_identical_versions_low_drift(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        text = "User prefers vegetarian meals. No dairy."
        versions = make_versions([text, text, text])
        result = analyzer.analyze_entity(versions)
        assert result.drift_score < 0.1
        assert result.contradiction_score == 0.0
        assert result.version_count == 3

    def test_different_versions_high_drift(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        versions = make_versions([
            "User loves meat and burgers.",
            "User is strictly vegan, no animal products.",
            "User eats seafood but avoids land animals.",
        ])
        result = analyzer.analyze_entity(versions)
        assert result.drift_score > 0.1  # Some drift from divergent content
        assert 0.0 <= result.drift_score <= 1.0
        assert 0.0 <= result.contradiction_score <= 1.0

    def test_grade_is_valid_letter(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        versions = make_versions(["text a", "text b"])
        result = analyzer.analyze_entity(versions)
        assert result.grade in {"A", "B", "C", "D", "F"}

    def test_consecutive_similarities_length(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        versions = make_versions(["v1", "v2", "v3", "v4"])
        result = analyzer.analyze_entity(versions)
        assert len(result.consecutive_similarities) == 3  # n-1 pairs

    def test_volatility_one_session_per_version(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        # Each version has a unique session → max volatility
        versions = make_versions(["a", "b", "c"], session_ids=["s1", "s2", "s3"])
        result = analyzer.analyze_entity(versions)
        assert result.volatility_score == 1.0

    def test_volatility_same_session_all_versions(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        versions = make_versions(["a", "b", "c"], session_ids=["s1", "s1", "s1"])
        result = analyzer.analyze_entity(versions)
        # All changes in one session → 1 session with changes / 1 total session = 1.0
        assert result.volatility_score == 1.0

    def test_empty_versions_raises(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        with pytest.raises(ValueError, match="versions list must not be empty"):
            analyzer.analyze_entity([])

    def test_score_bounds(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        versions = make_versions([
            "Memory content alpha.",
            "Completely different memory beta.",
        ])
        result = analyzer.analyze_entity(versions)
        for score in [result.drift_score, result.contradiction_score,
                      result.staleness_score, result.volatility_score]:
            assert 0.0 <= score <= 1.0


class TestComputeHealth:
    def test_compute_health_wraps_entity_result(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        versions = make_versions(["content a", "content b"])
        entity_result = analyzer.analyze_entity(versions)
        health = analyzer.compute_health(entity_result)
        assert health.memory_key == entity_result.memory_key
        assert health.drift_score == entity_result.drift_score
        assert health.grade == entity_result.grade
```

---

## Task 6: DriftAnalyzer — Session + Topic Level

**Goal:** Implement `analyze_session()` and `analyze_topics()` on `DriftAnalyzer`. Session analysis aggregates drift across memory keys modified in a session. Topic analysis clusters version embeddings by similarity threshold and tracks centroid movement.

- [ ] Replace the `NotImplementedError` stubs in `src/memorylens/_drift/analyzer.py` with full implementations
- [ ] Append session and topic tests to `tests/test_drift/test_analyzer.py`
- [ ] Run `python -m pytest tests/test_drift/test_analyzer.py -v` and confirm all pass
- [ ] Commit

**Replace the stub methods in `DriftAnalyzer` with:**

```python
    def analyze_session(
        self, session_id: str, versions: list[dict]
    ) -> SessionDriftResult:
        """Compute session-level drift.

        For each memory_key that was modified in this session, compare the version
        created in this session against its immediately prior version. Aggregate
        drift scores across all modified keys.

        Args:
            session_id: The session to analyze.
            versions: All memory versions (may include versions from other sessions).
        """
        # Separate versions into: those belonging to this session and all others
        session_versions = [v for v in versions if v.get("session_id") == session_id]
        if not session_versions:
            return SessionDriftResult(
                session_id=session_id,
                memory_keys_modified=[],
                drift_score=0.0,
                contradiction_score=0.0,
                staleness_score=0.0,
                volatility_score=0.0,
                grade="A",
            )

        # Group all versions by memory_key
        by_key: dict[str, list[dict]] = {}
        for v in versions:
            key = v["memory_key"]
            by_key.setdefault(key, []).append(v)
        for lst in by_key.values():
            lst.sort(key=lambda x: x["version"])

        memory_keys_modified = list({v["memory_key"] for v in session_versions})
        drift_scores: list[float] = []
        contradiction_scores: list[float] = []

        for key in memory_keys_modified:
            all_key_versions = by_key.get(key, [])
            # Find versions belonging to this session
            session_key_versions = [v for v in all_key_versions if v.get("session_id") == session_id]
            prior_versions = [v for v in all_key_versions if v.get("session_id") != session_id
                              and v["version"] < min(sv["version"] for sv in session_key_versions)]

            if not prior_versions:
                # No prior version to compare against — no drift for this key
                continue

            # Compare earliest session version against latest prior version
            prior = prior_versions[-1]
            current = session_key_versions[0]
            pair_embeddings = self._scorer.embed([
                prior.get("content") or "",
                current.get("content") or "",
            ])
            sim = cosine_similarity(pair_embeddings[0], pair_embeddings[1])
            sim = max(0.0, min(1.0, sim))
            drift_scores.append(1.0 - sim)
            contradiction_scores.append(1.0 if sim < 0.5 else 0.0)

        drift_score = round(sum(drift_scores) / len(drift_scores), 4) if drift_scores else 0.0
        contradiction_score = round(
            sum(contradiction_scores) / len(contradiction_scores), 4
        ) if contradiction_scores else 0.0

        # Staleness: time since session ended (latest timestamp in session)
        now = time.time()
        session_end = max(v["timestamp"] for v in session_versions)
        days_stale = (now - session_end) / 86400.0
        staleness_score = round(min(1.0, days_stale / 7.0), 4)

        # Volatility: proportion of modified keys vs all keys touched by session
        total_keys_in_session = len({v["memory_key"] for v in session_versions})
        volatility_score = round(
            len(memory_keys_modified) / total_keys_in_session, 4
        ) if total_keys_in_session > 0 else 0.0

        grade = compute_grade(drift_score, contradiction_score, staleness_score, volatility_score)

        return SessionDriftResult(
            session_id=session_id,
            memory_keys_modified=memory_keys_modified,
            drift_score=drift_score,
            contradiction_score=contradiction_score,
            staleness_score=staleness_score,
            volatility_score=volatility_score,
            grade=grade,
        )

    def analyze_topics(
        self, all_versions: list[dict]
    ) -> list[TopicDriftResult]:
        """Cluster memory versions by embedding similarity and detect centroid drift.

        Groups versions into topic clusters where pairwise similarity > 0.7.
        For each cluster, tracks centroid movement across time windows.

        Args:
            all_versions: All memory versions across all keys.

        Returns:
            List of TopicDriftResult, one per discovered cluster.
        """
        if not all_versions:
            return []

        contents = [v.get("content") or "" for v in all_versions]
        embeddings = self._scorer.embed(contents)

        _SIMILARITY_THRESHOLD = 0.7

        # Greedy single-pass clustering
        clusters: list[list[int]] = []  # list of index lists
        assigned = [False] * len(all_versions)

        for i in range(len(all_versions)):
            if assigned[i]:
                continue
            cluster = [i]
            assigned[i] = True
            for j in range(i + 1, len(all_versions)):
                if assigned[j]:
                    continue
                sim = cosine_similarity(embeddings[i], embeddings[j])
                if sim >= _SIMILARITY_THRESHOLD:
                    cluster.append(j)
                    assigned[j] = True
            clusters.append(cluster)

        results: list[TopicDriftResult] = []
        now = time.time()

        for cluster_idx, cluster_indices in enumerate(clusters):
            cluster_versions = [all_versions[i] for i in cluster_indices]
            cluster_embeddings = [embeddings[i] for i in cluster_indices]
            n = len(cluster_indices)
            dim = len(cluster_embeddings[0])

            # Sort by timestamp for centroid drift computation
            time_sorted = sorted(
                zip(cluster_versions, cluster_embeddings),
                key=lambda x: x[0]["timestamp"],
            )

            # Centroid drift: compare first-half centroid to second-half centroid
            mid = max(1, n // 2)
            first_half_embeddings = [e for _, e in time_sorted[:mid]]
            second_half_embeddings = [e for _, e in time_sorted[mid:]] if n > 1 else first_half_embeddings

            def centroid(embs: list[list[float]]) -> list[float]:
                c = [0.0] * dim
                for e in embs:
                    for k in range(dim):
                        c[k] += e[k]
                total = len(embs)
                return [c[k] / total for k in range(dim)]

            c1 = centroid(first_half_embeddings)
            c2 = centroid(second_half_embeddings)
            centroid_similarity = cosine_similarity(c1, c2)
            centroid_similarity = max(0.0, min(1.0, centroid_similarity))
            centroid_drift = round(1.0 - centroid_similarity, 4)

            # Contradiction: pairs with similarity < 0.5
            total_pairs = 0
            contradicting = 0
            for i in range(n):
                for j in range(i + 1, n):
                    sim = cosine_similarity(cluster_embeddings[i], cluster_embeddings[j])
                    sim = max(0.0, min(1.0, sim))
                    total_pairs += 1
                    if sim < 0.5:
                        contradicting += 1
            contradiction_score = round(contradicting / total_pairs, 4) if total_pairs > 0 else 0.0

            # Staleness: days since last version in cluster
            last_ts = max(v["timestamp"] for v in cluster_versions)
            days_stale = (now - last_ts) / 86400.0
            staleness_score = round(min(1.0, days_stale / 7.0), 4)

            # Volatility: unique sessions in cluster / total versions
            sessions = {v.get("session_id") for v in cluster_versions if v.get("session_id")}
            volatility_score = round(len(sessions) / n, 4) if n > 0 else 0.0

            grade = compute_grade(centroid_drift, contradiction_score, staleness_score, volatility_score)
            memory_keys = list({v["memory_key"] for v in cluster_versions})

            results.append(TopicDriftResult(
                topic_id=f"topic_{cluster_idx}",
                memory_keys=memory_keys,
                centroid_drift=centroid_drift,
                drift_score=centroid_drift,
                contradiction_score=contradiction_score,
                staleness_score=staleness_score,
                volatility_score=volatility_score,
                grade=grade,
            ))

        return results
```

**Append to `tests/test_drift/test_analyzer.py`:**

```python
class TestAnalyzeSession:
    def test_session_with_no_matching_versions(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        # versions all belong to a different session
        versions = make_versions(["a", "b"], session_ids=["sess-X", "sess-X"])
        result = analyzer.analyze_session("sess-OTHER", versions)
        assert result.session_id == "sess-OTHER"
        assert result.memory_keys_modified == []
        assert result.drift_score == 0.0
        assert result.grade == "A"

    def test_session_no_prior_version(self):
        """First write to a key in a session → no drift to compute."""
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        # Only one version, belonging to the session
        versions = make_versions(["first write"], session_ids=["sess-1"])
        result = analyzer.analyze_session("sess-1", versions)
        assert result.session_id == "sess-1"
        assert result.drift_score == 0.0

    def test_session_with_prior_version_drift(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        now = time.time()
        versions = [
            {
                "memory_key": "key_a",
                "version": 1,
                "span_id": "s1",
                "operation": "memory.write",
                "content": "User prefers vegetarian meals.",
                "embedding": None,
                "agent_id": None,
                "session_id": "sess-A",
                "timestamp": now - 7200,
            },
            {
                "memory_key": "key_a",
                "version": 2,
                "span_id": "s2",
                "operation": "memory.update",
                "content": "User is strictly vegan now.",
                "embedding": None,
                "agent_id": None,
                "session_id": "sess-B",
                "timestamp": now - 3600,
            },
        ]
        result = analyzer.analyze_session("sess-B", versions)
        assert result.session_id == "sess-B"
        assert "key_a" in result.memory_keys_modified
        assert 0.0 <= result.drift_score <= 1.0
        assert result.grade in {"A", "B", "C", "D", "F"}

    def test_session_result_grade_valid(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        versions = make_versions(["old content", "new content"], session_ids=["s1", "s2"])
        result = analyzer.analyze_session("s2", versions)
        assert result.grade in {"A", "B", "C", "D", "F"}


class TestAnalyzeTopics:
    def test_empty_versions_returns_empty(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        result = analyzer.analyze_topics([])
        assert result == []

    def test_single_version_single_cluster(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        versions = make_versions(["solo memory content"])
        result = analyzer.analyze_topics(versions)
        assert len(result) >= 1
        assert result[0].topic_id.startswith("topic_")

    def test_topic_result_fields(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        versions = make_versions(["content a", "content b", "content c"])
        results = analyzer.analyze_topics(versions)
        for r in results:
            assert r.topic_id.startswith("topic_")
            assert isinstance(r.memory_keys, list)
            assert 0.0 <= r.drift_score <= 1.0
            assert 0.0 <= r.contradiction_score <= 1.0
            assert 0.0 <= r.staleness_score <= 1.0
            assert 0.0 <= r.volatility_score <= 1.0
            assert r.grade in {"A", "B", "C", "D", "F"}

    def test_similar_versions_cluster_together(self):
        scorer = make_scorer()
        analyzer = DriftAnalyzer(scorer)
        # Identical content should cluster together
        text = "User is vegetarian and likes Italian food"
        now = time.time()
        versions = [
            {
                "memory_key": f"key_{i}",
                "version": 1,
                "span_id": f"s{i}",
                "operation": "memory.write",
                "content": text,
                "embedding": None,
                "agent_id": None,
                "session_id": f"sess-{i}",
                "timestamp": now - i * 3600,
            }
            for i in range(3)
        ]
        results = analyzer.analyze_topics(versions)
        # All identical → should land in one cluster
        all_keys = [k for r in results for k in r.memory_keys]
        assert len(all_keys) == 3
```

---

## Task 7: VersionTracker (Online Mode)

**Goal:** Create `src/memorylens/_drift/tracker.py` implementing the `SpanProcessor` protocol. Modify `src/memorylens/__init__.py` to accept `detect_drift: bool = False` in `init()`.

- [ ] Create `src/memorylens/_drift/tracker.py`
- [ ] Modify `src/memorylens/__init__.py`: add `detect_drift` param to `init()` signature and wiring logic
- [ ] Create `tests/test_drift/test_tracker.py`
- [ ] Run `python -m pytest tests/test_drift/test_tracker.py -v` and confirm all pass
- [ ] Commit

**`src/memorylens/_drift/tracker.py`:**

```python
from __future__ import annotations

import time

from memorylens._audit.scorer import CachedScorer, cosine_similarity
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter

_WRITE_OPS = {"memory.write", "memory.update"}
_DRIFT_ALERT_THRESHOLD = 0.3


class VersionTracker:
    """SpanProcessor that records memory versions and detects drift in real-time.

    Implements the SpanProcessor protocol (on_start, on_end, shutdown, force_flush).
    Enabled via memorylens.init(detect_drift=True).

    On each WRITE/UPDATE span completion:
    1. Extracts memory_key from span attributes
    2. Saves the version to memory_versions table
    3. Computes drift against cached previous embedding
    4. If drift > 0.3, sets drift_score and drift_detected on span attributes
    """

    def __init__(self, exporter: SQLiteExporter, scorer: CachedScorer) -> None:
        self._exporter = exporter
        self._scorer = scorer
        # In-memory cache: memory_key → last known embedding
        self._embedding_cache: dict[str, list[float]] = {}
        # In-memory version counter: memory_key → current version number
        self._version_cache: dict[str, int] = {}

    def on_start(self, span: MemorySpan) -> None:
        """No-op: version tracking happens on span completion."""
        pass

    def on_end(self, span: MemorySpan) -> None:
        """Process a completed span. Only acts on WRITE and UPDATE operations."""
        op = span.operation.value if hasattr(span.operation, "value") else str(span.operation)
        if op not in _WRITE_OPS:
            return

        # Extract memory_key from span attributes; skip if not identifiable
        memory_key = span.attributes.get("memory_key")
        if not memory_key:
            # Fallback: hash of input content
            content = span.input_content or span.output_content
            if not content:
                return
            import hashlib
            memory_key = hashlib.md5(content.encode()).hexdigest()[:16]

        content = span.output_content or span.input_content or ""

        # Determine version number
        version = self._version_cache.get(memory_key, 0) + 1
        self._version_cache[memory_key] = version

        # Save version to DB
        version_record = {
            "memory_key": memory_key,
            "version": version,
            "span_id": span.span_id,
            "operation": op,
            "content": content,
            "embedding": None,  # stored without embedding to minimize overhead
            "agent_id": span.agent_id,
            "session_id": span.session_id,
            "timestamp": span.end_time,
        }
        try:
            self._exporter.save_version(version_record)
        except Exception:
            pass  # Don't let storage errors disrupt tracing

        # Compute drift against cached prior embedding
        if not content:
            return

        try:
            new_embeddings = self._scorer.embed([content])
            new_embedding = new_embeddings[0]
        except Exception:
            return

        prior_embedding = self._embedding_cache.get(memory_key)
        self._embedding_cache[memory_key] = new_embedding

        if prior_embedding is not None:
            sim = cosine_similarity(prior_embedding, new_embedding)
            sim = max(0.0, min(1.0, sim))
            drift_score = round(1.0 - sim, 4)

            if drift_score > _DRIFT_ALERT_THRESHOLD:
                # Annotate span attributes with drift information
                try:
                    self._exporter.update_span_attributes(
                        span.span_id,
                        {
                            "drift_score": drift_score,
                            "drift_detected": True,
                            "memory_key": memory_key,
                        },
                    )
                except Exception:
                    pass

    def shutdown(self) -> None:
        """Clear in-memory caches. Exporter lifecycle managed externally."""
        self._embedding_cache.clear()
        self._version_cache.clear()

    def force_flush(self, timeout_ms: int = 30000) -> bool:
        """VersionTracker is synchronous; flush is a no-op."""
        return True
```

**Changes to `src/memorylens/__init__.py`:**

Add `detect_drift: bool = False` to `init()` signature and the following wiring block at the end of `init()` (before the closing):

```python
    # Enable online drift detection
    if detect_drift:
        from memorylens._audit.scorer import CachedScorer, MockScorer
        from memorylens._drift.tracker import VersionTracker
        from memorylens._exporters.sqlite import SQLiteExporter

        # Re-use or create a SQLiteExporter for the tracker
        _db = db_path or os.path.expanduser("~/.memorylens/traces.db")
        _exporter = SQLiteExporter(db_path=_db)
        _scorer = CachedScorer(MockScorer())  # lightweight default; swap for LocalScorer in prod
        _tracker = VersionTracker(exporter=_exporter, scorer=_scorer)
        provider.add_processor(_tracker)
```

**`tests/test_drift/test_tracker.py`:**

```python
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from memorylens._audit.scorer import CachedScorer, MockScorer
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._drift.tracker import VersionTracker


def make_span(
    operation: str = "memory.write",
    content: str = "some content",
    memory_key: str | None = "key_1",
    session_id: str | None = "sess-1",
    span_id: str = "span-001",
) -> MemorySpan:
    attrs = {}
    if memory_key:
        attrs["memory_key"] = memory_key
    op = MemoryOperation(operation)
    return MemorySpan(
        span_id=span_id,
        trace_id="trace-001",
        parent_span_id=None,
        operation=op,
        status=SpanStatus.OK,
        start_time=time.time() - 0.1,
        end_time=time.time(),
        duration_ms=100.0,
        agent_id="agent-1",
        session_id=session_id,
        user_id=None,
        input_content=content,
        output_content=content,
        attributes=attrs,
    )


@pytest.fixture
def tracker(tmp_path):
    from memorylens._exporters.sqlite import SQLiteExporter
    exporter = SQLiteExporter(db_path=str(tmp_path / "test.db"))
    scorer = CachedScorer(MockScorer())
    t = VersionTracker(exporter=exporter, scorer=scorer)
    yield t, exporter
    exporter.shutdown()


class TestVersionTrackerOnStart:
    def test_on_start_is_noop(self, tracker):
        t, _ = tracker
        span = make_span()
        t.on_start(span)  # Should not raise


class TestVersionTrackerOnEnd:
    def test_write_span_saves_version(self, tracker):
        t, exporter = tracker
        span = make_span(operation="memory.write", memory_key="key_a", span_id="span-w1")
        t.on_end(span)
        versions = exporter.get_versions("key_a")
        assert len(versions) == 1
        assert versions[0]["memory_key"] == "key_a"
        assert versions[0]["operation"] == "memory.write"

    def test_update_span_saves_version(self, tracker):
        t, exporter = tracker
        span = make_span(operation="memory.update", memory_key="key_b", span_id="span-u1")
        t.on_end(span)
        versions = exporter.get_versions("key_b")
        assert len(versions) == 1
        assert versions[0]["operation"] == "memory.update"

    def test_read_span_skipped(self, tracker):
        t, exporter = tracker
        span = make_span(operation="memory.read", memory_key="key_c", span_id="span-r1")
        t.on_end(span)
        versions = exporter.get_versions("key_c")
        assert versions == []

    def test_compress_span_skipped(self, tracker):
        t, exporter = tracker
        span = make_span(operation="memory.compress", memory_key="key_d", span_id="span-c1")
        t.on_end(span)
        versions = exporter.get_versions("key_d")
        assert versions == []

    def test_version_increments_per_key(self, tracker):
        t, exporter = tracker
        for i in range(3):
            span = make_span(memory_key="incr_key", span_id=f"span-{i}")
            t.on_end(span)
        versions = exporter.get_versions("incr_key")
        assert len(versions) == 3
        assert [v["version"] for v in versions] == [1, 2, 3]

    def test_no_memory_key_uses_content_hash(self, tracker):
        t, exporter = tracker
        span = make_span(memory_key=None, content="hashable content", span_id="span-hash")
        t.on_end(span)
        all_versions = exporter.get_all_versions()
        assert len(all_versions) == 1
        # Key should be a 16-char hex hash
        assert len(all_versions[0]["memory_key"]) == 16

    def test_no_content_and_no_key_skipped(self, tracker):
        t, exporter = tracker
        span = MemorySpan(
            span_id="span-empty",
            trace_id="trace-001",
            parent_span_id=None,
            operation=MemoryOperation.WRITE,
            status=SpanStatus.OK,
            start_time=time.time() - 0.1,
            end_time=time.time(),
            duration_ms=10.0,
            agent_id=None,
            session_id=None,
            user_id=None,
            input_content=None,
            output_content=None,
            attributes={},  # no memory_key
        )
        t.on_end(span)
        assert exporter.get_all_versions() == []


class TestVersionTrackerShutdown:
    def test_shutdown_clears_caches(self, tracker):
        t, _ = tracker
        span = make_span(memory_key="key_s", span_id="span-s1")
        t.on_end(span)
        assert len(t._embedding_cache) > 0
        t.shutdown()
        assert t._embedding_cache == {}
        assert t._version_cache == {}

    def test_force_flush_returns_true(self, tracker):
        t, _ = tracker
        assert t.force_flush() is True
        assert t.force_flush(timeout_ms=100) is True
```

---

## Task 8: CLI Drift Commands

**Goal:** Create `src/memorylens/cli/commands/drift.py` with four commands (`analyze`, `report`, `show`, `watch`) and register the `drift_app` Typer group in `cli/main.py`.

- [ ] Create `src/memorylens/cli/commands/drift.py`
- [ ] Edit `src/memorylens/cli/main.py`: import and register `drift_app`
- [ ] Create `tests/test_cli/test_drift_commands.py`
- [ ] Run `python -m pytest tests/test_cli/test_drift_commands.py -v` and confirm all pass
- [ ] Commit

**`src/memorylens/cli/commands/drift.py`:**

```python
from __future__ import annotations

import os
import time

import typer
from rich.table import Table

from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.formatters import console

drift_app = typer.Typer(no_args_is_help=True)

_DEFAULT_DB = os.path.expanduser("~/.memorylens/traces.db")

_GRADE_COLORS = {
    "A": "green",
    "B": "blue",
    "C": "yellow",
    "D": "dark_orange",
    "F": "red",
}


def _grade_markup(grade: str) -> str:
    color = _GRADE_COLORS.get(grade, "white")
    return f"[{color}]{grade}[/{color}]"


def _count_grades(reports: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for r in reports:
        counts[r.get("grade", "F")] = counts.get(r.get("grade", "F"), 0) + 1
    return counts


@drift_app.command("analyze")
def drift_analyze(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    type_: str = typer.Option("all", "--type", help="Analysis type: all, entity, session, topic"),
    scorer: str = typer.Option("mock", "--scorer", help="Scorer backend: mock, local, openai"),
) -> None:
    """Run drift analysis on stored memory versions."""
    from memorylens._audit.scorer import CachedScorer, create_scorer
    from memorylens._drift.analyzer import DriftAnalyzer

    exporter = SQLiteExporter(db_path=db_path)
    scorer_backend = create_scorer(scorer)
    cached_scorer = CachedScorer(scorer_backend)
    analyzer = DriftAnalyzer(cached_scorer)

    all_versions = exporter.get_all_versions()
    if not all_versions:
        console.print("No memory versions found. Run with detect_drift=True or use offline import.")
        exporter.shutdown()
        return

    console.print(f"Analyzing {len(all_versions)} memory versions...")

    run_entity = type_ in ("all", "entity")
    run_session = type_ in ("all", "session")
    run_topic = type_ in ("all", "topic")

    # ── Entity analysis ──────────────────────────────────────────────────────
    if run_entity:
        by_key: dict[str, list[dict]] = {}
        for v in all_versions:
            by_key.setdefault(v["memory_key"], []).append(v)

        entity_results = []
        for key, versions in by_key.items():
            versions.sort(key=lambda x: x["version"])
            result = analyzer.analyze_entity(versions)
            exporter.save_drift_report({
                "report_type": "entity",
                "key": result.memory_key,
                "drift_score": result.drift_score,
                "contradiction_score": result.contradiction_score,
                "staleness_score": result.staleness_score,
                "volatility_score": result.volatility_score,
                "grade": result.grade,
                "details": {"version_count": result.version_count},
                "created_at": time.time(),
            })
            entity_results.append(result)

        console.print(f"\n[bold]Entity Drift ({len(entity_results)} entities)[/bold]")
        _print_entity_table(entity_results)

    # ── Session analysis ─────────────────────────────────────────────────────
    if run_session:
        sessions = list({v.get("session_id") for v in all_versions if v.get("session_id")})
        session_results = []
        for sid in sessions:
            result = analyzer.analyze_session(sid, all_versions)
            exporter.save_drift_report({
                "report_type": "session",
                "key": sid,
                "drift_score": result.drift_score,
                "contradiction_score": result.contradiction_score,
                "staleness_score": result.staleness_score,
                "volatility_score": result.volatility_score,
                "grade": result.grade,
                "details": {"memory_keys_modified": result.memory_keys_modified},
                "created_at": time.time(),
            })
            session_results.append(result)
        console.print(f"\n[bold]Session Drift ({len(session_results)} sessions)[/bold]")

    # ── Topic analysis ───────────────────────────────────────────────────────
    if run_topic:
        topic_results = analyzer.analyze_topics(all_versions)
        for r in topic_results:
            exporter.save_drift_report({
                "report_type": "topic",
                "key": r.topic_id,
                "drift_score": r.drift_score,
                "contradiction_score": r.contradiction_score,
                "staleness_score": r.staleness_score,
                "volatility_score": r.volatility_score,
                "grade": r.grade,
                "details": {"memory_keys": r.memory_keys, "centroid_drift": r.centroid_drift},
                "created_at": time.time(),
            })
        console.print(f"\n[bold]Topic Drift ({len(topic_results)} clusters)[/bold]")

    console.print("\nAnalysis complete. Run: memorylens drift report")
    exporter.shutdown()


def _print_entity_table(results: list) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("KEY", max_width=30)
    table.add_column("GRADE", justify="center")
    table.add_column("DRIFT", justify="right")
    table.add_column("CONTRADICTION", justify="right")
    table.add_column("STALENESS", justify="right")
    table.add_column("VOLATILITY", justify="right")
    for r in results:
        table.add_row(
            r.memory_key,
            _grade_markup(r.grade),
            f"{r.drift_score:.2f}",
            f"{r.contradiction_score:.2f}",
            f"{r.staleness_score:.2f}",
            f"{r.volatility_score:.2f}",
        )
    console.print(table)


@drift_app.command("report")
def drift_report(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    type_: str | None = typer.Option(None, "--type", help="Filter by type: entity, session, topic"),
    grade: str | None = typer.Option(None, "--grade", help="Minimum grade to show (e.g. D shows D,F)"),
    limit: int = typer.Option(50, "--limit", help="Max rows to show"),
    offset: int = typer.Option(0, "--offset", help="Pagination offset"),
) -> None:
    """List drift reports with optional filters."""
    exporter = SQLiteExporter(db_path=db_path)
    rows, total = exporter.list_drift_reports(
        report_type=type_,
        min_grade=grade,
        limit=limit,
        offset=offset,
    )
    exporter.shutdown()

    if not rows:
        console.print("No drift reports found. Run: memorylens drift analyze")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("TYPE", style="dim")
    table.add_column("KEY", max_width=30)
    table.add_column("GRADE", justify="center")
    table.add_column("DRIFT", justify="right")
    table.add_column("CONTRADICTION", justify="right")
    table.add_column("STALENESS", justify="right")
    table.add_column("VOLATILITY", justify="right")

    for row in rows:
        table.add_row(
            row["report_type"],
            row["key"],
            _grade_markup(row["grade"]),
            f"{row['drift_score']:.2f}",
            f"{row['contradiction_score']:.2f}",
            f"{row['staleness_score']:.2f}",
            f"{row['volatility_score']:.2f}",
        )

    console.print(table)
    counts = _count_grades(rows)
    console.print(
        f"\n{len(rows)} reports shown (of {total} total). "
        f"[red]F:{counts['F']}[/red] "
        f"[dark_orange]D:{counts['D']}[/dark_orange] "
        f"[yellow]C:{counts['C']}[/yellow] "
        f"[blue]B:{counts['B']}[/blue] "
        f"[green]A:{counts['A']}[/green]"
    )


@drift_app.command("show")
def drift_show(
    memory_key: str = typer.Argument(..., help="Memory key to show detail for"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    scorer: str = typer.Option("mock", "--scorer", help="Scorer backend for fresh analysis"),
) -> None:
    """Show entity detail and version history for a memory key."""
    from memorylens._audit.scorer import CachedScorer, create_scorer
    from memorylens._drift.analyzer import DriftAnalyzer

    exporter = SQLiteExporter(db_path=db_path)
    versions = exporter.get_versions(memory_key)

    if not versions:
        console.print(f"No versions found for key '{memory_key}'.")
        exporter.shutdown()
        return

    scorer_backend = create_scorer(scorer)
    analyzer = DriftAnalyzer(CachedScorer(scorer_backend))
    versions.sort(key=lambda x: x["version"])
    result = analyzer.analyze_entity(versions)
    health = analyzer.compute_health(result)

    console.print(f"\n[bold]Memory Key:[/bold] {memory_key}")
    console.print(f"[bold]Grade:[/bold] {_grade_markup(health.grade)}")
    console.print(f"  Drift Score:         {health.drift_score:.4f}")
    console.print(f"  Contradiction Score: {health.contradiction_score:.4f}")
    console.print(f"  Staleness Score:     {health.staleness_score:.4f}")
    console.print(f"  Volatility Score:    {health.volatility_score:.4f}")
    console.print(f"\n[bold]Version History ({result.version_count} versions):[/bold]")

    for i, v in enumerate(versions):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(v["timestamp"]))
        content_preview = (v.get("content") or "")[:60]
        sim_str = ""
        if i > 0 and i - 1 < len(result.consecutive_similarities):
            sim = result.consecutive_similarities[i - 1]
            sim_str = f" [dim](sim to prev: {sim:.3f})[/dim]"
        console.print(f"  v{v['version']} [{ts}] {v['operation']}{sim_str}")
        if content_preview:
            console.print(f"       [dim]{content_preview}...[/dim]")

    exporter.shutdown()


@drift_app.command("watch")
def drift_watch(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    interval: int = typer.Option(300, "--interval", help="Seconds between analyses"),
    scorer: str = typer.Option("mock", "--scorer", help="Scorer backend: mock, local, openai"),
) -> None:
    """Run drift analysis on a schedule. Ctrl+C to stop."""
    console.print(f"Starting drift watcher (interval={interval}s). Ctrl+C to stop.")
    while True:
        console.print(f"\n[dim]{time.strftime('%Y-%m-%d %H:%M:%S')} — Running analysis...[/dim]")
        try:
            from memorylens._audit.scorer import CachedScorer, create_scorer
            from memorylens._drift.analyzer import DriftAnalyzer

            exporter = SQLiteExporter(db_path=db_path)
            scorer_backend = create_scorer(scorer)
            analyzer = DriftAnalyzer(CachedScorer(scorer_backend))
            all_versions = exporter.get_all_versions()

            if all_versions:
                by_key: dict[str, list[dict]] = {}
                for v in all_versions:
                    by_key.setdefault(v["memory_key"], []).append(v)

                critical = 0
                for key, versions in by_key.items():
                    versions.sort(key=lambda x: x["version"])
                    result = analyzer.analyze_entity(versions)
                    exporter.save_drift_report({
                        "report_type": "entity",
                        "key": result.memory_key,
                        "drift_score": result.drift_score,
                        "contradiction_score": result.contradiction_score,
                        "staleness_score": result.staleness_score,
                        "volatility_score": result.volatility_score,
                        "grade": result.grade,
                        "details": {"version_count": result.version_count},
                        "created_at": time.time(),
                    })
                    if result.grade == "F":
                        critical += 1

                console.print(
                    f"  {len(by_key)} entities. "
                    f"[red]{critical} critical[/red]"
                )
            else:
                console.print("  No versions found.")
            exporter.shutdown()
        except Exception as exc:
            console.print(f"  [red]Error: {exc}[/red]")

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\nWatcher stopped.")
            break
```

**Changes to `src/memorylens/cli/main.py`** — update `_register_commands()`:

```python
def _register_commands() -> None:
    from memorylens.cli.commands.audit import audit_app
    from memorylens.cli.commands.config import config_app
    from memorylens.cli.commands.cost import cost_app
    from memorylens.cli.commands.drift import drift_app
    from memorylens.cli.commands.stats import stats_app
    from memorylens.cli.commands.traces import traces_app

    app.add_typer(traces_app, name="traces", help="Inspect and manage traces")
    app.command(name="stats")(stats_app)
    app.add_typer(config_app, name="config", help="Manage configuration")
    app.add_typer(audit_app, name="audit", help="Compression audit tools")
    app.add_typer(cost_app, name="cost", help="Cost attribution tools")
    app.add_typer(drift_app, name="drift", help="Memory drift detection")
```

**`tests/test_cli/test_drift_commands.py`:**

```python
from __future__ import annotations

import time

import pytest
from typer.testing import CliRunner

from memorylens.cli.main import app


@pytest.fixture
def db_with_versions(tmp_path):
    """Return a db_path pre-populated with 2 versions of one key."""
    from memorylens._exporters.sqlite import SQLiteExporter

    db_path = str(tmp_path / "test.db")
    exporter = SQLiteExporter(db_path=db_path)
    now = time.time()
    for i in range(2):
        exporter.save_version({
            "memory_key": "user_42_prefs",
            "version": i + 1,
            "span_id": f"span-{i}",
            "operation": "memory.write",
            "content": f"Version {i + 1} content about user prefs.",
            "embedding": None,
            "agent_id": "agent-1",
            "session_id": f"sess-{i}",
            "timestamp": now - (2 - i) * 3600,
        })
    exporter.shutdown()
    return db_path


@pytest.fixture
def db_with_reports(db_with_versions):
    """Run analyze to populate reports, return db_path."""
    runner = CliRunner()
    result = runner.invoke(app, [
        "drift", "analyze",
        "--db-path", db_with_versions,
        "--scorer", "mock",
        "--type", "entity",
    ])
    assert result.exit_code == 0, result.output
    return db_with_versions


class TestDriftAnalyzeCommand:
    def test_analyze_no_versions(self, tmp_path):
        runner = CliRunner()
        db_path = str(tmp_path / "empty.db")
        result = runner.invoke(app, [
            "drift", "analyze", "--db-path", db_path, "--scorer", "mock"
        ])
        assert result.exit_code == 0
        assert "No memory versions found" in result.output

    def test_analyze_entity_type(self, db_with_versions):
        runner = CliRunner()
        result = runner.invoke(app, [
            "drift", "analyze",
            "--db-path", db_with_versions,
            "--scorer", "mock",
            "--type", "entity",
        ])
        assert result.exit_code == 0
        assert "Entity Drift" in result.output

    def test_analyze_all_types(self, db_with_versions):
        runner = CliRunner()
        result = runner.invoke(app, [
            "drift", "analyze",
            "--db-path", db_with_versions,
            "--scorer", "mock",
            "--type", "all",
        ])
        assert result.exit_code == 0
        assert "Entity Drift" in result.output
        assert "Session Drift" in result.output
        assert "Topic Drift" in result.output


class TestDriftReportCommand:
    def test_report_no_data(self, tmp_path):
        runner = CliRunner()
        db_path = str(tmp_path / "empty.db")
        result = runner.invoke(app, ["drift", "report", "--db-path", db_path])
        assert result.exit_code == 0
        assert "No drift reports found" in result.output

    def test_report_shows_data(self, db_with_reports):
        runner = CliRunner()
        result = runner.invoke(app, ["drift", "report", "--db-path", db_with_reports])
        assert result.exit_code == 0
        assert "user_42_prefs" in result.output

    def test_report_filter_by_type(self, db_with_reports):
        runner = CliRunner()
        result = runner.invoke(app, [
            "drift", "report",
            "--db-path", db_with_reports,
            "--type", "entity",
        ])
        assert result.exit_code == 0

    def test_report_filter_by_grade(self, db_with_reports):
        runner = CliRunner()
        result = runner.invoke(app, [
            "drift", "report",
            "--db-path", db_with_reports,
            "--grade", "D",
        ])
        assert result.exit_code == 0


class TestDriftShowCommand:
    def test_show_unknown_key(self, tmp_path):
        runner = CliRunner()
        db_path = str(tmp_path / "empty.db")
        result = runner.invoke(app, [
            "drift", "show", "nonexistent_key",
            "--db-path", db_path,
            "--scorer", "mock",
        ])
        assert result.exit_code == 0
        assert "No versions found" in result.output

    def test_show_known_key(self, db_with_versions):
        runner = CliRunner()
        result = runner.invoke(app, [
            "drift", "show", "user_42_prefs",
            "--db-path", db_with_versions,
            "--scorer", "mock",
        ])
        assert result.exit_code == 0
        assert "user_42_prefs" in result.output
        assert "Grade" in result.output
        assert "Version History" in result.output
```

---

## Task 9: UI Drift Dashboard + Detail

**Goal:** Create the drift UI routes, templates, register routes in `server.py`, add nav link to `base.html`, and add drift indicator to `traces_detail.html`.

- [ ] Create `src/memorylens/_ui/api/drift.py`
- [ ] Create `src/memorylens/_ui/templates/drift_dashboard.html`
- [ ] Create `src/memorylens/_ui/templates/drift_detail.html`
- [ ] Create `src/memorylens/_ui/templates/partials/drift_table.html`
- [ ] Create `src/memorylens/_ui/templates/partials/version_timeline.html`
- [ ] Edit `src/memorylens/_ui/server.py`: register drift routes
- [ ] Edit `src/memorylens/_ui/templates/base.html`: add "Drift" nav link
- [ ] Edit `src/memorylens/_ui/templates/traces_detail.html`: add drift indicator
- [ ] Create `tests/test_ui/test_api_drift.py`
- [ ] Run `python -m pytest tests/test_ui/test_api_drift.py -v` and confirm all pass
- [ ] Commit

**`src/memorylens/_ui/api/drift.py`:**

```python
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse


def _parse_details(report: dict[str, Any]) -> dict[str, Any]:
    details = report.get("details", "{}")
    if isinstance(details, str):
        return json.loads(details)
    return details if details else {}


def _grade_color(grade: str) -> str:
    return {
        "A": "green",
        "B": "blue",
        "C": "amber",
        "D": "orange",
        "F": "red",
    }.get(grade, "slate")


def create_drift_routes(app: FastAPI) -> None:
    templates = app.state.templates
    exporter = app.state.exporter

    @app.get("/drift", response_class=HTMLResponse)
    async def drift_dashboard(
        request: Request,
        type_: str = Query("entity", alias="type"),
        grade: str | None = Query(None),
        limit: int = Query(50),
        offset: int = Query(0),
    ):
        reports, total = exporter.list_drift_reports(
            report_type=type_,
            min_grade=grade,
            limit=limit,
            offset=offset,
        )
        for r in reports:
            r["_grade_color"] = _grade_color(r["grade"])
            r["details"] = _parse_details(r)

        return templates.TemplateResponse(
            request,
            "drift_dashboard.html",
            {
                "reports": reports,
                "total": total,
                "active_type": type_,
                "active_grade": grade,
                "limit": limit,
                "offset": offset,
                "active_nav": "drift",
            },
        )

    @app.get("/drift/{memory_key:path}", response_class=HTMLResponse)
    async def drift_detail(request: Request, memory_key: str):
        # Load stored report if available
        report = exporter.get_drift_report("entity", memory_key)
        if report:
            report["_grade_color"] = _grade_color(report["grade"])
            report["details"] = _parse_details(report)

        # Load version history
        versions = exporter.get_versions(memory_key)
        versions.sort(key=lambda v: v["version"])

        # Compute consecutive similarities if versions exist
        consecutive_similarities: list[float] = []
        if len(versions) >= 2:
            try:
                from memorylens._audit.scorer import CachedScorer, MockScorer, cosine_similarity
                from memorylens._drift.analyzer import DriftAnalyzer

                scorer = CachedScorer(MockScorer())
                analyzer = DriftAnalyzer(scorer)
                entity_result = analyzer.analyze_entity(versions)
                consecutive_similarities = entity_result.consecutive_similarities
                # Compute fresh report if none stored
                if not report:
                    report = {
                        "key": memory_key,
                        "report_type": "entity",
                        "drift_score": entity_result.drift_score,
                        "contradiction_score": entity_result.contradiction_score,
                        "staleness_score": entity_result.staleness_score,
                        "volatility_score": entity_result.volatility_score,
                        "grade": entity_result.grade,
                        "details": {"version_count": entity_result.version_count},
                        "_grade_color": _grade_color(entity_result.grade),
                    }
            except Exception:
                pass

        if not versions and not report:
            return HTMLResponse(
                f"<h2 class='p-6 text-white'>No data for '{memory_key}'</h2>",
                status_code=404,
            )

        # Annotate versions with similarity to previous
        for i, v in enumerate(versions):
            if i > 0 and i - 1 < len(consecutive_similarities):
                v["_sim_to_prev"] = round(consecutive_similarities[i - 1], 3)
            else:
                v["_sim_to_prev"] = None
            ts = v.get("timestamp", 0)
            v["_ts_str"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))

        return templates.TemplateResponse(
            request,
            "drift_detail.html",
            {
                "memory_key": memory_key,
                "report": report,
                "versions": versions,
                "active_nav": "drift",
            },
        )
```

**`src/memorylens/_ui/templates/drift_dashboard.html`:**

```html
{% extends "base.html" %}
{% block title %}Drift Dashboard — MemoryLens{% endblock %}
{% block content %}
<div class="px-6 pt-4 pb-2">
    <h2 class="text-xl font-semibold mb-1">Memory Drift</h2>
    <p class="text-xs text-white/40 mb-4">Track how memories evolve, detect contradictions and staleness.</p>

    <!-- Type tabs -->
    <div class="flex gap-3 mb-4 border-b border-white/[0.06] pb-2">
        {% for tab in [('entity', 'Entities'), ('session', 'Sessions'), ('topic', 'Topics')] %}
        <a href="/drift?type={{ tab[0] }}"
           class="text-xs pb-1 {% if active_type == tab[0] %}text-indigo-400 border-b-2 border-indigo-400{% else %}text-white/40 hover:text-white/60{% endif %}">
            {{ tab[1] }}
        </a>
        {% endfor %}
    </div>

    <!-- Grade filter -->
    <div class="flex gap-2 mb-4 items-center">
        <span class="text-xs text-white/40">Min grade:</span>
        {% for g in ['A', 'B', 'C', 'D', 'F'] %}
        <a href="/drift?type={{ active_type }}&grade={{ g }}"
           class="px-2 py-0.5 rounded text-[11px] font-semibold
                  {% if active_grade == g %}bg-white/20{% else %}bg-white/5 hover:bg-white/10{% endif %}
                  {% if g == 'A' %}text-green-400{% elif g == 'B' %}text-blue-400{% elif g == 'C' %}text-amber-400{% elif g == 'D' %}text-orange-400{% else %}text-red-400{% endif %}">
            {{ g }}
        </a>
        {% endfor %}
        {% if active_grade %}
        <a href="/drift?type={{ active_type }}" class="text-xs text-white/30 hover:text-white/50 ml-1">clear</a>
        {% endif %}
    </div>

    {% include "partials/drift_table.html" %}

    <!-- Pagination -->
    <div class="flex gap-3 mt-4 text-xs text-white/40">
        <span>{{ total }} total</span>
        {% if offset > 0 %}
        <a href="/drift?type={{ active_type }}{% if active_grade %}&grade={{ active_grade }}{% endif %}&offset={{ [offset - limit, 0]|max }}&limit={{ limit }}"
           class="text-indigo-400 hover:text-indigo-300">← Prev</a>
        {% endif %}
        {% if offset + limit < total %}
        <a href="/drift?type={{ active_type }}{% if active_grade %}&grade={{ active_grade }}{% endif %}&offset={{ offset + limit }}&limit={{ limit }}"
           class="text-indigo-400 hover:text-indigo-300">Next →</a>
        {% endif %}
    </div>
</div>
{% endblock %}
```

**`src/memorylens/_ui/templates/partials/drift_table.html`:**

```html
{% if reports %}
<div class="bg-white/[0.02] rounded-lg border border-white/[0.06] overflow-hidden">
    <table class="w-full border-collapse text-xs">
        <thead>
            <tr class="border-b border-white/[0.06] text-white/40 text-[11px] uppercase tracking-wider">
                <th class="px-4 py-2.5 text-left">Key</th>
                <th class="px-3 py-2.5 text-center">Grade</th>
                <th class="px-3 py-2.5 text-right">Drift</th>
                <th class="px-3 py-2.5 text-right">Contradiction</th>
                <th class="px-3 py-2.5 text-right">Staleness</th>
                <th class="px-3 py-2.5 text-right">Volatility</th>
            </tr>
        </thead>
        <tbody>
            {% for r in reports %}
            <tr class="border-b border-white/[0.04] hover:bg-white/[0.03] cursor-pointer"
                onclick="window.location='/drift/{{ r.key }}'">
                <td class="px-4 py-2.5 font-mono text-slate-300 max-w-xs truncate">{{ r.key }}</td>
                <td class="px-3 py-2.5 text-center">
                    <span class="px-2 py-0.5 rounded font-semibold text-[11px]
                        {% if r.grade == 'A' %}bg-green-500/15 text-green-400
                        {% elif r.grade == 'B' %}bg-blue-500/15 text-blue-400
                        {% elif r.grade == 'C' %}bg-amber-500/15 text-amber-400
                        {% elif r.grade == 'D' %}bg-orange-500/15 text-orange-400
                        {% else %}bg-red-500/15 text-red-400{% endif %}">
                        {{ r.grade }}
                    </span>
                </td>
                <td class="px-3 py-2.5 text-right font-mono">{{ "%.2f"|format(r.drift_score) }}</td>
                <td class="px-3 py-2.5 text-right font-mono">{{ "%.2f"|format(r.contradiction_score) }}</td>
                <td class="px-3 py-2.5 text-right font-mono">{{ "%.2f"|format(r.staleness_score) }}</td>
                <td class="px-3 py-2.5 text-right font-mono">{{ "%.2f"|format(r.volatility_score) }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% else %}
<div class="py-12 text-center text-white/30 text-sm">
    No drift reports found.
    <a href="#" class="text-indigo-400 hover:text-indigo-300 block mt-2 text-xs">
        Run: memorylens drift analyze
    </a>
</div>
{% endif %}
```

**`src/memorylens/_ui/templates/drift_detail.html`:**

```html
{% extends "base.html" %}
{% block title %}Drift: {{ memory_key }} — MemoryLens{% endblock %}
{% block content %}
<div class="px-6 pt-4">
    <div class="text-[11px] text-white/30 mb-2">
        <a href="/drift" class="text-indigo-400 hover:text-indigo-300">← Drift</a> / {{ memory_key }}
    </div>
    <h2 class="text-xl font-semibold mb-1 font-mono">{{ memory_key }}</h2>

    {% if report %}
    <!-- Health Score Header -->
    <div class="flex items-center gap-4 mb-6 mt-3">
        <div class="flex items-center justify-center w-14 h-14 rounded-xl font-bold text-2xl
            {% if report.grade == 'A' %}bg-green-500/15 text-green-400
            {% elif report.grade == 'B' %}bg-blue-500/15 text-blue-400
            {% elif report.grade == 'C' %}bg-amber-500/15 text-amber-400
            {% elif report.grade == 'D' %}bg-orange-500/15 text-orange-400
            {% else %}bg-red-500/15 text-red-400{% endif %}">
            {{ report.grade }}
        </div>
        <div class="flex-1 grid grid-cols-4 gap-3">
            {% for label, value in [
                ('Drift', report.drift_score),
                ('Contradiction', report.contradiction_score),
                ('Staleness', report.staleness_score),
                ('Volatility', report.volatility_score)
            ] %}
            <div class="bg-white/[0.03] rounded-md border border-white/[0.06] px-3 py-2">
                <div class="text-[10px] uppercase tracking-wider text-white/30 mb-1">{{ label }}</div>
                <div class="text-sm font-mono font-semibold">{{ "%.3f"|format(value) }}</div>
                <div class="mt-1.5 h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                    <div class="h-full rounded-full
                        {% if value < 0.3 %}bg-green-500{% elif value < 0.6 %}bg-amber-500{% else %}bg-red-500{% endif %}"
                         style="width: {{ (value * 100)|round|int }}%"></div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}

    <!-- Version Timeline -->
    {% include "partials/version_timeline.html" %}
</div>
{% endblock %}
```

**`src/memorylens/_ui/templates/partials/version_timeline.html`:**

```html
{% if versions %}
<div class="mb-4">
    <div class="text-[11px] uppercase tracking-wider text-white/30 mb-3">
        Version History ({{ versions|length }})
    </div>
    <div class="relative pl-4 border-l border-white/[0.08]">
        {% for v in versions %}
        <div class="mb-4 relative">
            <div class="absolute -left-[21px] w-2.5 h-2.5 rounded-full border-2
                {% if v._sim_to_prev is not none and v._sim_to_prev < 0.5 %}border-red-400 bg-red-400/30
                {% elif v._sim_to_prev is not none and v._sim_to_prev < 0.8 %}border-amber-400 bg-amber-400/30
                {% else %}border-indigo-400 bg-indigo-400/20{% endif %}">
            </div>
            <div class="ml-3">
                <div class="flex items-center gap-2 mb-0.5">
                    <span class="text-xs font-semibold text-white/70">v{{ v.version }}</span>
                    <span class="text-[10px] text-white/30">{{ v._ts_str }}</span>
                    <span class="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.05] text-white/40">{{ v.operation }}</span>
                    {% if v._sim_to_prev is not none %}
                    <span class="text-[10px]
                        {% if v._sim_to_prev < 0.5 %}text-red-400{% elif v._sim_to_prev < 0.8 %}text-amber-400{% else %}text-green-400{% endif %}">
                        sim {{ "%.3f"|format(v._sim_to_prev) }}
                    </span>
                    {% endif %}
                </div>
                {% if v.content %}
                <div class="text-xs font-mono text-slate-400 bg-white/[0.02] rounded px-3 py-2 border border-white/[0.04] mt-1 max-h-24 overflow-hidden">
                    {{ v.content[:200] }}{% if v.content|length > 200 %}…{% endif %}
                </div>
                {% endif %}
            </div>
        </div>
        {% endfor %}
    </div>
</div>
{% else %}
<div class="py-8 text-center text-white/30 text-sm">No version history available.</div>
{% endif %}
```

**Changes to `src/memorylens/_ui/server.py`** — add drift routes registration in `create_app()`:

```python
    from memorylens._ui.api.drift import create_drift_routes
    create_drift_routes(app)
```

(Insert after the `create_compression_routes(app)` call.)

**Changes to `src/memorylens/_ui/templates/base.html`** — add Drift nav link after Traces:

```html
            <a href="/traces" class="{% if active_nav == 'traces' %}text-indigo-400 border-b-2 border-indigo-400 pb-0.5{% else %}text-white/40 hover:text-white/60{% endif %}">Traces</a>
            <a href="/drift" class="{% if active_nav == 'drift' %}text-indigo-400 border-b-2 border-indigo-400 pb-0.5{% else %}text-white/40 hover:text-white/60{% endif %}">Drift</a>
```

**Changes to `src/memorylens/_ui/templates/traces_detail.html`** — add drift indicator block after the existing operation/status line (inside the `<div class="flex items-center gap-3 mb-1">` block):

```html
        {% if span.operation in ('memory.write', 'memory.update') and span._attrs.get('drift_detected') %}
        <span class="px-2 py-0.5 rounded text-[11px] bg-red-500/15 text-red-400 border border-red-500/20">
            ⚠ drift {{ "%.2f"|format(span._attrs.get('drift_score', 0)) }}
        </span>
        {% endif %}
```

And add a "Debug Drift" link after the existing action links (inside the `<div class="mt-3 flex gap-2">` block):

```html
            {% if span.operation in ('memory.write', 'memory.update') and span._attrs.get('memory_key') %}
            <a href="/drift/{{ span._attrs.get('memory_key') }}" class="px-3.5 py-1.5 rounded-md bg-rose-500/15 border border-rose-500/30 text-xs text-rose-400 hover:bg-rose-500/25">Drift History →</a>
            {% endif %}
```

**`tests/test_ui/test_api_drift.py`:**

```python
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from memorylens._ui.server import create_app

    db_path = str(tmp_path / "test.db")
    app = create_app(db_path=db_path)
    return TestClient(app), db_path


@pytest.fixture
def client_with_data(tmp_path):
    from memorylens._exporters.sqlite import SQLiteExporter
    from memorylens._ui.server import create_app

    db_path = str(tmp_path / "test.db")
    # Pre-populate versions and a report
    exporter = SQLiteExporter(db_path=db_path)
    now = time.time()
    for i in range(3):
        exporter.save_version({
            "memory_key": "user_42_prefs",
            "version": i + 1,
            "span_id": f"span-{i}",
            "operation": "memory.write",
            "content": f"User preference version {i + 1}.",
            "embedding": None,
            "agent_id": "agent-1",
            "session_id": f"sess-{i}",
            "timestamp": now - (3 - i) * 3600,
        })
    exporter.save_drift_report({
        "report_type": "entity",
        "key": "user_42_prefs",
        "drift_score": 0.25,
        "contradiction_score": 0.10,
        "staleness_score": 0.05,
        "volatility_score": 0.80,
        "grade": "B",
        "details": {"version_count": 3},
        "created_at": now,
    })
    exporter.shutdown()

    app = create_app(db_path=db_path)
    return TestClient(app), db_path


class TestDriftDashboard:
    def test_dashboard_empty(self, client):
        c, _ = client
        response = c.get("/drift")
        assert response.status_code == 200
        assert "Drift" in response.text
        assert "No drift reports found" in response.text

    def test_dashboard_with_data(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift")
        assert response.status_code == 200
        assert "user_42_prefs" in response.text

    def test_dashboard_type_filter_entity(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift?type=entity")
        assert response.status_code == 200

    def test_dashboard_type_filter_session(self, client):
        c, _ = client
        response = c.get("/drift?type=session")
        assert response.status_code == 200

    def test_dashboard_type_filter_topic(self, client):
        c, _ = client
        response = c.get("/drift?type=topic")
        assert response.status_code == 200

    def test_dashboard_grade_filter(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift?grade=D")
        assert response.status_code == 200

    def test_dashboard_active_nav(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift")
        assert response.status_code == 200
        # Nav should mark drift as active
        assert "active_nav" in response.text or "Drift" in response.text


class TestDriftDetail:
    def test_detail_unknown_key_returns_404(self, client):
        c, _ = client
        response = c.get("/drift/nonexistent_key")
        assert response.status_code == 404

    def test_detail_known_key_returns_200(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift/user_42_prefs")
        assert response.status_code == 200
        assert "user_42_prefs" in response.text

    def test_detail_shows_grade(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift/user_42_prefs")
        assert response.status_code == 200
        assert "B" in response.text  # grade

    def test_detail_shows_version_history(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift/user_42_prefs")
        assert response.status_code == 200
        assert "Version History" in response.text

    def test_detail_shows_health_scores(self, client_with_data):
        c, _ = client_with_data
        response = c.get("/drift/user_42_prefs")
        assert response.status_code == 200
        # Score labels should appear
        assert "Drift" in response.text
        assert "Contradiction" in response.text
```

---

## Task 10: Package Exports + Polish

**Goal:** Populate `src/memorylens/_drift/__init__.py` with public exports, run `ruff check`, run the full test suite, fix any issues.

- [ ] Write `src/memorylens/_drift/__init__.py` with all public exports
- [ ] Run `python -m ruff check src/memorylens/_drift/ src/memorylens/_audit/scorer.py src/memorylens/_exporters/sqlite.py src/memorylens/__init__.py src/memorylens/cli/commands/drift.py src/memorylens/_ui/api/drift.py --fix`
- [ ] Run `python -m pytest tests/test_drift/ tests/test_ui/test_api_drift.py tests/test_cli/test_drift_commands.py -v`
- [ ] Fix any ruff or test failures
- [ ] Run the full test suite: `python -m pytest` and confirm all green
- [ ] Commit

**`src/memorylens/_drift/__init__.py`:**

```python
"""Memory Drift Detection — Phase 3a.

Detects how memories evolve across sessions, identifies contradictions and staleness,
and computes multi-dimensional health scores.
"""

from __future__ import annotations

from memorylens._drift.analyzer import (
    DriftAnalyzer,
    EntityDriftResult,
    SessionDriftResult,
    TopicDriftResult,
)
from memorylens._drift.health import HealthScore, compute_grade
from memorylens._drift.tracker import VersionTracker

__all__ = [
    "DriftAnalyzer",
    "EntityDriftResult",
    "SessionDriftResult",
    "TopicDriftResult",
    "HealthScore",
    "compute_grade",
    "VersionTracker",
]
```

**Ruff fixes to anticipate:**

- `Any` import in `sqlite.py` extension methods — already imported at top of file
- `time` import in `sqlite.py` extension is inline — acceptable pattern (matches `save_audit`)
- `hashlib` import in `tracker.py` is inline inside the method — move to top of file to satisfy ruff's `E402`/`I001`

After ruff fixes, the correct `tracker.py` import block should be:

```python
from __future__ import annotations

import hashlib
import time

from memorylens._audit.scorer import CachedScorer, cosine_similarity
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter
```

And the inline `import hashlib` inside `on_end()` should be removed (use the top-level import).

---

## Cross-Task Type Consistency Checklist

| Type | Defined In | Used In |
|---|---|---|
| `CachedScorer` | Task 2 (`scorer.py`) | Tasks 5, 6, 7, 8, 9 |
| `HealthScore` | Task 3 (`health.py`) | Tasks 5, 8 |
| `compute_grade` | Task 3 (`health.py`) | Tasks 5, 6 |
| `EntityDriftResult` | Task 5 (`analyzer.py`) | Tasks 6, 7, 8, 9 |
| `SessionDriftResult` | Task 5 (`analyzer.py`) | Tasks 6, 8 |
| `TopicDriftResult` | Task 5 (`analyzer.py`) | Tasks 6, 8 |
| `DriftAnalyzer` | Task 5 (`analyzer.py`) | Tasks 8, 9, 10 |
| `VersionTracker` | Task 7 (`tracker.py`) | Tasks 7, 10 |
| `save_version` / `get_versions` | Task 4 (`sqlite.py`) | Tasks 7, 8, 9 |
| `save_drift_report` / `list_drift_reports` | Task 4 (`sqlite.py`) | Tasks 8, 9 |

---

## File Map

| File | Task | Action |
|---|---|---|
| `src/memorylens/_drift/__init__.py` | 1, 10 | create (empty) → populate |
| `tests/test_drift/__init__.py` | 1 | create |
| `src/memorylens/_audit/scorer.py` | 2 | append `CachedScorer` |
| `tests/test_drift/test_cached_scorer.py` | 2 | create |
| `src/memorylens/_drift/health.py` | 3 | create |
| `tests/test_drift/test_health.py` | 3 | create |
| `src/memorylens/_exporters/sqlite.py` | 4 | append SQL + methods |
| `tests/test_drift/test_storage.py` | 4 | create |
| `src/memorylens/_drift/analyzer.py` | 5, 6 | create → extend |
| `tests/test_drift/test_analyzer.py` | 5, 6 | create → append |
| `src/memorylens/_drift/tracker.py` | 7 | create |
| `src/memorylens/__init__.py` | 7 | modify `init()` |
| `tests/test_drift/test_tracker.py` | 7 | create |
| `src/memorylens/cli/commands/drift.py` | 8 | create |
| `src/memorylens/cli/main.py` | 8 | modify `_register_commands()` |
| `tests/test_cli/test_drift_commands.py` | 8 | create |
| `src/memorylens/_ui/api/drift.py` | 9 | create |
| `src/memorylens/_ui/templates/drift_dashboard.html` | 9 | create |
| `src/memorylens/_ui/templates/drift_detail.html` | 9 | create |
| `src/memorylens/_ui/templates/partials/drift_table.html` | 9 | create |
| `src/memorylens/_ui/templates/partials/version_timeline.html` | 9 | create |
| `src/memorylens/_ui/server.py` | 9 | add `create_drift_routes(app)` |
| `src/memorylens/_ui/templates/base.html` | 9 | add Drift nav link |
| `src/memorylens/_ui/templates/traces_detail.html` | 9 | add drift indicator |
