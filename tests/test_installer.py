import os
import subprocess
from pathlib import Path

import pytest

INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, stderr=subprocess.PIPE).strip()


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    repo = tmp_path / "remote"
    git("init", "--initial-branch=main", str(repo))
    git("-C", str(repo), "config", "user.name", "Installer Test")
    git("-C", str(repo), "config", "user.email", "installer@example.invalid")
    git("-C", str(repo), "config", "commit.gpgsign", "false")
    git("-C", str(repo), "config", "tag.gpgsign", "false")
    for version in ("v0.1.0", "v0.2.0", "unreleased"):
        (repo / "version.txt").write_text(version)
        git("-C", str(repo), "add", "version.txt")
        git("-C", str(repo), "commit", "-m", version)
        if version != "unreleased":
            git("-C", str(repo), "tag", version)
    return repo


def install(tmp_path: Path, remote: Path, tag: str, *, branch: str | None = None):
    installer = tmp_path / "install.sh"
    installer.write_text(INSTALLER.read_text().replace('RELEASE_TAG=""', f'RELEASE_TAG="{tag}"', 1))
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$INSTALLER"; REPO_URL_SSH="$REMOTE"; REPO_URL_HTTPS="$REMOTE"; clone_repo',
            "installer-test",
            *(["--branch", branch] if branch else []),
        ],
        env={
            **os.environ,
            "INSTALLER": str(installer),
            "REMOTE": remote.as_uri(),
            "IWANT_HOME": str(tmp_path / "home"),
            "IWANT_INSTALL_DIR": str(tmp_path / "installed"),
        },
        text=True,
        capture_output=True,
    )


def test_release_installer_pins_fresh_install_upgrade_and_rollback(tmp_path: Path, remote: Path):
    checkout = tmp_path / "installed"
    for tag in ("v0.1.0", "v0.2.0", "v0.1.0"):
        result = install(tmp_path, remote, tag)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (checkout / "version.txt").read_text() == tag
        assert git("-C", str(checkout), "rev-parse", "HEAD") == git("-C", str(remote), "rev-parse", tag)
        assert git("-C", str(checkout), "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"


def test_release_installer_rejects_dirty_checkout(tmp_path: Path, remote: Path):
    assert install(tmp_path, remote, "v0.1.0").returncode == 0
    version = tmp_path / "installed" / "version.txt"
    version.write_text("local changes")
    result = install(tmp_path, remote, "v0.2.0")
    assert result.returncode != 0
    assert "Local changes" in result.stdout
    assert version.read_text() == "local changes"


def test_missing_release_does_not_change_existing_checkout(tmp_path: Path, remote: Path):
    assert install(tmp_path, remote, "v0.1.0").returncode == 0
    result = install(tmp_path, remote, "v9.9.9")
    assert result.returncode != 0
    assert (tmp_path / "installed" / "version.txt").read_text() == "v0.1.0"


def test_explicit_branch_overrides_release_pin(tmp_path: Path, remote: Path):
    assert install(tmp_path, remote, "v0.1.0").returncode == 0
    result = install(tmp_path, remote, "v0.1.0", branch="main")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "installed" / "version.txt").read_text() == "unreleased"
    result = install(tmp_path, remote, "v0.2.0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "installed" / "version.txt").read_text() == "v0.2.0"
