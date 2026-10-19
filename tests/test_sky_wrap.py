import sys

import pytest

from iwant import sky_wrap
from iwant.records import ClusterRecord
from tests.fixtures import FakeSky


def row(name: str, status: str = "UP") -> ClusterRecord:
    return ClusterRecord(name, status, resources_str="1x GCP(L4:1)", cloud="gcp")


@pytest.fixture
def sky(monkeypatch: pytest.MonkeyPatch) -> FakeSky:
    sdk = FakeSky()
    monkeypatch.setitem(sys.modules, "sky", sdk)
    return sdk


def test_all_clusters_skips_non_iwant(sky: FakeSky) -> None:
    sky.rows = [row("iwant-a-v1-abc123"), row("someone-else")]
    clusters = sky_wrap.all_clusters()
    assert clusters is not None
    assert [c.name for c in clusters] == ["iwant-a-v1-abc123"]


def test_all_clusters_none_on_failure(sky: FakeSky, capsys: pytest.CaptureFixture[str]) -> None:
    sky.status_error = RuntimeError("api server down")
    assert sky_wrap.all_clusters() is None
    assert "api server down" in capsys.readouterr().out


def test_resolve_cluster_failure_does_not_claim_missing(
    sky: FakeSky, capsys: pytest.CaptureFixture[str]
) -> None:
    sky.status_error = RuntimeError("api server down")
    assert sky_wrap.resolve_cluster("iwant-a-v1-abc123") is None
    assert "No cluster named" not in capsys.readouterr().out


def test_status_filters_by_exact_cluster_name(sky: FakeSky, capsys: pytest.CaptureFixture[str]) -> None:
    sky.rows = [row("iwant-a-v1-aaaaaa"), row("iwant-a-v1-bbbbbb")]
    assert sky_wrap.status("iwant-a-v1-bbbbbb") == 0
    out = capsys.readouterr().out
    assert "bbbbbb" in out
    assert "aaaaaa" not in out


def test_status_fails_on_sdk_error(sky: FakeSky) -> None:
    sky.status_error = RuntimeError("boom")
    assert sky_wrap.status() == 1


def test_status_shows_endpoint_for_up_clusters(sky: FakeSky, capsys: pytest.CaptureFixture[str]) -> None:
    sky.rows = [row("iwant-a-v1-aaaaaa"), row("iwant-b-v1-bbbbbb", status="STOPPED")]
    sky.endpoint_result = {8000: "1.2.3.4:8000"}
    assert sky_wrap.status() == 0
    out = capsys.readouterr().out
    assert "ENDPOINT" in out
    assert "http://1.2.3.4:8000/v1" in out
    assert sky.endpoint_calls == [("iwant-a-v1-aaaaaa", 8000)]
