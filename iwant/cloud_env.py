"""Best-effort environment fixups so each cloud's Python SDK/client library
sees the same config its own CLI already has. Some SDKs don't read their
CLI's config files/state directly and silently misbehave without an
explicit env var - even though the CLI itself is fully configured and
works fine. Add one `_ensure_<cloud>()` function per cloud here as we hit
its version of this problem, and register it in `_FIXERS` below. Each
fixer must be best-effort (never raise, never block startup) - `ensure_cloud_env()`
also catches broadly as a second line of defense.

IMPORTANT: this file only ever reads back *non-secret* config that the
user's own CLI login already established (e.g. GCP's active project id via
`gcloud config get-value project` - the user already ran `gcloud auth
login`/`gcloud auth application-default login` themselves, we're not doing
any auth here). Never add a fixer that stores, generates, or accepts API
keys/access keys/service-account JSON - if a cloud's SDK needs a real
credential iwant doesn't have, the fix is telling the user which CLI login
command to run, not smuggling a secret through this module."""

import os
import subprocess


def _ensure_gcp() -> None:
    """google-auth (used internally by SkyPilot's GCP credential checks)
    needs an explicit project - confirmed by direct testing: unlike
    `gcloud` itself, it does NOT read `gcloud config get-value project`.
    Without this it logs "No project ID could be determined" and silently
    treats GCP as unusable even when `gcloud` itself is fully configured
    and `sky launch` on GCP works fine."""
    if os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return
    project = result.stdout.strip()
    if project and project != "(unset)":
        os.environ["GOOGLE_CLOUD_PROJECT"] = project


def _ensure_aws() -> None:
    """Placeholder: we haven't hit a concrete case yet of boto3/AWS's SDK
    failing to pick up something the `aws` CLI already has configured
    (e.g. a region from an SSO profile) the way google-auth does for GCP.
    Add the actual fix here once we have a confirmed failure to fix,
    following the same pattern as _ensure_gcp() - same registration in
    _FIXERS below, no other wiring needed."""
    return


_FIXERS = (_ensure_gcp, _ensure_aws)


def ensure_cloud_env() -> None:
    for fixer in _FIXERS:
        try:
            fixer()
        except Exception:
            pass  # best-effort only - never block startup over this
