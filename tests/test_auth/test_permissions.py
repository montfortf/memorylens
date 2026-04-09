from __future__ import annotations

from memorylens._auth.permissions import ROLES, check_permission, get_permissions


class TestPermissions:
    def test_admin_has_all_permissions(self):
        perms = get_permissions("admin")
        assert "manage_keys" in perms
        assert "access_admin" in perms
        assert "view_traces" in perms
        assert "ingest_traces" in perms

    def test_editor_cannot_manage_keys(self):
        assert check_permission("editor", "manage_keys") is False
        assert check_permission("editor", "access_admin") is False

    def test_editor_can_run_audits(self):
        assert check_permission("editor", "run_audits") is True
        assert check_permission("editor", "manage_alerts") is True

    def test_viewer_read_only(self):
        assert check_permission("viewer", "view_traces") is True
        assert check_permission("viewer", "run_audits") is False
        assert check_permission("viewer", "manage_keys") is False

    def test_ingester_only_ingest(self):
        perms = get_permissions("ingester")
        assert perms == {"ingest_traces"}

    def test_viewer_can_create_shared_links(self):
        assert check_permission("viewer", "create_shared_links") is True

    def test_ingester_cannot_create_shared_links(self):
        assert check_permission("ingester", "create_shared_links") is False

    def test_unknown_role_no_permissions(self):
        assert get_permissions("unknown") == set()

    def test_all_roles_defined(self):
        assert set(ROLES) == {"admin", "editor", "viewer", "ingester"}
