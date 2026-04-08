# MemoryLens Phase 2b — Compression Auditor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline compression auditor that computes semantic loss scores and sentence-level diffs for COMPRESS spans, accessible via CLI and Web UI.

**Architecture:** Pluggable scorer backends (local sentence-transformers default, optional OpenAI) compute embeddings. Analyzer splits pre/post content into sentences, compares via cosine similarity, stores results in a `compression_audits` SQLite table. CLI and UI views present the analysis.

**Tech Stack:** Python 3.10+, sentence-transformers, numpy, FastAPI (existing), Jinja2 (existing)

**Spec:** `docs/superpowers/specs/2026-04-08-memorylens-phase2b-compression-auditor-design.md`

---

## File Map

### New Files

| File | Responsibility |
|---|---|
| `src/memorylens/_audit/__init__.py` | Audit package exports |
| `src/memorylens/_audit/splitter.py` | Sentence splitting utility |
| `src/memorylens/_audit/scorer.py` | ScorerBackend protocol, LocalScorer, OpenAIScorer |
| `src/memorylens/_audit/analyzer.py` | CompressionAnalyzer, CompressionAudit, SentenceAnalysis |
| `src/memorylens/cli/commands/audit.py` | CLI audit compress/show/list commands |
| `src/memorylens/_ui/api/compression.py` | Compression audit UI routes |
| `src/memorylens/_ui/templates/compression_audit.html` | Compression audit page |
| `src/memorylens/_ui/templates/partials/sentence_diff.html` | Sentence diff partial |
| `tests/test_audit/__init__.py` | Test package |
| `tests/test_audit/test_splitter.py` | Sentence splitting tests |
| `tests/test_audit/test_analyzer.py` | Analyzer tests with mock scorer |
| `tests/test_audit/test_storage.py` | Audit storage tests |
| `tests/test_ui/test_api_compression.py` | UI compression routes tests |
| `tests/test_cli/test_audit_commands.py` | CLI audit command tests |

### Modified Files

| File | Change |
|---|---|
| `pyproject.toml` | Add `[audit]` extra |
| `src/memorylens/_exporters/sqlite.py` | Add `save_audit()`, `get_audit()`, `list_audits()` |
| `src/memorylens/_ui/server.py` | Register compression routes |
| `src/memorylens/_ui/templates/traces_detail.html` | Add "Debug Compression" button |
| `src/memorylens/cli/main.py` | Register audit command group |

---

## Task 1: Package Setup

**Files:**
- Modify: `pyproject.toml`
- Create: `src/memorylens/_audit/__init__.py`, `tests/test_audit/__init__.py`

- [ ] **Step 1: Update pyproject.toml**

Add `audit` to optional dependencies. Current `[project.optional-dependencies]` section — add after `ui`:

```toml
audit = ["sentence-transformers>=2.0", "numpy>=1.24"]
```

Also add `"numpy>=1.24"` to the `dev` list (needed for mock scorer tests without full sentence-transformers):

```toml
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "mypy>=1.10",
    "httpx>=0.27",
    "numpy>=1.24",
]
```

- [ ] **Step 2: Create package directories**

Create empty `__init__.py`:

```
src/memorylens/_audit/__init__.py
tests/test_audit/__init__.py
```

- [ ] **Step 3: Install and verify**

```bash
uv pip install -e ".[dev]"
uv run pytest tests/ -v --tb=short -q
```

Expected: 99 existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/memorylens/_audit/ tests/test_audit/
git commit -m "feat: add audit package structure and [audit] optional extra"
```

---

## Task 2: Sentence Splitter

**Files:**
- Create: `src/memorylens/_audit/splitter.py`
- Create: `tests/test_audit/test_splitter.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_audit/test_splitter.py`

```python
from __future__ import annotations

from memorylens._audit.splitter import split_sentences


class TestSplitSentences:
    def test_basic_split(self):
        text = "First sentence. Second sentence. Third sentence."
        result = split_sentences(text)
        assert result == ["First sentence.", "Second sentence.", "Third sentence."]

    def test_question_and_exclamation(self):
        text = "Is this a question? Yes it is! Great."
        result = split_sentences(text)
        assert result == ["Is this a question?", "Yes it is!", "Great."]

    def test_preserves_abbreviations(self):
        text = "Dr. Smith went to Washington. He arrived at 3 p.m. today."
        result = split_sentences(text)
        assert len(result) == 2

    def test_single_sentence(self):
        text = "Just one sentence."
        result = split_sentences(text)
        assert result == ["Just one sentence."]

    def test_no_trailing_period(self):
        text = "First sentence. Second without period"
        result = split_sentences(text)
        assert result == ["First sentence.", "Second without period"]

    def test_empty_string(self):
        result = split_sentences("")
        assert result == []

    def test_whitespace_only(self):
        result = split_sentences("   ")
        assert result == []

    def test_newlines(self):
        text = "First sentence.\nSecond sentence.\nThird."
        result = split_sentences(text)
        assert result == ["First sentence.", "Second sentence.", "Third."]

    def test_multiple_spaces(self):
        text = "First sentence.   Second sentence."
        result = split_sentences(text)
        assert result == ["First sentence.", "Second sentence."]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_audit/test_splitter.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

File: `src/memorylens/_audit/splitter.py`

```python
from __future__ import annotations

import re

# Common abbreviations that shouldn't trigger sentence splits
_ABBREVS = {"dr", "mr", "mrs", "ms", "prof", "sr", "jr", "st", "ave", "vs", "etc", "i.e", "e.g", "a.m", "p.m"}

_SENTENCE_END = re.compile(r'([.!?])(?:\s+|$)')


def split_sentences(text: str) -> list[str]:
    """Split text into sentences.

    Splits on sentence-ending punctuation (.!?) followed by whitespace or end-of-string.
    Handles common abbreviations like Dr., Mr., a.m., p.m.
    """
    if not text or not text.strip():
        return []

    sentences: list[str] = []
    current = ""

    for i, char in enumerate(text):
        current += char
        if char in ".!?":
            # Check if this is end of sentence
            is_end = False
            # End of string
            if i == len(text) - 1:
                is_end = True
            # Followed by whitespace
            elif i + 1 < len(text) and text[i + 1] in " \n\r\t":
                # Check it's not an abbreviation
                word_before = current.rstrip(".!?").rsplit(None, 1)[-1].lower() if current.rstrip(".!?").strip() else ""
                if word_before not in _ABBREVS:
                    is_end = True

            if is_end:
                stripped = current.strip()
                if stripped:
                    sentences.append(stripped)
                current = ""
        elif char in " \n\r\t" and not current.strip():
            current = ""

    # Handle remaining text without terminal punctuation
    remaining = current.strip()
    if remaining:
        sentences.append(remaining)

    return sentences
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_audit/test_splitter.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memorylens/_audit/splitter.py tests/test_audit/test_splitter.py
git commit -m "feat: add sentence splitter for compression auditor"
```

---

## Task 3: Scorer Backends

**Files:**
- Create: `src/memorylens/_audit/scorer.py`
- Create: `tests/test_audit/test_scorer.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_audit/test_scorer.py`

```python
from __future__ import annotations

import numpy as np

from memorylens._audit.scorer import MockScorer, cosine_similarity, create_scorer


class TestCosineSimlarity:
    def test_identical_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == 1.0

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert abs(cosine_similarity(a, b)) < 0.001

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert cosine_similarity(a, b) == -1.0

    def test_similar_vectors(self):
        a = [1.0, 0.5, 0.0]
        b = [1.0, 0.6, 0.0]
        score = cosine_similarity(a, b)
        assert score > 0.99


class TestMockScorer:
    def test_returns_embeddings(self):
        scorer = MockScorer()
        embeddings = scorer.embed(["hello world", "goodbye world"])
        assert len(embeddings) == 2
        assert len(embeddings[0]) > 0

    def test_similar_texts_similar_embeddings(self):
        scorer = MockScorer()
        embeddings = scorer.embed(["user likes jazz", "user likes jazz music"])
        score = cosine_similarity(embeddings[0], embeddings[1])
        # Same prefix should produce somewhat similar embeddings
        assert score > 0.5

    def test_different_texts_different_embeddings(self):
        scorer = MockScorer()
        embeddings = scorer.embed(["user likes jazz", "the weather is sunny today"])
        # Very different texts shouldn't be identical
        assert embeddings[0] != embeddings[1]


class TestCreateScorer:
    def test_create_mock(self):
        scorer = create_scorer("mock")
        assert isinstance(scorer, MockScorer)

    def test_create_unknown_raises(self):
        try:
            create_scorer("nonexistent")
            assert False, "Should have raised"
        except ValueError as e:
            assert "nonexistent" in str(e)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_audit/test_scorer.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

File: `src/memorylens/_audit/scorer.py`

```python
from __future__ import annotations

import hashlib
import math
from typing import Protocol


class ScorerBackend(Protocol):
    """Interface for embedding scorer backends."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a list of texts."""
        ...


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class MockScorer:
    """Deterministic scorer for testing. Produces hash-based embeddings."""

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._text_to_embedding(t) for t in texts]

    def _text_to_embedding(self, text: str) -> list[float]:
        """Generate a deterministic embedding from text using character n-gram hashing."""
        vec = [0.0] * self._dim
        words = text.lower().split()
        for word in words:
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            for i in range(self._dim):
                bit = (h >> (i % 128)) & 1
                vec[i] += 1.0 if bit else -1.0
        # Normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec


class LocalScorer:
    """Uses sentence-transformers all-MiniLM-L6-v2. No API key needed."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers not found. "
                "Install with: pip install memorylens[audit]"
            )
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts).tolist()


class OpenAIScorer:
    """Uses OpenAI text-embedding-3-small. Requires OPENAI_API_KEY."""

    def __init__(self, model: str = "text-embedding-3-small") -> None:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package not found. Install with: pip install openai"
            )
        self._client = openai.OpenAI()
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in response.data]


def create_scorer(name: str) -> ScorerBackend:
    """Factory function to create a scorer backend by name."""
    if name == "mock":
        return MockScorer()
    elif name == "local":
        return LocalScorer()
    elif name == "openai":
        return OpenAIScorer()
    else:
        raise ValueError(
            f"Unknown scorer '{name}'. Available: mock, local, openai"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_audit/test_scorer.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memorylens/_audit/scorer.py tests/test_audit/test_scorer.py
git commit -m "feat: add scorer backends (mock, local, openai) with cosine similarity"
```

---

## Task 4: Compression Analyzer

**Files:**
- Create: `src/memorylens/_audit/analyzer.py`
- Create: `tests/test_audit/test_analyzer.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_audit/test_analyzer.py`

```python
from __future__ import annotations

from memorylens._audit.analyzer import CompressionAnalyzer, CompressionAudit, SentenceAnalysis
from memorylens._audit.scorer import MockScorer


class TestCompressionAnalyzer:
    def test_basic_audit(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        audit = analyzer.analyze(
            span_id="s1",
            pre_content="User prefers vegetarian meals. No dairy products. Likes Italian food.",
            post_content="User is vegetarian, no dairy, likes Italian.",
        )

        assert isinstance(audit, CompressionAudit)
        assert audit.span_id == "s1"
        assert audit.scorer_backend == "mock"
        assert audit.pre_sentence_count == 3
        assert audit.post_sentence_count > 0
        assert 0.0 <= audit.semantic_loss_score <= 1.0
        assert 0.0 < audit.compression_ratio <= 1.0
        assert len(audit.sentences) == 3

    def test_sentence_statuses(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        audit = analyzer.analyze(
            span_id="s2",
            pre_content="User prefers vegetarian meals. Meeting was on Thursday. No dairy.",
            post_content="User is vegetarian with no dairy.",
        )

        statuses = {s.status for s in audit.sentences}
        # Should have at least some classification
        assert statuses.issubset({"preserved", "lost"})
        # Each sentence should have a score between 0 and 1
        for s in audit.sentences:
            assert 0.0 <= s.best_match_score <= 1.0

    def test_identical_content_low_loss(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        text = "User prefers vegetarian meals. No dairy products."
        audit = analyzer.analyze(span_id="s3", pre_content=text, post_content=text)

        # Identical content should have very low loss
        assert audit.semantic_loss_score < 0.1
        assert all(s.status == "preserved" for s in audit.sentences)

    def test_completely_different_content_high_loss(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        audit = analyzer.analyze(
            span_id="s4",
            pre_content="User prefers vegetarian meals. No dairy products. Likes Italian food.",
            post_content="The weather is sunny today.",
        )

        # Very different content should have higher loss
        assert audit.semantic_loss_score > 0.3

    def test_compression_ratio(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        audit = analyzer.analyze(
            span_id="s5",
            pre_content="A very long sentence about user preferences and details. Another long detailed sentence.",
            post_content="Short summary.",
        )

        assert audit.compression_ratio < 0.5  # post is shorter than pre

    def test_empty_pre_content(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        audit = analyzer.analyze(span_id="s6", pre_content="", post_content="Some output.")

        assert audit.pre_sentence_count == 0
        assert audit.semantic_loss_score == 0.0
        assert audit.sentences == []

    def test_to_dict(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        audit = analyzer.analyze(
            span_id="s7",
            pre_content="First sentence. Second sentence.",
            post_content="Combined sentence.",
        )

        d = audit.to_dict()
        assert d["span_id"] == "s7"
        assert isinstance(d["sentences"], list)
        assert isinstance(d["sentences"][0], dict)
        assert "text" in d["sentences"][0]
        assert "best_match_score" in d["sentences"][0]
        assert "status" in d["sentences"][0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_audit/test_analyzer.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

File: `src/memorylens/_audit/analyzer.py`

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from memorylens._audit.scorer import ScorerBackend, cosine_similarity
from memorylens._audit.splitter import split_sentences


@dataclass(frozen=True)
class SentenceAnalysis:
    """Analysis of a single sentence from pre-compression content."""

    text: str
    best_match_score: float
    status: str  # "preserved" or "lost"


@dataclass(frozen=True)
class CompressionAudit:
    """Complete audit result for a single COMPRESS span."""

    span_id: str
    semantic_loss_score: float
    compression_ratio: float
    pre_sentence_count: int
    post_sentence_count: int
    sentences: list[SentenceAnalysis]
    scorer_backend: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


_PRESERVED_THRESHOLD = 0.7


class CompressionAnalyzer:
    """Analyzes compression quality by comparing pre/post content at sentence level."""

    def __init__(self, scorer: ScorerBackend) -> None:
        self._scorer = scorer
        self._backend_name = type(scorer).__name__.lower().replace("scorer", "")

    def analyze(
        self,
        span_id: str,
        pre_content: str,
        post_content: str,
    ) -> CompressionAudit:
        pre_sentences = split_sentences(pre_content)
        post_sentences = split_sentences(post_content)

        if not pre_sentences:
            return CompressionAudit(
                span_id=span_id,
                semantic_loss_score=0.0,
                compression_ratio=0.0 if not pre_content else len(post_content) / len(pre_content),
                pre_sentence_count=0,
                post_sentence_count=len(post_sentences),
                sentences=[],
                scorer_backend=self._backend_name,
            )

        # Embed all sentences in one batch
        all_texts = pre_sentences + post_sentences
        all_embeddings = self._scorer.embed(all_texts)

        pre_embeddings = all_embeddings[: len(pre_sentences)]
        post_embeddings = all_embeddings[len(pre_sentences) :]

        # For each pre-sentence, find best match in post-sentences
        sentence_analyses: list[SentenceAnalysis] = []
        for i, pre_sent in enumerate(pre_sentences):
            if not post_embeddings:
                best_score = 0.0
            else:
                best_score = max(
                    cosine_similarity(pre_embeddings[i], post_emb)
                    for post_emb in post_embeddings
                )
            # Clamp to [0, 1]
            best_score = max(0.0, min(1.0, best_score))
            status = "preserved" if best_score >= _PRESERVED_THRESHOLD else "lost"
            sentence_analyses.append(
                SentenceAnalysis(
                    text=pre_sent,
                    best_match_score=round(best_score, 4),
                    status=status,
                )
            )

        # Compute overall loss score
        mean_score = sum(s.best_match_score for s in sentence_analyses) / len(sentence_analyses)
        semantic_loss = round(1.0 - mean_score, 4)

        compression_ratio = round(len(post_content) / len(pre_content), 4) if pre_content else 0.0

        return CompressionAudit(
            span_id=span_id,
            semantic_loss_score=semantic_loss,
            compression_ratio=compression_ratio,
            pre_sentence_count=len(pre_sentences),
            post_sentence_count=len(post_sentences),
            sentences=sentence_analyses,
            scorer_backend=self._backend_name,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_audit/test_analyzer.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memorylens/_audit/analyzer.py tests/test_audit/test_analyzer.py
git commit -m "feat: add compression analyzer with sentence-level semantic diff"
```

---

## Task 5: Audit Storage (SQLiteExporter Extensions)

**Files:**
- Modify: `src/memorylens/_exporters/sqlite.py`
- Create: `tests/test_audit/test_storage.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_audit/test_storage.py`

```python
from __future__ import annotations

import json

from memorylens._audit.analyzer import CompressionAudit, SentenceAnalysis
from memorylens._exporters.sqlite import SQLiteExporter


def _make_audit(span_id: str = "s1", loss: float = 0.45) -> CompressionAudit:
    return CompressionAudit(
        span_id=span_id,
        semantic_loss_score=loss,
        compression_ratio=0.35,
        pre_sentence_count=3,
        post_sentence_count=1,
        sentences=[
            SentenceAnalysis(text="First sentence.", best_match_score=0.92, status="preserved"),
            SentenceAnalysis(text="Second sentence.", best_match_score=0.45, status="lost"),
            SentenceAnalysis(text="Third sentence.", best_match_score=0.88, status="preserved"),
        ],
        scorer_backend="mock",
    )


class TestAuditStorage:
    def test_save_and_get(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        audit = _make_audit("s1")
        exporter.save_audit(audit)

        result = exporter.get_audit("s1")
        assert result is not None
        assert result["span_id"] == "s1"
        assert result["semantic_loss_score"] == 0.45
        assert result["scorer_backend"] == "mock"
        sentences = json.loads(result["sentences"])
        assert len(sentences) == 3
        assert sentences[0]["text"] == "First sentence."
        exporter.shutdown()

    def test_get_nonexistent(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        result = exporter.get_audit("nonexistent")
        assert result is None
        exporter.shutdown()

    def test_save_overwrites(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.save_audit(_make_audit("s1", loss=0.5))
        exporter.save_audit(_make_audit("s1", loss=0.3))

        result = exporter.get_audit("s1")
        assert result["semantic_loss_score"] == 0.3
        exporter.shutdown()

    def test_list_audits(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.save_audit(_make_audit("s1", loss=0.1))
        exporter.save_audit(_make_audit("s2", loss=0.5))
        exporter.save_audit(_make_audit("s3", loss=0.8))

        rows, total = exporter.list_audits()
        assert total == 3
        assert len(rows) == 3
        exporter.shutdown()

    def test_list_audits_pagination(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        for i in range(5):
            exporter.save_audit(_make_audit(f"s{i}", loss=i * 0.2))

        rows, total = exporter.list_audits(limit=2, offset=0)
        assert total == 5
        assert len(rows) == 2
        exporter.shutdown()

    def test_lazy_table_creation(self, tmp_path):
        """Table should not exist until first save_audit call."""
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)

        # get_audit should work even before table exists
        result = exporter.get_audit("s1")
        assert result is None

        # After save, table exists
        exporter.save_audit(_make_audit("s1"))
        result = exporter.get_audit("s1")
        assert result is not None
        exporter.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_audit/test_storage.py -v
```

Expected: FAIL — `AttributeError` (no `save_audit` method)

- [ ] **Step 3: Implement audit storage methods**

Add to `src/memorylens/_exporters/sqlite.py`, before the `shutdown()` method. Also add the table creation SQL and an `_ensure_audit_table()` helper:

```python
_CREATE_AUDIT_TABLE = """
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
"""

_INSERT_AUDIT = """
INSERT OR REPLACE INTO compression_audits (
    span_id, semantic_loss_score, compression_ratio,
    pre_sentence_count, post_sentence_count,
    sentences, scorer_backend, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""
```

Add these constants after the existing `_INSERT_SPAN` constant. Then add these methods to the `SQLiteExporter` class:

```python
    def _ensure_audit_table(self) -> None:
        """Create the compression_audits table if it doesn't exist."""
        self._conn.execute(_CREATE_AUDIT_TABLE)
        self._conn.commit()

    def save_audit(self, audit: Any) -> None:
        """Save a compression audit result. Creates table if needed."""
        import time

        self._ensure_audit_table()
        self._conn.execute(_INSERT_AUDIT, (
            audit.span_id,
            audit.semantic_loss_score,
            audit.compression_ratio,
            audit.pre_sentence_count,
            audit.post_sentence_count,
            json.dumps(audit.to_dict()["sentences"]),
            audit.scorer_backend,
            time.time(),
        ))
        self._conn.commit()

    def get_audit(self, span_id: str) -> dict[str, Any] | None:
        """Get audit result for a span, or None if not audited."""
        try:
            self._ensure_audit_table()
        except Exception:
            return None
        cursor = self._conn.execute(
            "SELECT * FROM compression_audits WHERE span_id = ?", (span_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_audits(
        self, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """List all audits with pagination. Returns (rows, total_count)."""
        self._ensure_audit_table()
        total = self._conn.execute(
            "SELECT COUNT(*) FROM compression_audits"
        ).fetchone()[0]
        cursor = self._conn.execute(
            "SELECT * FROM compression_audits ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        return rows, total
```

Note: The `save_audit` method uses `Any` type for the audit parameter to avoid a circular import (sqlite.py shouldn't import from _audit). The method accesses `.span_id`, `.semantic_loss_score`, etc. and `.to_dict()["sentences"]`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_audit/test_storage.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest tests/ -v --tb=short -q
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/memorylens/_exporters/sqlite.py tests/test_audit/test_storage.py
git commit -m "feat: add compression audit storage (save/get/list) with lazy table creation"
```

---

## Task 6: CLI Audit Commands

**Files:**
- Create: `src/memorylens/cli/commands/audit.py`
- Modify: `src/memorylens/cli/main.py`
- Create: `tests/test_cli/test_audit_commands.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_cli/test_audit_commands.py`

```python
from __future__ import annotations

import json

from typer.testing import CliRunner

from memorylens._audit.analyzer import CompressionAudit, SentenceAnalysis
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.main import app

runner = CliRunner()


def _make_compress_span(
    span_id: str = "s1",
    trace_id: str = "t1",
    pre: str = "User prefers jazz. Also likes classical music. Plays piano.",
    post: str = "User likes jazz and classical, plays piano.",
) -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=None,
        operation=MemoryOperation.COMPRESS,
        status=SpanStatus.OK,
        start_time=1000000000000.0,
        end_time=1000100000000.0,
        duration_ms=100.0,
        agent_id="bot",
        session_id="sess-1",
        user_id="user-1",
        input_content=pre,
        output_content=post,
        attributes={"model": "gpt-4o-mini"},
    )


def _seed_db(db_path: str) -> None:
    exporter = SQLiteExporter(db_path=db_path)
    exporter.export([
        _make_compress_span("s1", "t1"),
        _make_compress_span("s2", "t2",
            pre="Meeting on Thursday. Weather was nice. Budget discussion.",
            post="Budget was discussed.",
        ),
    ])
    exporter.shutdown()


class TestAuditCompress:
    def test_audit_compress_runs(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, ["audit", "compress", "--db-path", db_path, "--scorer", "mock"])
        assert result.exit_code == 0
        assert "2" in result.stdout  # 2 spans analyzed

    def test_audit_compress_specific_trace(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, [
            "audit", "compress", "--db-path", db_path,
            "--scorer", "mock", "--trace-id", "t1",
        ])
        assert result.exit_code == 0


class TestAuditShow:
    def test_show_after_audit(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        # First audit
        runner.invoke(app, ["audit", "compress", "--db-path", db_path, "--scorer", "mock"])
        # Then show
        result = runner.invoke(app, ["audit", "show", "s1", "--db-path", db_path])
        assert result.exit_code == 0
        assert "s1" in result.stdout

    def test_show_not_found(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        result = runner.invoke(app, ["audit", "show", "nonexistent", "--db-path", db_path])
        assert result.exit_code == 0
        assert "not found" in result.stdout.lower() or "No audit" in result.stdout


class TestAuditList:
    def test_list_after_audit(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _seed_db(db_path)
        runner.invoke(app, ["audit", "compress", "--db-path", db_path, "--scorer", "mock"])
        result = runner.invoke(app, ["audit", "list", "--db-path", db_path])
        assert result.exit_code == 0
```

- [ ] **Step 2: Create the audit CLI commands**

File: `src/memorylens/cli/commands/audit.py`

```python
from __future__ import annotations

import json
import os
from typing import Optional

import typer
from rich.table import Table

from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.formatters import console

audit_app = typer.Typer(no_args_is_help=True)

_DEFAULT_DB = os.path.expanduser("~/.memorylens/traces.db")


@audit_app.command("compress")
def audit_compress(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    scorer: str = typer.Option("local", "--scorer", help="Scorer backend: local, openai, mock"),
    trace_id: Optional[str] = typer.Option(None, "--trace-id", help="Audit specific trace only"),
    force: bool = typer.Option(False, "--force", help="Re-audit already-audited spans"),
) -> None:
    """Analyze COMPRESS spans for semantic loss."""
    from memorylens._audit.analyzer import CompressionAnalyzer
    from memorylens._audit.scorer import create_scorer

    exporter = SQLiteExporter(db_path=db_path)
    scorer_backend = create_scorer(scorer)
    analyzer = CompressionAnalyzer(scorer_backend)

    # Get all COMPRESS spans
    kwargs: dict = {"operation": "memory.compress", "limit": 10000}
    if trace_id:
        kwargs["trace_id"] = trace_id
    spans = exporter.query(**kwargs)

    if not spans:
        console.print("No COMPRESS spans found.")
        exporter.shutdown()
        return

    # Filter out already-audited unless --force
    if not force:
        spans = [s for s in spans if exporter.get_audit(s["span_id"]) is None]

    if not spans:
        console.print("All COMPRESS spans already audited. Use --force to re-audit.")
        exporter.shutdown()
        return

    console.print(f"Analyzing {len(spans)} COMPRESS spans...")

    results = []
    for span in spans:
        pre = span.get("input_content", "") or ""
        post = span.get("output_content", "") or ""
        audit = analyzer.analyze(span["span_id"], pre, post)
        exporter.save_audit(audit)
        results.append(audit)

    # Print results table
    table = Table(show_header=True, header_style="bold")
    table.add_column("SPAN ID", style="dim", max_width=12)
    table.add_column("LOSS SCORE", justify="right")
    table.add_column("RATIO", justify="right")
    table.add_column("PRESERVED", justify="right")
    table.add_column("LOST", justify="right")
    table.add_column("STATUS")

    for audit in results:
        preserved = sum(1 for s in audit.sentences if s.status == "preserved")
        lost = sum(1 for s in audit.sentences if s.status == "lost")
        total_s = len(audit.sentences)

        if audit.semantic_loss_score < 0.3:
            status = "[green]✓ low loss[/green]"
        elif audit.semantic_loss_score < 0.6:
            status = "[yellow]⚠ moderate loss[/yellow]"
        else:
            status = "[red]✗ high loss[/red]"

        table.add_row(
            audit.span_id[:12],
            f"{audit.semantic_loss_score:.2f}",
            f"{audit.compression_ratio:.2f}",
            f"{preserved}/{total_s}",
            f"{lost}/{total_s}",
            status,
        )

    console.print(table)
    console.print(f"\nSummary: {len(results)} spans audited.")
    exporter.shutdown()


@audit_app.command("show")
def audit_show(
    span_id: str = typer.Argument(..., help="Span ID to show audit for"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
) -> None:
    """Show detailed audit for a span."""
    exporter = SQLiteExporter(db_path=db_path)
    result = exporter.get_audit(span_id)
    exporter.shutdown()

    if not result:
        console.print(f"No audit found for span {span_id}. Run: memorylens audit compress")
        return

    loss = result["semantic_loss_score"]
    if loss < 0.3:
        loss_label = "[green]low[/green]"
    elif loss < 0.6:
        loss_label = "[yellow]moderate[/yellow]"
    else:
        loss_label = "[red]high[/red]"

    console.print(f"\n[bold]Compression Audit: {result['span_id']}[/bold]\n")
    console.print(f"  Loss Score:    {loss:.2f} ({loss_label})")
    ratio = result["compression_ratio"]
    console.print(f"  Ratio:         {ratio:.2f} ({(1 - ratio) * 100:.0f}% reduction)")
    console.print(f"  Sentences:     {result['pre_sentence_count']} pre, {result['post_sentence_count']} post")
    console.print(f"  Scorer:        {result['scorer_backend']}")

    sentences = json.loads(result["sentences"])
    console.print(f"\n  [bold]Pre-compression ({len(sentences)} sentences):[/bold]")
    for s in sentences:
        icon = "[green]✓[/green]" if s["status"] == "preserved" else "[red]✗[/red]"
        score = s["best_match_score"]
        console.print(f"    {icon} [{score:.2f}] \"{s['text']}\"")
    console.print()


@audit_app.command("list")
def audit_list(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    min_loss: float = typer.Option(0.0, "--min-loss", help="Minimum loss score to show"),
) -> None:
    """List all audit results."""
    exporter = SQLiteExporter(db_path=db_path)
    rows, total = exporter.list_audits(limit=100)
    exporter.shutdown()

    if not rows:
        console.print("No audits found. Run: memorylens audit compress")
        return

    if min_loss > 0:
        rows = [r for r in rows if r["semantic_loss_score"] >= min_loss]

    table = Table(show_header=True, header_style="bold")
    table.add_column("SPAN ID", style="dim", max_width=12)
    table.add_column("LOSS SCORE", justify="right")
    table.add_column("RATIO", justify="right")
    table.add_column("SENTENCES", justify="right")
    table.add_column("SCORER")

    for row in rows:
        table.add_row(
            row["span_id"][:12],
            f"{row['semantic_loss_score']:.2f}",
            f"{row['compression_ratio']:.2f}",
            f"{row['pre_sentence_count']}",
            row["scorer_backend"],
        )

    console.print(table)
    console.print(f"\n{len(rows)} audits shown (of {total} total).")
```

- [ ] **Step 3: Register audit commands in main.py**

In `src/memorylens/cli/main.py`, add to `_register_commands()`:

```python
from memorylens.cli.commands.audit import audit_app
app.add_typer(audit_app, name="audit", help="Compression audit tools")
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_cli/test_audit_commands.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memorylens/cli/commands/audit.py src/memorylens/cli/main.py tests/test_cli/test_audit_commands.py
git commit -m "feat: add CLI audit commands (compress, show, list)"
```

---

## Task 7: UI Compression Audit View

**Files:**
- Create: `src/memorylens/_ui/api/compression.py`
- Create: `src/memorylens/_ui/templates/compression_audit.html`
- Create: `src/memorylens/_ui/templates/partials/sentence_diff.html`
- Modify: `src/memorylens/_ui/server.py`
- Modify: `src/memorylens/_ui/templates/traces_detail.html`
- Create: `tests/test_ui/test_api_compression.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_ui/test_api_compression.py`

```python
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from memorylens._audit.analyzer import CompressionAudit, SentenceAnalysis
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter
from memorylens._ui.server import create_app


def _make_compress_span(span_id: str = "s1", trace_id: str = "t1") -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=None,
        operation=MemoryOperation.COMPRESS,
        status=SpanStatus.OK,
        start_time=1000000000000.0,
        end_time=1000100000000.0,
        duration_ms=100.0,
        agent_id="bot",
        session_id="sess-1",
        user_id="user-1",
        input_content="User prefers jazz. Also likes classical.",
        output_content="User likes jazz and classical.",
        attributes={"model": "gpt-4o-mini"},
    )


def _make_audit(span_id: str = "s1") -> CompressionAudit:
    return CompressionAudit(
        span_id=span_id,
        semantic_loss_score=0.35,
        compression_ratio=0.65,
        pre_sentence_count=2,
        post_sentence_count=1,
        sentences=[
            SentenceAnalysis(text="User prefers jazz.", best_match_score=0.92, status="preserved"),
            SentenceAnalysis(text="Also likes classical.", best_match_score=0.55, status="lost"),
        ],
        scorer_backend="mock",
    )


def _create_seeded_client(tmp_path, with_audit: bool = False) -> TestClient:
    db_path = str(tmp_path / "test.db")
    exporter = SQLiteExporter(db_path=db_path)
    exporter.export([
        _make_compress_span("s1", "t1"),
        MemorySpan(
            span_id="s2", trace_id="t2", parent_span_id=None,
            operation=MemoryOperation.WRITE, status=SpanStatus.OK,
            start_time=1000.0, end_time=1010.0, duration_ms=10.0,
            agent_id="bot", session_id="sess-1", user_id="user-1",
            input_content="data", output_content="stored",
            attributes={"backend": "test"},
        ),
    ])
    if with_audit:
        exporter.save_audit(_make_audit("s1"))
    exporter.shutdown()
    app = create_app(db_path=db_path)
    return TestClient(app)


class TestCompressionAuditPage:
    def test_page_with_audit(self, tmp_path):
        client = _create_seeded_client(tmp_path, with_audit=True)
        resp = client.get("/traces/t1/compression")
        assert resp.status_code == 200
        assert "Compression" in resp.text
        assert "0.92" in resp.text  # preserved score
        assert "0.55" in resp.text  # lost score

    def test_page_without_audit(self, tmp_path):
        client = _create_seeded_client(tmp_path, with_audit=False)
        resp = client.get("/traces/t1/compression")
        assert resp.status_code == 200
        assert "not been audited" in resp.text or "Run Audit" in resp.text

    def test_page_404_for_non_compress(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t2/compression")
        assert resp.status_code == 404

    def test_page_404_for_missing_trace(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/nonexistent/compression")
        assert resp.status_code == 404

    def test_detail_page_shows_compression_link(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t1")
        assert "Debug Compression" in resp.text

    def test_detail_page_hides_compression_link_for_write(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t2")
        assert "Debug Compression" not in resp.text
```

- [ ] **Step 2: Create compression routes**

File: `src/memorylens/_ui/api/compression.py`

```python
from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse


def _parse_attributes(span: dict[str, Any]) -> dict[str, Any]:
    attrs = span.get("attributes", "{}")
    if isinstance(attrs, str):
        return json.loads(attrs)
    return attrs


def _operation_badge_class(operation: str) -> str:
    return {
        "memory.write": "badge-write",
        "memory.read": "badge-read",
        "memory.compress": "badge-compress",
        "memory.update": "badge-update",
    }.get(operation, "badge-write")


def create_compression_routes(app: FastAPI) -> None:
    templates = app.state.templates
    exporter = app.state.exporter

    @app.get("/traces/{trace_id}/compression", response_class=HTMLResponse)
    async def compression_audit_page(request: Request, trace_id: str):
        rows, _ = exporter.query_extended(trace_id=trace_id)
        if not rows:
            return HTMLResponse("<h2>Trace not found</h2>", status_code=404)
        span = rows[0]
        if span.get("operation") != "memory.compress":
            return HTMLResponse(
                "<h2>Compression audit is only available for COMPRESS operations</h2>",
                status_code=404,
            )
        span["_attrs"] = _parse_attributes(span)
        span["_badge"] = _operation_badge_class(span.get("operation", ""))

        # Check if audit exists
        audit_data = exporter.get_audit(span["span_id"])
        audit = None
        if audit_data:
            sentences = audit_data.get("sentences", "[]")
            if isinstance(sentences, str):
                sentences = json.loads(sentences)
            audit = {
                **audit_data,
                "sentences": sentences,
            }

        return templates.TemplateResponse(
            request, "compression_audit.html",
            {
                "span": span,
                "audit": audit,
                "active_nav": "traces",
            },
        )

    @app.post("/api/traces/{trace_id}/audit")
    async def run_audit(
        request: Request,
        trace_id: str,
        scorer: str = Query("mock"),
    ):
        rows, _ = exporter.query_extended(trace_id=trace_id)
        if not rows:
            return HTMLResponse("Trace not found", status_code=404)
        span = rows[0]
        if span.get("operation") != "memory.compress":
            return HTMLResponse("Not a COMPRESS span", status_code=400)

        try:
            from memorylens._audit.analyzer import CompressionAnalyzer
            from memorylens._audit.scorer import create_scorer

            scorer_backend = create_scorer(scorer)
            analyzer = CompressionAnalyzer(scorer_backend)
            audit = analyzer.analyze(
                span["span_id"],
                span.get("input_content", "") or "",
                span.get("output_content", "") or "",
            )
            exporter.save_audit(audit)
        except ImportError:
            return HTMLResponse(
                "Audit dependencies not found. Install with: pip install memorylens[audit]",
                status_code=500,
            )

        return RedirectResponse(
            url=f"/traces/{trace_id}/compression", status_code=303
        )
```

- [ ] **Step 3: Create compression_audit.html**

File: `src/memorylens/_ui/templates/compression_audit.html`

```html
{% extends "base.html" %}
{% block title %}Compression Audit — MemoryLens{% endblock %}
{% block content %}
<div class="px-6 pt-4">
    <div class="text-[11px] text-white/30 mb-2">
        <a href="/traces" class="text-indigo-400 hover:text-indigo-300">← Traces</a>
        / <a href="/traces/{{ span.trace_id }}" class="text-indigo-400 hover:text-indigo-300">{{ span.trace_id[:12] }}</a>
        / Compression Audit
    </div>
    <div class="flex items-center gap-3 mb-1">
        <h2 class="text-xl font-semibold">Compression Audit</h2>
        <span class="px-2 py-0.5 rounded text-[11px] {{ span._badge }}">{{ span.operation }}</span>
        <span class="text-xs status-{{ span.status }}">● {{ span.status }}</span>
    </div>
    <div class="text-xs text-white/35">{{ span.agent_id or '-' }} · {{ span.session_id or '-' }} · {{ "%.1f"|format(span.duration_ms) }}ms</div>
</div>

<div class="px-6 py-4">
{% if audit %}
    {# Summary card #}
    <div class="grid grid-cols-4 gap-4 mb-5">
        <div class="bg-white/[0.03] rounded-md border border-white/[0.06] p-4 text-center">
            <div class="text-[11px] uppercase tracking-wider text-white/30 mb-1">Loss Score</div>
            <div class="text-2xl font-mono font-bold
                {% if audit.semantic_loss_score < 0.3 %}text-emerald-400
                {% elif audit.semantic_loss_score < 0.6 %}text-amber-400
                {% else %}text-red-400{% endif %}">
                {{ "%.2f"|format(audit.semantic_loss_score) }}
            </div>
            <div class="text-[10px] text-white/30 mt-1">
                {% if audit.semantic_loss_score < 0.3 %}low loss
                {% elif audit.semantic_loss_score < 0.6 %}moderate loss
                {% else %}high loss{% endif %}
            </div>
        </div>
        <div class="bg-white/[0.03] rounded-md border border-white/[0.06] p-4 text-center">
            <div class="text-[11px] uppercase tracking-wider text-white/30 mb-1">Compression Ratio</div>
            <div class="text-2xl font-mono font-bold text-slate-200">{{ "%.0f"|format((1 - audit.compression_ratio) * 100) }}%</div>
            <div class="text-[10px] text-white/30 mt-1">reduction</div>
        </div>
        <div class="bg-white/[0.03] rounded-md border border-white/[0.06] p-4 text-center">
            <div class="text-[11px] uppercase tracking-wider text-white/30 mb-1">Preserved</div>
            {% set preserved = audit.sentences|selectattr("status", "eq", "preserved")|list|length %}
            <div class="text-2xl font-mono font-bold text-emerald-400">{{ preserved }}/{{ audit.sentences|length }}</div>
            <div class="text-[10px] text-white/30 mt-1">sentences</div>
        </div>
        <div class="bg-white/[0.03] rounded-md border border-white/[0.06] p-4 text-center">
            <div class="text-[11px] uppercase tracking-wider text-white/30 mb-1">Lost</div>
            {% set lost = audit.sentences|selectattr("status", "eq", "lost")|list|length %}
            <div class="text-2xl font-mono font-bold text-red-400">{{ lost }}/{{ audit.sentences|length }}</div>
            <div class="text-[10px] text-white/30 mt-1">sentences</div>
        </div>
    </div>

    {# Sentence diff #}
    {% include "partials/sentence_diff.html" %}

    {# Post-compression content #}
    {% if span.output_content %}
    <div class="mt-5">
        <div class="text-[11px] uppercase tracking-wider text-white/30 mb-1.5">Post-compression</div>
        <div class="px-4 py-3 bg-white/[0.03] rounded-md border border-white/[0.06] font-mono text-xs leading-relaxed text-slate-300">
            {{ span.output_content }}
        </div>
    </div>
    {% endif %}

{% else %}
    {# No audit yet #}
    <div class="bg-white/[0.03] rounded-md border border-white/[0.06] p-8 text-center">
        <div class="text-white/40 mb-4">This span has not been audited yet.</div>
        <form method="post" action="/api/traces/{{ span.trace_id }}/audit?scorer=mock">
            <button type="submit"
                class="px-4 py-2 rounded-md bg-indigo-500/20 border border-indigo-500/30 text-sm text-indigo-400 hover:bg-indigo-500/30 cursor-pointer">
                Run Audit
            </button>
        </form>
        <div class="text-[11px] text-white/20 mt-3">
            For local embeddings: pip install memorylens[audit]
        </div>
    </div>
{% endif %}
</div>
{% endblock %}
```

- [ ] **Step 4: Create sentence_diff.html partial**

File: `src/memorylens/_ui/templates/partials/sentence_diff.html`

```html
<div class="mb-5">
    <div class="text-[11px] uppercase tracking-wider text-white/30 mb-2.5">Sentence Analysis</div>
    <div class="bg-white/[0.03] rounded-md border border-white/[0.06] p-5">
        <div class="flex flex-col gap-2">
        {% for s in audit.sentences %}
            {% set pct = (s.best_match_score * 100)|int %}
            {% set preserved = s.status == "preserved" %}
            <div class="flex items-center gap-3 {% if not preserved %}opacity-60{% endif %}">
                <div class="w-6 text-center text-[13px]">
                    {% if preserved %}
                    <span class="text-emerald-400">✓</span>
                    {% else %}
                    <span class="text-red-400">✗</span>
                    {% endif %}
                </div>
                <div class="flex-1 relative h-7 bg-white/[0.02] rounded overflow-hidden">
                    <div class="absolute left-0 top-0 h-full rounded-sm flex items-center pl-2.5 text-[11px]
                        {% if preserved %}score-bar-returned text-emerald-200{% else %}score-bar-filtered text-red-300{% endif %}"
                        style="width:{{ pct }}%">
                        {{ s.text[:50] }}{% if s.text|length > 50 %}...{% endif %}
                    </div>
                </div>
                <div class="w-12 text-right font-mono text-[13px] {% if preserved %}text-emerald-400 font-semibold{% else %}text-red-400{% endif %}">
                    {{ "%.2f"|format(s.best_match_score) }}
                </div>
                <div class="w-20">
                    {% if preserved %}
                    <span class="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 text-[10px]">PRESERVED</span>
                    {% else %}
                    <span class="px-2 py-0.5 rounded bg-red-500/10 text-red-400 text-[10px] border border-red-500/20">LOST</span>
                    {% endif %}
                </div>
            </div>
        {% endfor %}
        </div>
    </div>
</div>
```

- [ ] **Step 5: Register compression routes in server.py**

In `src/memorylens/_ui/server.py`, add after the trace routes registration:

```python
    from memorylens._ui.api.compression import create_compression_routes
    create_compression_routes(app)
```

- [ ] **Step 6: Add "Debug Compression" button to traces_detail.html**

In `src/memorylens/_ui/templates/traces_detail.html`, find the action buttons section (line 66-69) and add the compression button:

```html
        <div class="mt-3 flex gap-2">
            {% if span.operation == 'memory.read' %}
            <a href="/traces/{{ span.trace_id }}/retrieval" class="px-3.5 py-1.5 rounded-md bg-indigo-500/15 border border-indigo-500/30 text-xs text-indigo-400 hover:bg-indigo-500/25">Debug Retrieval →</a>
            {% endif %}
            {% if span.operation == 'memory.compress' %}
            <a href="/traces/{{ span.trace_id }}/compression" class="px-3.5 py-1.5 rounded-md bg-amber-500/15 border border-amber-500/30 text-xs text-amber-400 hover:bg-amber-500/25">Debug Compression →</a>
            {% endif %}
        </div>
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/test_ui/test_api_compression.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 8: Run full suite**

```bash
uv run pytest tests/ -v --tb=short -q
```

Expected: All tests pass.

- [ ] **Step 9: Commit**

```bash
git add src/memorylens/_ui/api/compression.py src/memorylens/_ui/templates/compression_audit.html src/memorylens/_ui/templates/partials/sentence_diff.html src/memorylens/_ui/server.py src/memorylens/_ui/templates/traces_detail.html tests/test_ui/test_api_compression.py
git commit -m "feat: add compression audit UI view with sentence diff visualization"
```

---

## Task 8: Audit Package Exports + Final Polish

**Files:**
- Modify: `src/memorylens/_audit/__init__.py`

- [ ] **Step 1: Write the audit package exports**

File: `src/memorylens/_audit/__init__.py`

```python
from memorylens._audit.analyzer import CompressionAnalyzer, CompressionAudit, SentenceAnalysis
from memorylens._audit.scorer import (
    LocalScorer,
    MockScorer,
    OpenAIScorer,
    ScorerBackend,
    cosine_similarity,
    create_scorer,
)
from memorylens._audit.splitter import split_sentences

__all__ = [
    "CompressionAnalyzer",
    "CompressionAudit",
    "SentenceAnalysis",
    "LocalScorer",
    "MockScorer",
    "OpenAIScorer",
    "ScorerBackend",
    "cosine_similarity",
    "create_scorer",
    "split_sentences",
]
```

- [ ] **Step 2: Run ruff**

```bash
uv run ruff check src/ tests/ --fix
uv run ruff format src/ tests/
```

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: ALL tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/memorylens/_audit/__init__.py
git commit -m "feat: add audit package exports"
```

If ruff made changes:
```bash
git add -u
git commit -m "style: format code with ruff"
```

---

## Summary

| Task | Component | Tests |
|------|-----------|-------|
| 1 | Package setup + deps | — |
| 2 | Sentence splitter | 9 |
| 3 | Scorer backends | 8 |
| 4 | Compression analyzer | 7 |
| 5 | Audit storage (SQLite) | 6 |
| 6 | CLI audit commands | 5 |
| 7 | UI compression audit view | 6 |
| 8 | Package exports + polish | — |

**Total: 8 tasks, ~41 new tests, ~14 new files**
