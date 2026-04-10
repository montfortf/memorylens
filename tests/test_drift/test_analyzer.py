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
        versions = [
            {
                "memory_key": "fresh_key",
                "version": 1,
                "span_id": "s1",
                "operation": "memory.write",
                "content": "Fresh content.",
                "embedding": None,
                "agent_id": None,
                "session_id": None,
                "timestamp": time.time(),
            }
        ]
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
        versions = make_versions(
            [
                "User loves meat and burgers.",
                "User is strictly vegan, no animal products.",
                "User eats seafood but avoids land animals.",
            ]
        )
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
        versions = make_versions(
            [
                "Memory content alpha.",
                "Completely different memory beta.",
            ]
        )
        result = analyzer.analyze_entity(versions)
        for score in [
            result.drift_score,
            result.contradiction_score,
            result.staleness_score,
            result.volatility_score,
        ]:
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
