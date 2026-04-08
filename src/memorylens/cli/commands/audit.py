from __future__ import annotations

import json
import os

import typer
from rich.table import Table

from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.formatters import console

audit_app = typer.Typer(no_args_is_help=True)

_DEFAULT_DB = os.path.expanduser("~/.memorylens/traces.db")


@audit_app.command("compress")
def audit_compress(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    scorer: str = typer.Option("local", "--scorer", help="Scorer backend: local, openai, mock"),
    trace_id: str | None = typer.Option(None, "--trace-id", help="Audit specific trace only"),
    force: bool = typer.Option(False, "--force", help="Re-audit already-audited spans"),
) -> None:
    """Analyze COMPRESS spans for semantic loss."""
    from memorylens._audit.analyzer import CompressionAnalyzer
    from memorylens._audit.scorer import create_scorer

    exporter = SQLiteExporter(db_path=db_path)
    scorer_backend = create_scorer(scorer)
    analyzer = CompressionAnalyzer(scorer_backend)

    # Get all COMPRESS spans
    kwargs: dict = {"operation": "memory.compress", "limit": 10000}
    if trace_id:
        kwargs["trace_id"] = trace_id
    spans = exporter.query(**kwargs)

    if not spans:
        console.print("No COMPRESS spans found.")
        exporter.shutdown()
        return

    # Filter out already-audited unless --force
    if not force:
        spans = [s for s in spans if exporter.get_audit(s["span_id"]) is None]

    if not spans:
        console.print("All COMPRESS spans already audited. Use --force to re-audit.")
        exporter.shutdown()
        return

    console.print(f"Analyzing {len(spans)} COMPRESS spans...")

    results = []
    for span in spans:
        pre = span.get("input_content", "") or ""
        post = span.get("output_content", "") or ""
        audit = analyzer.analyze(span["span_id"], pre, post)
        exporter.save_audit(audit)
        results.append(audit)

    # Print results table
    table = Table(show_header=True, header_style="bold")
    table.add_column("SPAN ID", style="dim", max_width=12)
    table.add_column("LOSS SCORE", justify="right")
    table.add_column("RATIO", justify="right")
    table.add_column("PRESERVED", justify="right")
    table.add_column("LOST", justify="right")
    table.add_column("STATUS")

    for audit in results:
        preserved = sum(1 for s in audit.sentences if s.status == "preserved")
        lost = sum(1 for s in audit.sentences if s.status == "lost")
        total_s = len(audit.sentences)

        if audit.semantic_loss_score < 0.3:
            status = "[green]✓ low loss[/green]"
        elif audit.semantic_loss_score < 0.6:
            status = "[yellow]⚠ moderate loss[/yellow]"
        else:
            status = "[red]✗ high loss[/red]"

        table.add_row(
            audit.span_id[:12],
            f"{audit.semantic_loss_score:.2f}",
            f"{audit.compression_ratio:.2f}",
            f"{preserved}/{total_s}",
            f"{lost}/{total_s}",
            status,
        )

    console.print(table)
    console.print(f"\nSummary: {len(results)} spans audited.")
    exporter.shutdown()


@audit_app.command("show")
def audit_show(
    span_id: str = typer.Argument(..., help="Span ID to show audit for"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
) -> None:
    """Show detailed audit for a span."""
    exporter = SQLiteExporter(db_path=db_path)
    result = exporter.get_audit(span_id)
    exporter.shutdown()

    if not result:
        console.print(f"No audit found for span {span_id}. Run: memorylens audit compress")
        return

    loss = result["semantic_loss_score"]
    if loss < 0.3:
        loss_label = "[green]low[/green]"
    elif loss < 0.6:
        loss_label = "[yellow]moderate[/yellow]"
    else:
        loss_label = "[red]high[/red]"

    console.print(f"\n[bold]Compression Audit: {result['span_id']}[/bold]\n")
    console.print(f"  Loss Score:    {loss:.2f} ({loss_label})")
    ratio = result["compression_ratio"]
    console.print(f"  Ratio:         {ratio:.2f} ({(1 - ratio) * 100:.0f}% reduction)")
    console.print(f"  Sentences:     {result['pre_sentence_count']} pre, {result['post_sentence_count']} post")
    console.print(f"  Scorer:        {result['scorer_backend']}")

    sentences = json.loads(result["sentences"])
    console.print(f"\n  [bold]Pre-compression ({len(sentences)} sentences):[/bold]")
    for s in sentences:
        icon = "[green]✓[/green]" if s["status"] == "preserved" else "[red]✗[/red]"
        score = s["best_match_score"]
        console.print(f"    {icon} [{score:.2f}] \"{s['text']}\"")
    console.print()


@audit_app.command("list")
def audit_list(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    min_loss: float = typer.Option(0.0, "--min-loss", help="Minimum loss score to show"),
) -> None:
    """List all audit results."""
    exporter = SQLiteExporter(db_path=db_path)
    rows, total = exporter.list_audits(limit=100)
    exporter.shutdown()

    if not rows:
        console.print("No audits found. Run: memorylens audit compress")
        return

    if min_loss > 0:
        rows = [r for r in rows if r["semantic_loss_score"] >= min_loss]

    table = Table(show_header=True, header_style="bold")
    table.add_column("SPAN ID", style="dim", max_width=12)
    table.add_column("LOSS SCORE", justify="right")
    table.add_column("RATIO", justify="right")
    table.add_column("SENTENCES", justify="right")
    table.add_column("SCORER")

    for row in rows:
        table.add_row(
            row["span_id"][:12],
            f"{row['semantic_loss_score']:.2f}",
            f"{row['compression_ratio']:.2f}",
            f"{row['pre_sentence_count']}",
            row["scorer_backend"],
        )

    console.print(table)
    console.print(f"\n{len(rows)} audits shown (of {total} total).")
