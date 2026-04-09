from __future__ import annotations

from memorylens._auth.keys import generate_key, hash_key, key_prefix, verify_key


class TestKeys:
    def test_generate_key_format(self):
        key = generate_key()
        assert key.startswith("ml_")
        assert len(key) == 35  # "ml_" + 32 hex chars

    def test_generate_key_unique(self):
        keys = {generate_key() for _ in range(10)}
        assert len(keys) == 10

    def test_hash_key_deterministic(self):
        key = "ml_abc123"
        assert hash_key(key) == hash_key(key)

    def test_hash_key_different_for_different_keys(self):
        assert hash_key("ml_aaa") != hash_key("ml_bbb")

    def test_key_prefix(self):
        assert key_prefix("ml_a1b2c3d4e5f6") == "ml_a1b2c..."

    def test_verify_key_valid(self):
        key = generate_key()
        h = hash_key(key)
        assert verify_key(key, h) is True

    def test_verify_key_invalid(self):
        key = generate_key()
        assert verify_key(key, "wrong_hash") is False
