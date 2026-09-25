import sys
from unittest.mock import MagicMock

from iwant import sky_wrap


def _row(name, status="UP"):
    return {"name": name, "status": status, "resources_str": "1x GCP(L4:1)", "cloud": "gcp"}


def _fake_sky(monkeypatch, rows=None, error=None):
    fake_sky = MagicMock()
    if error:
        fake_sky.status.side_effect = error
    else:
        fake_sky.status.return_value = rows
    monkeypatch.setitem(sys.modules, "sky", fake_sky)
    fake_sky.get.side_effect = lambda v: v
    return fake_sky


def test_all_clusters_skips_non_iwant(monkeypatch):
    _fake_sky(monkeypatch, [_row("iwant-a-v1-abc123"), _row("someone-else")])
    assert [c["name"] for c in sky_wrap.all_clusters()] == ["iwant-a-v1-abc123"]


def test_all_clusters_none_on_failure(monkeypatch, capsys):
    _fake_sky(monkeypatch, error=RuntimeError("api server down"))
    assert sky_wrap.all_clusters() is None
    assert "api server down" in capsys.readouterr().out


def test_resolve_cluster_failure_does_not_claim_missing(monkeypatch, capsys):
    _fake_sky(monkeypatch, error=RuntimeError("api server down"))
    assert sky_wrap.resolve_cluster("iwant-a-v1-abc123") is None
    assert "No cluster named" not in capsys.readouterr().out


def test_status_filters_by_exact_cluster_name(monkeypatch, capsys):
    _fake_sky(monkeypatch, [_row("iwant-a-v1-aaaaaa"), _row("iwant-a-v1-bbbbbb")])
    assert sky_wrap.status("iwant-a-v1-bbbbbb") == 0
    out = capsys.readouterr().out
    assert "bbbbbb" in out
    assert "aaaaaa" not in out


def test_status_fails_on_sdk_error(monkeypatch):
    _fake_sky(monkeypatch, error=RuntimeError("boom"))
    assert sky_wrap.status() == 1
