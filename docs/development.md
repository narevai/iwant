# Development

The devcontainer includes cloud authentication and terminal recording tools.
Install the development dependencies and run the same checks as CI:

```bash
make install-dev
make check
```

The root `Makefile` defines the commands used by both CI and the release workflow.
Run individual checks with `make lint`, `make format-check`, `make types`, or
`make test`. Use `make format` to apply formatting. To select an interpreter,
pass `PYTHON=/path/to/python` to any target, including `install-dev`.

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

## Releases

`project.version` in `pyproject.toml` is the only maintained source of the CLI
version. Package metadata, `iwant --version`, release titles, and Git tags derive
from it. Changelog headings identify historical release notes; they do not set
the version. Model recipe versions remain independent.

To release:

1. Set `project.version` in `pyproject.toml` (the first release is `0.1.0`).
2. Move the changes from `[Unreleased]` into a matching `## [X.Y.Z]` section in
   `CHANGELOG.md`. An optional ` - YYYY-MM-DD` date is supported.
3. Merge the changes into `main`.
4. In GitHub Actions, select **Release → Run workflow**, using the `main` branch.

The workflow reads the version without a version input, requires matching,
nonempty changelog notes, and rejects an existing tag. It runs lint, formatting,
types, and tests, then generates an `install.sh` pinned to `vX.Y.Z`. It creates
that tag at the checked-out commit and publishes a GitHub Release with the
changelog entry and installer attached. Failed checks do not create a release.

Users download the installer from `releases/latest/download/install.sh` or
`releases/download/vX.Y.Z/install.sh`. Both install the exact release tag,
including when updating an existing installation. The installer template in the
repository defaults to `main`; the workflow stamps the release tag into the
published asset. `--branch NAME` explicitly selects a development branch instead.

Use patch versions for fixes and minor versions for features or breaking changes
while the CLI is below `1.0`. Describe breaking changes explicitly in the notes.
Releases do not publish packages to PyPI.
