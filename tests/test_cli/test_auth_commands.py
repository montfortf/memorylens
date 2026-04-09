from __future__ import annotations

import pytest
from typer.testing import CliRunner

from memorylens.cli.main import app


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


class TestCreateKeyCommand:
    def test_create_first_key_no_admin_required(self, db_path):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["auth", "create-key", "my-admin", "--role", "admin", "--db-path", db_path],
        )
        assert result.exit_code == 0, result.output
        assert "Created API key" in result.output
        assert "ml_" in result.output
        assert "my-admin" in result.output
        assert "admin" in result.output

    def test_created_key_starts_with_ml(self, db_path):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["auth", "create-key", "k1", "--role", "viewer", "--db-path", db_path],
        )
        assert result.exit_code == 0
        # Extract key from output
        lines = result.output.splitlines()
        key_line = next(l for l in lines if "ml_" in l)
        key = key_line.split("ml_")[1].split()[0]
        assert len(key) == 32  # 32 hex chars after ml_

    def test_create_second_key_requires_admin_key(self, db_path):
        runner = CliRunner()
        # Create first key
        runner.invoke(app, ["auth", "create-key", "admin", "--role", "admin", "--db-path", db_path])
        # Try to create second without admin key
        result = runner.invoke(app, ["auth", "create-key", "viewer1", "--role", "viewer", "--db-path", db_path])
        assert result.exit_code != 0
        assert "Admin key required" in result.output

    def test_create_second_key_with_valid_admin_key(self, db_path):
        runner = CliRunner()
        # Create first admin key and capture the raw key
        result1 = runner.invoke(
            app, ["auth", "create-key", "admin", "--role", "admin", "--db-path", db_path]
        )
        assert result1.exit_code == 0
        # Parse key from output
        lines = result1.output.splitlines()
        key_line = next(l for l in lines if "ml_" in l)
        raw_key = key_line.strip().split()[-1]

        # Create second key using admin key
        result2 = runner.invoke(
            app,
            ["auth", "create-key", "viewer1", "--role", "viewer", "--admin-key", raw_key, "--db-path", db_path],
        )
        assert result2.exit_code == 0, result2.output
        assert "Created API key" in result2.output
        assert "viewer1" in result2.output

    def test_create_key_with_invalid_admin_key_fails(self, db_path):
        runner = CliRunner()
        runner.invoke(app, ["auth", "create-key", "admin", "--role", "admin", "--db-path", db_path])
        result = runner.invoke(
            app,
            ["auth", "create-key", "viewer1", "--role", "viewer", "--admin-key", "ml_invalid", "--db-path", db_path],
        )
        assert result.exit_code != 0
        assert "Invalid admin key" in result.output

    def test_invalid_role_fails(self, db_path):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["auth", "create-key", "k1", "--role", "superuser", "--db-path", db_path],
        )
        assert result.exit_code != 0
        assert "Invalid role" in result.output

    def test_all_valid_roles_accepted(self, tmp_path):
        runner = CliRunner()
        for role in ["admin", "editor", "viewer", "ingester"]:
            # Each role gets its own fresh DB so no admin key is needed
            fresh_db = str(tmp_path / f"test_{role}.db")
            result = runner.invoke(
                app,
                ["auth", "create-key", f"key-{role}", "--role", role, "--db-path", fresh_db],
            )
            assert result.exit_code == 0, f"Role {role} failed: {result.output}"

    def test_save_this_key_warning_shown(self, db_path):
        runner = CliRunner()
        result = runner.invoke(
            app, ["auth", "create-key", "k1", "--role", "admin", "--db-path", db_path]
        )
        assert result.exit_code == 0
        assert "Save this key" in result.output


class TestListKeysCommand:
    def test_empty_db_shows_message(self, db_path):
        runner = CliRunner()
        result = runner.invoke(app, ["auth", "list-keys", "--db-path", db_path])
        assert result.exit_code == 0
        assert "No API keys found" in result.output

    def test_lists_created_keys(self, db_path):
        runner = CliRunner()
        runner.invoke(app, ["auth", "create-key", "admin-key", "--role", "admin", "--db-path", db_path])
        result = runner.invoke(app, ["auth", "list-keys", "--db-path", db_path])
        assert result.exit_code == 0
        assert "admin-key" in result.output
        assert "admin" in result.output

    def test_lists_multiple_keys(self, db_path):
        runner = CliRunner()
        runner.invoke(app, ["auth", "create-key", "k1", "--role", "admin", "--db-path", db_path])
        # Get the admin key to create more
        result1 = runner.invoke(app, ["auth", "create-key", "k1", "--role", "admin", "--db-path", db_path])
        lines = result1.output.splitlines()
        key_line = next((l for l in lines if "ml_" in l), None)
        if key_line:
            raw_key = key_line.strip().split()[-1]
            runner.invoke(
                app,
                ["auth", "create-key", "k2", "--role", "viewer", "--admin-key", raw_key, "--db-path", db_path],
            )
        result = runner.invoke(app, ["auth", "list-keys", "--db-path", db_path])
        assert result.exit_code == 0
        assert "k1" in result.output

    def test_shows_table_headers(self, db_path):
        runner = CliRunner()
        runner.invoke(app, ["auth", "create-key", "k1", "--role", "admin", "--db-path", db_path])
        result = runner.invoke(app, ["auth", "list-keys", "--db-path", db_path])
        assert result.exit_code == 0
        assert "NAME" in result.output
        assert "ROLE" in result.output
        assert "PREFIX" in result.output

    def test_shows_prefix_not_full_key(self, db_path):
        runner = CliRunner()
        result1 = runner.invoke(
            app, ["auth", "create-key", "k1", "--role", "admin", "--db-path", db_path]
        )
        # Capture full key
        lines = result1.output.splitlines()
        key_line = next(l for l in lines if "ml_" in l)
        raw_key = key_line.strip().split()[-1]

        result = runner.invoke(app, ["auth", "list-keys", "--db-path", db_path])
        # Full key should NOT appear in list output
        assert raw_key not in result.output
        # But prefix (ml_...) should appear
        assert "ml_" in result.output


class TestRevokeKeyCommand:
    def test_revoke_existing_key(self, db_path):
        runner = CliRunner()
        runner.invoke(app, ["auth", "create-key", "to-revoke", "--role", "viewer", "--db-path", db_path])
        result = runner.invoke(app, ["auth", "revoke-key", "to-revoke", "--db-path", db_path])
        assert result.exit_code == 0
        assert "to-revoke" in result.output

        # Verify it's gone from list
        list_result = runner.invoke(app, ["auth", "list-keys", "--db-path", db_path])
        assert "to-revoke" not in list_result.output

    def test_revoke_nonexistent_key_succeeds_silently(self, db_path):
        runner = CliRunner()
        result = runner.invoke(app, ["auth", "revoke-key", "nonexistent", "--db-path", db_path])
        assert result.exit_code == 0

    def test_revoke_shows_key_name(self, db_path):
        runner = CliRunner()
        runner.invoke(app, ["auth", "create-key", "my-key", "--role", "viewer", "--db-path", db_path])
        result = runner.invoke(app, ["auth", "revoke-key", "my-key", "--db-path", db_path])
        assert result.exit_code == 0
        assert "my-key" in result.output

    def test_revoke_leaves_other_keys_intact(self, db_path):
        runner = CliRunner()
        # Create first key (admin)
        result1 = runner.invoke(
            app, ["auth", "create-key", "admin", "--role", "admin", "--db-path", db_path]
        )
        lines = result1.output.splitlines()
        key_line = next(l for l in lines if "ml_" in l)
        raw_key = key_line.strip().split()[-1]

        # Create second key
        runner.invoke(
            app,
            ["auth", "create-key", "viewer", "--role", "viewer", "--admin-key", raw_key, "--db-path", db_path],
        )

        # Revoke viewer
        runner.invoke(app, ["auth", "revoke-key", "viewer", "--db-path", db_path])

        # Admin should still be there
        list_result = runner.invoke(app, ["auth", "list-keys", "--db-path", db_path])
        assert "admin" in list_result.output
        assert "viewer" not in list_result.output
