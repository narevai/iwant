from pathlib import Path

import pytest

from scripts.release_notes import release_notes


def test_notes_use_project_version_and_stop_at_next_entry(tmp_path: Path):
    project = tmp_path / "pyproject.toml"
    project.write_text('[project]\nversion = "0.2.0"\n')
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\nFuture work\n\n"
        "## [0.2.0] - 2026-10-12\n\n### Added\n\n- New feature\n\n"
        "## [0.1.0]\n\n- Old feature\n"
    )
    assert release_notes(project, changelog) == ("0.2.0", "### Added\n\n- New feature\n")


@pytest.mark.parametrize(
    "contents",
    ["## [0.1.0]\nOld release", "## [0.2.0]\n", "## [0.2.0]\nA\n## [0.2.0]\nB"],
)
def test_missing_empty_or_duplicate_notes_fail(tmp_path: Path, contents: str):
    project = tmp_path / "pyproject.toml"
    project.write_text('[project]\nversion = "0.2.0"\n')
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(contents)
    with pytest.raises(ValueError, match="one nonempty changelog entry"):
        release_notes(project, changelog)
