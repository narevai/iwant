import pytest
from click.testing import CliRunner

from iwant import cli
from iwant.cli import main


@pytest.fixture(autouse=True)
def no_background_sdk_import(monkeypatch):
    # These CLI-only tests need no SDK; a lingering import races later fixtures
    # that replace sys.modules["sky"] with a local test module.
    monkeypatch.setattr(cli, "_prefetch_sky", lambda: None)


def test_help_lists_commands_in_sections():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    commands = result.output.split("Commands:\n", 1)[1]
    assert [line.split()[0] if line.strip() else "" for line in commands.splitlines()] == [
        "up",
        "down",
        "",
        "auth",
        "",
        "list",
        "ssh",
    ]


def test_up_help():
    result = CliRunner().invoke(main, ["up", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output


def test_up_missing_model_non_interactive():
    # CliRunner's stdin is not a tty, so this takes the non-interactive
    # "no model given" path instead of opening a picker.
    result = CliRunner().invoke(main, ["up"])
    assert result.exit_code != 0
