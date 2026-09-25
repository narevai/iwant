"""Environment fixups so each cloud's Python SDK sees the config its CLI
already has. Some SDKs don't read their CLI's config and need an explicit
env var instead. Each fixer is best-effort: it must never raise or block
startup.

Only non-secret config from the user's own CLI login is read here (e.g. the
active GCP project). Never store or pass credentials through this module -
if an SDK needs one, tell the user which login command to run."""

import os
import subprocess


def _ensure_gcp() -> None:
    """google-auth (used by SkyPilot's GCP checks) doesn't read gcloud's
    active project, so without GOOGLE_CLOUD_PROJECT it treats GCP as
    unusable even when gcloud itself is configured."""
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


_FIXERS = (_ensure_gcp,)


def ensure_cloud_env() -> None:
    for fixer in _FIXERS:
        try:
            fixer()
        except Exception:
            pass  # best-effort, never block startup
