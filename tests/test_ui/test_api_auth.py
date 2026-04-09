from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from memorylens._ui.server import create_app

    db_path = str(tmp_path / "test.db")
    app = create_app(db_path=db_path)
    return TestClient(app, follow_redirects=False), db_path


@pytest.fixture
def client_with_key(tmp_path):
    from memorylens._auth.keys import generate_key, hash_key, key_prefix
    from memorylens._exporters.sqlite import SQLiteExporter
    from memorylens._ui.server import create_app

    db_path = str(tmp_path / "test.db")
    exp = SQLiteExporter(db_path=db_path)
    key = generate_key()
    exp.save_api_key({
        "key_hash": hash_key(key),
        "key_prefix": key_prefix(key),
        "name": "test-admin",
        "role": "admin",
        "created_at": time.time(),
    })
    exp.shutdown()

    app = create_app(db_path=db_path)
    return TestClient(app, follow_redirects=False), db_path, key


class TestLoginPage:
    def test_get_login_returns_200(self, client):
        c, _ = client
        response = c.get("/login")
        assert response.status_code == 200

    def test_login_page_has_key_input(self, client):
        c, _ = client
        response = c.get("/login")
        assert 'name="key"' in response.text

    def test_login_page_has_submit_button(self, client):
        c, _ = client
        response = c.get("/login")
        assert "Sign in" in response.text or 'type="submit"' in response.text

    def test_login_page_shows_memorylens(self, client):
        c, _ = client
        response = c.get("/login")
        assert "MemoryLens" in response.text

    def test_post_login_no_auth_mode_redirects(self, client):
        """In no-auth mode (no keys in DB), any key submission succeeds."""
        c, _ = client
        response = c.post("/login", data={"key": "anything"})
        assert response.status_code == 303
        assert response.headers["location"] == "/traces"

    def test_post_login_valid_key_sets_cookie(self, client_with_key):
        c, _, key = client_with_key
        response = c.post("/login", data={"key": key})
        assert response.status_code == 303
        assert "memorylens_key" in response.cookies

    def test_post_login_valid_key_redirects_to_traces(self, client_with_key):
        c, _, key = client_with_key
        response = c.post("/login", data={"key": key})
        assert response.status_code == 303
        assert "/traces" in response.headers["location"]

    def test_post_login_invalid_key_shows_error(self, client_with_key):
        c, _, _ = client_with_key
        response = c.post("/login", data={"key": "ml_invalid_key_xxxx"})
        assert response.status_code == 200
        assert "Invalid" in response.text

    def test_post_login_invalid_key_no_cookie(self, client_with_key):
        c, _, _ = client_with_key
        response = c.post("/login", data={"key": "ml_wrong"})
        assert "memorylens_key" not in response.cookies


class TestLoginCookieExpiry:
    def test_cookie_is_httponly(self, client_with_key):
        c, _, key = client_with_key
        response = c.post("/login", data={"key": key})
        # httponly cookies are set but not accessible via JS — check Set-Cookie header
        set_cookie = response.headers.get("set-cookie", "")
        assert "httponly" in set_cookie.lower()
