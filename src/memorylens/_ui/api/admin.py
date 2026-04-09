from __future__ import annotations

import time

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from memorylens._auth.keys import generate_key, hash_key, key_prefix
from memorylens._auth.permissions import ROLES


def create_admin_routes(app: FastAPI) -> None:
    templates = app.state.templates
    exporter = app.state.exporter

    def _get_admin_role(request: Request) -> str | None:
        """Inline auth check — returns role if admin, None otherwise."""
        from memorylens._auth.keys import hash_key as hk

        raw_key = None

        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            raw_key = auth[7:]

        if not raw_key:
            raw_key = request.query_params.get("key")

        if not raw_key:
            raw_key = request.cookies.get("memorylens_key")

        if not raw_key:
            return None

        # No-auth mode: if no keys exist, treat as admin
        if not exporter.has_any_keys():
            return "admin"

        key_data = exporter.get_api_key_by_hash(hk(raw_key))
        if not key_data:
            return None
        return key_data.get("role")

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_page(request: Request):
        # No-auth mode: allow through
        if not exporter.has_any_keys():
            role = "admin"
        else:
            role = _get_admin_role(request)
            if role != "admin":
                return RedirectResponse(url="/login", status_code=303)

        keys = exporter.list_api_keys()
        shared_links = exporter.list_shared_links()

        return templates.TemplateResponse(
            request,
            "admin.html",
            {
                "keys": keys,
                "shared_links": shared_links,
                "roles": ROLES,
                "active_nav": "admin",
                "new_key": None,
            },
        )

    @app.post("/admin/create-key", response_class=HTMLResponse)
    async def admin_create_key(
        request: Request,
        name: str = Form(...),
        role: str = Form(...),
    ):
        # Auth check
        if exporter.has_any_keys():
            admin_role = _get_admin_role(request)
            if admin_role != "admin":
                return RedirectResponse(url="/login", status_code=303)

        if role not in ROLES:
            role = "viewer"

        key = generate_key()
        exporter.save_api_key({
            "key_hash": hash_key(key),
            "key_prefix": key_prefix(key),
            "name": name,
            "role": role,
            "created_at": time.time(),
        })

        keys = exporter.list_api_keys()
        shared_links = exporter.list_shared_links()

        return templates.TemplateResponse(
            request,
            "admin.html",
            {
                "keys": keys,
                "shared_links": shared_links,
                "roles": ROLES,
                "active_nav": "admin",
                "new_key": key,
                "new_key_name": name,
            },
        )

    @app.post("/admin/revoke-key/{name}", response_class=HTMLResponse)
    async def admin_revoke_key(request: Request, name: str):
        # Auth check
        if exporter.has_any_keys():
            admin_role = _get_admin_role(request)
            if admin_role != "admin":
                return RedirectResponse(url="/login", status_code=303)

        exporter.delete_api_key(name)
        return RedirectResponse(url="/admin", status_code=303)
