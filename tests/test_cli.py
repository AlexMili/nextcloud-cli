"""Smoke tests for the CLI entry point."""

from click.testing import CliRunner

from nextcloud_cli.cli import main


def test_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for command in ("login", "logout", "files", "notes", "calendar", "tasks", "contacts", "check"):
        assert command in result.output


def test_short_help_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["-h"])
    assert result.exit_code == 0


def test_subcommand_help() -> None:
    runner = CliRunner()
    for path in (
        ["files", "--help"],
        ["files", "list", "--help"],
        ["calendar", "create", "-h"],
        ["tasks", "create", "--help"],
        ["contacts", "list", "-h"],
    ):
        result = runner.invoke(main, path)
        assert result.exit_code == 0, f"{path} failed: {result.output}"


def test_version() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "nxcloud" in result.output
