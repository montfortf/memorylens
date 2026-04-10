from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from memorylens._auth.keys import hash_key
from memorylens._auth.permissions import check_permission


class AuthMiddleware:
    """FastAPI dependency for API key authentication."""

    def __init__(self, exporter: Any) -> None:
        self._exporter = exporter

    def _extract_key(self, request: Request) -> str | None:
        """Extract API key from header, query param, or cookie."""
        # Authorization header
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]

        # Query param
        key = request.query_params.get("key")
        if key:
            return key

        # Cookie
        key = request.cookies.get("memorylens_key")
        if key:
            return key

        return None

    def _get_role(self, request: Request) -> str | None:
        """Authenticate and return role, or None if no auth needed/invalid."""
        if not self._exporter.has_any_keys():
            return "admin"  # No-auth mode

        key = self._extract_key(request)
        if not key:
            return None

        key_hash = hash_key(key)
        key_data = self._exporter.get_api_key_by_hash(key_hash)
        if not key_data:
            return None

        self._exporter.update_api_key_last_used(key_hash)
        return key_data["role"]

    def require(self, permission: str):
        """Return a FastAPI dependency that requires a specific permission."""
        def dependency(request: Request):
            role = self._get_role(request)
            if role is None:
                # Check if this is a UI page request or API
                if "text/html" in request.headers.get("accept", ""):
                    return RedirectResponse(url="/login", status_code=303)
                raise HTTPException(status_code=401, detail="Invalid or missing API key")
            if not check_permission(role, permission):
                raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required: {permission}")
            request.state.role = role
            return role
        return dependency

    def optional(self):
        """Return a dependency that authenticates but doesn't require it."""
        def dependency(request: Request):
            role = self._get_role(request)
            request.state.role = role or "anonymous"
            return role
        return dependency
