from __future__ import annotations

import contextlib
import io

from .records import CloudCheckResult, CloudStatus
from .sky_api import SkyCloudApi, check_clouds
from .spinner import Spinner

# Clouds iwant can launch on - each needs its SkyPilot extra in
# pyproject.toml (skypilot[gcp]).
COMPUTE_CLOUDS = ["gcp"]

SETUP_HINTS: dict[str, str] = {
    "gcp": "gcloud auth login && gcloud auth application-default login",
}


def setup_hint(cloud: str) -> str:
    return SETUP_HINTS[cloud]


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
                if not isinstance(sky, SkyCloudApi):
                    raise TypeError("SkyPilot does not expose its cloud credential checker")
                response = CloudCheckResult.model_validate(check_clouds(sky, COMPUTE_CLOUDS))
    except Exception as e:
        print(f"sky.check.check() failed: {e}")
        return None

    return response.enabled_clouds()


def enabled_infra() -> list[str]:
    """Which of COMPUTE_CLOUDS are enabled; [] if that can't be determined."""
    enabled = _fetch_enabled()
    if enabled is None:
        return []
    if not enabled:
        print("(sky.check.check() reported no enabled clouds)")
    return [c for c in COMPUTE_CLOUDS if c in enabled]


def check_all() -> list[CloudStatus]:
    """Every cloud in COMPUTE_CLOUDS mapped to whether it's enabled."""
    enabled = _fetch_enabled() or set()
    return [CloudStatus(c, c in enabled) for c in COMPUTE_CLOUDS]
