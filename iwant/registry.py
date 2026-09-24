import re
import secrets
from pathlib import Path

RECIPES_DIR = Path(__file__).resolve().parent / "recipes"

# Each recipe is recipes/<model>/v<N>.yaml. A published version is never
# edited - any config change goes into a new v<N+1>.yaml, so a benchmark
# tagged <model>@v<N> always points at the exact config it ran against.
# `iwant launch` always takes the highest N (latest).
_VERSION_RE = re.compile(r"v(\d+)\.yaml")


class ModelNotFoundError(Exception):
    pass


def _versions(model_dir: Path) -> list[int]:
    if not model_dir.is_dir():
        return []
    return sorted(int(m.group(1)) for p in model_dir.iterdir() if (m := _VERSION_RE.fullmatch(p.name)))


def list_models() -> list[str]:
    if not RECIPES_DIR.exists():
        return []
    return sorted(p.name for p in RECIPES_DIR.iterdir() if _versions(p))


def resolve_task_yaml(model: str) -> tuple[Path, int]:
    """(path, version) of `model`'s latest recipe version."""
    versions = _versions(RECIPES_DIR / model)
    if not versions:
        available = ", ".join(list_models()) or "(none)"
        raise ModelNotFoundError(f"No recipe for model '{model}'. Available: {available}")
    return RECIPES_DIR / model / f"v{versions[-1]}.yaml", versions[-1]


def new_cluster_name(model: str, version: int) -> str:
    """Unique name per launch - lets the same model run on more than one
    cluster/cloud at once (a plain `iwant-<model>` name would collide).
    Carries the recipe version so `iwant status` shows what's running."""
    return f"iwant-{model}-v{version}-{secrets.token_hex(3)}"


def is_cluster_of_model(cluster: str, model: str) -> bool:
    """Whether `cluster` was created by new_cluster_name() for `model` (any
    version). Exact match on the model segment, so e.g. "step-3.7-flash"
    doesn't also match "step-3.7-flash-optimized" clusters."""
    return re.fullmatch(rf"iwant-{re.escape(model)}-v\d+-[0-9a-f]+", cluster) is not None
