from __future__ import annotations

import os
import time

import typer
from rich.table import Table

from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.formatters import console

drift_app = typer.Typer(no_args_is_help=True)

_DEFAULT_DB = os.path.expanduser("~/.memorylens/traces.db")

_GRADE_COLORS = {
    "A": "green",
    "B": "blue",
    "C": "yellow",
    "D": "dark_orange",
    "F": "red",
}


def _grade_markup(grade: str) -> str:
    color = _GRADE_COLORS.get(grade, "white")
    return f"[{color}]{grade}[/{color}]"


def _count_grades(reports: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for r in reports:
        counts[r.get("grade", "F")] = counts.get(r.get("grade", "F"), 0) + 1
    return counts


@drift_app.command("analyze")
def drift_analyze(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    type_: str = typer.Option("all", "--type", help="Analysis type: all, entity, session, topic"),
    scorer: str = typer.Option("mock", "--scorer", help="Scorer backend: mock, local, openai"),
) -> None:
    """Run drift analysis on stored memory versions."""
    from memorylens._audit.scorer import CachedScorer, create_scorer
    from memorylens._drift.analyzer import DriftAnalyzer

    exporter = SQLiteExporter(db_path=db_path)
    scorer_backend = create_scorer(scorer)
    cached_scorer = CachedScorer(scorer_backend)
    analyzer = DriftAnalyzer(cached_scorer)

    all_versions = exporter.get_all_versions()
    if not all_versions:
        console.print("No memory versions found. Run with detect_drift=True or use offline import.")
        exporter.shutdown()
        return

    console.print(f"Analyzing {len(all_versions)} memory versions...")

    run_entity = type_ in ("all", "entity")
    run_session = type_ in ("all", "session")
    run_topic = type_ in ("all", "topic")

    # ── Entity analysis ──────────────────────────────────────────────────────
    if run_entity:
        by_key: dict[str, list[dict]] = {}
        for v in all_versions:
            by_key.setdefault(v["memory_key"], []).append(v)

        entity_results = []
        for key, versions in by_key.items():
            versions.sort(key=lambda x: x["version"])
            result = analyzer.analyze_entity(versions)
            exporter.save_drift_report(
                {
                    "report_type": "entity",
                    "key": result.memory_key,
                    "drift_score": result.drift_score,
                    "contradiction_score": result.contradiction_score,
                    "staleness_score": result.staleness_score,
                    "volatility_score": result.volatility_score,
                    "grade": result.grade,
                    "details": {"version_count": result.version_count},
                    "created_at": time.time(),
                }
            )
            entity_results.append(result)

        console.print(f"\n[bold]Entity Drift ({len(entity_results)} entities)[/bold]")
        _print_entity_table(entity_results)

    # ── Session analysis ─────────────────────────────────────────────────────
    if run_session:
        sessions = list({v.get("session_id") for v in all_versions if v.get("session_id")})
        session_results = []
        for sid in sessions:
            result = analyzer.analyze_session(sid, all_versions)
            exporter.save_drift_report(
                {
                    "report_type": "session",
                    "key": sid,
                    "drift_score": result.drift_score,
                    "contradiction_score": result.contradiction_score,
                    "staleness_score": result.staleness_score,
                    "volatility_score": result.volatility_score,
                    "grade": result.grade,
                    "details": {"memory_keys_modified": result.memory_keys_modified},
                    "created_at": time.time(),
                }
            )
            session_results.append(result)
        console.print(f"\n[bold]Session Drift ({len(session_results)} sessions)[/bold]")

    # ── Topic analysis ───────────────────────────────────────────────────────
    if run_topic:
        topic_results = analyzer.analyze_topics(all_versions)
        for r in topic_results:
            exporter.save_drift_report(
                {
                    "report_type": "topic",
                    "key": r.topic_id,
                    "drift_score": r.drift_score,
                    "contradiction_score": r.contradiction_score,
                    "staleness_score": r.staleness_score,
                    "volatility_score": r.volatility_score,
                    "grade": r.grade,
                    "details": {"memory_keys": r.memory_keys, "centroid_drift": r.centroid_drift},
                    "created_at": time.time(),
                }
            )
        console.print(f"\n[bold]Topic Drift ({len(topic_results)} clusters)[/bold]")

    console.print("\nAnalysis complete. Run: memorylens drift report")
    exporter.shutdown()


def _print_entity_table(results: list) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("KEY", max_width=30)
    table.add_column("GRADE", justify="center")
    table.add_column("DRIFT", justify="right")
    table.add_column("CONTRADICTION", justify="right")
    table.add_column("STALENESS", justify="right")
    table.add_column("VOLATILITY", justify="right")
    for r in results:
        table.add_row(
            r.memory_key,
            _grade_markup(r.grade),
            f"{r.drift_score:.2f}",
            f"{r.contradiction_score:.2f}",
            f"{r.staleness_score:.2f}",
            f"{r.volatility_score:.2f}",
        )
    console.print(table)


@drift_app.command("report")
def drift_report(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    type_: str | None = typer.Option(None, "--type", help="Filter by type: entity, session, topic"),
    grade: str | None = typer.Option(
        None, "--grade", help="Minimum grade to show (e.g. D shows D,F)"
    ),
    limit: int = typer.Option(50, "--limit", help="Max rows to show"),
    offset: int = typer.Option(0, "--offset", help="Pagination offset"),
) -> None:
    """List drift reports with optional filters."""
    exporter = SQLiteExporter(db_path=db_path)
    rows, total = exporter.list_drift_reports(
        report_type=type_,
        min_grade=grade,
        limit=limit,
        offset=offset,
    )
    exporter.shutdown()

    if not rows:
        console.print("No drift reports found. Run: memorylens drift analyze")
        return

    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("TYPE", style="dim")
    table.add_column("KEY", no_wrap=True)
    table.add_column("GRADE", justify="center")
    table.add_column("DRIFT", justify="right")
    table.add_column("CONTRADICTION", justify="right")
    table.add_column("STALENESS", justify="right")
    table.add_column("VOLATILITY", justify="right")

    for row in rows:
        table.add_row(
            row["report_type"],
            row["key"],
            _grade_markup(row["grade"]),
            f"{row['drift_score']:.2f}",
            f"{row['contradiction_score']:.2f}",
            f"{row['staleness_score']:.2f}",
            f"{row['volatility_score']:.2f}",
        )

    console.print(table)
    counts = _count_grades(rows)
    console.print(
        f"\n{len(rows)} reports shown (of {total} total). "
        f"[red]F:{counts['F']}[/red] "
        f"[dark_orange]D:{counts['D']}[/dark_orange] "
        f"[yellow]C:{counts['C']}[/yellow] "
        f"[blue]B:{counts['B']}[/blue] "
        f"[green]A:{counts['A']}[/green]"
    )


@drift_app.command("show")
def drift_show(
    memory_key: str = typer.Argument(..., help="Memory key to show detail for"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    scorer: str = typer.Option("mock", "--scorer", help="Scorer backend for fresh analysis"),
) -> None:
    """Show entity detail and version history for a memory key."""
    from memorylens._audit.scorer import CachedScorer, create_scorer
    from memorylens._drift.analyzer import DriftAnalyzer

    exporter = SQLiteExporter(db_path=db_path)
    versions = exporter.get_versions(memory_key)

    if not versions:
        console.print(f"No versions found for key '{memory_key}'.")
        exporter.shutdown()
        return

    scorer_backend = create_scorer(scorer)
    analyzer = DriftAnalyzer(CachedScorer(scorer_backend))
    versions.sort(key=lambda x: x["version"])
    result = analyzer.analyze_entity(versions)
    health = analyzer.compute_health(result)

    console.print(f"\n[bold]Memory Key:[/bold] {memory_key}")
    console.print(f"[bold]Grade:[/bold] {_grade_markup(health.grade)}")
    console.print(f"  Drift Score:         {health.drift_score:.4f}")
    console.print(f"  Contradiction Score: {health.contradiction_score:.4f}")
    console.print(f"  Staleness Score:     {health.staleness_score:.4f}")
    console.print(f"  Volatility Score:    {health.volatility_score:.4f}")
    console.print(f"\n[bold]Version History ({result.version_count} versions):[/bold]")

    for i, v in enumerate(versions):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(v["timestamp"]))
        content_preview = (v.get("content") or "")[:60]
        sim_str = ""
        if i > 0 and i - 1 < len(result.consecutive_similarities):
            sim = result.consecutive_similarities[i - 1]
            sim_str = f" [dim](sim to prev: {sim:.3f})[/dim]"
        console.print(f"  v{v['version']} [{ts}] {v['operation']}{sim_str}")
        if content_preview:
            console.print(f"       [dim]{content_preview}...[/dim]")

    exporter.shutdown()


@drift_app.command("watch")
def drift_watch(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
    interval: int = typer.Option(300, "--interval", help="Seconds between analyses"),
    scorer: str = typer.Option("mock", "--scorer", help="Scorer backend: mock, local, openai"),
) -> None:
    """Run drift analysis on a schedule. Ctrl+C to stop."""
    console.print(f"Starting drift watcher (interval={interval}s). Ctrl+C to stop.")
    while True:
        console.print(f"\n[dim]{time.strftime('%Y-%m-%d %H:%M:%S')} — Running analysis...[/dim]")
        try:
            from memorylens._audit.scorer import CachedScorer, create_scorer
            from memorylens._drift.analyzer import DriftAnalyzer

            exporter = SQLiteExporter(db_path=db_path)
            scorer_backend = create_scorer(scorer)
            analyzer = DriftAnalyzer(CachedScorer(scorer_backend))
            all_versions = exporter.get_all_versions()

            if all_versions:
                by_key: dict[str, list[dict]] = {}
                for v in all_versions:
                    by_key.setdefault(v["memory_key"], []).append(v)

                critical = 0
                for key, versions in by_key.items():
                    versions.sort(key=lambda x: x["version"])
                    result = analyzer.analyze_entity(versions)
                    exporter.save_drift_report(
                        {
                            "report_type": "entity",
                            "key": result.memory_key,
                            "drift_score": result.drift_score,
                            "contradiction_score": result.contradiction_score,
                            "staleness_score": result.staleness_score,
                            "volatility_score": result.volatility_score,
                            "grade": result.grade,
                            "details": {"version_count": result.version_count},
                            "created_at": time.time(),
                        }
                    )
                    if result.grade == "F":
                        critical += 1

                console.print(f"  {len(by_key)} entities. [red]{critical} critical[/red]")
            else:
                console.print("  No versions found.")
            exporter.shutdown()
        except Exception as exc:
            console.print(f"  [red]Error: {exc}[/red]")

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\nWatcher stopped.")
            break
