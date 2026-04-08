from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 0.0000025, "output": 0.00001},
    "gpt-4o-mini": {"input": 0.00000015, "output": 0.0000006},
    "gpt-4-turbo": {"input": 0.00001, "output": 0.00003},
    "claude-3-opus": {"input": 0.000015, "output": 0.000075},
    "claude-3-sonnet": {"input": 0.000003, "output": 0.000015},
    "claude-3-haiku": {"input": 0.00000025, "output": 0.00000125},
    "text-embedding-3-small": {"input": 0.00000002, "output": 0.0},
    "text-embedding-3-large": {"input": 0.00000013, "output": 0.0},
}

_USER_PRICING_PATH = Path.home() / ".memorylens" / "pricing.json"


def load_pricing(user_path: str | Path | None = None) -> dict[str, dict[str, float]]:
    """Load DEFAULT_PRICING merged with user pricing if it exists."""
    pricing = dict(DEFAULT_PRICING)
    path = Path(user_path) if user_path else _USER_PRICING_PATH
    if path.exists():
        user_pricing = json.loads(path.read_text())
        pricing.update(user_pricing)
    return pricing


def save_user_pricing(pricing: dict[str, dict[str, float]], user_path: str | Path | None = None) -> None:
    """Save user pricing overrides."""
    path = Path(user_path) if user_path else _USER_PRICING_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pricing, indent=2) + "\n")
