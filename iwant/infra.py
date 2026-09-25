import contextlib
import io

from .spinner import Spinner

# Clouds iwant can launch a GPU instance on. `sky check` also lists
# storage-only integrations, which are left out.
COMPUTE_CLOUDS = [
    "gcp",
    "aws",
    "azure",
    "runpod",
    "lambda",
    "kubernetes",
    "paperspace",
    "fluidstack",
    "vast",
    "oci",
    "ibm",
    "cudo",
]

# Setup commands for clouds with a known login flow; the rest get a link to
# SkyPilot's docs.
SETUP_HINTS: dict[str, str] = {
    "gcp": "gcloud auth login && gcloud auth application-default login",
    "aws": "aws configure   (or: aws sso login --profile <profile>, for SSO-based orgs)",
    "azure": "az login",
    "kubernetes": "point kubectl at a cluster with GPU nodes, then confirm with: kubectl get nodes",
}
_GENERIC_HINT_TMPL = (
    'pip install "skypilot[{cloud}]" and follow the {cloud} setup steps at '
    "https://docs.skypilot.co/en/latest/getting-started/installation.html"
)


def setup_hint(cloud: str) -> str:
    return SETUP_HINTS.get(cloud, _GENERIC_HINT_TMPL.format(cloud=cloud))


def _fetch_enabled() -> set[str] | None:
    """Enabled cloud names (lowercase), or None if the check itself failed
    (an empty set means it ran and found nothing enabled).

    sky.check.check() returns {workspace: {cloud: [capabilities]}}. Outside
    the `sky` CLI it also prints raw console payloads to stdout, so stdout
    is hidden for the call; stderr is kept, since real credential warnings
    go there."""
    import sky  # lazy: slow to import, see cli._prefetch_sky()

    try:
        with Spinner("Checking cloud credentials..."):
            with contextlib.redirect_stdout(io.StringIO()):
                raw = sky.check.check(clouds=COMPUTE_CLOUDS, quiet=True)
    except Exception as e:
        print(f"sky.check.check() failed: {e}")
        return None

    if not isinstance(raw, dict):
        print(f"(sky.check.check() returned unexpected shape: {raw!r})")
        return None

    enabled: set[str] = set()
    for value in raw.values():
        if isinstance(value, dict):
            enabled.update(k.lower() for k in value.keys())
        elif isinstance(value, (list, tuple, set)):
            enabled.update(str(k).lower() for k in value)
    return enabled


def enabled_infra() -> list[str]:
    """Which of COMPUTE_CLOUDS are enabled; [] if that can't be determined."""
    enabled = _fetch_enabled()
    if enabled is None:
        return []
    if not enabled:
        print("(sky.check.check() reported no enabled clouds)")
    return [c for c in COMPUTE_CLOUDS if c in enabled]


def check_all() -> dict[str, bool]:
    """Every cloud in COMPUTE_CLOUDS mapped to whether it's enabled."""
    enabled = _fetch_enabled() or set()
    return {c: (c in enabled) for c in COMPUTE_CLOUDS}
