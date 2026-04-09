from __future__ import annotations

import secrets
import time
from typing import Any


def create_shared_link(
    link_type: str,
    target: str,
    created_by: str,
    query_params: dict | None = None,
    expires_in: int | None = None,
) -> dict:
    """Create a shared link dict ready for storage."""
    link_id = secrets.token_hex(4)  # 8 char hex ID
    return {
        "id": link_id,
        "link_type": link_type,
        "target": target,
        "query_params": query_params or {},
        "created_by": created_by,
        "created_at": time.time(),
        "expires_at": time.time() + expires_in if expires_in else None,
    }


def resolve_shared_link(link: dict) -> str:
    """Convert a shared link to the target URL."""
    import json

    base_urls = {
        "trace": f"/traces/{link['target']}",
        "drift": f"/drift/{link['target']}",
        "alerts": "/alerts",
    }
    url = base_urls.get(link["link_type"], f"/traces/{link['target']}")
    params = link.get("query_params")
    if params:
        if isinstance(params, str):
            params = json.loads(params)
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            url += f"?{qs}"
    return url


def is_link_expired(link: dict) -> bool:
    """Check if a shared link has expired."""
    expires_at = link.get("expires_at")
    if expires_at is None:
        return False
    return time.time() > expires_at
