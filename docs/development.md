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

See the [release guide](releases.md) for how the Makefile, GitHub workflow, and
versioned installer connect, plus the steps to publish and verify a release.

Use patch versions for fixes and minor versions for features or breaking changes
while the CLI is below `1.0`. Describe changes clearly in pull request titles and
edit the generated release notes when breaking changes need extra explanation.
