from __future__ import annotations

import json

from memorylens._audit.analyzer import CompressionAudit, SentenceAnalysis
from memorylens._exporters.sqlite import SQLiteExporter


def _make_audit(span_id: str = "s1", loss: float = 0.45) -> CompressionAudit:
    return CompressionAudit(
        span_id=span_id,
        semantic_loss_score=loss,
        compression_ratio=0.35,
        pre_sentence_count=3,
        post_sentence_count=1,
        sentences=[
            SentenceAnalysis(text="First sentence.", best_match_score=0.92, status="preserved"),
            SentenceAnalysis(text="Second sentence.", best_match_score=0.45, status="lost"),
            SentenceAnalysis(text="Third sentence.", best_match_score=0.88, status="preserved"),
        ],
        scorer_backend="mock",
    )


class TestAuditStorage:
    def test_save_and_get(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        audit = _make_audit("s1")
        exporter.save_audit(audit)

        result = exporter.get_audit("s1")
        assert result is not None
        assert result["span_id"] == "s1"
        assert result["semantic_loss_score"] == 0.45
        assert result["scorer_backend"] == "mock"
        sentences = json.loads(result["sentences"])
        assert len(sentences) == 3
        assert sentences[0]["text"] == "First sentence."
        exporter.shutdown()

    def test_get_nonexistent(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        result = exporter.get_audit("nonexistent")
        assert result is None
        exporter.shutdown()

    def test_save_overwrites(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.save_audit(_make_audit("s1", loss=0.5))
        exporter.save_audit(_make_audit("s1", loss=0.3))

        result = exporter.get_audit("s1")
        assert result["semantic_loss_score"] == 0.3
        exporter.shutdown()

    def test_list_audits(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        exporter.save_audit(_make_audit("s1", loss=0.1))
        exporter.save_audit(_make_audit("s2", loss=0.5))
        exporter.save_audit(_make_audit("s3", loss=0.8))

        rows, total = exporter.list_audits()
        assert total == 3
        assert len(rows) == 3
        exporter.shutdown()

    def test_list_audits_pagination(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)
        for i in range(5):
            exporter.save_audit(_make_audit(f"s{i}", loss=i * 0.2))

        rows, total = exporter.list_audits(limit=2, offset=0)
        assert total == 5
        assert len(rows) == 2
        exporter.shutdown()

    def test_lazy_table_creation(self, tmp_path):
        """Table should not exist until first save_audit call."""
        db_path = str(tmp_path / "test.db")
        exporter = SQLiteExporter(db_path=db_path)

        # get_audit should work even before table exists
        result = exporter.get_audit("s1")
        assert result is None

        # After save, table exists
        exporter.save_audit(_make_audit("s1"))
        result = exporter.get_audit("s1")
        assert result is not None
        exporter.shutdown()
