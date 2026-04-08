from __future__ import annotations

import json
from pathlib import Path

import typer

from memorylens.cli.formatters import console

config_app = typer.Typer(no_args_is_help=True)

_CONFIG_PATH = Path.home() / ".memorylens" / "config.json"


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        return json.loads(_CONFIG_PATH.read_text())
    return {}


def _save_config(config: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")


@config_app.command("show")
def config_show() -> None:
    """Show current configuration."""
    config = _load_config()
    if not config:
        console.print("No configuration set. Using defaults.")
        return
    console.print_json(json.dumps(config, indent=2))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key (e.g. exporter)"),
    value: str = typer.Argument(..., help="Config value"),
) -> None:
    """Set a configuration value."""
    config = _load_config()
    parts = key.split(".")
    current = config
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value
    _save_config(config)
    console.print(f"Set {key} = {value}")
