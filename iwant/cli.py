import sys
import threading

import click

from . import infra as infra_mod
from . import launch as launch_mod
from . import sky_wrap, tui
from .cloud_env import ensure_cloud_env
from .registry import ModelNotFoundError


def _prefetch_sky() -> None:
    """Start importing `sky` in the background. It takes a few seconds, so
    modules import it lazily, inside the functions that use it; this hides
    most of that cost behind the interactive pickers. A later `import sky`
    elsewhere just waits for this one to finish."""
    try:
        import sky  # noqa: F401
    except Exception:
        pass  # imported again, with error handling, where it's used


class _SectionedGroup(click.Group):
    """Lists commands in a fixed order, in blank-line-separated sections."""

    SECTIONS = (("up", "down"), ("auth",), ("list", "ssh"))

    def list_commands(self, ctx):
        return [name for section in self.SECTIONS for name in section]

    def format_commands(self, ctx, formatter):
        width = max(len(name) for name in self.list_commands(ctx))
        with formatter.section("Commands"):
            for i, section in enumerate(self.SECTIONS):
                if i:
                    formatter.write("\n")
                formatter.write_dl(
                    [(name.ljust(width), self.commands[name].get_short_help_str()) for name in section]
                )


@click.group(cls=_SectionedGroup)
def main():
    """iwant - launch vLLM model servers on cloud GPUs."""
    ensure_cloud_env()
    threading.Thread(target=_prefetch_sky, daemon=True).start()


def _pick_running(action: str, statuses: set[str] | None = None) -> str | None:
    if not sys.stdin.isatty():
        click.echo(
            "No cluster given and not interactive - pass the exact cluster name (see `iwant list`).",
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
    """The exact cluster name given, or one picked interactively if omitted.
    `statuses` limits what the picker offers (e.g. a STOPPED cluster can't
    be ssh'd into, but can still be torn down)."""
    if cluster:
        return sky_wrap.resolve_cluster(cluster, statuses=statuses)
    return _pick_running(action, statuses)


@main.command(name="up", short_help="Deploy model")
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
    help="Skip the infra picker, launch on this infra directly (e.g. gcp, or gcp/us-central1).",
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
    """Deploy MODEL on a cloud GPU (pick one interactively if omitted) and
    print the server address and API key."""
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


@main.command(name="down", short_help="Tear down a model")
@click.argument("cluster", required=False)
def down_cmd(cluster):
    """Tear down CLUSTER (see `iwant list`); pick interactively if omitted."""
    cluster = _resolve_or_pick(cluster, "tear down")
    if cluster is None:
        sys.exit(1)
    sys.exit(sky_wrap.down(cluster))


@main.command(name="auth", short_help="Login to your cloud provider")
def auth_cmd():
    """Show which clouds are ready, and how to log in to the rest."""
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


@main.command(name="list", short_help="Show deployed models")
@click.argument("cluster", required=False)
def list_cmd(cluster):
    """Show deployed models, or just CLUSTER."""
    sys.exit(sky_wrap.status(cluster))


@main.command(name="ssh", short_help="SSH into a cluster")
@click.argument("cluster", required=False)
def ssh_cmd(cluster):
    """SSH into CLUSTER; pick interactively if omitted."""
    cluster = _resolve_or_pick(cluster, "ssh into", statuses={"UP"})
    if cluster is None:
        sys.exit(1)
    sys.exit(sky_wrap.ssh(cluster))


if __name__ == "__main__":
    main()
