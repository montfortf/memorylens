from __future__ import annotations

import random


class Sampler:
    """Rate-based sampler. Returns True if the span should be recorded."""

    def __init__(self, rate: float = 1.0) -> None:
        if not 0.0 <= rate <= 1.0:
            raise ValueError(f"Sample rate must be between 0.0 and 1.0, got {rate}")
        self._rate = rate

    @property
    def rate(self) -> float:
        return self._rate

    def should_sample(self) -> bool:
        if self._rate == 1.0:
            return True
        if self._rate == 0.0:
            return False
        return random.random() < self._rate
