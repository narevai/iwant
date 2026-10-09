import subprocess
import time

from .records import ClusterRecord, RunningCluster
from .spinner import Spinner


def _relative_time(ts: float | None) -> str:
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


def _iwant_rows(spinner_message: str) -> list[ClusterRecord] | None:
    """sky.status() rows for iwant clusters, or None if the call failed
    (error already printed). On None, don't claim a cluster is missing - it
    may exist while the API server is unreachable."""
    import sky  # lazy: slow to import, see cli._prefetch_sky()

    try:
        with Spinner(spinner_message):
            rows = sky.get(sky.status())
    except Exception as e:
        print(f"sky.status() failed: {e}")
        return None
    records = [ClusterRecord.from_sdk(row) for row in rows or []]
    return [row for row in records if row.name.startswith("iwant-")]


def all_clusters() -> list[RunningCluster] | None:
    """Typed picker records, or None when the cloud status lookup fails."""
    rows = _iwant_rows("Checking clusters...")
    if rows is None:
        return None
    return [RunningCluster(row.name, row.resources_str, row.status) for row in rows]


def resolve_cluster(cluster: str, statuses: set[str] | None = None) -> str | None:
    """`cluster` if an iwant cluster with that exact name exists, else None
    (after listing the available ones)."""
    clusters = all_clusters()
    if clusters is None:
        return None
    if any(c.name == cluster for c in clusters):
        return cluster

    print(f"No cluster named '{cluster}' found.")
    available = [c.name for c in clusters if statuses is None or c.status in statuses]
    if available:
        print("Running: " + ", ".join(available))
    return None


def status(cluster: str | None = None) -> int:
    result = _iwant_rows("Checking status...")
    if result is None:
        return 1
    if cluster:
        result = [row for row in result if row.name == cluster]
    if not result:
        print("No clusters found.")
        return 0

    up = [row.name for row in result if row.status == "UP"]
    endpoints: dict[str, str | None] = {}
    if up:
        with Spinner("Looking up endpoints..."):
            endpoints = {name: endpoint(name) for name in up}

    rows: list[tuple[str, str, str, str, str, str, str]] = []
    for row in result:
        cloud = row.cloud
        region = row.region
        infra = f"{cloud} ({region})" if cloud and region else (cloud or "-")
        autostop_min = row.autostop
        autostop = "-"
        if autostop_min and autostop_min > 0:
            autostop = f"{autostop_min}m" + (" (down)" if row.to_down else "")
        ep = endpoints.get(row.name)
        rows.append(
            (
                row.name,
                infra,
                row.resources_str,
                row.status,
                f"http://{ep}/v1" if ep else "-",
                autostop,
                _relative_time(row.launched_at),
            )
        )

    header = ("NAME", "INFRA", "RESOURCES", "STATUS", "ENDPOINT", "AUTOSTOP", "LAUNCHED")
    table = [header, *rows]
    widths = [max(len(str(r[i])) for r in table) for i in range(len(header))]
    for r in table:
        print("  ".join(str(v).ljust(w) for v, w in zip(r, widths)))
    return 0


def down(cluster: str) -> int:
    import sky  # lazy: slow to import, see cli._prefetch_sky()

    try:
        with Spinner(f"Tearing down {cluster}..."):
            sky.get(sky.down(cluster))
    except Exception as e:
        print(f"sky.down() failed: {e}")
        return 1
    print(f"Torn down {cluster}.")
    return 0


def ssh(cluster: str) -> int:
    # SkyPilot adds a Host entry for each cluster to ~/.ssh/config.
    return subprocess.call(["ssh", cluster])


def endpoint(cluster: str) -> str | None:
    """The vLLM server's "ip:port", or None if it can't be looked up."""
    import sky  # lazy: slow to import, see cli._prefetch_sky()

    try:
        result = sky.get(sky.endpoints(cluster, port=8000))
    except Exception:
        return None
    # Expect {port: "ip:port"}; anything else, or another port, isn't the vLLM server.
    if isinstance(result, dict):
        return result.get(8000)
    return None
