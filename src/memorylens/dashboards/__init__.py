from __future__ import annotations

import shutil
from pathlib import Path

_DASHBOARDS_DIR = Path(__file__).parent


def get_dashboard_path(platform: str, name: str) -> Path:
    """Get path to a dashboard JSON file."""
    path = _DASHBOARDS_DIR / platform / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Dashboard not found: {platform}/{name}.json")
    return path


def list_dashboards(platform: str) -> list[str]:
    """List available dashboard names for a platform."""
    platform_dir = _DASHBOARDS_DIR / platform
    if not platform_dir.exists():
        return []
    return sorted(p.stem for p in platform_dir.glob("*.json"))


def export_dashboards(
    platform: str, output_dir: Path, name: str | None = None
) -> list[Path]:
    """Copy dashboard JSON files to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    names = [name] if name else list_dashboards(platform)
    exported = []
    for n in names:
        src = get_dashboard_path(platform, n)
        dst = output_dir / f"memorylens-{platform}-{n}.json"
        shutil.copy2(src, dst)
        exported.append(dst)
    return exported
