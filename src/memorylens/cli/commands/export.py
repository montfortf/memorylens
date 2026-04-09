from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer

from memorylens.cli.formatters import console

export_app = typer.Typer(no_args_is_help=True)


@export_app.command("dashboard")
def export_dashboard(
    format: str = typer.Option(..., "--format", help="Platform: grafana or datadog"),
    output: str = typer.Option("./dashboards", "--output", "-o", help="Output directory"),
    name: Optional[str] = typer.Option(None, "--name", help="Export specific dashboard only"),
) -> None:
    """Export pre-built dashboard configurations."""
    from memorylens.dashboards import export_dashboards, list_dashboards

    available = list_dashboards(format)
    if not available:
        console.print(f"[red]Unknown platform: {format}[/red]. Available: grafana, datadog")
        raise typer.Exit(1)

    if name and name not in available:
        console.print(f"[red]Unknown dashboard: {name}[/red]. Available: {', '.join(available)}")
        raise typer.Exit(1)

    output_dir = Path(output)
    exported = export_dashboards(format, output_dir, name)

    console.print(f"\nExported {len(exported)} dashboard(s) to {output_dir}/:\n")
    for path in exported:
        console.print(f"  [green]\u2713[/green] {path.name}")
    console.print(f"\nImport these into your {format.title()} instance.")
