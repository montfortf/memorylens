from __future__ import annotations

import importlib
import inspect

import typer

from memorylens.cli.formatters import console

validate_app = typer.Typer(no_args_is_help=True)


@validate_app.command("integration")
def validate_integration(
    module_path: str = typer.Argument(
        ..., help="Python module path (e.g. my_package.instrumentor)"
    ),
) -> None:
    """Validate a MemoryLens integration module."""
    checks_passed = 0
    checks_failed = 0

    # Check 1: Import
    console.print(f"\nValidating: {module_path}\n")
    try:
        module = importlib.import_module(module_path)
        console.print("  [green]✓[/green] Import successful")
        checks_passed += 1
    except Exception as e:
        console.print(f"  [red]✗[/red] Import failed: {e}")
        checks_failed += 1
        _print_summary(checks_passed, checks_failed, module_path)
        return

    # Check 2: Find instrumentors
    instrumentors = []
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if hasattr(obj, "instrument") and hasattr(obj, "uninstrument"):
            instrumentors.append((name, obj))

    if instrumentors:
        for name, _ in instrumentors:
            console.print(f"  [green]✓[/green] Found instrumentor: {name}")
        checks_passed += 1
    else:
        console.print(
            "  [red]✗[/red] No instrumentor found (need class with instrument/uninstrument)"
        )
        checks_failed += 1
        _print_summary(checks_passed, checks_failed, module_path)
        return

    # Check 3-5: For each instrumentor
    for name, cls in instrumentors:
        try:
            instance = cls()
            console.print(f"  [green]✓[/green] {name}() instantiated")
            checks_passed += 1
        except Exception as e:
            console.print(f"  [red]✗[/red] {name}() failed: {e}")
            checks_failed += 1
            continue

        # Check instrument()
        try:
            instance.instrument()
            console.print(f"  [green]✓[/green] {name}.instrument() completed")
            checks_passed += 1
        except Exception as e:
            console.print(f"  [red]✗[/red] {name}.instrument() failed: {e}")
            checks_failed += 1

        # Check uninstrument()
        try:
            instance.uninstrument()
            console.print(f"  [green]✓[/green] {name}.uninstrument() completed")
            checks_passed += 1
        except Exception as e:
            console.print(f"  [red]✗[/red] {name}.uninstrument() failed: {e}")
            checks_failed += 1

    _print_summary(checks_passed, checks_failed, module_path)


def _print_summary(passed: int, failed: int, module_path: str) -> None:
    total = passed + failed
    if failed == 0:
        console.print(f"\n[green]PASSED[/green]: {module_path} ({passed}/{total} checks)")
    else:
        console.print(
            f"\n[red]FAILED[/red]: {module_path} ({passed}/{total} checks passed, {failed} failed)"
        )
