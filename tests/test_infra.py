import sys

import pytest

from iwant import infra
from iwant.records import CloudStatus
from tests.fixtures import FakeSky


@pytest.fixture
def sky(monkeypatch: pytest.MonkeyPatch) -> FakeSky:
    sdk = FakeSky()
    monkeypatch.setitem(sys.modules, "sky", sdk)
    return sdk


def test_setup_hint_known_cloud() -> None:
    assert "gcloud" in infra.setup_hint("gcp")


def test_every_cloud_has_a_setup_hint() -> None:
    assert set(infra.SETUP_HINTS) == set(infra.COMPUTE_CLOUDS)


def test_compute_clouds_are_lowercase_and_unique() -> None:
    assert len(infra.COMPUTE_CLOUDS) == len(set(infra.COMPUTE_CLOUDS))
    assert all(c == c.lower() for c in infra.COMPUTE_CLOUDS)


def test_enabled_infra_parses_check_result(sky: FakeSky) -> None:
    sky.check.response = {"default": {"gcp": ["compute", "storage"]}}
    assert infra.enabled_infra() == ["gcp"]
    assert sky.check.calls == [(infra.COMPUTE_CLOUDS, True)]


def test_enabled_infra_empty_on_exception(sky: FakeSky, capsys: pytest.CaptureFixture[str]) -> None:
    sky.check.error = RuntimeError("boom")
    assert infra.enabled_infra() == []
    assert "boom" in capsys.readouterr().out


def test_enabled_infra_empty_on_unexpected_shape(sky: FakeSky, capsys: pytest.CaptureFixture[str]) -> None:
    sky.check.response = "not a dict"
    assert infra.enabled_infra() == []
    assert "failed" in capsys.readouterr().out


def test_check_all_marks_disabled_clouds_false(sky: FakeSky) -> None:
    sky.check.response = {}
    assert infra.check_all() == [CloudStatus(c, False) for c in infra.COMPUTE_CLOUDS]


def test_enabled_infra_filters_to_compute_clouds_order(sky: FakeSky) -> None:
    sky.check.response = {"default": {"gcp": [], "not-a-real-cloud": []}}
    assert infra.enabled_infra() == ["gcp"]
