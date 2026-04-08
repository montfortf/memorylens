from __future__ import annotations

from memorylens._audit.scorer import CachedScorer, MockScorer


class TestCachedScorer:
    def test_cache_hit_avoids_scorer_call(self):
        """Second embed of same text must not call scorer again."""
        call_count = 0
        original_embed = MockScorer.embed

        class CountingMock(MockScorer):
            def embed(self, texts):
                nonlocal call_count
                call_count += len(texts)
                return original_embed(self, texts)

        scorer = CachedScorer(CountingMock())
        scorer.embed(["hello world"])
        first_count = call_count
        scorer.embed(["hello world"])

        assert call_count == first_count  # no additional calls

    def test_cache_miss_calls_scorer(self):
        """New text must produce an embedding via the underlying scorer."""
        scorer = CachedScorer(MockScorer())
        result = scorer.embed(["unique text for cache miss test"])
        assert len(result) == 1
        assert len(result[0]) == 64  # MockScorer default dim

    def test_mixed_batch_only_embeds_new_texts(self):
        """Mixed batch: cached texts reuse cache, new texts get embedded."""
        call_count = 0
        original_embed = MockScorer.embed

        class CountingMock(MockScorer):
            def embed(self, texts):
                nonlocal call_count
                call_count += len(texts)
                return original_embed(self, texts)

        mock = CountingMock()
        scorer = CachedScorer(mock)

        # Prime cache with text_a
        scorer.embed(["text_a"])
        count_after_first = call_count

        # Embed text_a (cached) + text_b (new)
        results = scorer.embed(["text_a", "text_b"])
        assert call_count == count_after_first + 1  # only text_b sent to scorer
        assert len(results) == 2
        assert len(results[0]) == 64
        assert len(results[1]) == 64

    def test_clear_cache_forces_reembed(self):
        """After clear_cache(), same text must be re-embedded."""
        call_count = 0
        original_embed = MockScorer.embed

        class CountingMock(MockScorer):
            def embed(self, texts):
                nonlocal call_count
                call_count += len(texts)
                return original_embed(self, texts)

        scorer = CachedScorer(CountingMock())
        scorer.embed(["text to clear"])
        count_after_first = call_count
        scorer.clear_cache()
        scorer.embed(["text to clear"])
        assert call_count == count_after_first + 1  # re-embedded after clear

    def test_deterministic_embeddings(self):
        """Same text always produces identical embedding vectors."""
        scorer = CachedScorer(MockScorer())
        r1 = scorer.embed(["deterministic check"])
        scorer.clear_cache()
        r2 = scorer.embed(["deterministic check"])
        assert r1[0] == r2[0]
