"""Typed records shared by cloud adapters and CLI presentation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel


class CloudCheckResult(
    RootModel[dict[str, Union[dict[str, list[str]], list[str], tuple[str, ...], set[str]]]]
):
    """SDK workspace-to-cloud capabilities, including cloud-name sequences."""

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True)

    def enabled_clouds(self) -> set[str]:
        return {cloud.lower() for clouds in self.root.values() for cloud in clouds}


class EndpointResult(RootModel[dict[int, str]]):
    """SDK port-to-address response."""

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True)


class SdkClusterRecord(BaseModel):
    """Only the SDK response fields consumed by iwant.

    Pydantic reads both response objects and mappings, normalizes string enum
    values, and ignores SDK metadata which iwant does not consume.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True, extra="ignore")

    name: Optional[str] = None
    status: Optional[str] = None
    resources_str: Optional[str] = None
    cloud: Optional[str] = None
    region: Optional[str] = None
    autostop: Optional[int] = Field(default=None, strict=True)
    to_down: bool = Field(default=False, strict=True)
    launched_at: Optional[float] = Field(default=None, strict=True)


@dataclass(frozen=True)
class ClusterRecord:
    name: str
    status: str
    resources_str: str = "-"
    cloud: str = "-"
    region: str = ""
    autostop: int | None = None
    to_down: bool = False
    launched_at: float | None = None

    @classmethod
    def from_sdk(cls, record: object) -> "ClusterRecord":
        if isinstance(record, cls):
            return record
        row = SdkClusterRecord.model_validate(record)
        return cls(
            name=row.name if row.name is not None else "?",
            status=row.status if row.status is not None else "?",
            resources_str=row.resources_str if row.resources_str is not None else "-",
            cloud=row.cloud if row.cloud is not None else "-",
            region=row.region if row.region is not None else "",
            autostop=row.autostop,
            to_down=row.to_down,
            launched_at=row.launched_at,
        )


@dataclass(frozen=True)
class RunningCluster:
    name: str
    infra: str
    status: str


@dataclass(frozen=True)
class CloudStatus:
    name: str
    enabled: bool
