"""Batch a daily pyproject version bump, explicitly run CI, then publish."""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def version() -> str:
    value = command("uv", "version", "--short")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise ValueError("Releases require a stable X.Y.Z version in pyproject.toml")
    return value


def main_head() -> str:
    _ = command("git", "fetch", "origin", "main", "--tags")
    head = command("git", "rev-parse", "HEAD")
    return head if head == command("git", "rev-parse", "origin/main") else ""


def ci_passed(head: str) -> bool:
    conclusions = command(
        "gh",
        "api",
        f"repos/{os.environ['GITHUB_REPOSITORY']}/commits/{head}/check-runs",
        "--paginate",
        "--jq",
        '.check_runs[] | select(.name == "CI passed" and .app.slug == "github-actions") | .conclusion',
    ).splitlines()
    return bool(conclusions) and conclusions[0] == "success"


def bump_pr(current_version: str) -> str:
    major, minor, patch = map(int, current_version.split("."))
    next_version = f"{major}.{minor}.{patch + 1}"
    branch = f"release/v{next_version}"
    pr = command(
        "gh",
        "pr",
        "list",
        "--base",
        "main",
        "--head",
        branch,
        "--state",
        "open",
        "--json",
        "url",
        "--jq",
        ".[0].url // empty",
    )
    if pr:
        _ = command("gh", "pr", "update-branch", pr, "--rebase")
    else:
        _ = command("git", "switch", "-c", branch)
        _ = command("uv", "version", "--frozen", next_version)
        _ = command("git", "add", "pyproject.toml")
        _ = command("git", "config", "user.name", "iwant release bot")
        _ = command("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        _ = command("git", "-c", "commit.gpgsign=false", "commit", "-m", f"chore: release v{next_version}")
        _ = command("git", "push", "origin", f"HEAD:refs/heads/{branch}")
        with tempfile.TemporaryDirectory() as directory:
            body = Path(directory) / "body.md"
            _ = body.write_text(
                f"Bump project.version to {next_version} for the daily batch of merged changes.\n\n"
                "The release workflow explicitly runs CI, merges after required checks pass, "
                "then checks main before publication.\n"
            )
            pr = command(
                "gh",
                "pr",
                "create",
                "--base",
                "main",
                "--head",
                branch,
                "--title",
                f"chore: release v{next_version}",
                "--body-file",
                str(body),
            )
    # GITHUB_TOKEN cannot start unattended PR CI through push/PR events.
    # Explicit workflow_dispatch is supported and needs no separate credential.
    _ = command("gh", "workflow", "run", "ci.yml", "--ref", branch)
    return "version-pr"


def prepare(*, allow_bump: bool = True) -> str:
    head = main_head()
    if not head:
        print("A newer main commit exists; defer to the next daily run.")
        return "skip"
    current_version = version()
    tag = f"v{current_version}"
    if tag in command("git", "tag", "--list").splitlines():
        assets = command("gh", "release", "view", tag, "--json", "assets", "--jq", ".assets[].name")
        if "install.sh" not in assets.splitlines():
            raise RuntimeError(f"Release {tag} is incomplete; inspect and repair it before retrying")
        if command("git", "rev-list", "-n", "1", tag) == head or not allow_bump:
            print("No new daily release to prepare.")
            return "skip"
        _ = command("git", "merge-base", "--is-ancestor", tag, head)
        return bump_pr(current_version) if ci_passed(head) else "skip"
    return "release" if ci_passed(head) else "skip"


def finish_ci(branch: str, tested_head: str) -> str:
    if branch.startswith("release/v"):
        # Only merge the bot's open version PR at the exact successfully tested SHA.
        rows = command(
            "gh",
            "pr",
            "list",
            "--base",
            "main",
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "url,headRefOid,author",
            "--jq",
            ".[] | [.url, .headRefOid, .author.login] | @tsv",
        )
        for row in rows.splitlines():
            pr, head, author = row.split("\t")
            if head == tested_head and author in {"github-actions[bot]", "app/github-actions"}:
                _ = command("gh", "pr", "merge", pr, "--squash", "--match-head-commit", tested_head)
                # Merging with GITHUB_TOKEN does not trigger push CI; dispatch it too.
                _ = command("gh", "workflow", "run", "ci.yml", "--ref", "main")
                return "merged"
        return "skip"
    if branch != "main" or main_head() != tested_head:
        return "skip"
    current_version = version()
    commits = command(
        "gh",
        "pr",
        "list",
        "--base",
        "main",
        "--head",
        f"release/v{current_version}",
        "--state",
        "merged",
        "--json",
        "mergeCommit",
        "--jq",
        ".[].mergeCommit.oid",
    ).splitlines()
    # Ordinary successful merges never create a release outside the daily schedule.
    return prepare(allow_bump=False) if tested_head in commits else "skip"


if __name__ == "__main__":
    result = (
        finish_ci(os.environ["RELEASE_CI_BRANCH"], os.environ["RELEASE_CI_SHA"])
        if "--finish-ci" in sys.argv[1:]
        else prepare()
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        _ = output.write(f"action={result}\n")
