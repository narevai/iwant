# Development

The devcontainer includes cloud authentication and terminal recording tools.
Install the development dependencies and run the same checks as CI:

```bash
make install
make check
```

The root `Makefile` defines the commands used by both CI and the release workflow.
`make install` installs the project and its development tools. Run individual
checks with `make lint` (Ruff and type checking), `make format-check`, or
`make test`. Use `make format` to apply formatting. To select an interpreter,
pass `PYTHON=/path/to/python` to any target, including `install`.

CI installs the full dependency set, runs tests, imports SkyPilot, and checks CLI
startup on Python 3.9–3.14. Every version is required to pass. Python 3.15 is
excluded from CI and package metadata because SkyPilot's PuLP 4.0.1 dependency
fails during wheel packaging on Python 3.15 ARM64 (`Large file option has not
been set`). Revisit the upper bound when the upstream build issue is resolved.

The installer continues to select Python 3.9–3.13, matching SkyPilot's documented
range. To check Python 3.9 locally in an isolated environment:

```bash
uv venv --seed --python 3.9 /tmp/iwant-py39
make install PYTHON=/tmp/iwant-py39/bin/python
make check PYTHON=/tmp/iwant-py39/bin/python
```

### Generate the GIFs

The README banner types `iwant up MODEL` and cycles through all model arguments
from the recipe registry. It never submits the command. Regenerate it after
adding a model:

```bash
python -m demo.render_banner
```

The static [banner](assets/banner.png) remains available as an alternative.

The demos are generated from editable VHS tapes and the real Click CLI. Local
fixtures simulate provisioning, health checks, and SSH, so recording needs no
cloud resources and incurs no GPU charges.

```bash
bash demo/render.sh functionality up       # launch walkthrough
bash demo/render.sh functionality dry-run  # preview walkthrough
bash demo/render.sh functionality quickstart # launch, prompt, answer, teardown
bash demo/render.sh                        # all 14 GIFs and MP4s
```

The quickstart runs curl against a loopback-only fixture with a fixed sample answer.
The renderer checks that both formats decode successfully. See the
[demo guide](../demo/README.md#regenerate) for tools, recording details, and the full gallery.

## Dependency updates

[Renovate](https://docs.renovatebot.com/) uses [`renovate.json`](../renovate.json)
to open pull requests targeting `main` for Python packages, GitHub Actions,
devcontainer features, and Docker images. Python minimum versions are bumped
so updates already inside an allowed range still produce a PR and run CI.
Patch, minor, and major updates are eligible for squash automerge when all
required checks pass. Failing updates stay open for investigation. Renovate
rebases branches when `main` changes, so each update is checked against the
latest merged code.

### One-time GitHub setup

1. Install the [Renovate GitHub App](https://github.com/apps/renovate) and grant
   it access to `narevai/iwant`. Enable repository Issues for its Dependency Dashboard.
2. Merge this configuration and CI workflow into `main`.
3. In **Settings → General → Pull Requests**, enable **Allow squash merging**
   and **Allow auto-merge**.
4. Protect `main` with a branch rule or ruleset requiring pull requests and the
   **CI passed** check from GitHub Actions. Require branches to be up to date
   before merging. Run CI once if the check is not yet available in the selector.
   Do this before allowing Renovate to process updates: platform automerge relies
   on required checks to prevent an early merge.
5. Required human approvals will also block bot PRs. For unattended merges,
   the applicable rules must permit Renovate PRs to merge without human approval;
   do not give it a bypass of required CI checks.

`CI passed` requires lint/type checks, formatting, and the entire Python test
matrix to succeed; failures, cancellations, and skipped jobs fail the gate.
Add any future mandatory CI jobs to its `needs` list.

The Click `<8.2.0` and Python 3.9 basedpyright `<1.40` ceilings are preserved.
Changing supported Python versions requires updating the CI matrix and installer
alongside package metadata. A newest upstream version that drops a supported
Python version can fail CI and remain unmerged; a green PR is required for every
update. This repository has no Python lockfile, so Renovate tracks direct
requirements rather than providing a complete transitive dependency lock.

Dependency PRs can auto-merge throughout the day. At **00:00 UTC daily**, the
release workflow batches new changes into one patch-version PR that updates
`project.version` in `pyproject.toml`, the only version source. It explicitly
runs CI for the version PR, merges it when required checks pass, runs CI on
main, and publishes. Days without changes are skipped. No daily manual bump or
additional secret is needed. Enable Actions PR creation as described in the
[release guide](releases.md).

## Releases

See the [release guide](releases.md) for how the Makefile, GitHub workflow, and
versioned installer connect, plus the steps to publish and verify a release.

Use patch versions for fixes and minor versions for features or breaking changes
while the CLI is below `1.0`. Describe changes clearly in pull request titles and
edit the generated release notes when breaking changes need extra explanation.
