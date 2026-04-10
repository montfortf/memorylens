from __future__ import annotations

import time

from memorylens._auth.sharing import create_shared_link, is_link_expired, resolve_shared_link


class TestCreateSharedLink:
    def test_returns_dict_with_required_fields(self):
        link = create_shared_link("trace", "abc123", "admin-key")
        assert "id" in link
        assert link["link_type"] == "trace"
        assert link["target"] == "abc123"
        assert link["created_by"] == "admin-key"
        assert "created_at" in link
        assert "expires_at" in link

    def test_id_is_8_hex_chars(self):
        link = create_shared_link("trace", "abc123", "admin-key")
        assert len(link["id"]) == 8
        int(link["id"], 16)  # should not raise

    def test_no_expiry_by_default(self):
        link = create_shared_link("trace", "abc123", "admin-key")
        assert link["expires_at"] is None

    def test_expires_in_sets_future_expiry(self):
        before = time.time()
        link = create_shared_link("trace", "abc123", "admin-key", expires_in=3600)
        after = time.time()
        assert link["expires_at"] is not None
        assert before + 3600 <= link["expires_at"] <= after + 3600

    def test_empty_query_params_by_default(self):
        link = create_shared_link("trace", "abc123", "admin-key")
        assert link["query_params"] == {}

    def test_custom_query_params_stored(self):
        link = create_shared_link("drift", "key1", "admin-key", query_params={"foo": "bar"})
        assert link["query_params"] == {"foo": "bar"}

    def test_each_call_produces_unique_id(self):
        ids = {create_shared_link("trace", "t", "u")["id"] for _ in range(20)}
        assert len(ids) == 20

    def test_drift_link_type(self):
        link = create_shared_link("drift", "some-key", "editor")
        assert link["link_type"] == "drift"
        assert link["target"] == "some-key"

    def test_alerts_link_type(self):
        link = create_shared_link("alerts", "", "viewer")
        assert link["link_type"] == "alerts"


class TestResolveSharedLink:
    def test_trace_link_resolves_to_trace_detail(self):
        link = create_shared_link("trace", "trace-abc", "admin")
        url = resolve_shared_link(link)
        assert url == "/traces/trace-abc"

    def test_drift_link_resolves_to_drift_detail(self):
        link = create_shared_link("drift", "user_pref", "admin")
        url = resolve_shared_link(link)
        assert url == "/drift/user_pref"

    def test_alerts_link_resolves_to_alerts(self):
        link = create_shared_link("alerts", "", "admin")
        url = resolve_shared_link(link)
        assert url == "/alerts"

    def test_unknown_link_type_falls_back_to_trace(self):
        link = {"link_type": "unknown", "target": "x", "query_params": {}}
        url = resolve_shared_link(link)
        assert url == "/traces/x"

    def test_query_params_appended(self):
        link = create_shared_link("trace", "t1", "admin", query_params={"status": "error"})
        url = resolve_shared_link(link)
        assert "?status=error" in url

    def test_multiple_query_params(self):
        link = create_shared_link("drift", "k", "admin", query_params={"a": "1", "b": "2"})
        url = resolve_shared_link(link)
        assert "?" in url
        assert "a=1" in url
        assert "b=2" in url

    def test_empty_query_params_no_question_mark(self):
        link = create_shared_link("trace", "t1", "admin", query_params={})
        url = resolve_shared_link(link)
        assert "?" not in url

    def test_string_query_params_parsed(self):
        """query_params stored as JSON string (from DB) should still resolve."""
        import json

        link = {"link_type": "trace", "target": "t2", "query_params": json.dumps({"x": "1"})}
        url = resolve_shared_link(link)
        assert "x=1" in url


class TestIsLinkExpired:
    def test_no_expiry_never_expired(self):
        link = create_shared_link("trace", "t", "admin")
        assert is_link_expired(link) is False

    def test_future_expiry_not_expired(self):
        link = create_shared_link("trace", "t", "admin", expires_in=3600)
        assert is_link_expired(link) is False

    def test_past_expiry_is_expired(self):
        link = {
            "link_type": "trace",
            "target": "t",
            "created_by": "admin",
            "created_at": time.time() - 7200,
            "expires_at": time.time() - 3600,
        }
        assert is_link_expired(link) is True

    def test_none_expires_at_not_expired(self):
        link = {"expires_at": None}
        assert is_link_expired(link) is False
