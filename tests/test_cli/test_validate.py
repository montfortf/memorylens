from __future__ import annotations

from typer.testing import CliRunner

from memorylens.cli.main import app

runner = CliRunner()


class TestValidateIntegration:
    def test_validate_existing_langchain(self):
        result = runner.invoke(
            app, ["validate", "integration", "memorylens.integrations.langchain.instrumentor"]
        )
        assert result.exit_code == 0
        # Module imports fine; instrument() will fail because langchain isn't installed
        assert "Import successful" in result.output
        assert "Found instrumentor" in result.output

    def test_validate_existing_mem0(self):
        result = runner.invoke(
            app, ["validate", "integration", "memorylens.integrations.mem0.instrumentor"]
        )
        assert result.exit_code == 0
        # Module imports fine; instrument() will fail because mem0 isn't installed
        assert "Import successful" in result.output

    def test_validate_nonexistent_module(self):
        result = runner.invoke(app, ["validate", "integration", "nonexistent.module"])
        assert result.exit_code == 0
        assert "FAILED" in result.output or "Import failed" in result.output

    def test_validate_module_without_instrumentor(self):
        result = runner.invoke(app, ["validate", "integration", "memorylens._core.schema"])
        assert result.exit_code == 0
        assert "No instrumentor" in result.output or "FAILED" in result.output
