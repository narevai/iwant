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
    _ = git(repo, "config", "commit.gpgsign", "false")
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


@pytest.mark.parametrize("ci_result", ["success", "failure", "pending", ""])
def test_daily_release_requires_successful_main_ci(
    release_repo: Path, monkeypatch: pytest.MonkeyPatch, ci_result: str
) -> None:
    from scripts import prepare_release

    monkeypatch.chdir(release_repo)
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/repo")
    original_command = prepare_release.command

    def command(*args: str) -> str:
        if args[0] == "gh":
            return ci_result
        return original_command(*args)

    monkeypatch.setattr(prepare_release, "command", command)
    assert prepare_release.prepare() == ("release" if ci_result == "success" else "skip")
    assert not (release_repo.parent / "published").exists()


def test_automatic_release_skips_stale_main(release_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import prepare_release

    old_head = git(release_repo, "rev-parse", "HEAD")
    _ = git(release_repo, "commit", "--allow-empty", "-m", "Newer main")
    _ = git(release_repo, "push", "origin", "main")
    _ = git(release_repo, "checkout", "--detach", old_head)
    monkeypatch.chdir(release_repo)
    assert prepare_release.prepare() == "skip"


@pytest.mark.parametrize("complete", [True, False])
def test_automatic_release_checks_existing_assets(
    release_repo: Path, monkeypatch: pytest.MonkeyPatch, complete: bool
) -> None:
    from scripts import prepare_release

    _ = git(release_repo, "tag", "v0.1.0")
    _ = git(release_repo, "push", "origin", "v0.1.0")
    monkeypatch.chdir(release_repo)
    original_command = prepare_release.command

    def command(*args: str) -> str:
        if args[0] == "gh":
            return "install.sh" if complete else ""
        return original_command(*args)

    monkeypatch.setattr(prepare_release, "command", command)
    if complete:
        assert prepare_release.prepare() == "skip"
    else:
        with pytest.raises(RuntimeError, match="incomplete"):
            _ = prepare_release.prepare()


@pytest.mark.parametrize("existing_pr", [False, True])
def test_daily_bump_commits_pyproject_and_dispatches_ci(
    release_repo: Path, monkeypatch: pytest.MonkeyPatch, existing_pr: bool
) -> None:
    from scripts import prepare_release

    _ = git(release_repo, "tag", "v0.1.0")
    _ = git(release_repo, "push", "origin", "v0.1.0")
    _ = git(release_repo, "commit", "--allow-empty", "-m", "Dependency updates")
    _ = git(release_repo, "push", "origin", "main")
    main_commit = git(release_repo, "rev-parse", "HEAD")
    monkeypatch.chdir(release_repo)
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/repo")
    original_command = prepare_release.command
    gh_calls: list[tuple[str, ...]] = []

    def command(*args: str) -> str:
        if args[0] != "gh":
            return original_command(*args)
        gh_calls.append(args)
        if args[1:3] == ("release", "view"):
            return "install.sh"
        if args[1] == "api":
            return "success"
        if args[1:3] == ("pr", "list"):
            return "https://github.com/example/repo/pull/42" if existing_pr else ""
        if args[1:3] == ("pr", "create"):
            assert "0.1.1" in Path(args[args.index("--body-file") + 1]).read_text()
            return "https://github.com/example/repo/pull/42"
        return ""

    monkeypatch.setattr(prepare_release, "command", command)
    assert prepare_release.prepare() == "version-pr"
    assert gh_calls[-1] == ("gh", "workflow", "run", "ci.yml", "--ref", "release/v0.1.1")
    assert git(release_repo, "rev-parse", "origin/main") == main_commit
    if existing_pr:
        assert any(call[1:3] == ("pr", "update-branch") for call in gh_calls)
    else:
        assert 'version = "0.1.1"' in (release_repo / "pyproject.toml").read_text()
        assert git(release_repo, "diff", "--name-only", "main", "HEAD") == "pyproject.toml"
        assert git(release_repo, "status", "--porcelain") == ""


@pytest.mark.parametrize("head_matches,bot", [(True, True), (False, True), (True, False)])
def test_version_pr_merge_requires_tested_head_and_bot_author(
    monkeypatch: pytest.MonkeyPatch, head_matches: bool, bot: bool
) -> None:
    from scripts import prepare_release

    calls: list[tuple[str, ...]] = []

    def command(*args: str) -> str:
        calls.append(args)
        if args[1:3] == ("pr", "list"):
            head = "tested-head" if head_matches else "other-head"
            author = "github-actions[bot]" if bot else "someone-else"
            return f"https://github.com/example/repo/pull/42\t{head}\t{author}"
        return ""

    monkeypatch.setattr(prepare_release, "command", command)
    result = prepare_release.finish_ci("release/v0.1.1", "tested-head")
    if head_matches and bot:
        assert result == "merged"
        assert calls[1][-2:] == ("--match-head-commit", "tested-head")
        assert calls[-1] == ("gh", "workflow", "run", "ci.yml", "--ref", "main")
    else:
        assert result == "skip"
        assert len(calls) == 1


@pytest.mark.parametrize("version_merge", [True, False])
def test_main_ci_only_publishes_daily_version_merge(
    release_repo: Path, monkeypatch: pytest.MonkeyPatch, version_merge: bool
) -> None:
    from scripts import prepare_release

    monkeypatch.chdir(release_repo)
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/repo")
    head = git(release_repo, "rev-parse", "HEAD")
    original_command = prepare_release.command

    def command(*args: str) -> str:
        if args[:3] == ("gh", "pr", "list"):
            return head if version_merge else "unrelated-commit"
        if args[:2] == ("gh", "api"):
            return "success"
        return original_command(*args)

    monkeypatch.setattr(prepare_release, "command", command)
    assert prepare_release.finish_ci("main", head) == ("release" if version_merge else "skip")
