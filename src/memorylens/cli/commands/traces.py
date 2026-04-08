from __future__ import annotations

import json
import os
from typing import Optional

import typer

from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.formatters import console, print_json, print_span_detail, print_spans_table

traces_app = typer.Typer(no_args_is_help=True)

_DEFAULT_DB = os.path.expanduser("~/.memorylens/traces.db")


def _get_exporter(db_path: str) -> SQLiteExporter:
    return SQLiteExporter(db_path=db_path)


@traces_app.command("list")
def traces_list(
    operation: Optional[str] = typer.Option(None, help="Filter by operation (e.g. memory.write)"),
    status: Optional[str] = typer.Option(None, help="Filter by status (ok, error, dropped)"),
    agent_id: Optional[str] = typer.Option(None, "--agent-id", help="Filter by agent ID"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Filter by session ID"),
    limit: int = typer.Option(50, help="Max results"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    use_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List recent traces."""
    exporter = _get_exporter(db_path)
    spans = exporter.query(
        operation=operation,
        status=status,
        agent_id=agent_id,
        session_id=session_id,
        limit=limit,
    )
    exporter.shutdown()

    if use_json:
        for s in spans:
            if isinstance(s.get("attributes"), str):
                s["attributes"] = json.loads(s["attributes"])
        print_json(spans)
    else:
        print_spans_table(spans)


@traces_app.command("show")
def traces_show(
    trace_id: str = typer.Argument(..., help="Trace ID to inspect"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    use_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show detailed view of a trace."""
    exporter = _get_exporter(db_path)
    spans = exporter.query(trace_id=trace_id)
    exporter.shutdown()

    if not spans:
        console.print(f"No trace found with ID: {trace_id}")
        return

    if use_json:
        for s in spans:
            if isinstance(s.get("attributes"), str):
                s["attributes"] = json.loads(s["attributes"])
        print_json(spans)
    else:
        for span in spans:
            print_span_detail(span)


@traces_app.command("export")
def traces_export(
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    limit: int = typer.Option(1000, help="Max spans to export"),
) -> None:
    """Export traces as JSONL."""
    exporter = _get_exporter(db_path)
    spans = exporter.query(limit=limit)
    exporter.shutdown()

    lines = []
    for span in spans:
        if isinstance(span.get("attributes"), str):
            span["attributes"] = json.loads(span["attributes"])
        lines.append(json.dumps(span, default=str))

    if output:
        with open(output, "w") as f:
            f.write("\n".join(lines) + "\n")
        console.print(f"Exported {len(lines)} spans to {output}")
    else:
        for line in lines:
            typer.echo(line)
