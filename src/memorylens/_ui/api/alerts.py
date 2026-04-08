from __future__ import annotations

import time

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse


def create_alerts_routes(app: FastAPI) -> None:
    templates = app.state.templates
    exporter = app.state.exporter

    @app.get("/alerts", response_class=HTMLResponse)
    async def alerts_page(
        request: Request,
        alert_type: str | None = Query(None, alias="type"),
        limit: int = Query(50),
    ):
        rules = exporter.list_alert_rules()
        history = exporter.list_alert_history(alert_type=alert_type, limit=limit)

        # Annotate history with human-readable timestamps
        for event in history:
            fired_at = event.get("fired_at", 0)
            event["_fired_at_str"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(fired_at))

        return templates.TemplateResponse(
            request,
            "alerts.html",
            {
                "rules": rules,
                "history": history,
                "active_type": alert_type,
                "limit": limit,
                "active_nav": "alerts",
            },
        )
