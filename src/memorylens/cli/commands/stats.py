from __future__ import annotations

import os
from collections import Counter

import typer

from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.formatters import console, print_json

from rich.table import Table

_DEFAULT_DB = os.path.expanduser("~/.memorylens/traces.db")


def stats_app(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    group_by: str = typer.Option("operation", help="Group by: operation, status, agent_id"),
    use_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show summary statistics."""
    exporter = SQLiteExporter(db_path=db_path)
    spans = exporter.query(limit=10000)
    exporter.shutdown()

    if not spans:
        console.print("No spans found.")
        return

    counts: Counter = Counter()
    durations: dict[str, list[float]] = {}
    for span in spans:
        key = span.get(group_by, "unknown") or "unknown"
        counts[key] += 1
        durations.setdefault(key, []).append(span.get("duration_ms", 0))

    if use_json:
        data = [
            {
                group_by: key,
                "count": count,
                "avg_duration_ms": round(sum(durations[key]) / len(durations[key]), 1),
            }
            for key, count in counts.most_common()
        ]
        print_json(data)
    else:
        table = Table(show_header=True, header_style="bold")
        table.add_column(group_by.upper())
        table.add_column("COUNT", justify="right")
        table.add_column("AVG DURATION", justify="right")

        for key, count in counts.most_common():
            avg = sum(durations[key]) / len(durations[key])
            table.add_row(str(key), str(count), f"{avg:.1f}ms")

        console.print(table)
