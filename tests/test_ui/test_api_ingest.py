from __future__ import annotations

from fastapi.testclient import TestClient

from memorylens._exporters.sqlite import SQLiteExporter
from memorylens._ui.server import create_app


def _create_ingest_client(tmp_path) -> tuple[TestClient, str]:
    db_path = str(tmp_path / "ingest.db")
    app = create_app(db_path=db_path, ingest=True)
    return TestClient(app), db_path


def _make_otlp_payload(
    operation: str = "memory.write",
    status: str = "ok",
    agent_id: str = "bot",
    span_id: str = "abc123",
    trace_id: str = "def456",
) -> dict:
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": []},
                "scopeSpans": [
                    {
                        "scope": {"name": "memorylens", "version": "0.1.0"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": span_id,
                                "name": operation,
                                "kind": 1,
                                "startTimeUnixNano": "1000000000000",
                                "endTimeUnixNano": "1000012000000",
                                "attributes": [
                                    {
                                        "key": "memorylens.operation",
                                        "value": {"stringValue": operation},
                                    },
                                    {"key": "memorylens.status", "value": {"stringValue": status}},
                                    {
                                        "key": "memorylens.agent_id",
                                        "value": {"stringValue": agent_id},
                                    },
                                    {
                                        "key": "memorylens.session_id",
                                        "value": {"stringValue": "sess-1"},
                                    },
                                    {
                                        "key": "memorylens.user_id",
                                        "value": {"stringValue": "user-1"},
                                    },
                                    {
                                        "key": "memorylens.input_content",
                                        "value": {"stringValue": "test data"},
                                    },
                                    {"key": "memorylens.backend", "value": {"stringValue": "mem0"}},
                                ],
                                "status": {"code": 1},
                            }
                        ],
                    }
                ],
            }
        ],
    }


class TestOTLPIngest:
    def test_ingest_valid_payload(self, tmp_path):
        client, db_path = _create_ingest_client(tmp_path)
        payload = _make_otlp_payload()
        resp = client.post("/v1/traces", json=payload)
        assert resp.status_code == 200

        exporter = SQLiteExporter(db_path=db_path)
        rows = exporter.query(limit=10)
        assert len(rows) == 1
        assert rows[0]["operation"] == "memory.write"
        assert rows[0]["agent_id"] == "bot"
        exporter.shutdown()

    def test_ingest_ignores_non_memorylens_spans(self, tmp_path):
        client, db_path = _create_ingest_client(tmp_path)
        payload = {
            "resourceSpans": [
                {
                    "resource": {"attributes": []},
                    "scopeSpans": [
                        {
                            "scope": {"name": "other"},
                            "spans": [
                                {
                                    "traceId": "t1",
                                    "spanId": "s1",
                                    "name": "http.request",
                                    "kind": 1,
                                    "startTimeUnixNano": "1000",
                                    "endTimeUnixNano": "2000",
                                    "attributes": [
                                        {"key": "http.method", "value": {"stringValue": "GET"}},
                                    ],
                                    "status": {"code": 1},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        resp = client.post("/v1/traces", json=payload)
        assert resp.status_code == 200

        exporter = SQLiteExporter(db_path=db_path)
        rows = exporter.query(limit=10)
        assert len(rows) == 0
        exporter.shutdown()

    def test_ingest_empty_payload(self, tmp_path):
        client, _ = _create_ingest_client(tmp_path)
        resp = client.post("/v1/traces", json={"resourceSpans": []})
        assert resp.status_code == 200

    def test_ingest_malformed_payload(self, tmp_path):
        client, _ = _create_ingest_client(tmp_path)
        resp = client.post("/v1/traces", json={"bad": "data"})
        assert resp.status_code == 400

    def test_ingest_not_available_without_flag(self, tmp_path):
        db_path = str(tmp_path / "noingest.db")
        app = create_app(db_path=db_path, ingest=False)
        client = TestClient(app)
        resp = client.post("/v1/traces", json={})
        assert resp.status_code == 404 or resp.status_code == 405
