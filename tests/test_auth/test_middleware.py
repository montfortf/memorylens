from __future__ import annotations

import time

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from memorylens._auth.keys import generate_key, hash_key, key_prefix
from memorylens._auth.middleware import AuthMiddleware
from memorylens._exporters.sqlite import SQLiteExporter


def _create_app_with_auth(tmp_path, create_admin_key: bool = False):
    db_path = str(tmp_path / "auth.db")
    exporter = SQLiteExporter(db_path=db_path)
    auth = AuthMiddleware(exporter)
    app = FastAPI()

    admin_key = None
    if create_admin_key:
        admin_key = generate_key()
        exporter.save_api_key({
            "key_hash": hash_key(admin_key),
            "key_prefix": key_prefix(admin_key),
            "name": "admin",
            "role": "admin",
            "created_at": time.time(),
        })

    @app.get("/protected")
    async def protected(role: str = Depends(auth.require("view_traces"))):
        return {"role": role}

    @app.get("/admin-only")
    async def admin_only(role: str = Depends(auth.require("manage_keys"))):
        return {"role": role}

    return TestClient(app), admin_key, exporter


class TestAuthMiddleware:
    def test_no_auth_mode(self, tmp_path):
        client, _, _ = _create_app_with_auth(tmp_path, create_admin_key=False)
        resp = client.get("/protected")
        assert resp.status_code == 200

    def test_auth_with_valid_header(self, tmp_path):
        client, key, _ = _create_app_with_auth(tmp_path, create_admin_key=True)
        resp = client.get("/protected", headers={"Authorization": f"Bearer {key}"})
        assert resp.status_code == 200

    def test_auth_with_query_param(self, tmp_path):
        client, key, _ = _create_app_with_auth(tmp_path, create_admin_key=True)
        resp = client.get(f"/protected?key={key}")
        assert resp.status_code == 200

    def test_auth_missing_key_returns_401(self, tmp_path):
        client, _, _ = _create_app_with_auth(tmp_path, create_admin_key=True)
        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_auth_invalid_key_returns_401(self, tmp_path):
        client, _, _ = _create_app_with_auth(tmp_path, create_admin_key=True)
        resp = client.get("/protected", headers={"Authorization": "Bearer ml_invalid"})
        assert resp.status_code == 401

    def test_insufficient_permissions_returns_403(self, tmp_path):
        db_path = str(tmp_path / "auth2.db")
        exporter = SQLiteExporter(db_path=db_path)
        auth = AuthMiddleware(exporter)
        app = FastAPI()

        viewer_key = generate_key()
        exporter.save_api_key({
            "key_hash": hash_key(viewer_key),
            "key_prefix": key_prefix(viewer_key),
            "name": "viewer",
            "role": "viewer",
            "created_at": time.time(),
        })

        @app.get("/admin-only")
        async def admin_only(role: str = Depends(auth.require("manage_keys"))):
            return {"role": role}

        client = TestClient(app)
        resp = client.get("/admin-only", headers={"Authorization": f"Bearer {viewer_key}"})
        assert resp.status_code == 403

    def test_auth_with_cookie(self, tmp_path):
        client, key, _ = _create_app_with_auth(tmp_path, create_admin_key=True)
        resp = client.get("/protected", cookies={"memorylens_key": key})
        assert resp.status_code == 200

    def test_no_auth_mode_admin_only_accessible(self, tmp_path):
        client, _, _ = _create_app_with_auth(tmp_path, create_admin_key=False)
        resp = client.get("/admin-only")
        assert resp.status_code == 200

    def test_last_used_updated_on_valid_auth(self, tmp_path):
        client, key, exporter = _create_app_with_auth(tmp_path, create_admin_key=True)
        h = hash_key(key)

        before = time.time()
        client.get("/protected", headers={"Authorization": f"Bearer {key}"})
        after = time.time()

        key_data = exporter.get_api_key_by_hash(h)
        assert key_data["last_used_at"] is not None
        assert before <= key_data["last_used_at"] <= after

    def test_role_returned_in_response(self, tmp_path):
        client, key, _ = _create_app_with_auth(tmp_path, create_admin_key=True)
        resp = client.get("/protected", headers={"Authorization": f"Bearer {key}"})
        assert resp.json() == {"role": "admin"}
