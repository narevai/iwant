from dataclasses import dataclass
from enum import Enum

from iwant.records import ClusterRecord


class SDKStatus(Enum):
    UP = "UP"


@dataclass
class SDKRecord:
    name: str
    status: SDKStatus
    resources_str: str
    autostop: int
    to_down: bool


def test_cluster_normalizes_sdk_mapping_and_object() -> None:
    record = SDKRecord("iwant-model-v1-abc123", SDKStatus.UP, "L4:1", 30, True)
    expected = ClusterRecord(record.name, "UP", "L4:1", autostop=30, to_down=True)
    assert ClusterRecord.from_sdk(record) == expected
    assert (
        ClusterRecord.from_sdk(
            {
                "name": record.name,
                "status": "UP",
                "resources_str": "L4:1",
                "autostop": 30,
                "to_down": True,
            }
        )
        == expected
    )


def test_cluster_nullable_sdk_fields_use_typed_defaults() -> None:
    record = ClusterRecord.from_sdk({"name": "iwant-model", "status": None, "autostop": None})
    assert record.status == "?"
    assert record.autostop is None
    assert record.launched_at is None
