# Releasing iwant

Releases are published manually from `main`. Each GitHub Release contains an
installer pinned to its Git tag, so users can install or roll back to a specific
version. Merging a change does not publish a release.

## How the pieces connect

- [`pyproject.toml`](../pyproject.toml) holds `project.version`, the source for the
  package version, release title, and Git tag. Model recipe versions are separate.
- [The Release workflow](../.github/workflows/release.yml) sets up Python and uv,
  then runs `make install` and `make release`. It provides a GitHub token with
  permission to publish the release.
- [The Makefile](../Makefile) defines the checks and release commands used both
  locally and in GitHub Actions.
- [`install.sh`](../install.sh) is the installer template. The release command
  sets its `RELEASE_TAG` to the published tag and attaches that copy to the
  release. The repository template defaults to `main`.

## Prepare and publish

1. Set `project.version` in `pyproject.toml` to an unused stable version such as
   `0.1.0`. Use `X.Y.Z` format. Increase the version for each subsequent release.
2. Validate locally from the repository root:

   ```bash
   make install
   make check
   ```

3. Commit the changes and merge them into `main`. The release workflow itself
   must also be merged before it can be triggered.
4. Open [GitHub Actions → Release](https://github.com/narevai/iwant/actions/workflows/release.yml).
   Select **Run workflow**, choose `main`, and click **Run workflow**.
5. Open the new workflow run and wait for it to finish successfully.

The release job skips runs selected on a branch other than `main`. Only one
release job runs at a time.

## What the release command does

`make release` first runs `make check`: Ruff, type checking, formatting checks,
and tests. It then requires a clean `main` checkout and reads the version with
`uv version --short`.

Before publishing, it rejects an existing remote version tag, generates an
installer pinned to `vX.Y.Z`, and checks that the pin was applied and the script
passes shell syntax and help checks.

Finally, `gh release create` creates the tag at the checked-out commit, publishes
the installer with GitHub-generated release notes, and marks the release as
latest. Notes come from the repository's merged pull requests and contributors.
Review them after publication, especially when changes need migration guidance.
This process does not publish to PyPI.

## Verify the release

1. Confirm the workflow run is green.
2. Open [GitHub Releases](https://github.com/narevai/iwant/releases) and confirm
   that the expected tag, title, notes, and `install.sh` attachment are present.
3. Download the installer for that exact version. For example, for `0.1.0`:

   ```bash
   curl -fsSL https://github.com/narevai/iwant/releases/download/v0.1.0/install.sh -o /tmp/iwant-install.sh
   IWANT_NO_TELEMETRY=1 bash /tmp/iwant-install.sh --skip-auth
   iwant --version
   ```

   The command should report `0.1.0`. This performs an actual installation or
   update; `--skip-auth` skips cloud authentication setup.

The README's installation command uses
`https://github.com/narevai/iwant/releases/latest/download/install.sh`, which
downloads the installer attached to the latest release. Its embedded tag still
pins the installed code to that release.

## Publish from a local checkout

With `make`, Python, uv, Git, and the GitHub CLI installed, use a clean `main`
checkout whose changes have been pushed to GitHub:

```bash
gh auth login
make install
make release
```

`make release` publishes a real release. To validate without publishing, use
`make check`; its release tests use local Git repositories and a fake GitHub CLI.

## If a release fails

Open the failed workflow step and fix the reported error. Check or installer
validation failures stop publication. An existing tag requires a new version
for a normal subsequent release.

If failure occurs during publication, inspect both the Git tag and GitHub Release
before retrying: publication can leave partial state behind. A rerun rejects an
existing tag, so it cannot automatically repair an incomplete release.
