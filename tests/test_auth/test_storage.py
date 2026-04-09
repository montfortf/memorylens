from __future__ import annotations

import time

import pytest

from memorylens._auth.keys import generate_key, hash_key, key_prefix
from memorylens._exporters.sqlite import SQLiteExporter


@pytest.fixture
def exporter(tmp_path):
    db_path = str(tmp_path / "test_auth.db")
    exp = SQLiteExporter(db_path=db_path)
    yield exp
    exp.shutdown()


def _make_key_data(name: str = "test-key", role: str = "viewer") -> tuple[str, dict]:
    key = generate_key()
    data = {
        "key_hash": hash_key(key),
        "key_prefix": key_prefix(key),
        "name": name,
        "role": role,
        "created_at": time.time(),
    }
    return key, data


class TestApiKeyStorage:
    def test_has_any_keys_empty(self, exporter):
        assert exporter.has_any_keys() is False

    def test_save_and_has_keys(self, exporter):
        _, data = _make_key_data()
        exporter.save_api_key(data)
        assert exporter.has_any_keys() is True

    def test_get_api_key_by_hash(self, exporter):
        key, data = _make_key_data(name="admin", role="admin")
        exporter.save_api_key(data)
        result = exporter.get_api_key_by_hash(hash_key(key))
        assert result is not None
        assert result["name"] == "admin"
        assert result["role"] == "admin"
        assert result["key_prefix"] == data["key_prefix"]

    def test_get_api_key_by_hash_missing(self, exporter):
        result = exporter.get_api_key_by_hash("nonexistent_hash")
        assert result is None

    def test_list_api_keys_empty(self, exporter):
        assert exporter.list_api_keys() == []

    def test_list_api_keys(self, exporter):
        _, d1 = _make_key_data(name="key1", role="admin")
        _, d2 = _make_key_data(name="key2", role="viewer")
        exporter.save_api_key(d1)
        exporter.save_api_key(d2)
        keys = exporter.list_api_keys()
        assert len(keys) == 2
        names = {k["name"] for k in keys}
        assert names == {"key1", "key2"}

    def test_delete_api_key(self, exporter):
        _, data = _make_key_data(name="to-delete")
        exporter.save_api_key(data)
        assert exporter.has_any_keys() is True
        exporter.delete_api_key("to-delete")
        assert exporter.has_any_keys() is False
        assert exporter.list_api_keys() == []

    def test_delete_nonexistent_key_is_noop(self, exporter):
        exporter.delete_api_key("does-not-exist")  # should not raise

    def test_update_api_key_last_used(self, exporter):
        key, data = _make_key_data(name="active-key")
        exporter.save_api_key(data)
        h = hash_key(key)

        before = time.time()
        exporter.update_api_key_last_used(h)
        after = time.time()

        result = exporter.get_api_key_by_hash(h)
        assert result["last_used_at"] is not None
        assert before <= result["last_used_at"] <= after

    def test_save_duplicate_name_different_hash(self, exporter):
        """Two keys can share a name but not a hash (UNIQUE constraint on hash)."""
        _, d1 = _make_key_data(name="shared-name", role="viewer")
        _, d2 = _make_key_data(name="shared-name", role="editor")
        exporter.save_api_key(d1)
        exporter.save_api_key(d2)  # different hash, should succeed
        keys = exporter.list_api_keys()
        assert len(keys) == 2

    def test_role_stored_correctly(self, exporter):
        for role in ("admin", "editor", "viewer", "ingester"):
            key = generate_key()
            exporter.save_api_key({
                "key_hash": hash_key(key),
                "key_prefix": key_prefix(key),
                "name": f"key-{role}",
                "role": role,
                "created_at": time.time(),
            })
        keys = exporter.list_api_keys()
        roles = {k["role"] for k in keys}
        assert roles == {"admin", "editor", "viewer", "ingester"}
