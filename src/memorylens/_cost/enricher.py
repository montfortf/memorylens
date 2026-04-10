from __future__ import annotations

from typing import Any

from memorylens._cost.pricing import load_pricing


class CostEnricher:
    """Computes dollar costs from token counts in span attributes."""

    def __init__(self, pricing: dict[str, dict[str, float]] | None = None) -> None:
        self._pricing = pricing if pricing is not None else load_pricing()

    def enrich_span(self, attrs: dict[str, Any]) -> dict[str, float] | None:
        """Compute cost from tokens_in/tokens_out/model.

        Returns dict with cost_usd to merge into attributes, or None if no token data.
        """
        tokens_in = attrs.get("tokens_in", 0)
        tokens_out = attrs.get("tokens_out", 0)

        if not tokens_in and not tokens_out:
            return None

        model = attrs.get("model", "")
        model_pricing = self._pricing.get(model)

        if model_pricing is None:
            # Unknown model — still record tokens but cost is 0
            return {"cost_usd": 0.0, "_cost_warning": f"unknown model: {model}"}

        cost = int(tokens_in) * model_pricing.get("input", 0) + int(tokens_out) * model_pricing.get(
            "output", 0
        )
        return {"cost_usd": round(cost, 10)}
