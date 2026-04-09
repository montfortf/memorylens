from __future__ import annotations

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from memorylens._auth.keys import hash_key


def create_auth_routes(app: FastAPI) -> None:
    templates = app.state.templates
    exporter = app.state.exporter

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": None},
        )

    @app.post("/login", response_class=HTMLResponse)
    async def login_submit(request: Request, key: str = Form(...)):
        # If no keys exist, auth is disabled — redirect straight through
        if not exporter.has_any_keys():
            response = RedirectResponse(url="/traces", status_code=303)
            return response

        key_hash = hash_key(key)
        key_data = exporter.get_api_key_by_hash(key_hash)

        if not key_data:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "Invalid API key. Please try again."},
            )

        exporter.update_api_key_last_used(key_hash)
        response = RedirectResponse(url="/traces", status_code=303)
        response.set_cookie("memorylens_key", key, httponly=True, samesite="lax")
        return response
