from __future__ import annotations

import pytest

from memorylens._core.tracer import TracerProvider


@pytest.fixture(autouse=True)
def _reset_tracer_provider():
    """Reset the global TracerProvider between tests."""
    TracerProvider.reset()
    yield
    TracerProvider.reset()
