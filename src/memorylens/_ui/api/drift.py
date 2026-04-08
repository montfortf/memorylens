from __future__ import annotations

import json
import time
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse


def _parse_details(report: dict[str, Any]) -> dict[str, Any]:
    details = report.get("details", "{}")
    if isinstance(details, str):
        return json.loads(details)
    return details if details else {}


def _grade_color(grade: str) -> str:
    return {
        "A": "green",
        "B": "blue",
        "C": "amber",
        "D": "orange",
        "F": "red",
    }.get(grade, "slate")


def create_drift_routes(app: FastAPI) -> None:
    templates = app.state.templates
    exporter = app.state.exporter

    @app.get("/drift", response_class=HTMLResponse)
    async def drift_dashboard(
        request: Request,
        type_: str = Query("entity", alias="type"),
        grade: str | None = Query(None),
        limit: int = Query(50),
        offset: int = Query(0),
    ):
        reports, total = exporter.list_drift_reports(
            report_type=type_,
            min_grade=grade,
            limit=limit,
            offset=offset,
        )
        for r in reports:
            r["_grade_color"] = _grade_color(r["grade"])
            r["details"] = _parse_details(r)

        return templates.TemplateResponse(
            request,
            "drift_dashboard.html",
            {
                "reports": reports,
                "total": total,
                "active_type": type_,
                "active_grade": grade,
                "limit": limit,
                "offset": offset,
                "active_nav": "drift",
            },
        )

    @app.get("/drift/{memory_key:path}", response_class=HTMLResponse)
    async def drift_detail(request: Request, memory_key: str):
        # Load stored report if available
        report = exporter.get_drift_report("entity", memory_key)
        if report:
            report["_grade_color"] = _grade_color(report["grade"])
            report["details"] = _parse_details(report)

        # Load version history
        versions = exporter.get_versions(memory_key)
        versions.sort(key=lambda v: v["version"])

        # Compute consecutive similarities if versions exist
        consecutive_similarities: list[float] = []
        if len(versions) >= 2:
            try:
                from memorylens._audit.scorer import CachedScorer, MockScorer
                from memorylens._drift.analyzer import DriftAnalyzer

                scorer = CachedScorer(MockScorer())
                analyzer = DriftAnalyzer(scorer)
                entity_result = analyzer.analyze_entity(versions)
                consecutive_similarities = entity_result.consecutive_similarities
                # Compute fresh report if none stored
                if not report:
                    report = {
                        "key": memory_key,
                        "report_type": "entity",
                        "drift_score": entity_result.drift_score,
                        "contradiction_score": entity_result.contradiction_score,
                        "staleness_score": entity_result.staleness_score,
                        "volatility_score": entity_result.volatility_score,
                        "grade": entity_result.grade,
                        "details": {"version_count": entity_result.version_count},
                        "_grade_color": _grade_color(entity_result.grade),
                    }
            except Exception:
                pass

        if not versions and not report:
            return HTMLResponse(
                f"<h2 class='p-6 text-white'>No data for '{memory_key}'</h2>",
                status_code=404,
            )

        # Annotate versions with similarity to previous
        for i, v in enumerate(versions):
            if i > 0 and i - 1 < len(consecutive_similarities):
                v["_sim_to_prev"] = round(consecutive_similarities[i - 1], 3)
            else:
                v["_sim_to_prev"] = None
            ts = v.get("timestamp", 0)
            v["_ts_str"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))

        return templates.TemplateResponse(
            request,
            "drift_detail.html",
            {
                "memory_key": memory_key,
                "report": report,
                "versions": versions,
                "active_nav": "drift",
            },
        )
