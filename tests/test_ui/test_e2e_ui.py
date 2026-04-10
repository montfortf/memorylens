from __future__ import annotations

from fastapi.testclient import TestClient

import memorylens
from memorylens import context, instrument_read, instrument_write
from memorylens._ui.server import create_app


class TestEndToEndUI:
    def test_sdk_writes_ui_reads(self, tmp_path):
        """Full flow: SDK writes traces -> UI serves them."""
        db_path = str(tmp_path / "e2e_ui.db")

        memorylens.init(
            service_name="test",
            exporter="sqlite",
            db_path=db_path,
            capture_content=True,
        )

        @instrument_write(backend="test_db")
        def store(content: str) -> str:
            return "stored"

        @instrument_read(backend="test_db")
        def search(query: str) -> list[str]:
            return ["r1", "r2"]

        with context(agent_id="e2e-bot", session_id="e2e-sess"):
            store("user likes jazz")
            search("music preferences")

        memorylens.shutdown()

        app = create_app(db_path=db_path)
        client = TestClient(app)

        resp = client.get("/traces")
        assert resp.status_code == 200
        assert "e2e-bot" in resp.text

        resp = client.get("/api/traces", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "memory.write" in resp.text
        assert "memory.read" in resp.text

    def test_ingest_and_view(self, tmp_path):
        """Ingest OTLP traces then view them in UI."""
        db_path = str(tmp_path / "e2e_ingest.db")
        app = create_app(db_path=db_path, ingest=True)
        client = TestClient(app)

        payload = {
            "resourceSpans": [
                {
                    "resource": {"attributes": []},
                    "scopeSpans": [
                        {
                            "scope": {"name": "memorylens"},
                            "spans": [
                                {
                                    "traceId": "e2etrace",
                                    "spanId": "e2espan",
                                    "name": "memory.write",
                                    "kind": 1,
                                    "startTimeUnixNano": "1000000000000",
                                    "endTimeUnixNano": "1000012000000",
                                    "attributes": [
                                        {
                                            "key": "memorylens.operation",
                                            "value": {"stringValue": "memory.write"},
                                        },
                                        {
                                            "key": "memorylens.status",
                                            "value": {"stringValue": "ok"},
                                        },
                                        {
                                            "key": "memorylens.agent_id",
                                            "value": {"stringValue": "ingest-bot"},
                                        },
                                        {
                                            "key": "memorylens.input_content",
                                            "value": {"stringValue": "ingested data"},
                                        },
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

        resp = client.get("/traces")
        assert resp.status_code == 200
        assert "ingest-bot" in resp.text
