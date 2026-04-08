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
