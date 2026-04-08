from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table


console = Console()


def print_spans_table(spans: list[dict[str, Any]]) -> None:
    """Print spans as a rich table."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("SPAN ID", style="dim", max_width=12)
    table.add_column("OPERATION")
    table.add_column("STATUS")
    table.add_column("DURATION")
    table.add_column("AGENT")
    table.add_column("SESSION", style="dim")

    for span in spans:
        status_style = {
            "ok": "green",
            "error": "red",
            "dropped": "yellow",
        }.get(span.get("status", ""), "")

        table.add_row(
            span.get("span_id", "")[:12],
            span.get("operation", ""),
            f"[{status_style}]{span.get('status', '')}[/{status_style}]",
            f"{span.get('duration_ms', 0):.1f}ms",
            span.get("agent_id", "-") or "-",
            span.get("session_id", "-") or "-",
        )

    console.print(table)


def print_span_detail(span: dict[str, Any]) -> None:
    """Print detailed view of a single span."""
    console.print(f"\n[bold]Trace: {span.get('span_id', '')} — {span.get('operation', '')}[/bold]\n")
    console.print(f"  Status:     {span.get('status', '')}")
    console.print(f"  Duration:   {span.get('duration_ms', 0):.1f}ms")
    console.print(f"  Agent:      {span.get('agent_id', '-') or '-'}")
    console.print(f"  Session:    {span.get('session_id', '-') or '-'}")
    console.print(f"  User:       {span.get('user_id', '-') or '-'}")

    attrs = span.get("attributes", "{}")
    if isinstance(attrs, str):
        attrs = json.loads(attrs)
    if attrs:
        console.print("\n  [bold]Attributes:[/bold]")
        for k, v in attrs.items():
            console.print(f"    {k}: {v}")

    if span.get("input_content"):
        console.print(f"\n  [bold]Input:[/bold]\n    {span['input_content']}")
    if span.get("output_content"):
        console.print(f"\n  [bold]Output:[/bold]\n    {span['output_content']}")
    console.print()


def print_json(data: Any) -> None:
    """Print data as formatted JSON."""
    console.print_json(json.dumps(data, default=str))
