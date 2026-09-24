from click.testing import CliRunner

from iwant import registry
from iwant.cli import main


def test_help():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "launch" in result.output


def test_launch_help():
    result = CliRunner().invoke(main, ["launch", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output


def test_list_no_models(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "RECIPES_DIR", tmp_path / "empty")

    result = CliRunner().invoke(main, ["list"])
    assert result.exit_code == 0
    assert "No model configs" in result.output


def test_list_shows_models(tmp_path, monkeypatch):
    recipes = tmp_path / "recipes"
    recipes.mkdir()
    (recipes / "gpt-oss-20b").mkdir()
    (recipes / "gpt-oss-20b" / "v1.yaml").write_text("resources: {}")
    monkeypatch.setattr(registry, "RECIPES_DIR", recipes)

    result = CliRunner().invoke(main, ["list"])
    assert result.exit_code == 0
    assert "gpt-oss-20b" in result.output


def test_launch_missing_model_non_interactive():
    # CliRunner's stdin is not a real tty, so this should hit the
    # non-interactive "no model given" path rather than opening a picker.
    result = CliRunner().invoke(main, ["launch"])
    assert result.exit_code != 0
