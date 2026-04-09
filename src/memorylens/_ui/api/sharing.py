from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from memorylens._auth.sharing import create_shared_link, is_link_expired, resolve_shared_link


def create_sharing_routes(app: FastAPI) -> None:
    exporter = app.state.exporter

    def _get_key_data(request: Request) -> dict | None:
        """Extract and validate API key from request. Returns key_data or None."""
        from memorylens._auth.keys import hash_key

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

        return exporter.get_api_key_by_hash(hash_key(raw_key))

    @app.post("/api/share")
    async def create_share(request: Request):
        # No-auth mode: always allow with "anonymous" creator
        if exporter.has_any_keys():
            key_data = _get_key_data(request)
            if not key_data:
                return JSONResponse({"error": "Authentication required"}, status_code=401)

            from memorylens._auth.permissions import check_permission
            if not check_permission(key_data["role"], "create_shared_links"):
                return JSONResponse({"error": "Insufficient permissions"}, status_code=403)

            created_by = key_data["key_prefix"]
        else:
            created_by = "anonymous"

        body = await request.json()
        link_type = body.get("link_type", "trace")
        target = body.get("target", "")
        query_params = body.get("query_params")
        expires_in = body.get("expires_in")

        link = create_shared_link(
            link_type=link_type,
            target=target,
            created_by=created_by,
            query_params=query_params,
            expires_in=expires_in,
        )
        exporter.save_shared_link(link)

        return JSONResponse({"url": f"/shared/{link['id']}", "id": link["id"]})

    @app.get("/shared/{link_id}")
    async def resolve_share(request: Request, link_id: str):
        link = exporter.get_shared_link(link_id)
        if not link:
            return JSONResponse({"error": "Link not found"}, status_code=404)

        if is_link_expired(link):
            return JSONResponse({"error": "Link has expired"}, status_code=410)

        url = resolve_shared_link(link)
        return RedirectResponse(url=url, status_code=302)
