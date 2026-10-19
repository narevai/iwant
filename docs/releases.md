# Releasing iwant

Releases batch merged changes once daily at **00:00 UTC**. Each
GitHub Release contains an installer pinned to its Git tag, so users can install
or roll back to a specific version. Manual publication remains available.

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

## Automation setup

Complete the [Renovate and branch protection setup](development.md#one-time-github-setup).
In **Settings → Actions → General → Workflow permissions**, enable **Allow
GitHub Actions to create and approve pull requests**. The release workflow
requests permissions to create and merge version PRs, dispatch CI, read checks,
and publish releases using GitHub's built-in `GITHUB_TOKEN`. No extra token or
secret is needed. Organization policies must allow these permissions.

Require **CI passed** and up-to-date branches on `main`. Required human approvals
will block unattended version PR merges; do not bypass required CI checks.

## Version policy and daily publication

`project.version` in `pyproject.toml` is the **only source of the version**.
The daily workflow reads it and commits a patch bump back to that file through
a PR. GitHub tags label published versions; the workflow does not derive the
package version from Git tags or install different versions than the metadata.

1. Dependency updates and other changes merge throughout the day.
2. At **00:00 UTC**, the workflow checks `main` and its CI results.
3. If the declared version was published and new commits have merged, it opens
   one PR bumping `project.version`, for example `0.2.0` to `0.2.1`. If that
   version PR is already open, it rebases it. `release/vX.Y.Z` branches are
   reserved for automation. Without new changes, it skips.
4. The workflow explicitly dispatches the full CI workflow on the version
   branch. After success, it merges only the bot-authored PR whose head exactly
   matches the tested commit. GitHub still enforces branch protection.
5. It explicitly dispatches CI on `main` after merging. After that succeeds,
   the release workflow publishes the version now committed in `pyproject.toml`.
   Ordinary dependency merges do not start another release or bump.
6. An initial or manually bumped unused version is published directly by the
   daily run only after successful CI on that exact main commit.

Explicit `workflow_dispatch` calls can start CI with the built-in token without
relying on approval of automatically generated PR runs. See
[GitHub's token event behavior](https://docs.github.com/en/actions/concepts/security/github_token).
No one needs to remember daily version bumps. You can still set an appropriate
minor version in a feature PR; routine daily bumps increment the patch.

GitHub may delay scheduled runs and CI takes time, so publication is after the
requested midnight start. Failed checks or merge conflicts stop the pipeline.
If `main` moves ahead, the next nightly run retries or includes the newer changes.
Existing releases are checked for their installer; incomplete releases require
manual investigation. Version commits go through PRs rather than direct pushes.

## Manual publication

To start a batch before the nightly run, open
[GitHub Actions → Release](https://github.com/narevai/iwant/actions/workflows/release.yml),
select **Run workflow**, choose `main`, and run it. The same version bump, CI,
merge, and publication steps apply. Only one release job runs at a time;
selecting another branch skips the job.

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
in `pyproject.toml` for a subsequent release.

If failure occurs during publication, inspect both the Git tag and GitHub Release
before retrying: publication can leave partial state behind. A rerun rejects an
existing tag, so it cannot automatically repair an incomplete release.
