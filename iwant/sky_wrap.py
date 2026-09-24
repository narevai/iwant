import subprocess
import time

from .registry import is_cluster_of_model
from .sky_client import resolve
from .spinner import Spinner


def _field(row, name, default=None):
    """sky.status() rows are Pydantic-model-like objects, not dicts -
    confirmed via a real `iwant status` dump. Try both so this doesn't
    silently break if a future SkyPilot version switches representations."""
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def _status_value(status) -> str:
    if status is None:
        return "?"
    return getattr(status, "value", None) or str(status)


def _relative_time(ts) -> str:
    if not ts:
        return "-"
    delta = time.time() - ts
    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"


def _iwant_rows(spinner_message: str) -> list | None:
    """Every iwant-managed sky.status() row, or None if the call itself
    failed (error already printed) - distinct from an empty list, which
    means the call worked and there's legitimately nothing running. Callers
    must not report "no such cluster" on None: the cluster may well exist
    (and be billing) while the API server is just unreachable."""
    import sky  # lazy - see sky_client.resolve()'s comment

    try:
        with Spinner(spinner_message):
            rows = resolve(sky.status())
    except Exception as e:
        print(f"sky.status() failed: {e}")
        return None
    return [row for row in rows or [] if (_field(row, "name") or "").startswith("iwant-")]


def all_clusters() -> list[dict] | None:
    """Every iwant-managed cluster ({"name", "infra", "status"}), from one
    sky.status() call - infra is its own resources_str, no extra request.
    Includes every status; callers filter by what's usable for their action.
    None if sky.status() failed - see _iwant_rows()."""
    rows = _iwant_rows("Checking clusters...")
    if rows is None:
        return None
    return [
        {
            "name": _field(row, "name"),
            "infra": _field(row, "resources_str"),
            "status": _status_value(_field(row, "status")),
        }
        for row in rows
    ]


def resolve_cluster(cluster: str, statuses: set[str] | None = None) -> str | None:
    """`cluster` must be an exact cluster name - no resolving by model name;
    that ambiguity (a model can have more than one concurrent cluster) is
    what the interactive picker is for, shown when the CLI argument is
    omitted entirely (see cli.py:_pick_running), not guessed here."""
    clusters = all_clusters()
    if clusters is None:
        return None
    if any(c["name"] == cluster for c in clusters):
        return cluster

    print(f"No cluster named '{cluster}' found.")
    available = [c["name"] for c in clusters if statuses is None or c["status"] in statuses]
    if available:
        print("Running: " + ", ".join(available))
    return None


def status(name: str | None = None) -> int:
    """`name` is either an exact cluster name or a recipe name - the latter
    shows every cluster launched from that model (any recipe version)."""
    result = _iwant_rows("Checking status...")
    if result is None:
        return 1
    if name:
        result = [
            row
            for row in result
            if _field(row, "name") == name or is_cluster_of_model(_field(row, "name"), name)
        ]
    if not result:
        print("No clusters found.")
        return 0

    rows = []
    for row in result:
        cloud = _field(row, "cloud")
        region = _field(row, "region")
        infra = f"{cloud} ({region})" if cloud and region else (cloud or "-")
        autostop_min = _field(row, "autostop")
        autostop = "-"
        if autostop_min and autostop_min > 0:
            autostop = f"{autostop_min}m" + (" (down)" if _field(row, "to_down") else "")
        rows.append(
            (
                _field(row, "name", "?"),
                infra,
                _field(row, "resources_str", "-"),
                _status_value(_field(row, "status")),
                autostop,
                _relative_time(_field(row, "launched_at")),
            )
        )

    header = ["NAME", "INFRA", "RESOURCES", "STATUS", "AUTOSTOP", "LAUNCHED"]
    table = [header, *rows]
    widths = [max(len(str(r[i])) for r in table) for i in range(len(header))]
    for r in table:
        print("  ".join(str(v).ljust(w) for v, w in zip(r, widths)))
    return 0


def down(cluster: str) -> int:
    import sky  # lazy - see sky_client.resolve()'s comment

    try:
        with Spinner(f"Tearing down {cluster}..."):
            resolve(sky.down(cluster))
    except Exception as e:
        print(f"sky.down() failed: {e}")
        return 1
    print(f"Torn down {cluster}.")
    return 0


def stop(cluster: str) -> int:
    import sky  # lazy - see sky_client.resolve()'s comment

    try:
        with Spinner(f"Stopping {cluster}..."):
            resolve(sky.stop(cluster))
    except Exception as e:
        print(f"sky.stop() failed: {e}")
        return 1
    print(f"Stopped {cluster}.")
    return 0


def ssh(cluster: str) -> int:
    # SkyPilot writes a Host entry named after the cluster to ~/.ssh/config
    # on a successful launch - no SDK equivalent needed, plain ssh works.
    return subprocess.call(["ssh", cluster])


def endpoint(cluster: str, quiet: bool = False) -> str | None:
    import sky  # lazy - see sky_client.resolve()'s comment

    try:
        if quiet:
            # Used for silent probing (launch.py checks post-launch state) -
            # a spinner here would just flicker uselessly.
            result = resolve(sky.endpoints(cluster, port=8000))
        else:
            with Spinner("Looking up endpoint..."):
                result = resolve(sky.endpoints(cluster, port=8000))
    except Exception as e:
        if not quiet:
            print(f"sky.endpoints() failed: {e}")
        return None
    # sky.endpoints() is documented to resolve to Dict[int, str] - don't
    # accept a bare string here. A resolved request_id string used to slip
    # through this check when resolve() swallowed sky.get() failures, which
    # made a *failed* launch print a request_id as if it were the server URL.
    # Also don't fall back to some *other* port if 8000 isn't there - we
    # asked for port=8000 explicitly, so a different port isn't the vLLM
    # server, it'd just be misleadingly printed as if it were.
    if isinstance(result, dict):
        return result.get(8000)
    return None
