import contextlib
import io

from .sky_client import resolve
from .spinner import Spinner

# `sky check` also lists storage-only integrations (Cloudflare, HuggingFace,
# VastData, ...) that can never be a `sky launch` target - curated to the
# clouds actually worth renting a GPU box on for this repo's use case.
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

# Confident, hand-verified setup instructions - only for clouds we actually
# know the login flow for. Everything else in COMPUTE_CLOUDS falls back to
# a generic doc pointer (_GENERIC_HINT) rather than guessing exact steps.
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
    """The set of enabled cloud names (lowercase) from sky.check.check(), or
    None if the check itself failed outright - distinct from an empty set,
    which means the check ran fine and legitimately found nothing enabled.

    Confirmed by direct introspection of the installed SkyPilot 0.13.0:
    `sky.check` is a *module* (sky/check.py), the actual function is
    `sky.check.check(...)`, called directly (synchronous - it returns the
    real Dict[str, Dict[str, List[str]]] {workspace: {cloud: [caps]}}, not
    a request_id, so wrapping it in resolve() is a defensive no-op, not
    strictly required).

    That call also prints its own raw, unrendered rich-console payload
    lines (`<sky-payload>"<rich_init>...`) straight to stdout when invoked
    outside the normal `sky` CLI - cosmetic noise, not an error. Swallowed
    here by redirecting stdout for just this call (the Spinner still shows:
    it captured the real stdout up front, see spinner.py). stderr (e.g. a
    genuine `google.auth` warning about missing credentials) is left alone
    since that's actually useful when something's really misconfigured."""
    import sky  # lazy - see sky_client.resolve()'s comment

    try:
        with Spinner("Checking cloud credentials..."):
            with contextlib.redirect_stdout(io.StringIO()):
                raw = resolve(sky.check.check(clouds=COMPUTE_CLOUDS, quiet=True))
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
    """Best-effort: which of our curated clouds does the SDK report as
    enabled. On any failure/surprise, returns [] - callers should treat
    that as "couldn't tell, fall back to the yaml's own infra:"."""
    enabled = _fetch_enabled()
    if enabled is None:
        return []
    if not enabled:
        print("(sky.check.check() reported no enabled clouds)")
    return [c for c in COMPUTE_CLOUDS if c in enabled]


def check_all() -> dict[str, bool]:
    """Every curated cloud mapped to whether it's enabled - unlike
    enabled_infra(), keeps the disabled ones too, for `iwant setup`."""
    enabled = _fetch_enabled() or set()
    return {c: (c in enabled) for c in COMPUTE_CLOUDS}
