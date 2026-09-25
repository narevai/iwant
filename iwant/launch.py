import os
import secrets
import sys
import tempfile
import time
from typing import TYPE_CHECKING

import requests
import yaml

from . import infra as infra_mod
from . import sky_wrap, tui
from .registry import list_models, new_cluster_name, resolve_task_yaml
from .spinner import Spinner

if TYPE_CHECKING:
    # Type hints only - `sky` is imported lazily at runtime.
    import sky

DEFAULT_IDLE_MINUTES = 30

# vLLM only opens its port once the model is loaded and warmed up, which can
# take a long time. HEALTH_CHECK_TIMEOUT counts from the last new line in the
# remote job log, so a slow but progressing launch doesn't time out. Keep it
# well above ~20 minutes: a large checkpoint download prints nothing for a
# long time. HEALTH_CHECK_GLOBAL_TIMEOUT caps the total wait regardless.
HEALTH_CHECK_TIMEOUT = 1800
HEALTH_CHECK_GLOBAL_TIMEOUT = 3600
HEALTH_CHECK_INTERVAL = 5

# Returned when the user backs out of a picker - distinct from None, which
# is a valid value for several of the settings.
_CANCELLED = object()


def _materialize_task_yaml(
    source_path,
    infra: str | None,
    api_key: str | None,
    use_spot: bool,
    hf_token: str | None = None,
    recipe: str | None = None,
) -> str:
    """Path to the recipe with CLI overrides applied: a temp copy if there
    is anything to override (the caller deletes it), else the recipe itself."""
    if infra is None and api_key is None and not use_spot and hf_token is None and recipe is None:
        return str(source_path)
    with open(source_path) as f:
        data = yaml.safe_load(f) or {}
    if infra:
        data.setdefault("resources", {})["infra"] = infra
    if api_key:
        data.setdefault("envs", {})["VLLM_API_KEY"] = api_key
    if hf_token:
        data.setdefault("envs", {})["HF_TOKEN"] = hf_token
    if use_spot:
        data.setdefault("resources", {})["use_spot"] = True
    if recipe:
        # Stays on the cluster too (`echo $IWANT_RECIPE` over ssh).
        data.setdefault("envs", {})["IWANT_RECIPE"] = recipe
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", prefix="iwant-task-", delete=False)
    yaml.safe_dump(data, tmp)
    tmp.close()
    return tmp.name


def _resolve_autostop(idle_minutes: int | None, autostop_given: bool, interactive: bool):
    """Returns the final idle-minutes-to-autostop (None means disabled), or
    _CANCELLED if the user backed out of the picker."""
    if idle_minutes is None and not autostop_given and interactive:
        picked = tui.pick_autostop()
        if picked is None:
            print("Cancelled.")
            return _CANCELLED
        idle_minutes = None if picked == -1 else picked
        autostop_given = True

    if idle_minutes is None and not autostop_given:
        idle_minutes = DEFAULT_IDLE_MINUTES
    return idle_minutes


def _resolve_model(model: str | None, interactive: bool):
    """The model name, or _CANCELLED (after printing why)."""
    if model is not None:
        return model
    if not interactive:
        print("No model given. Pass one, e.g. `iwant up gpt-oss-20b`.")
        return _CANCELLED
    models = list_models()
    if not models:
        print("No model configs found under recipes/.")
        return _CANCELLED
    picked = tui.pick_model(models)
    if picked is None:
        print("Cancelled.")
        return _CANCELLED
    return picked


def _resolve_infra(infra: str | None, interactive: bool):
    """The chosen infra, or _CANCELLED if the user backed out or no cloud is
    enabled - better to stop here than fail at sky.launch() after all the
    other prompts."""
    if infra is not None or not interactive:
        return infra

    enabled = infra_mod.enabled_infra()
    if not enabled:
        print("No cloud is set up to launch on. Run `iwant auth` to see how to enable one.")
        return _CANCELLED

    picked = tui.pick_infra(enabled)
    if picked is None:
        print("Cancelled.")
        return _CANCELLED
    return picked


def _resolve_spot(use_spot: bool, interactive: bool):
    """use_spot, asking only if --spot wasn't given; _CANCELLED if the user
    backed out."""
    if use_spot or not interactive:
        return use_spot
    picked = tui.pick_spot()
    if picked is None:
        print("Cancelled.")
        return _CANCELLED
    return picked


def _resolve_dry_run(dry_run: bool, interactive: bool):
    """dry_run, asking only if --dry-run wasn't given; _CANCELLED if the user
    backed out."""
    if dry_run or not interactive:
        return dry_run
    picked = tui.pick_dry_run()
    if picked is None:
        print("Cancelled.")
        return _CANCELLED
    return picked


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}m {seconds % 60}s" if seconds >= 60 else f"{seconds}s"


def _tail_progress_line(cluster: str, job_id) -> str | None:
    """Last non-empty line of the launch job's log, shown as progress while
    the server isn't up yet. None if there's no job or the fetch fails."""
    if job_id is None:
        return None
    import sky  # lazy: slow to import, see cli._prefetch_sky()

    try:
        chunks = sky.tail_logs(cluster, job_id, follow=False, tail=5, preload_content=False)
        text = "".join(c for c in chunks if c)
    except Exception:
        return None
    # Progress bars redraw with \r, so split on it too and keep the last segment.
    segments = [seg.strip() for seg in text.replace("\r", "\n").split("\n") if seg.strip()]
    if not segments:
        return None
    last = segments[-1]
    return last if len(last) <= 100 else last[:97] + "..."


# SkyPilot job statuses that mean the job is still going.
_JOB_NONTERMINAL = {"INIT", "PENDING", "SETTING_UP", "RUNNING"}


def _job_terminal_status(cluster: str, job_id) -> str | None:
    """The launch job's status if it has ended (e.g. "FAILED"). The server
    is meant to run forever, so any final status means it won't come up.
    None if it's still running or the lookup fails."""
    if job_id is None:
        return None
    import sky  # lazy: slow to import, see cli._prefetch_sky()

    try:
        statuses = sky.get(sky.job_status(cluster, job_ids=[job_id]))
    except Exception:
        return None
    if not isinstance(statuses, dict):
        return None
    status = statuses.get(job_id)
    if status is None:
        return None
    value = getattr(status, "value", None) or str(status)
    return None if value in _JOB_NONTERMINAL else value


def _wait_until_healthy(
    ep: str, key: str | None, spinner: Spinner, cluster: str, job_id
) -> tuple[bool, float, str | None]:
    """Polls GET /v1/models until vLLM responds, the job ends, or a timeout
    hits (see HEALTH_CHECK_TIMEOUT). Shows the latest job log line in the
    spinner meanwhile.

    Returns (healthy, elapsed, job_status); job_status is set only if the
    job ended, so a crashed server fails fast instead of waiting it out."""
    url = f"http://{ep}/v1/models"
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    start = time.monotonic()
    last_progress_at = start
    last_line: str | None = None
    while (
        time.monotonic() - last_progress_at < HEALTH_CHECK_TIMEOUT
        and time.monotonic() - start < HEALTH_CHECK_GLOBAL_TIMEOUT
    ):
        now = time.monotonic()
        elapsed = now - start
        line = _tail_progress_line(cluster, job_id)
        if line and line != last_line:
            last_line = line
            last_progress_at = now
        status = last_line or "Waiting for the server to respond..."
        spinner.message = f"{status} ({_format_duration(elapsed)})"
        try:
            if requests.get(url, headers=headers, timeout=5).status_code == 200:
                return True, time.monotonic() - start, None
        except requests.RequestException:
            pass
        job_status = _job_terminal_status(cluster, job_id)
        if job_status:
            return False, time.monotonic() - start, job_status
        time.sleep(HEALTH_CHECK_INTERVAL)
    return False, time.monotonic() - start, None


def _run_launch(
    task: "sky.Task",
    cluster: str,
    idle_minutes: int | None,
    dry_run: bool,
    quiet: bool,
    key: str | None,
    use_spot: bool,
    recipe: str,
) -> int:
    """Submits the launch, waits for the server and prints the result."""
    import sky  # lazy: slow to import, see cli._prefetch_sky()

    try:
        with Spinner("Submitting launch request..."):
            request_id = sky.launch(
                task,
                cluster_name=cluster,
                idle_minutes_to_autostop=idle_minutes,
                down=idle_minutes is not None,
                dryrun=dry_run,
            )
    except Exception as e:
        print(f"sky.launch() failed: {e}")
        return 1

    if dry_run:
        try:
            print("Dry run plan:", sky.get(request_id))
        except Exception as e:
            print(f"Could not resolve the dry-run plan: {e}")
            return 1
        return 0

    job_id = None
    if quiet:
        print("Launching quietly (Ctrl+C stops waiting - the job keeps running remotely)...")
        try:
            job_id, handle = sky.get(request_id)
            print(f"Job {job_id} started on {handle}.")
        except KeyboardInterrupt:
            print("\nStopped waiting.")
        except Exception as e:
            print(f"Launch failed: {e}")
            print(f"The cluster may still exist (and bill) - check `iwant list`, `iwant down {cluster}`.")
            return 1
    else:
        print(
            "Launch submitted, streaming logs (Ctrl+C to stop watching - "
            "the job keeps running remotely either way; pass --quiet to hide this)..."
        )
        try:
            job_id, handle = sky.stream_and_get(request_id)
            print(f"Job {job_id} started on {handle}.")
        except KeyboardInterrupt:
            print("\nDetached.")
        except Exception as e:
            print(f"Launch failed: {e}")
            print(f"The cluster may still exist (and bill) - check `iwant list`, `iwant down {cluster}`.")
            return 1

    ep = sky_wrap.endpoint(cluster)
    print()
    if ep:
        spinner = Spinner("Waiting for the server to respond...")
        start = time.monotonic()
        try:
            with spinner:
                healthy, elapsed, job_status = _wait_until_healthy(ep, key, spinner, cluster, job_id)
        except KeyboardInterrupt:
            print(
                f"\nStopped waiting after {_format_duration(time.monotonic() - start)} - "
                f"the job keeps running remotely. Check `iwant ssh {cluster}` or `iwant list`."
            )
            return 1
        if healthy:
            print(f"Server started (took {_format_duration(elapsed)} to respond).")
            print(f"Server:  http://{ep}/v1")
            print(f"API key: {key}")
            print(f"SSH:     ssh {cluster}")
            print(f"Recipe:  {recipe}")
            print(f"Test:    fry http://{ep} --token {key} --recipe {recipe}")
            print(f"Pricing: {'spot (can be reclaimed anytime)' if use_spot else 'on-demand'}")
            return 0
        if job_status:
            print(
                f"The server job ended ({job_status}) after {_format_duration(elapsed)} - "
                f"see `sky logs {cluster} {job_id}`. The cluster is still up (and billing): "
                f"`iwant down {cluster}` when done."
            )
            return 1
        print(
            f"Port is up (http://{ep}/v1) but the server isn't responding yet after "
            f"{_format_duration(elapsed)} - it may still be loading the model. "
            f"Check `iwant ssh {cluster}` or `iwant list`."
        )
        return 1

    print("Could not confirm the server endpoint yet - check `iwant list`.")
    return 1


def launch(
    model: str | None,
    idle_minutes: int | None = None,
    autostop_given: bool = False,
    dry_run: bool = False,
    yes: bool = False,
    infra: str | None = None,
    api_key: str | None = None,
    quiet: bool = False,
    use_spot: bool = False,
    hf_token: str | None = None,
) -> int:
    interactive = not yes and sys.stdin.isatty()

    model = _resolve_model(model, interactive)
    if model is _CANCELLED:
        return 1

    task_yaml, version = resolve_task_yaml(model)
    recipe = f"{model}@v{version}"
    cluster = new_cluster_name(model, version)
    print(f"Recipe: {recipe} (latest)")

    chosen_infra = _resolve_infra(infra, interactive)
    if chosen_infra is _CANCELLED:
        return 1

    use_spot = _resolve_spot(use_spot, interactive)
    if use_spot is _CANCELLED:
        return 1

    idle_minutes = _resolve_autostop(idle_minutes, autostop_given, interactive)
    if idle_minutes is _CANCELLED:
        return 1

    dry_run = _resolve_dry_run(dry_run, interactive)
    if dry_run is _CANCELLED:
        return 1

    key = None if dry_run else (api_key or secrets.token_hex(24))
    task_path = _materialize_task_yaml(
        task_yaml, infra=chosen_infra, api_key=key, use_spot=use_spot, hf_token=hf_token, recipe=recipe
    )
    import sky  # lazy: slow to import, see cli._prefetch_sky()

    try:
        task = sky.Task.from_yaml(task_path)
    finally:
        # Delete the temp copy (it holds the API key), never the recipe itself.
        if task_path != str(task_yaml):
            os.unlink(task_path)

    if key:
        print()
        print(f"API key (save this now): {key}")

    return _run_launch(task, cluster, idle_minutes, dry_run, quiet, key, use_spot, recipe)
