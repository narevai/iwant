import sys
import threading

import click

from . import infra as infra_mod
from . import launch as launch_mod
from . import sky_wrap, tui
from .cloud_env import ensure_cloud_env
from .registry import ModelNotFoundError, list_models


def _prefetch_sky() -> None:
    """`sky`'s own import graph is large (multi-second on a cold cache) and
    is now imported lazily, only inside the functions that actually call
    it (see sky_client.resolve()'s comment) - so commands/prompts that
    don't need it (e.g. the model picker) aren't held up by it.

    This kicks that import off in the background as early as possible
    instead: Python's import system is thread-safe, so whichever function
    later does its own `import sky` either gets the already-finished
    module for free, or transparently waits for this thread if it hasn't
    finished yet - never worse than not prefetching, and usually the whole
    cost ends up hidden behind however long the user spends answering the
    interactive pickers."""
    try:
        import sky  # noqa: F401
    except Exception:
        pass  # the real import (with real error handling) happens again where it's actually needed


@click.group()
def main():
    """iwant - launch vLLM model servers on the cloud via the SkyPilot Python SDK."""
    ensure_cloud_env()
    threading.Thread(target=_prefetch_sky, daemon=True).start()


def _pick_running(action: str, statuses: set[str] | None = None) -> str | None:
    if not sys.stdin.isatty():
        click.echo(
            "No cluster given and not interactive - pass the exact cluster name (see `iwant status`).",
            err=True,
        )
        return None
    instances = sky_wrap.all_clusters()
    if instances is None:
        return None  # sky.status() failed - error already printed
    if statuses is not None:
        instances = [i for i in instances if i["status"] in statuses]
    if not instances:
        click.echo("No running instances found.")
        return None
    return tui.pick_running_instance(instances, message=f"Which instance do you want to {action}?")


def _resolve_or_pick(cluster: str | None, action: str, statuses: set[str] | None = None) -> str | None:
    """CLUSTER must be an exact cluster name - see sky_wrap.resolve_cluster().
    `statuses` restricts what the picker offers when CLUSTER is omitted -
    e.g. a STOPPED cluster can't be ssh'd into, but can still be torn down."""
    if cluster:
        return sky_wrap.resolve_cluster(cluster, statuses=statuses)
    return _pick_running(action, statuses)


@main.command(name="list")
def list_cmd():
    """List available model configs (recipes/<model>/v<N>.yaml)."""
    models = list_models()
    if not models:
        click.echo("No model configs found under recipes/.")
        return
    for name in models:
        click.echo(name)


@main.command(name="launch")
@click.argument("model", required=False)
@click.option("--dry-run", is_flag=True, help="Show the launch plan, spend no money.")
@click.option(
    "--yes",
    is_flag=True,
    help="Skip all interactive prompts: the model/infra/spot/autostop/dry-run pickers.",
)
@click.option(
    "--infra",
    default=None,
    help="Skip the infra picker, launch on this infra directly (e.g. gcp, aws, runpod).",
)
@click.option(
    "--spot",
    is_flag=True,
    help="Use spot/preemptible instances (cheaper, can be reclaimed anytime). Omit to pick interactively.",
)
@click.option(
    "--api-key",
    default=None,
    help="Use this vLLM API key instead of generating a random one.",
)
@click.option(
    "--hf-token",
    default=None,
    envvar="HF_TOKEN",
    help="Sets HF_TOKEN in the launched instance's environment - for gated models "
    "or faster/authenticated HuggingFace downloads. Also reads the HF_TOKEN env var.",
)
@click.option(
    "--idle-minutes",
    type=int,
    default=None,
    help=f"Autostop+teardown the cluster after this many idle minutes "
    f"(default {launch_mod.DEFAULT_IDLE_MINUTES}). Omit this and "
    "--no-autostop to pick interactively.",
)
@click.option(
    "--no-autostop",
    is_flag=True,
    help="Disable autostop - leaves the cluster (and its billing) running until you `iwant down` it.",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Don't stream setup/boot logs - wait silently and print the final summary.",
)
def launch_cmd(model, dry_run, yes, infra, spot, api_key, hf_token, idle_minutes, no_autostop, quiet):
    """Launch MODEL (or pick one interactively if omitted): provisions the GPU
    instance via the SkyPilot SDK, installs and starts vLLM, prints the
    server address and API key."""
    try:
        code = launch_mod.launch(
            model,
            idle_minutes=None if no_autostop else idle_minutes,
            autostop_given=no_autostop or idle_minutes is not None,
            dry_run=dry_run,
            yes=yes,
            infra=infra,
            use_spot=spot,
            api_key=api_key,
            hf_token=hf_token,
            quiet=quiet,
        )
    except ModelNotFoundError as e:
        raise click.ClickException(str(e)) from e
    sys.exit(code)


@main.command(name="status")
@click.argument("model", required=False)
def status_cmd(model):
    """List iwant clusters (wraps sky.status()); pass MODEL (recipe name or
    exact cluster name) to filter - shows every matching cluster, since a
    model can have more than one running at once."""
    sys.exit(sky_wrap.status(model))


@main.command(name="down")
@click.argument("cluster", required=False)
def down_cmd(cluster):
    """Tear down a cluster (wraps sky.down()). CLUSTER is an exact cluster
    name (see `iwant status`); pick interactively if omitted."""
    cluster = _resolve_or_pick(cluster, "tear down")
    if cluster is None:
        sys.exit(1)
    sys.exit(sky_wrap.down(cluster))


@main.command(name="stop")
@click.argument("cluster", required=False)
def stop_cmd(cluster):
    """Stop a cluster without deleting it (wraps sky.stop()). CLUSTER is an
    exact cluster name; pick interactively if omitted."""
    cluster = _resolve_or_pick(cluster, "stop", statuses={"UP"})
    if cluster is None:
        sys.exit(1)
    sys.exit(sky_wrap.stop(cluster))


@main.command(name="ssh")
@click.argument("cluster", required=False)
def ssh_cmd(cluster):
    """SSH into a running cluster. CLUSTER is an exact cluster name; pick
    interactively if omitted."""
    cluster = _resolve_or_pick(cluster, "ssh into", statuses={"UP"})
    if cluster is None:
        sys.exit(1)
    sys.exit(sky_wrap.ssh(cluster))


@main.command(name="endpoint")
@click.argument("cluster", required=False)
def endpoint_cmd(cluster):
    """Print a cluster's server address (IP:port). CLUSTER is an exact
    cluster name; pick interactively if omitted."""
    cluster = _resolve_or_pick(cluster, "get the endpoint for", statuses={"UP"})
    if cluster is None:
        sys.exit(1)
    ep = sky_wrap.endpoint(cluster)
    if ep:
        click.echo(ep)
        sys.exit(0)
    sys.exit(1)


@main.command(name="check")
def check_cmd():
    """List which curated clouds the SDK reports as enabled (best-effort)."""
    enabled = infra_mod.enabled_infra()
    if not enabled:
        click.echo(
            "Could not confirm any enabled infra via the SDK (or none are "
            "enabled). Check `gcloud auth list` / `gcloud config get project`."
        )
        sys.exit(1)
    for name in enabled:
        click.echo(f"{name}: enabled")


@main.command(name="setup")
def setup_cmd():
    """Check status of every curated cloud SkyPilot could launch on, and how
    to set up one that isn't ready yet."""
    statuses = infra_mod.check_all()

    if not sys.stdin.isatty():
        for cloud, ok in statuses.items():
            if ok:
                click.echo(f"{cloud}: enabled")
            else:
                click.echo(f"{cloud}: not set up - {infra_mod.setup_hint(cloud)}")
        return

    picked = tui.pick_setup_target(statuses)
    if picked is None:
        return
    if statuses[picked]:
        click.echo(f"{picked}: already enabled - nothing to do.")
    else:
        click.echo(f"{picked}: not set up yet. To enable it, run:")
        click.echo(f"  {infra_mod.setup_hint(picked)}")


if __name__ == "__main__":
    main()
