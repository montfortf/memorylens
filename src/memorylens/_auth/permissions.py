from __future__ import annotations

ROLES = ("admin", "editor", "viewer", "ingester")

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "view_traces", "view_drift", "view_alerts",
        "run_audits", "manage_alerts", "run_drift",
        "ingest_traces", "manage_keys", "access_admin",
        "create_shared_links",
    },
    "editor": {
        "view_traces", "view_drift", "view_alerts",
        "run_audits", "manage_alerts", "run_drift",
        "ingest_traces", "create_shared_links",
    },
    "viewer": {
        "view_traces", "view_drift", "view_alerts",
        "ingest_traces", "create_shared_links",
    },
    "ingester": {
        "ingest_traces",
    },
}


def check_permission(role: str, permission: str) -> bool:
    """Check if a role has a specific permission."""
    perms = ROLE_PERMISSIONS.get(role, set())
    return permission in perms


def get_permissions(role: str) -> set[str]:
    """Get all permissions for a role."""
    return ROLE_PERMISSIONS.get(role, set())
