from __future__ import annotations

import json
import os

import typer
from rich.table import Table

from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.formatters import console

cost_app = typer.Typer(no_args_is_help=True)

_DEFAULT_DB = os.path.expanduser("~/.memorylens/traces.db")


@cost_app.command("enrich")
def cost_enrich(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    trace_id: str | None = typer.Option(None, "--trace-id", help="Enrich specific trace"),
    force: bool = typer.Option(False, "--force", help="Recalculate all costs"),
) -> None:
    """Compute dollar costs from token counts in span attributes."""
    from memorylens._cost.enricher import CostEnricher
    from memorylens._cost.pricing import load_pricing

    exporter = SQLiteExporter(db_path=db_path)
    enricher = CostEnricher(pricing=load_pricing())

    kwargs: dict = {"limit": 10000}
    if trace_id:
        kwargs["trace_id"] = trace_id
    spans = exporter.query(**kwargs)

    enriched = 0
    skipped = 0
    warnings = 0

    for span in spans:
        attrs = json.loads(span["attributes"]) if isinstance(span["attributes"], str) else span["attributes"]

        if not force and "cost_usd" in attrs:
            skipped += 1
            continue

        result = enricher.enrich_span(attrs)
        if result is None:
            skipped += 1
            continue

        exporter.update_span_attributes(span["span_id"], result)
        enriched += 1
        if "_cost_warning" in result:
            warnings += 1

    console.print(f"Enriched: {enriched}, Skipped: {skipped}, Warnings: {warnings}")
    exporter.shutdown()


@cost_app.command("report")
def cost_report(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    group_by: str = typer.Option("operation", help="Group by: operation, agent_id, session_id"),
) -> None:
    """Show aggregated cost report."""
    exporter = SQLiteExporter(db_path=db_path)
    spans = exporter.query(limit=10000)
    exporter.shutdown()

    if not spans:
        console.print("No spans found.")
        return

    groups: dict[str, dict] = {}
    for span in spans:
        attrs = json.loads(span["attributes"]) if isinstance(span["attributes"], str) else span["attributes"]
        key = span.get(group_by) or attrs.get(group_by) or "unknown"
        if key not in groups:
            groups[key] = {"spans": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}
        groups[key]["spans"] += 1
        groups[key]["tokens_in"] += int(attrs.get("tokens_in", 0))
        groups[key]["tokens_out"] += int(attrs.get("tokens_out", 0))
        groups[key]["cost_usd"] += float(attrs.get("cost_usd", 0))

    table = Table(show_header=True, header_style="bold", title=f"Cost Report (grouped by {group_by})")
    table.add_column(group_by.upper())
    table.add_column("SPANS", justify="right")
    table.add_column("TOKENS IN", justify="right")
    table.add_column("TOKENS OUT", justify="right")
    table.add_column("TOTAL COST", justify="right")

    total_spans = total_in = total_out = total_cost = 0
    for key, data in sorted(groups.items()):
        table.add_row(
            str(key),
            str(data["spans"]),
            f"{data['tokens_in']:,}",
            f"{data['tokens_out']:,}",
            f"${data['cost_usd']:.4f}",
        )
        total_spans += data["spans"]
        total_in += data["tokens_in"]
        total_out += data["tokens_out"]
        total_cost += data["cost_usd"]

    console.print(table)
    console.print(f"\nTotal: {total_spans} spans, {total_in:,} tokens in, {total_out:,} tokens out, ${total_cost:.4f}")


@cost_app.command("pricing")
def cost_pricing(
    set_value: str | None = typer.Option(None, "--set", help="Set pricing: model.input=0.001"),
) -> None:
    """Show or update pricing table."""
    from pathlib import Path

    from memorylens._cost.pricing import load_pricing, save_user_pricing

    if set_value:
        parts = set_value.split("=")
        if len(parts) != 2:
            console.print("Format: --set model.input=0.001")
            return
        key_path, value = parts[0], float(parts[1])
        model, field = key_path.rsplit(".", 1)

        user_path = Path.home() / ".memorylens" / "pricing.json"
        user_pricing: dict = {}
        if user_path.exists():
            user_pricing = json.loads(user_path.read_text())
        if model not in user_pricing:
            user_pricing[model] = {}
        user_pricing[model][field] = value
        save_user_pricing(user_pricing)
        console.print(f"Set {model}.{field} = {value}")
        return

    pricing = load_pricing()
    table = Table(show_header=True, header_style="bold", title="Pricing Table")
    table.add_column("MODEL")
    table.add_column("INPUT ($/token)", justify="right")
    table.add_column("OUTPUT ($/token)", justify="right")

    for model, prices in sorted(pricing.items()):
        table.add_row(model, f"{prices['input']:.10f}", f"{prices['output']:.10f}")

    console.print(table)
