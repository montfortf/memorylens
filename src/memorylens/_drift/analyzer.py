from __future__ import annotations

import time
from dataclasses import dataclass, field

from memorylens._audit.scorer import CachedScorer, cosine_similarity
from memorylens._drift.health import HealthScore, compute_grade


@dataclass(frozen=True)
class EntityDriftResult:
    """Drift analysis result for a single memory entity (memory_key)."""

    memory_key: str
    version_count: int
    drift_score: float  # 0.0–1.0: mean cross-version drift
    contradiction_score: float  # 0.0–1.0: proportion of pairs with similarity < 0.5
    staleness_score: float  # 0.0–1.0: based on days since last update
    volatility_score: float  # 0.0–1.0: sessions with changes / total sessions
    grade: str  # A / B / C / D / F
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
    centroid_drift: float  # How much the cluster centroid moved over time
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
        contradiction_score = (
            round(contradicting_pairs / total_pairs, 4) if total_pairs > 0 else 0.0
        )

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
            round(len(sessions_with_changes) / len(all_sessions), 4) if all_sessions else 0.0
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

    def analyze_session(self, session_id: str, versions: list[dict]) -> SessionDriftResult:
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
            session_key_versions = [
                v for v in all_key_versions if v.get("session_id") == session_id
            ]
            prior_versions = [
                v
                for v in all_key_versions
                if v.get("session_id") != session_id
                and v["version"] < min(sv["version"] for sv in session_key_versions)
            ]

            if not prior_versions:
                # No prior version to compare against — no drift for this key
                continue

            # Compare earliest session version against latest prior version
            prior = prior_versions[-1]
            current = session_key_versions[0]
            pair_embeddings = self._scorer.embed(
                [
                    prior.get("content") or "",
                    current.get("content") or "",
                ]
            )
            sim = cosine_similarity(pair_embeddings[0], pair_embeddings[1])
            sim = max(0.0, min(1.0, sim))
            drift_scores.append(1.0 - sim)
            contradiction_scores.append(1.0 if sim < 0.5 else 0.0)

        drift_score = round(sum(drift_scores) / len(drift_scores), 4) if drift_scores else 0.0
        contradiction_score = (
            round(sum(contradiction_scores) / len(contradiction_scores), 4)
            if contradiction_scores
            else 0.0
        )

        # Staleness: time since session ended (latest timestamp in session)
        now = time.time()
        session_end = max(v["timestamp"] for v in session_versions)
        days_stale = (now - session_end) / 86400.0
        staleness_score = round(min(1.0, days_stale / 7.0), 4)

        # Volatility: proportion of modified keys vs all keys touched by session
        total_keys_in_session = len({v["memory_key"] for v in session_versions})
        volatility_score = (
            round(len(memory_keys_modified) / total_keys_in_session, 4)
            if total_keys_in_session > 0
            else 0.0
        )

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

    def analyze_topics(self, all_versions: list[dict]) -> list[TopicDriftResult]:
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
            second_half_embeddings = (
                [e for _, e in time_sorted[mid:]] if n > 1 else first_half_embeddings
            )

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

            grade = compute_grade(
                centroid_drift, contradiction_score, staleness_score, volatility_score
            )
            memory_keys = list({v["memory_key"] for v in cluster_versions})

            results.append(
                TopicDriftResult(
                    topic_id=f"topic_{cluster_idx}",
                    memory_keys=memory_keys,
                    centroid_drift=centroid_drift,
                    drift_score=centroid_drift,
                    contradiction_score=contradiction_score,
                    staleness_score=staleness_score,
                    volatility_score=volatility_score,
                    grade=grade,
                )
            )

        return results

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
