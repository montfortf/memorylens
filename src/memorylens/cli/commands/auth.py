from __future__ import annotations

import os
import time

import typer
from rich.table import Table

from memorylens._auth.keys import generate_key, hash_key, key_prefix
from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.formatters import console

auth_app = typer.Typer(no_args_is_help=True)

_DEFAULT_DB = os.path.expanduser("~/.memorylens/traces.db")


@auth_app.command("create-key")
def create_key(
    name: str = typer.Argument(..., help="Descriptive name for the key"),
    role: str = typer.Option("viewer", "--role", help="Role: admin, editor, viewer, ingester"),
    admin_key: str | None = typer.Option(None, "--admin-key", help="Admin key for authorization"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
) -> None:
    """Create a new API key."""
    from memorylens._auth.permissions import ROLES

    if role not in ROLES:
        console.print(f"[red]Invalid role: {role}[/red]. Available: {', '.join(ROLES)}")
        raise typer.Exit(1)

    exporter = SQLiteExporter(db_path=db_path)

    # If keys exist, require admin key
    if exporter.has_any_keys():
        if not admin_key:
            console.print("[red]Admin key required.[/red] Use --admin-key ml_...")
            exporter.shutdown()
            raise typer.Exit(1)
        admin_hash = hash_key(admin_key)
        admin_data = exporter.get_api_key_by_hash(admin_hash)
        if not admin_data or admin_data["role"] != "admin":
            console.print("[red]Invalid admin key.[/red]")
            exporter.shutdown()
            raise typer.Exit(1)

    key = generate_key()
    exporter.save_api_key({
        "key_hash": hash_key(key),
        "key_prefix": key_prefix(key),
        "name": name,
        "role": role,
        "created_at": time.time(),
    })
    exporter.shutdown()

    console.print(f"\n[green]Created API key:[/green] {key}")
    console.print(f"  Name: {name}")
    console.print(f"  Role: {role}")
    console.print("\n[yellow]Save this key — it won't be shown again.[/yellow]\n")


@auth_app.command("list-keys")
def list_keys(
    admin_key: str | None = typer.Option(None, "--admin-key", help="Admin key"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
) -> None:
    """List all API keys."""
    exporter = SQLiteExporter(db_path=db_path)
    keys = exporter.list_api_keys()
    exporter.shutdown()

    if not keys:
        console.print("No API keys found. Create one with: memorylens auth create-key")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("NAME")
    table.add_column("ROLE")
    table.add_column("PREFIX")
    table.add_column("CREATED")
    table.add_column("LAST USED")

    for k in keys:
        table.add_row(
            k["name"],
            k["role"],
            k["key_prefix"],
            str(k.get("created_at", "-")),
            str(k.get("last_used_at", "-") or "never"),
        )

    console.print(table)


@auth_app.command("revoke-key")
def revoke_key(
    name: str = typer.Argument(..., help="Key name to revoke"),
    admin_key: str | None = typer.Option(None, "--admin-key", help="Admin key"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
) -> None:
    """Revoke an API key."""
    exporter = SQLiteExporter(db_path=db_path)
    exporter.delete_api_key(name)
    exporter.shutdown()
    console.print(f"Revoked key: {name}")
