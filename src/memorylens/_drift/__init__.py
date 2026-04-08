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
