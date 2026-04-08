from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from memorylens._alerts.webhook import send_webhook


class TestSendWebhook:
    def test_sends_post_with_json_payload(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            result = send_webhook("https://hooks.example.com/test", {"key": "value"})

        assert result is True
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://hooks.example.com/test"
        assert req.method == "POST"
        assert req.get_header("Content-type") == "application/json"
        body = json.loads(req.data)
        assert body == {"key": "value"}

    def test_uses_10_second_timeout(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            send_webhook("https://hooks.example.com/test", {})

        # timeout=10 is passed as kwarg
        _, kwargs = mock_urlopen.call_args
        assert kwargs.get("timeout") == 10

    def test_returns_false_on_connection_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            result = send_webhook("https://hooks.example.com/test", {"x": 1})
        assert result is False

    def test_returns_false_on_timeout(self):
        import socket
        with patch("urllib.request.urlopen", side_effect=socket.timeout("timed out")):
            result = send_webhook("https://hooks.example.com/test", {"x": 1})
        assert result is False

    def test_returns_false_on_4xx_status(self):
        mock_response = MagicMock()
        mock_response.status = 400
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = send_webhook("https://hooks.example.com/test", {})
        assert result is False

    def test_payload_format_matches_spec(self):
        """Verify the payload matches the webhook payload format from spec."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        payload = {
            "alert": "drift_threshold_exceeded",
            "rule_name": "critical-drift",
            "message": "Entity user_42_diet_prefs has grade F (drift: 0.82)",
            "details": {"memory_key": "user_42_diet_prefs", "grade": "F", "drift_score": 0.82},
            "timestamp": "2026-04-08T12:00:00Z",
        }

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            result = send_webhook("https://hooks.slack.com/test", payload)

        assert result is True
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data)
        assert body["alert"] == "drift_threshold_exceeded"
        assert body["rule_name"] == "critical-drift"
        assert "details" in body
        assert "timestamp" in body
