"""Typed records shared by cloud adapters and CLI presentation."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import cast


def record_field(record: object, name: str) -> object:
    """Normalize SDK mappings/objects at the external data boundary."""
    if isinstance(record, Mapping):
        return cast(Mapping[str, object], record).get(name)
    return getattr(record, name, None)


def text_field(record: object, name: str, default: str = "-") -> str:
    value = record_field(record, name)
    if value is None:
        return default
    if isinstance(value, Enum):
        value = value.value
    return str(value)


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
        autostop = record_field(record, "autostop")
        launched_at = record_field(record, "launched_at")
        return cls(
            name=text_field(record, "name", "?"),
            status=text_field(record, "status", "?"),
            resources_str=text_field(record, "resources_str"),
            cloud=text_field(record, "cloud"),
            region=text_field(record, "region", ""),
            autostop=autostop if isinstance(autostop, int) else None,
            to_down=record_field(record, "to_down") is True,
            launched_at=float(launched_at) if isinstance(launched_at, (int, float)) else None,
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
