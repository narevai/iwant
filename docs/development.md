# Development

The devcontainer includes cloud authentication and terminal recording tools.
Install the development dependencies and run the same checks as CI:

```bash
uv pip install --system -e '.[dev]'
python -m pytest
python -m ruff check .
python -m ruff format --check .
basedpyright --pythonpath "$(command -v python)"
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
