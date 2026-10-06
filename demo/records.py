from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, NamedTuple, TypeVar, cast

import yaml


def yaml_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("Expected a YAML mapping")
    return cast(Mapping[str, object], value)


def yaml_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Expected a string for {field}")
    return value


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
        data = yaml_mapping(yaml.safe_load(source.read_text()))
        envs = yaml_mapping(data.get("envs"))
        resources = yaml_mapping(data.get("resources"))
        return cls(
            recipe=yaml_string(envs.get("IWANT_RECIPE", f"{source.parent.name}@{source.stem}"), "recipe"),
            resources=Resources(
                infra=yaml_string(resources.get("infra", "gcp"), "infra"),
                accelerators=yaml_string(resources.get("accelerators"), "accelerators"),
            ),
        )


@dataclass(frozen=True)
class LaunchPlan:
    recipe: str
    resources: Resources
    idle_minutes: int | None

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
