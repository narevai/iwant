from click.testing import CliRunner

from iwant.cli import main


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
