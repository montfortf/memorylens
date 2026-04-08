from __future__ import annotations

import os

import typer

app = typer.Typer(
    name="memorylens",
    help="Observability and debugging for AI agent memory systems.",
    no_args_is_help=True,
)


def _register_commands() -> None:
    from memorylens.cli.commands.audit import audit_app
    from memorylens.cli.commands.config import config_app
    from memorylens.cli.commands.stats import stats_app
    from memorylens.cli.commands.traces import traces_app

    app.add_typer(traces_app, name="traces", help="Inspect and manage traces")
    app.command(name="stats")(stats_app)
    app.add_typer(config_app, name="config", help="Manage configuration")
    app.add_typer(audit_app, name="audit", help="Compression audit tools")


_register_commands()


@app.command()
def init() -> None:
    """Initialize MemoryLens local storage."""
    from pathlib import Path

    ml_dir = Path.home() / ".memorylens"
    ml_dir.mkdir(exist_ok=True)
    typer.echo(f"Initialized MemoryLens at {ml_dir}")


@app.command()
def ui(
    port: int = typer.Option(8000, help="Port to serve on"),
    db_path: str = typer.Option(
        os.path.expanduser("~/.memorylens/traces.db"), "--db-path", help="SQLite database path"
    ),
    ingest: bool = typer.Option(False, "--ingest", help="Accept OTLP HTTP traces at /v1/traces"),
) -> None:
    """Launch the MemoryLens web dashboard."""
    try:
        from memorylens._ui.server import run as run_ui
    except ImportError:
        typer.echo(
            "UI dependencies not found. Install with: pip install memorylens[ui]",
            err=True,
        )
        raise typer.Exit(1)
    run_ui(db_path=db_path, port=port, ingest=ingest)


if __name__ == "__main__":
    app()
