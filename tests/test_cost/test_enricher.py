from __future__ import annotations

from memorylens._cost.enricher import CostEnricher


class TestCostEnricher:
    def test_compute_cost_with_known_model(self):
        pricing = {"gpt-4o-mini": {"input": 0.00000015, "output": 0.0000006}}
        enricher = CostEnricher(pricing=pricing)
        result = enricher.enrich_span(
            {"tokens_in": 1000, "tokens_out": 500, "model": "gpt-4o-mini"}
        )
        assert result is not None
        expected = 1000 * 0.00000015 + 500 * 0.0000006
        assert abs(result["cost_usd"] - expected) < 1e-9

    def test_skip_no_token_data(self):
        enricher = CostEnricher(pricing={})
        result = enricher.enrich_span({"backend": "mem0"})
        assert result is None

    def test_unknown_model_returns_zero_cost(self):
        enricher = CostEnricher(pricing={})
        result = enricher.enrich_span({"tokens_in": 100, "model": "unknown"})
        assert result is not None
        assert result["cost_usd"] == 0.0
        assert "_cost_warning" in result

    def test_input_only(self):
        pricing = {"text-embedding-3-small": {"input": 0.00000002, "output": 0.0}}
        enricher = CostEnricher(pricing=pricing)
        result = enricher.enrich_span({"tokens_in": 5000, "model": "text-embedding-3-small"})
        assert result is not None
        assert result["cost_usd"] == 5000 * 0.00000002

    def test_zero_tokens(self):
        enricher = CostEnricher(pricing={"m": {"input": 0.01, "output": 0.01}})
        result = enricher.enrich_span({"tokens_in": 0, "tokens_out": 0})
        assert result is None
