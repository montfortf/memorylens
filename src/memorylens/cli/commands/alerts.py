from __future__ import annotations

import os
import time
from typing import Optional

import typer
from rich.table import Table

from memorylens._exporters.sqlite import SQLiteExporter
from memorylens.cli.formatters import console

alerts_app = typer.Typer(no_args_is_help=True)

_DEFAULT_DB = os.path.expanduser("~/.memorylens/traces.db")

_VALID_TYPES = {"drift", "cost", "retrieval", "compression_loss", "error_rate"}


@alerts_app.command("add")
def alerts_add(
    name: str = typer.Argument(..., help="Alert rule name"),
    alert_type: str = typer.Option(..., "--type", help="Alert type: drift, cost, retrieval, compression_loss, error_rate"),
    threshold: float = typer.Option(..., "--threshold", help="Threshold value"),
    webhook: Optional[str] = typer.Option(None, "--webhook", help="Webhook URL for notifications"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
) -> None:
    """Add a new alert rule."""
    if alert_type not in _VALID_TYPES:
        console.print(f"[red]Unknown alert type '{alert_type}'. Valid: {', '.join(sorted(_VALID_TYPES))}[/red]")
        raise typer.Exit(1)

    exporter = SQLiteExporter(db_path=db_path)
    try:
        exporter.save_alert_rule({
            "name": name,
            "alert_type": alert_type,
            "threshold": threshold,
            "webhook_url": webhook,
            "enabled": True,
            "created_at": time.time(),
        })
        console.print(f"[green]Alert rule '{name}' added.[/green] Type: {alert_type}, threshold: {threshold}")
    except Exception as exc:
        console.print(f"[red]Failed to add rule: {exc}[/red]")
        raise typer.Exit(1)
    finally:
        exporter.shutdown()


@alerts_app.command("list")
def alerts_list(
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
) -> None:
    """List all alert rules."""
    exporter = SQLiteExporter(db_path=db_path)
    rules = exporter.list_alert_rules()
    exporter.shutdown()

    if not rules:
        console.print("No alert rules defined. Run: memorylens alerts add")
        return

    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("NAME", no_wrap=True)
    table.add_column("TYPE")
    table.add_column("THRESHOLD", justify="right")
    table.add_column("ENABLED", justify="center")
    table.add_column("WEBHOOK", max_width=40)

    for rule in rules:
        enabled_str = "[green]yes[/green]" if rule["enabled"] else "[dim]no[/dim]"
        webhook_str = rule.get("webhook_url") or "[dim]—[/dim]"
        table.add_row(
            rule["name"],
            rule["alert_type"],
            str(rule["threshold"]),
            enabled_str,
            webhook_str,
        )
    console.print(table)


@alerts_app.command("remove")
def alerts_remove(
    name: str = typer.Argument(..., help="Alert rule name to remove"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
) -> None:
    """Remove an alert rule by name."""
    exporter = SQLiteExporter(db_path=db_path)
    existing = exporter.get_alert_rule(name)
    if existing is None:
        console.print(f"[yellow]No rule named '{name}' found.[/yellow]")
        exporter.shutdown()
        return
    exporter.delete_alert_rule(name)
    exporter.shutdown()
    console.print(f"[green]Alert rule '{name}' removed.[/green]")


@alerts_app.command("enable")
def alerts_enable(
    name: str = typer.Argument(..., help="Alert rule name to enable"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
) -> None:
    """Enable an alert rule."""
    exporter = SQLiteExporter(db_path=db_path)
    existing = exporter.get_alert_rule(name)
    if existing is None:
        console.print(f"[yellow]No rule named '{name}' found.[/yellow]")
        exporter.shutdown()
        return
    exporter.update_alert_rule(name, {"enabled": 1})
    exporter.shutdown()
    console.print(f"[green]Alert rule '{name}' enabled.[/green]")


@alerts_app.command("disable")
def alerts_disable(
    name: str = typer.Argument(..., help="Alert rule name to disable"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
) -> None:
    """Disable an alert rule."""
    exporter = SQLiteExporter(db_path=db_path)
    existing = exporter.get_alert_rule(name)
    if existing is None:
        console.print(f"[yellow]No rule named '{name}' found.[/yellow]")
        exporter.shutdown()
        return
    exporter.update_alert_rule(name, {"enabled": 0})
    exporter.shutdown()
    console.print(f"[dim]Alert rule '{name}' disabled.[/dim]")


@alerts_app.command("history")
def alerts_history(
    alert_type: Optional[str] = typer.Option(None, "--type", help="Filter by alert type"),
    limit: int = typer.Option(20, "--limit", help="Max rows to show"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
) -> None:
    """Show recent alert history."""
    exporter = SQLiteExporter(db_path=db_path)
    events = exporter.list_alert_history(alert_type=alert_type, limit=limit)
    exporter.shutdown()

    if not events:
        console.print("No alert history found.")
        return

    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("FIRED AT", no_wrap=True)
    table.add_column("TYPE")
    table.add_column("MESSAGE", max_width=60)

    for event in events:
        fired_at = event.get("fired_at", 0)
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(fired_at))
        table.add_row(ts, event["alert_type"], event["message"])

    console.print(table)


@alerts_app.command("monitor")
def alerts_monitor(
    interval: int = typer.Option(60, "--interval", help="Seconds between evaluations"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
) -> None:
    """Evaluate all enabled alert rules on a loop. Fires webhooks. Ctrl+C to stop."""
    from memorylens._alerts.evaluator import AlertEvaluator

    console.print(f"Starting alert monitor (interval={interval}s). Ctrl+C to stop.")
    exporter = SQLiteExporter(db_path=db_path)
    evaluator = AlertEvaluator(exporter)

    try:
        while True:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            console.print(f"\n[dim]{ts} — Evaluating rules...[/dim]")
            rules = exporter.list_alert_rules(enabled_only=True)
            if not rules:
                console.print("  [dim]No enabled rules.[/dim]")
            else:
                for rule in rules:
                    events = evaluator.evaluate_rule(rule)
                    for event in events:
                        console.print(
                            f"  [red]ALERT[/red] [{event.alert_type}] {event.message}"
                        )
                        evaluator.fire_alert(event, rule)
                if not any(True for rule in rules):
                    console.print("  All rules checked.")
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                break
    except KeyboardInterrupt:
        pass
    finally:
        exporter.shutdown()
    console.print("\nMonitor stopped.")


@alerts_app.command("tail")
def alerts_tail(
    interval: int = typer.Option(60, "--interval", help="Seconds between evaluations"),
    db_path: str = typer.Option(_DEFAULT_DB, "--db-path", help="SQLite database path"),
) -> None:
    """Evaluate all enabled alert rules and print to console only (no webhook). Ctrl+C to stop."""
    from memorylens._alerts.evaluator import AlertEvaluator

    console.print(f"Starting alert tail (interval={interval}s). Ctrl+C to stop.")
    exporter = SQLiteExporter(db_path=db_path)
    evaluator = AlertEvaluator(exporter)

    try:
        while True:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            console.print(f"\n[dim]{ts} — Evaluating rules...[/dim]")
            rules = exporter.list_alert_rules(enabled_only=True)
            if not rules:
                console.print("  [dim]No enabled rules.[/dim]")
            else:
                for rule in rules:
                    events = evaluator.evaluate_rule(rule)
                    for event in events:
                        console.print(
                            f"  [red]ALERT[/red] [{event.alert_type}] {event.message}"
                        )
                        # No webhook — save to history only
                        rule_id = rule.get("id", 0)
                        exporter.save_alert_event({
                            "rule_id": rule_id,
                            "alert_type": event.alert_type,
                            "message": event.message,
                            "details": event.details,
                            "fired_at": time.time(),
                        })
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                break
    except KeyboardInterrupt:
        pass
    finally:
        exporter.shutdown()
    console.print("\nTail stopped.")
