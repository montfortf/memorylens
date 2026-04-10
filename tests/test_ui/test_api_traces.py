from __future__ import annotations

from fastapi.testclient import TestClient

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter
from memorylens._ui.server import create_app


def _make_span(
    span_id: str = "s1",
    trace_id: str = "t1",
    operation: MemoryOperation = MemoryOperation.WRITE,
    status: SpanStatus = SpanStatus.OK,
    input_content: str = "test input",
    output_content: str = "test output",
    attributes: dict | None = None,
) -> MemorySpan:
    return MemorySpan(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=None,
        operation=operation,
        status=status,
        start_time=1000000000000.0,
        end_time=1000012000000.0,
        duration_ms=12.0,
        agent_id="bot",
        session_id="sess-1",
        user_id="user-1",
        input_content=input_content,
        output_content=output_content,
        attributes=attributes or {"backend": "test"},
    )


def _create_seeded_client(tmp_path) -> TestClient:
    db_path = str(tmp_path / "test.db")
    exporter = SQLiteExporter(db_path=db_path)
    exporter.export(
        [
            _make_span("s1", "t1", MemoryOperation.WRITE),
            _make_span(
                "s2",
                "t2",
                MemoryOperation.READ,
                attributes={
                    "backend": "pinecone",
                    "query": "music prefs",
                    "scores": [0.92, 0.87, 0.65],
                    "threshold": 0.7,
                    "top_k": 5,
                    "results_count": 2,
                },
            ),
            _make_span("s3", "t3", MemoryOperation.WRITE, status=SpanStatus.ERROR),
        ]
    )
    exporter.shutdown()
    app = create_app(db_path=db_path)
    return TestClient(app)


class TestTraceListPage:
    def test_traces_page_returns_html(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "MemoryLens" in resp.text

    def test_traces_page_contains_spans(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces")
        assert "t1" in resp.text

    def test_index_redirects_to_traces(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == "/traces"


class TestTraceListAPI:
    def test_api_traces_returns_partial(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/api/traces", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "<nav" not in resp.text

    def test_api_traces_filter_operation(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/api/traces?operation=memory.read", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "memory.read" in resp.text

    def test_api_traces_filter_status(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/api/traces?status=error", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "error" in resp.text


class TestTraceDetailPage:
    def test_detail_returns_html(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t1")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "memory.write" in resp.text

    def test_detail_shows_attributes(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t1")
        assert "backend" in resp.text

    def test_detail_not_found(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/nonexistent")
        assert resp.status_code == 404

    def test_detail_shows_read_retrieval_link(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t2")
        assert "Debug Retrieval" in resp.text

    def test_detail_hides_retrieval_link_for_write(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t1")
        assert "Debug Retrieval" not in resp.text


class TestRetrievalDebugger:
    def test_retrieval_page_returns_html(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t2/retrieval")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Retrieval" in resp.text

    def test_retrieval_shows_scores(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t2/retrieval")
        assert "0.92" in resp.text
        assert "0.87" in resp.text

    def test_retrieval_shows_threshold(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t2/retrieval")
        assert "0.7" in resp.text

    def test_retrieval_404_for_write_span(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/t1/retrieval")
        assert resp.status_code == 404

    def test_retrieval_404_for_missing_trace(self, tmp_path):
        client = _create_seeded_client(tmp_path)
        resp = client.get("/traces/nonexistent/retrieval")
        assert resp.status_code == 404
