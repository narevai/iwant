from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Generic, NamedTuple, Optional, TypeVar

from pydantic import RootModel
from typing_extensions import override

from iwant.recipe import Recipe
from iwant.records import ClusterRecord


class DemoState(RootModel[list[ClusterRecord]]):
    """Validated state shared by the recording simulator and chat fixture."""

    @classmethod
    def read(cls, path: Path) -> DemoState:
        return cls.model_validate_json(path.read_text()) if path.exists() else cls([])


@dataclass(frozen=True)
class Resources:
    infra: str
    accelerators: str


@dataclass(frozen=True)
class DemoTask:
    recipe: str
    resources: Resources

    @classmethod
    def from_yaml(cls, path: str | Path) -> DemoTask:
        source = Path(path)
        document = Recipe.from_yaml(source)
        accelerators = document.resources.accelerators
        if accelerators is None:
            raise ValueError("Demo recipes require accelerators")
        return cls(
            recipe=document.envs.IWANT_RECIPE or f"{source.parent.name}@{source.stem}",
            resources=Resources(infra=document.resources.infra or "gcp", accelerators=accelerators),
        )


@dataclass(frozen=True)
class LaunchPlan:
    recipe: str
    resources: Resources
    idle_minutes: Optional[int]

    @override
    def __str__(self) -> str:
        idle = f"{self.idle_minutes}m" if self.idle_minutes is not None else "disabled"
        return (
            f"Launch plan\n\nRecipe: {self.recipe}\nGPU: {self.resources.accelerators}\n"
            f"Cloud: {self.resources.infra}\nIdle teardown: {idle}"
        )


class LaunchResult(NamedTuple):
    job_id: int
    cluster_name: str


T = TypeVar("T")


@dataclass(frozen=True)
class DemoRequest(Generic[T]):
    result: T


@dataclass(frozen=True)
class HealthResponse:
    status_code: int
