from __future__ import annotations

from memorylens._audit.analyzer import CompressionAnalyzer, CompressionAudit
from memorylens._audit.scorer import MockScorer


class TestCompressionAnalyzer:
    def test_basic_audit(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        audit = analyzer.analyze(
            span_id="s1",
            pre_content="User prefers vegetarian meals. No dairy products. Likes Italian food.",
            post_content="User is vegetarian, no dairy, likes Italian.",
        )

        assert isinstance(audit, CompressionAudit)
        assert audit.span_id == "s1"
        assert audit.scorer_backend == "mock"
        assert audit.pre_sentence_count == 3
        assert audit.post_sentence_count > 0
        assert 0.0 <= audit.semantic_loss_score <= 1.0
        assert 0.0 < audit.compression_ratio <= 1.0
        assert len(audit.sentences) == 3

    def test_sentence_statuses(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        audit = analyzer.analyze(
            span_id="s2",
            pre_content="User prefers vegetarian meals. Meeting was on Thursday. No dairy.",
            post_content="User is vegetarian with no dairy.",
        )

        statuses = {s.status for s in audit.sentences}
        # Should have at least some classification
        assert statuses.issubset({"preserved", "lost"})
        # Each sentence should have a score between 0 and 1
        for s in audit.sentences:
            assert 0.0 <= s.best_match_score <= 1.0

    def test_identical_content_low_loss(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        text = "User prefers vegetarian meals. No dairy products."
        audit = analyzer.analyze(span_id="s3", pre_content=text, post_content=text)

        # Identical content should have very low loss
        assert audit.semantic_loss_score < 0.1
        assert all(s.status == "preserved" for s in audit.sentences)

    def test_completely_different_content_high_loss(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        audit = analyzer.analyze(
            span_id="s4",
            pre_content="User prefers vegetarian meals. No dairy products. Likes Italian food.",
            post_content="The weather is sunny today.",
        )

        # Very different content should have higher loss
        assert audit.semantic_loss_score > 0.3

    def test_compression_ratio(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        audit = analyzer.analyze(
            span_id="s5",
            pre_content="A very long sentence about user preferences and details. Another long detailed sentence.",
            post_content="Short summary.",
        )

        assert audit.compression_ratio < 0.5  # post is shorter than pre

    def test_empty_pre_content(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        audit = analyzer.analyze(span_id="s6", pre_content="", post_content="Some output.")

        assert audit.pre_sentence_count == 0
        assert audit.semantic_loss_score == 0.0
        assert audit.sentences == []

    def test_to_dict(self):
        scorer = MockScorer()
        analyzer = CompressionAnalyzer(scorer)

        audit = analyzer.analyze(
            span_id="s7",
            pre_content="First sentence. Second sentence.",
            post_content="Combined sentence.",
        )

        d = audit.to_dict()
        assert d["span_id"] == "s7"
        assert isinstance(d["sentences"], list)
        assert isinstance(d["sentences"][0], dict)
        assert "text" in d["sentences"][0]
        assert "best_match_score" in d["sentences"][0]
        assert "status" in d["sentences"][0]
