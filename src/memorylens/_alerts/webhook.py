from __future__ import annotations

import json
import urllib.request


def send_webhook(url: str, payload: dict) -> bool:
    """Send a JSON POST to url with payload. Returns True on success."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except Exception:
        return False
