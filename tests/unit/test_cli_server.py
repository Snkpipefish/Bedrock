"""Tester for ``bedrock server`` CLI-kommandoen (session 93)."""

from __future__ import annotations

from click.testing import CliRunner

from bedrock.cli.server import server_cmd


def test_server_help_lists_all_options() -> None:
    """--help skal vise alle CLI-flagg."""
    runner = CliRunner()
    result = runner.invoke(server_cmd, ["--help"])
    assert result.exit_code == 0
    assert "--host" in result.output
    assert "--port" in result.output
    assert "--data-root" in result.output
    assert "--debug" in result.output
    assert "--use-waitress" in result.output


def test_server_help_documents_endpoints() -> None:
    """--help skal forklare hvor UI er tilgjengelig."""
    runner = CliRunner()
    result = runner.invoke(server_cmd, ["--help"])
    assert result.exit_code == 0
    # Help-tekst skal nevne UI-endpoint
    assert "host:port" in result.output or "UI" in result.output
