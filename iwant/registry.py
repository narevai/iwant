import re
import secrets
from pathlib import Path

RECIPES_DIR = Path(__file__).resolve().parent / "recipes"

# Recipes live in recipes/<model>/v<N>.yaml; `iwant launch` takes the highest
# N. Published versions aren't edited - changes go into v<N+1>.yaml, so
# <model>@v<N> always means the same config.
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
    """Unique per launch, so the same model can run on several clusters at once."""
    return f"iwant-{model}-v{version}-{secrets.token_hex(3)}"
