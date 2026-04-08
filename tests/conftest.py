from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_tracer_provider():
    """Reset the global TracerProvider between tests."""
    yield
    # Will be updated in Task 6 once TracerProvider exists
