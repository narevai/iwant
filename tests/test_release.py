import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import TypeAdapter

ROOT = Path(__file__).resolve().parents[1]


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
        text=True,
        stderr=subprocess.PIPE,
    ).strip()


@pytest.fixture
def release_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in ("Makefile", "install.sh"):
        destination = repo / name
        destination.parent.mkdir(exist_ok=True)
        _ = shutil.copyfile(ROOT / name, destination)
    _ = (repo / "pyproject.toml").write_text('[project]\nname = "release-fixture"\nversion = "0.1.0"\n')
    _ = git(repo, "init", "--initial-branch=main")
    _ = git(repo, "config", "user.name", "Release Test")
    _ = git(repo, "config", "user.email", "release@example.invalid")
    _ = git(repo, "add", ".")
    _ = git(repo, "commit", "-m", "Release fixture")
    remote = tmp_path / "remote.git"
    _ = git(repo, "init", "--bare", str(remote))
    _ = git(repo, "remote", "add", "origin", remote.as_uri())
    _ = git(repo, "push", "origin", "main")
    return repo


def run_release(repo: Path, *, github_ref: str = "") -> subprocess.CompletedProcess[str]:
    bin_dir = repo.parent / "bin"
    bin_dir.mkdir()
    # Capture publication inputs instead of accessing GitHub.
    gh = bin_dir / "gh"
    _ = gh.write_text(
        f"#!{sys.executable}\n"
        + "import json, os, pathlib, shutil, sys\n"
        + 'capture = pathlib.Path(os.environ["RELEASE_CAPTURE"])\n'
        + "capture.mkdir()\n"
        + "args = sys.argv[1:]\n"
        + '(capture / "args.json").write_text(json.dumps(args))\n'
        + 'shutil.copyfile(args[3], capture / "install.sh")\n'
    )
    gh.chmod(0o755)
    return subprocess.run(
        # The full check target runs separately; skip it in these publication tests.
        ["make", "--assume-old=check", "release"],
        cwd=repo,
        env={
            **os.environ,
            "GITHUB_REF": github_ref,
            "PYTHON": sys.executable,
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "RELEASE_CAPTURE": str(repo.parent / "published"),
        },
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("detached", [False, True])
def test_release_publishes_exact_commit_and_pinned_installer(release_repo: Path, detached: bool) -> None:
    if detached:
        _ = git(release_repo, "checkout", "--detach")
    result = run_release(release_repo, github_ref="refs/heads/main" if detached else "")
    assert result.returncode == 0, result.stdout + result.stderr
    published = release_repo.parent / "published"
    args = TypeAdapter(list[str]).validate_json((published / "args.json").read_text())
    assert args[:3] == ["release", "create", "v0.1.0"]
    assert args[args.index("--target") + 1] == git(release_repo, "rev-parse", "HEAD")
    assert args[args.index("--title") + 1] == "iwant 0.1.0"
    assert "--latest" in args
    assert "--generate-notes" in args
    assert 'RELEASE_TAG="v0.1.0"' in (published / "install.sh").read_text()


@pytest.mark.parametrize("failure", ["existing-tag", "dirty", "branch", "template", "remote"])
def test_release_validation_failures_prevent_publication(release_repo: Path, failure: str) -> None:
    if failure == "existing-tag":
        _ = git(release_repo, "tag", "v0.1.0")
        _ = git(release_repo, "push", "origin", "v0.1.0")
    elif failure == "dirty":
        with (release_repo / "pyproject.toml").open("a") as project:
            _ = project.write("\n# Uncommitted edits\n")
    elif failure == "branch":
        _ = git(release_repo, "checkout", "-b", "feature")
    elif failure == "template":
        installer = release_repo / "install.sh"
        _ = installer.write_text(installer.read_text().replace('RELEASE_TAG=""', "RELEASE_TAG=''"))
        _ = git(release_repo, "add", "install.sh")
        _ = git(release_repo, "commit", "-m", "Change installer template")
    else:
        _ = git(release_repo, "remote", "set-url", "origin", (release_repo.parent / "missing.git").as_uri())
    result = run_release(release_repo)
    assert result.returncode != 0
    assert not (release_repo.parent / "published").exists()
