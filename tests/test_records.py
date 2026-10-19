from dataclasses import dataclass
from enum import Enum

import pytest
from pydantic import ValidationError

from iwant.records import CloudCheckResult, ClusterRecord, EndpointResult


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


def test_cluster_response_normalizes_timestamps_and_ignores_sdk_metadata() -> None:
    record = ClusterRecord.from_sdk(
        {"name": "iwant-model", "status": SDKStatus.UP, "launched_at": 123, "metadata": {"sdk": "extra"}}
    )
    assert record.name == "iwant-model"
    assert record.status == "UP"
    assert record.launched_at == 123.0


def test_cloud_check_rejects_invalid_capabilities() -> None:
    with pytest.raises(ValidationError):
        _ = CloudCheckResult.model_validate({"default": {"gcp": "not a capability list"}})


def test_cloud_check_normalizes_cloud_names() -> None:
    response = CloudCheckResult.model_validate({"one": {"GCP": []}, "two": ["AWS", "gcp"]})
    assert response.enabled_clouds() == {"gcp", "aws"}


@pytest.mark.parametrize("response", [[], "not endpoints", {8000: 123}, {"8000": "1.2.3.4:8000"}])
def test_endpoint_response_rejects_invalid_types(response: object) -> None:
    with pytest.raises(ValidationError):
        _ = EndpointResult.model_validate(response)
