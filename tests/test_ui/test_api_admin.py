from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_no_auth(tmp_path):
    """App with no keys (no-auth mode)."""
    from memorylens._ui.server import create_app

    db_path = str(tmp_path / "test.db")
    app = create_app(db_path=db_path)
    return TestClient(app, follow_redirects=False), db_path


@pytest.fixture
def admin_client(tmp_path):
    """App with one admin key; returns (client, db_path, raw_key)."""
    from memorylens._auth.keys import generate_key, hash_key, key_prefix
    from memorylens._exporters.sqlite import SQLiteExporter
    from memorylens._ui.server import create_app

    db_path = str(tmp_path / "test.db")
    exp = SQLiteExporter(db_path=db_path)
    key = generate_key()
    exp.save_api_key({
        "key_hash": hash_key(key),
        "key_prefix": key_prefix(key),
        "name": "admin",
        "role": "admin",
        "created_at": time.time(),
    })
    exp.shutdown()

    app = create_app(db_path=db_path)
    # Client with cookie auth
    client = TestClient(app, follow_redirects=False, cookies={"memorylens_key": key})
    return client, db_path, key


@pytest.fixture
def viewer_client(tmp_path):
    """App with one viewer key; returns (client, db_path, raw_key)."""
    from memorylens._auth.keys import generate_key, hash_key, key_prefix
    from memorylens._exporters.sqlite import SQLiteExporter
    from memorylens._ui.server import create_app

    db_path = str(tmp_path / "test.db")
    exp = SQLiteExporter(db_path=db_path)
    key = generate_key()
    exp.save_api_key({
        "key_hash": hash_key(key),
        "key_prefix": key_prefix(key),
        "name": "viewer",
        "role": "viewer",
        "created_at": time.time(),
    })
    exp.shutdown()

    app = create_app(db_path=db_path)
    client = TestClient(app, follow_redirects=False, cookies={"memorylens_key": key})
    return client, db_path, key


class TestAdminPageAccess:
    def test_no_auth_mode_allows_admin(self, client_no_auth):
        c, _ = client_no_auth
        response = c.get("/admin")
        assert response.status_code == 200

    def test_admin_key_allows_admin_page(self, admin_client):
        c, _, _ = admin_client
        response = c.get("/admin")
        assert response.status_code == 200

    def test_viewer_key_redirects_to_login(self, viewer_client):
        c, _, _ = viewer_client
        response = c.get("/admin")
        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    def test_no_key_redirects_to_login(self, tmp_path):
        from memorylens._auth.keys import generate_key, hash_key
        from memorylens._exporters.sqlite import SQLiteExporter
        from memorylens._ui.server import create_app

        db_path = str(tmp_path / "test.db")
        exp = SQLiteExporter(db_path=db_path)
        exp.save_api_key({
            "key_hash": hash_key(generate_key()),
            "key_prefix": "ml_test...",
            "name": "admin",
            "role": "admin",
            "created_at": time.time(),
        })
        exp.shutdown()

        app = create_app(db_path=db_path)
        c = TestClient(app, follow_redirects=False)
        response = c.get("/admin")
        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    def test_admin_page_shows_keys_table(self, admin_client):
        c, _, _ = admin_client
        response = c.get("/admin")
        assert response.status_code == 200
        assert "admin" in response.text

    def test_admin_page_shows_create_form(self, admin_client):
        c, _, _ = admin_client
        response = c.get("/admin")
        assert response.status_code == 200
        assert 'action="/admin/create-key"' in response.text

    def test_admin_page_shows_roles_dropdown(self, admin_client):
        c, _, _ = admin_client
        response = c.get("/admin")
        assert response.status_code == 200
        for role in ["admin", "editor", "viewer", "ingester"]:
            assert role in response.text

    def test_admin_page_shows_shared_links_section(self, admin_client):
        c, _, _ = admin_client
        response = c.get("/admin")
        assert response.status_code == 200
        assert "Shared Links" in response.text


class TestAdminCreateKey:
    def test_create_key_in_no_auth_mode(self, client_no_auth):
        c, _ = client_no_auth
        response = c.post("/admin/create-key", data={"name": "new-key", "role": "viewer"})
        assert response.status_code == 200
        assert "new-key" in response.text
        assert "ml_" in response.text  # raw key shown once

    def test_create_key_as_admin(self, admin_client):
        c, _, _ = admin_client
        response = c.post("/admin/create-key", data={"name": "ci-bot", "role": "ingester"})
        assert response.status_code == 200
        assert "ci-bot" in response.text
        assert "ml_" in response.text

    def test_create_key_shows_warning_to_save(self, admin_client):
        c, _, _ = admin_client
        response = c.post("/admin/create-key", data={"name": "newkey", "role": "viewer"})
        assert response.status_code == 200
        assert "won't be shown again" in response.text or "save it now" in response.text.lower()

    def test_create_key_as_viewer_redirects(self, viewer_client):
        c, _, _ = viewer_client
        response = c.post("/admin/create-key", data={"name": "x", "role": "viewer"})
        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    def test_created_key_appears_in_keys_list(self, admin_client):
        c, _, _ = admin_client
        c.post("/admin/create-key", data={"name": "added-key", "role": "editor"})
        response = c.get("/admin")
        assert "added-key" in response.text


class TestAdminRevokeKey:
    def test_revoke_key_as_admin(self, admin_client):
        c, db_path, _ = admin_client
        # Add a second key to revoke
        from memorylens._auth.keys import generate_key, hash_key
        from memorylens._exporters.sqlite import SQLiteExporter

        exp = SQLiteExporter(db_path=db_path)
        exp.save_api_key({
            "key_hash": hash_key(generate_key()),
            "key_prefix": "ml_todel...",
            "name": "to-delete",
            "role": "viewer",
            "created_at": time.time(),
        })
        exp.shutdown()

        response = c.post("/admin/revoke-key/to-delete")
        assert response.status_code == 303
        assert response.headers["location"] == "/admin"

    def test_revoke_key_as_viewer_redirects(self, viewer_client):
        c, _, _ = viewer_client
        response = c.post("/admin/revoke-key/some-key")
        assert response.status_code == 303
        assert "/login" in response.headers["location"]


class TestSharingRoutes:
    def test_create_share_no_auth_mode(self, client_no_auth):
        c, _ = client_no_auth
        response = c.post(
            "/api/share",
            json={"link_type": "trace", "target": "trace-abc"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert data["url"].startswith("/shared/")

    def test_create_share_with_valid_key(self, admin_client):
        c, _, _ = admin_client
        response = c.post(
            "/api/share",
            json={"link_type": "drift", "target": "user_pref"},
        )
        assert response.status_code == 200
        assert "url" in response.json()

    def test_create_share_no_key_in_auth_mode_returns_401(self, tmp_path):
        from memorylens._auth.keys import generate_key, hash_key
        from memorylens._exporters.sqlite import SQLiteExporter
        from memorylens._ui.server import create_app

        db_path = str(tmp_path / "test.db")
        exp = SQLiteExporter(db_path=db_path)
        exp.save_api_key({
            "key_hash": hash_key(generate_key()),
            "key_prefix": "ml_test...",
            "name": "admin",
            "role": "admin",
            "created_at": time.time(),
        })
        exp.shutdown()

        app = create_app(db_path=db_path)
        c = TestClient(app, follow_redirects=False)
        response = c.post("/api/share", json={"link_type": "trace", "target": "x"})
        assert response.status_code == 401

    def test_resolve_shared_link_redirects(self, client_no_auth):
        c, _ = client_no_auth
        # Create a link first
        create_resp = c.post("/api/share", json={"link_type": "trace", "target": "t123"})
        link_id = create_resp.json()["id"]

        response = c.get(f"/shared/{link_id}")
        assert response.status_code == 302
        assert "/traces/t123" in response.headers["location"]

    def test_resolve_unknown_link_returns_404(self, client_no_auth):
        c, _ = client_no_auth
        response = c.get("/shared/deadbeef")
        assert response.status_code == 404

    def test_resolve_expired_link_returns_410(self, client_no_auth):
        c, _ = client_no_auth
        # Create a link with 1-second expiry
        create_resp = c.post(
            "/api/share",
            json={"link_type": "trace", "target": "t1", "expires_in": -1},
        )
        link_id = create_resp.json()["id"]

        response = c.get(f"/shared/{link_id}")
        assert response.status_code == 410
