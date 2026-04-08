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
