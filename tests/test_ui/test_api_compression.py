from __future__ import annotations

from fastapi.testclient import TestClient

from memorylens._audit.analyzer import CompressionAudit, SentenceAnalysis
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter
from memorylens._ui.server import create_app


def _make_compress_span(span_id: str = "s1", trace_id: str = "t1") -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=None,
        operation=MemoryOperation.COMPRESS,
        status=SpanStatus.OK,
        start_time=1000000000000.0,
        end_time=1000100000000.0,
        duration_ms=100.0,
        agent_id="bot",
        session_id="sess-1",
        user_id="user-1",
        input_content="User prefers jazz. Also likes classical.",
        output_content="User likes jazz and classical.",
        attributes={"model": "gpt-4o-mini"},
    )


def _make_audit(span_id: str = "s1") -> CompressionAudit:
    return CompressionAudit(
        span_id=span_id,
        semantic_loss_score=0.35,
        compression_ratio=0.65,
        pre_sentence_count=2,
        post_sentence_count=1,
        sentences=[
            SentenceAnalysis(text="User prefers jazz.", best_match_score=0.92, status="preserved"),
            SentenceAnalysis(text="Also likes classical.", best_match_score=0.55, status="lost"),
        ],
        scorer_backend="mock",
    )


def _create_seeded_client(tmp_path, with_audit: bool = False) -> TestClient:
    db_path = str(tmp_path / "test.db")
    exporter = SQLiteExporter(db_path=db_path)
    exporter.export([
        _make_compress_span("s1", "t1"),
        MemorySpan(
            span_id="s2", trace_id="t2", parent_span_id=None,
            operation=MemoryOperation.WRITE, status=SpanStatus.OK,
            start_time=1000.0, end_time=1010.0, duration_ms=10.0,
            agent_id="bot", session_id="sess-1", user_id="user-1",
            input_content="data", output_content="stored",
            attributes={"backend": "test"},
        ),
    ])
    if with_audit:
        exporter.save_audit(_make_audit("s1"))
    exporter.shutdown()
    app = create_app(db_path=db_path)
    return TestClient(app)


class TestCompressionAuditPage:
    def test_page_with_audit(self, tmp_path):
        client = _create_seeded_client(tmp_path, with_audit=True)
        resp = client.get("/traces/t1/compression")
        assert resp.status_code == 200
        assert "Compression" in resp.text
        assert "0.92" in resp.text  # preserved score
        assert "0.55" in resp.text  # lost score

    def test_page_without_audit(self, tmp_path):
        client = _create_seeded_client(tmp_path, with_audit=False)
        resp = client.get("/traces/t1/compression")
        assert resp.status_code == 200
        assert "not been audited" in resp.text or "Run Audit" in resp.text

    def test_page_404_for_non_compress(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t2/compression")
        assert resp.status_code == 404

    def test_page_404_for_missing_trace(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/nonexistent/compression")
        assert resp.status_code == 404

    def test_detail_page_shows_compression_link(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t1")
        assert "Debug Compression" in resp.text

    def test_detail_page_hides_compression_link_for_write(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t2")
        assert "Debug Compression" not in resp.text
