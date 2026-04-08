from __future__ import annotations

import numpy as np

from memorylens._audit.scorer import MockScorer, cosine_similarity, create_scorer


class TestCosineSimlarity:
    def test_identical_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == 1.0

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert abs(cosine_similarity(a, b)) < 0.001

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert cosine_similarity(a, b) == -1.0

    def test_similar_vectors(self):
        a = [1.0, 0.5, 0.0]
        b = [1.0, 0.6, 0.0]
        score = cosine_similarity(a, b)
        assert score > 0.99


class TestMockScorer:
    def test_returns_embeddings(self):
        scorer = MockScorer()
        embeddings = scorer.embed(["hello world", "goodbye world"])
        assert len(embeddings) == 2
        assert len(embeddings[0]) > 0

    def test_similar_texts_similar_embeddings(self):
        scorer = MockScorer()
        embeddings = scorer.embed(["user likes jazz", "user likes jazz music"])
        score = cosine_similarity(embeddings[0], embeddings[1])
        # Same prefix should produce somewhat similar embeddings
        assert score > 0.5

    def test_different_texts_different_embeddings(self):
        scorer = MockScorer()
        embeddings = scorer.embed(["user likes jazz", "the weather is sunny today"])
        # Very different texts shouldn't be identical
        assert embeddings[0] != embeddings[1]


class TestCreateScorer:
    def test_create_mock(self):
        scorer = create_scorer("mock")
        assert isinstance(scorer, MockScorer)

    def test_create_unknown_raises(self):
        try:
            create_scorer("nonexistent")
            assert False, "Should have raised"
        except ValueError as e:
            assert "nonexistent" in str(e)
