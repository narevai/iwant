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
from .sky_client import resolve
from .spinner import Spinner

if TYPE_CHECKING:
    # Only for the type hint below - never imported at runtime, see the
    # lazy-import comment in sky_client.resolve().
    import sky

DEFAULT_IDLE_MINUTES = 30

# vLLM's HTTP server doesn't bind its port until model load + CUDA graph
# capture + kernel warmup are *all* done - confirmed on a real DeepSeek-V4-Flash
# launch (8x H100), nothing listening at all until the very last second. Two
# limits, deliberately different in kind: HEALTH_CHECK_TIMEOUT is
# *resettable* - it counts time since the remote job's log last changed (see
# _tail_progress_line()), not total elapsed time, so a launch that's still
# visibly progressing (just slowly) never times out on this one alone. The
# checkpoint download itself is a silent ~12+ minute gap in that log (HF's
# downloader doesn't print progress there) - 30 min clears that with real
# margin; don't drop this much below ~20 minutes. HEALTH_CHECK_GLOBAL_TIMEOUT
# is a flat ceiling on top - total wall-clock time regardless of progress,
# the actual backstop against something that keeps logging forever without
# ever really finishing.
HEALTH_CHECK_TIMEOUT = 1800
HEALTH_CHECK_GLOBAL_TIMEOUT = 3600
HEALTH_CHECK_INTERVAL = 5

# Distinct from any real return value (idle_minutes/model/infra can all
# legitimately be None) - marks "the user backed out of an interactive
# picker", so callers can tell that apart from "nothing to pick/no override".
_CANCELLED = object()


def _materialize_task_yaml(
    source_path,
    infra: str | None,
    api_key: str | None,
    use_spot: bool,
    hf_token: str | None = None,
    recipe: str | None = None,
) -> str:
    """sky.Task's mutator API for overriding envs/resources on an
    already-loaded Task isn't reliably documented across versions - instead
    of guessing method names, patch the yaml dict directly and load a fresh
    Task from that (a plain, well-understood operation)."""
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
    """Returns the model name, or _CANCELLED if nothing usable could be
    resolved (each case below prints its own reason before returning)."""
    if model is not None:
        return model
    if not interactive:
        print("No model given. Pass one, e.g. `iwant launch gpt-oss-20b` (see `iwant list`).")
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
    """Returns the chosen infra key, or _CANCELLED if the user backed out of
    an active picker, or if the SDK couldn't confirm any infra enabled at
    all - launching against an infra we can't even confirm is set up just
    fails later (at sky.launch(), after already asking about autostop/
    dry-run), so stop here instead of silently falling back to the task
    yaml's own default `infra:`."""
    if infra is not None or not interactive:
        return infra

    enabled = infra_mod.enabled_infra()
    if not enabled:
        print(
            "No cloud infra confirmed enabled via the SDK - can't launch "
            "without one.\nRun `iwant setup` to check status and see how "
            "to enable a specific cloud."
        )
        return _CANCELLED

    picked = tui.pick_infra(enabled)
    if picked is None:
        print("Cancelled.")
        return _CANCELLED
    return picked


def _resolve_spot(use_spot: bool, interactive: bool):
    """Returns the final use_spot bool, or _CANCELLED if the user backed out
    of the picker. Same pattern as _resolve_dry_run: an explicit --spot on
    the CLI always wins outright, only ask when nothing already decided it."""
    if use_spot or not interactive:
        return use_spot
    picked = tui.pick_spot()
    if picked is None:
        print("Cancelled.")
        return _CANCELLED
    return picked


def _resolve_dry_run(dry_run: bool, interactive: bool):
    """Returns the final dry_run bool, or _CANCELLED if the user backed out
    of the picker. An explicit `--dry-run` on the CLI always wins outright
    (same pattern as every other resolver here) - only ask when nothing
    already decided it."""
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
    """Best-effort: the most recent non-empty line of the launch job's
    remote log, via sky.tail_logs(follow=False) - a real progress signal
    (model loading, CUDA graph capture, kernel warmup) for the long stretch
    where the HTTP health check can't see anything yet. Returns None (and
    the caller falls back to a generic message) if there's no job_id yet or
    the log fetch fails for any reason - this is a nice-to-have, never
    something that should block/fail the health check itself."""
    if job_id is None:
        return None
    import sky  # lazy - see sky_client.resolve()'s comment

    try:
        chunks = sky.tail_logs(cluster, job_id, follow=False, tail=5, preload_content=False)
        text = "".join(c for c in chunks if c)
    except Exception:
        return None
    # Job logs include progress bars written with \r (carriage returns),
    # e.g. "Capturing CUDA graphs: 2%|...4%|...8%|..." concatenated on one
    # line - split on both \r and \n and keep only the last real segment.
    segments = [seg.strip() for seg in text.replace("\r", "\n").split("\n") if seg.strip()]
    if not segments:
        return None
    last = segments[-1]
    return last if len(last) <= 100 else last[:97] + "..."


# SkyPilot's JobStatus values that mean the job is still going (see
# sky/skylet/job_lib.py: JobStatus.nonterminal_statuses()). Compared by
# string value so this doesn't need to import sky's internals.
_JOB_NONTERMINAL = {"INIT", "PENDING", "SETTING_UP", "RUNNING"}


def _job_terminal_status(cluster: str, job_id) -> str | None:
    """Best-effort: the launch job's status if it has already ended (e.g.
    "FAILED", "FAILED_SETUP") - a vLLM server is meant to run forever, so
    *any* terminal status here means it's never going to answer the health
    check. None if still running, unknown, or the lookup fails - never a
    reason on its own to stop waiting."""
    if job_id is None:
        return None
    import sky  # lazy - see sky_client.resolve()'s comment

    try:
        statuses = resolve(sky.job_status(cluster, job_ids=[job_id]))
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
    """Polls GET /v1/models until vLLM responds, or gives up - either
    HEALTH_CHECK_TIMEOUT passes with no new remote log output, or
    HEALTH_CHECK_GLOBAL_TIMEOUT passes regardless (see the constants'
    comments above). sky.endpoints() only confirms the port is reachable,
    not that vLLM is actually serving (confirmed live: vLLM's HTTP server
    doesn't bind its port until model load + CUDA graph capture + kernel
    warmup are *all* done, so there's nothing to poll there for most of the
    wait). Tails the remote job log for a real progress line (see
    _tail_progress_line()), shown in `spinner`'s message instead of a
    static counter.

    Returns (healthy, elapsed, job_status) - job_status is set only when
    the launch job already ended (see _job_terminal_status()), so a crashed
    vLLM fails fast instead of burning GPU time until the timeout."""
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
    """Everything from submitting the launch request to reporting the
    outcome - the part of `launch()` that actually talks to SkyPilot."""
    import sky  # lazy - see sky_client.resolve()'s comment

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
            print("Dry run plan:", resolve(request_id))
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
            print(f"The cluster may still exist (and bill) - check `iwant status`, `iwant down {cluster}`.")
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
            print(f"The cluster may still exist (and bill) - check `iwant status`, `iwant down {cluster}`.")
            return 1

    ep = sky_wrap.endpoint(cluster, quiet=True)
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
                f"the job keeps running remotely. Check `iwant ssh {cluster}` or `iwant status`."
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
            f"Check `iwant ssh {cluster}` or `iwant status`."
        )
        return 1

    print("Could not confirm the server endpoint yet - check `iwant status`.")
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
    import sky  # lazy - see sky_client.resolve()'s comment

    try:
        task = sky.Task.from_yaml(task_path)
    finally:
        # _materialize_task_yaml only creates a real temp file (possibly
        # containing the plaintext API key) when there's something to
        # override - don't delete the original recipe yaml.
        if task_path != str(task_yaml):
            os.unlink(task_path)

    if key:
        print()
        print(f"API key (save this now): {key}")

    return _run_launch(task, cluster, idle_minutes, dry_run, quiet, key, use_spot, recipe)
