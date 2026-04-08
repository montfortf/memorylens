from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from memorylens._exporters.sqlite import SQLiteExporter

_DEFAULT_DB = os.path.expanduser("~/.memorylens/traces.db")
_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"


def create_app(db_path: str = _DEFAULT_DB, ingest: bool = False) -> FastAPI:
    """Create the FastAPI app with all routes and middleware."""
    app = FastAPI(title="MemoryLens", docs_url=None, redoc_url=None)

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    exporter = SQLiteExporter(db_path=db_path)

    app.state.templates = templates
    app.state.exporter = exporter

    @app.get("/")
    async def index():
        return RedirectResponse(url="/traces")

    from memorylens._ui.api.traces import create_trace_routes

    create_trace_routes(app)

    from memorylens._ui.api.compression import create_compression_routes

    create_compression_routes(app)

    from memorylens._ui.api.drift import create_drift_routes

    create_drift_routes(app)

    if ingest:
        from memorylens._ui.api.ingest import create_ingest_routes

        create_ingest_routes(app)

    return app


def run(db_path: str = _DEFAULT_DB, port: int = 8000, ingest: bool = False) -> None:
    """Start the uvicorn server."""
    import uvicorn

    app = create_app(db_path=db_path, ingest=ingest)
    print(f"MemoryLens UI running at http://127.0.0.1:{port}")
    if ingest:
        print(f"OTLP ingest accepting traces at http://127.0.0.1:{port}/v1/traces")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
