from __future__ import annotations

import typer

app = typer.Typer(
    name="memorylens",
    help="Observability and debugging for AI agent memory systems.",
    no_args_is_help=True,
)


def _register_commands() -> None:
    from memorylens.cli.commands.traces import traces_app
    from memorylens.cli.commands.stats import stats_app
    from memorylens.cli.commands.config import config_app

    app.add_typer(traces_app, name="traces", help="Inspect and manage traces")
    app.command(name="stats")(stats_app)
    app.add_typer(config_app, name="config", help="Manage configuration")


_register_commands()


@app.command()
def init() -> None:
    """Initialize MemoryLens local storage."""
    from pathlib import Path

    ml_dir = Path.home() / ".memorylens"
    ml_dir.mkdir(exist_ok=True)
    typer.echo(f"Initialized MemoryLens at {ml_dir}")


if __name__ == "__main__":
    app()
