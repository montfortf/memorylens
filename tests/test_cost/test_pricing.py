from __future__ import annotations

import json

from memorylens._cost.pricing import DEFAULT_PRICING, load_pricing, save_user_pricing


class TestPricing:
    def test_default_pricing_has_common_models(self):
        assert "gpt-4o" in DEFAULT_PRICING
        assert "gpt-4o-mini" in DEFAULT_PRICING
        assert "text-embedding-3-small" in DEFAULT_PRICING

    def test_load_pricing_returns_defaults(self, tmp_path):
        pricing = load_pricing(user_path=tmp_path / "nonexistent.json")
        assert pricing == DEFAULT_PRICING

    def test_load_pricing_merges_user(self, tmp_path):
        user_file = tmp_path / "pricing.json"
        user_file.write_text(json.dumps({"custom-model": {"input": 0.001, "output": 0.002}}))
        pricing = load_pricing(user_path=user_file)
        assert "custom-model" in pricing
        assert "gpt-4o" in pricing  # defaults still present

    def test_user_pricing_overrides_defaults(self, tmp_path):
        user_file = tmp_path / "pricing.json"
        user_file.write_text(json.dumps({"gpt-4o": {"input": 0.999, "output": 0.999}}))
        pricing = load_pricing(user_path=user_file)
        assert pricing["gpt-4o"]["input"] == 0.999

    def test_save_user_pricing(self, tmp_path):
        user_file = tmp_path / "pricing.json"
        save_user_pricing({"my-model": {"input": 0.01, "output": 0.02}}, user_path=user_file)
        assert user_file.exists()
        data = json.loads(user_file.read_text())
        assert data["my-model"]["input"] == 0.01
