import sys
from unittest.mock import MagicMock

from iwant import infra


def test_setup_hint_known_cloud():
    assert "gcloud" in infra.setup_hint("gcp")


def test_every_cloud_has_a_setup_hint():
    assert set(infra.SETUP_HINTS) == set(infra.COMPUTE_CLOUDS)


def test_compute_clouds_are_lowercase_and_unique():
    assert len(infra.COMPUTE_CLOUDS) == len(set(infra.COMPUTE_CLOUDS))
    assert all(c == c.lower() for c in infra.COMPUTE_CLOUDS)


def test_fetch_enabled_parses_check_result(monkeypatch):
    fake_sky = MagicMock()
    fake_sky.check.check.return_value = {"default": {"gcp": ["compute", "storage"]}}
    monkeypatch.setitem(sys.modules, "sky", fake_sky)

    assert infra._fetch_enabled() == {"gcp"}


def test_fetch_enabled_none_on_exception(monkeypatch):
    fake_sky = MagicMock()
    fake_sky.check.check.side_effect = RuntimeError("boom")
    monkeypatch.setitem(sys.modules, "sky", fake_sky)

    assert infra._fetch_enabled() is None


def test_fetch_enabled_none_on_unexpected_shape(monkeypatch):
    fake_sky = MagicMock()
    fake_sky.check.check.return_value = "not a dict"
    monkeypatch.setitem(sys.modules, "sky", fake_sky)

    assert infra._fetch_enabled() is None


def test_check_all_marks_disabled_clouds_false(monkeypatch):
    monkeypatch.setattr(infra, "_fetch_enabled", lambda: set())
    statuses = infra.check_all()
    assert statuses == {c: False for c in infra.COMPUTE_CLOUDS}


def test_enabled_infra_filters_to_compute_clouds_order(monkeypatch):
    monkeypatch.setattr(infra, "_fetch_enabled", lambda: {"gcp", "not-a-real-cloud"})
    assert infra.enabled_infra() == ["gcp"]
