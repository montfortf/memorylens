from __future__ import annotations

import time

import pytest
from typer.testing import CliRunner

from memorylens.cli.main import app


@pytest.fixture
def db_with_versions(tmp_path):
    """Return a db_path pre-populated with 2 versions of one key."""
    from memorylens._exporters.sqlite import SQLiteExporter

    db_path = str(tmp_path / "test.db")
    exporter = SQLiteExporter(db_path=db_path)
    now = time.time()
    for i in range(2):
        exporter.save_version(
            {
                "memory_key": "user_42_prefs",
                "version": i + 1,
                "span_id": f"span-{i}",
                "operation": "memory.write",
                "content": f"Version {i + 1} content about user prefs.",
                "embedding": None,
                "agent_id": "agent-1",
                "session_id": f"sess-{i}",
                "timestamp": now - (2 - i) * 3600,
            }
        )
    exporter.shutdown()
    return db_path


@pytest.fixture
def db_with_reports(db_with_versions):
    """Run analyze to populate reports, return db_path."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "drift",
            "analyze",
            "--db-path",
            db_with_versions,
            "--scorer",
            "mock",
            "--type",
            "entity",
        ],
    )
    assert result.exit_code == 0, result.output
    return db_with_versions


class TestDriftAnalyzeCommand:
    def test_analyze_no_versions(self, tmp_path):
        runner = CliRunner()
        db_path = str(tmp_path / "empty.db")
        result = runner.invoke(app, ["drift", "analyze", "--db-path", db_path, "--scorer", "mock"])
        assert result.exit_code == 0
        assert "No memory versions found" in result.output

    def test_analyze_entity_type(self, db_with_versions):
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "drift",
                "analyze",
                "--db-path",
                db_with_versions,
                "--scorer",
                "mock",
                "--type",
                "entity",
            ],
        )
        assert result.exit_code == 0
        assert "Entity Drift" in result.output

    def test_analyze_all_types(self, db_with_versions):
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "drift",
                "analyze",
                "--db-path",
                db_with_versions,
                "--scorer",
                "mock",
                "--type",
                "all",
            ],
        )
        assert result.exit_code == 0
        assert "Entity Drift" in result.output
        assert "Session Drift" in result.output
        assert "Topic Drift" in result.output


class TestDriftReportCommand:
    def test_report_no_data(self, tmp_path):
        runner = CliRunner()
        db_path = str(tmp_path / "empty.db")
        result = runner.invoke(app, ["drift", "report", "--db-path", db_path])
        assert result.exit_code == 0
        assert "No drift reports found" in result.output

    def test_report_shows_data(self, db_with_reports):
        runner = CliRunner()
        result = runner.invoke(app, ["drift", "report", "--db-path", db_with_reports])
        assert result.exit_code == 0
        assert "user_42_prefs" in result.output

    def test_report_filter_by_type(self, db_with_reports):
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "drift",
                "report",
                "--db-path",
                db_with_reports,
                "--type",
                "entity",
            ],
        )
        assert result.exit_code == 0

    def test_report_filter_by_grade(self, db_with_reports):
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "drift",
                "report",
                "--db-path",
                db_with_reports,
                "--grade",
                "D",
            ],
        )
        assert result.exit_code == 0


class TestDriftShowCommand:
    def test_show_unknown_key(self, tmp_path):
        runner = CliRunner()
        db_path = str(tmp_path / "empty.db")
        result = runner.invoke(
            app,
            [
                "drift",
                "show",
                "nonexistent_key",
                "--db-path",
                db_path,
                "--scorer",
                "mock",
            ],
        )
        assert result.exit_code == 0
        assert "No versions found" in result.output

    def test_show_known_key(self, db_with_versions):
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "drift",
                "show",
                "user_42_prefs",
                "--db-path",
                db_with_versions,
                "--scorer",
                "mock",
            ],
        )
        assert result.exit_code == 0
        assert "user_42_prefs" in result.output
        assert "Grade" in result.output
        assert "Version History" in result.output
