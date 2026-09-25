import os
import sys
from unittest.mock import MagicMock

import yaml

from iwant import launch as launch_mod

# --- _tail_progress_line ---


def test_tail_progress_line_no_job_id_skips_sky_entirely():
    assert launch_mod._tail_progress_line("cluster", None) is None


def test_tail_progress_line_returns_last_segment(monkeypatch):
    fake_sky = MagicMock()
    fake_sky.tail_logs.return_value = iter(["line one\n", "line two\n"])
    monkeypatch.setitem(sys.modules, "sky", fake_sky)
    assert launch_mod._tail_progress_line("cluster", 1) == "line two"


def test_tail_progress_line_splits_on_carriage_return_progress_bars(monkeypatch):
    fake_sky = MagicMock()
    fake_sky.tail_logs.return_value = iter(["Capturing: 1%\rCapturing: 50%\rCapturing: 99%"])
    monkeypatch.setitem(sys.modules, "sky", fake_sky)
    assert launch_mod._tail_progress_line("cluster", 1) == "Capturing: 99%"


def test_tail_progress_line_truncates_long_lines(monkeypatch):
    fake_sky = MagicMock()
    fake_sky.tail_logs.return_value = iter(["x" * 200])
    monkeypatch.setitem(sys.modules, "sky", fake_sky)
    result = launch_mod._tail_progress_line("cluster", 1)
    assert len(result) == 100
    assert result.endswith("...")


def test_tail_progress_line_none_on_exception(monkeypatch):
    fake_sky = MagicMock()
    fake_sky.tail_logs.side_effect = RuntimeError("boom")
    monkeypatch.setitem(sys.modules, "sky", fake_sky)
    assert launch_mod._tail_progress_line("cluster", 1) is None


def test_tail_progress_line_none_on_empty_log(monkeypatch):
    fake_sky = MagicMock()
    fake_sky.tail_logs.return_value = iter(["", None, "  \n"])
    monkeypatch.setitem(sys.modules, "sky", fake_sky)
    assert launch_mod._tail_progress_line("cluster", 1) is None


# --- _resolve_autostop ---


def test_resolve_autostop_explicit_value_wins(monkeypatch):
    monkeypatch.setattr(launch_mod.tui, "pick_autostop", lambda: (_ for _ in ()).throw(AssertionError))
    assert launch_mod._resolve_autostop(45, False, True) == 45


def test_resolve_autostop_no_autostop_flag_wins(monkeypatch):
    monkeypatch.setattr(launch_mod.tui, "pick_autostop", lambda: (_ for _ in ()).throw(AssertionError))
    assert launch_mod._resolve_autostop(None, True, True) is None


def test_resolve_autostop_non_interactive_defaults():
    assert launch_mod._resolve_autostop(None, False, False) == launch_mod.DEFAULT_IDLE_MINUTES


def test_resolve_autostop_picker_disable_maps_to_none(monkeypatch):
    monkeypatch.setattr(launch_mod.tui, "pick_autostop", lambda: -1)
    assert launch_mod._resolve_autostop(None, False, True) is None


def test_resolve_autostop_picker_value(monkeypatch):
    monkeypatch.setattr(launch_mod.tui, "pick_autostop", lambda: 90)
    assert launch_mod._resolve_autostop(None, False, True) == 90


def test_resolve_autostop_picker_cancel(monkeypatch):
    monkeypatch.setattr(launch_mod.tui, "pick_autostop", lambda: None)
    assert launch_mod._resolve_autostop(None, False, True) is launch_mod._CANCELLED


# --- _resolve_model ---


def test_resolve_model_explicit():
    assert launch_mod._resolve_model("gpt-oss-20b", True) == "gpt-oss-20b"


def test_resolve_model_non_interactive_no_model():
    assert launch_mod._resolve_model(None, False) is launch_mod._CANCELLED


def test_resolve_model_no_configs(monkeypatch):
    monkeypatch.setattr(launch_mod, "list_models", lambda: [])
    assert launch_mod._resolve_model(None, True) is launch_mod._CANCELLED


def test_resolve_model_picker(monkeypatch):
    monkeypatch.setattr(launch_mod, "list_models", lambda: ["a", "b"])
    monkeypatch.setattr(launch_mod.tui, "pick_model", lambda models: "b")
    assert launch_mod._resolve_model(None, True) == "b"


def test_resolve_model_picker_cancel(monkeypatch):
    monkeypatch.setattr(launch_mod, "list_models", lambda: ["a"])
    monkeypatch.setattr(launch_mod.tui, "pick_model", lambda models: None)
    assert launch_mod._resolve_model(None, True) is launch_mod._CANCELLED


# --- _resolve_infra ---


def test_resolve_infra_explicit():
    assert launch_mod._resolve_infra("gcp", True) == "gcp"


def test_resolve_infra_non_interactive_falls_back_to_none():
    assert launch_mod._resolve_infra(None, False) is None


def test_resolve_infra_no_enabled_cancels(monkeypatch):
    monkeypatch.setattr(launch_mod.infra_mod, "enabled_infra", lambda: [])
    assert launch_mod._resolve_infra(None, True) is launch_mod._CANCELLED


def test_resolve_infra_picker(monkeypatch):
    monkeypatch.setattr(launch_mod.infra_mod, "enabled_infra", lambda: ["gcp", "aws"])
    monkeypatch.setattr(launch_mod.tui, "pick_infra", lambda clouds: "aws")
    assert launch_mod._resolve_infra(None, True) == "aws"


def test_resolve_infra_picker_cancel(monkeypatch):
    monkeypatch.setattr(launch_mod.infra_mod, "enabled_infra", lambda: ["gcp"])
    monkeypatch.setattr(launch_mod.tui, "pick_infra", lambda clouds: None)
    assert launch_mod._resolve_infra(None, True) is launch_mod._CANCELLED


# --- _resolve_dry_run ---


def test_resolve_dry_run_explicit_true_skips_picker(monkeypatch):
    monkeypatch.setattr(launch_mod.tui, "pick_dry_run", lambda: (_ for _ in ()).throw(AssertionError))
    assert launch_mod._resolve_dry_run(True, True) is True


def test_resolve_dry_run_non_interactive():
    assert launch_mod._resolve_dry_run(False, False) is False


def test_resolve_dry_run_picker(monkeypatch):
    monkeypatch.setattr(launch_mod.tui, "pick_dry_run", lambda: True)
    assert launch_mod._resolve_dry_run(False, True) is True


def test_resolve_dry_run_picker_cancel(monkeypatch):
    monkeypatch.setattr(launch_mod.tui, "pick_dry_run", lambda: None)
    assert launch_mod._resolve_dry_run(False, True) is launch_mod._CANCELLED


# --- _resolve_spot ---


def test_resolve_spot_explicit_true_skips_picker(monkeypatch):
    monkeypatch.setattr(launch_mod.tui, "pick_spot", lambda: (_ for _ in ()).throw(AssertionError))
    assert launch_mod._resolve_spot(True, True) is True


def test_resolve_spot_non_interactive():
    assert launch_mod._resolve_spot(False, False) is False


def test_resolve_spot_picker(monkeypatch):
    monkeypatch.setattr(launch_mod.tui, "pick_spot", lambda: True)
    assert launch_mod._resolve_spot(False, True) is True


def test_resolve_spot_picker_cancel(monkeypatch):
    monkeypatch.setattr(launch_mod.tui, "pick_spot", lambda: None)
    assert launch_mod._resolve_spot(False, True) is launch_mod._CANCELLED


# --- _materialize_task_yaml ---


def test_materialize_task_yaml_no_overrides_returns_source(tmp_path):
    src = tmp_path / "server.yaml"
    src.write_text("resources:\n  infra: gcp\n")
    result = launch_mod._materialize_task_yaml(src, infra=None, api_key=None, use_spot=False)
    assert result == str(src)


def test_materialize_task_yaml_overrides_infra_and_key(tmp_path):
    src = tmp_path / "server.yaml"
    src.write_text("resources:\n  infra: gcp\nenvs:\n  VLLM_API_KEY: placeholder\n")

    result_path = launch_mod._materialize_task_yaml(src, infra="aws", api_key="secret123", use_spot=False)
    try:
        assert result_path != str(src)
        with open(result_path) as f:
            data = yaml.safe_load(f)
        assert data["resources"]["infra"] == "aws"
        assert data["envs"]["VLLM_API_KEY"] == "secret123"
        assert "use_spot" not in data["resources"]
        # the source recipe itself must stay untouched
        assert "secret123" not in src.read_text()
    finally:
        os.unlink(result_path)


def test_materialize_task_yaml_overrides_use_spot(tmp_path):
    src = tmp_path / "server.yaml"
    src.write_text("resources:\n  infra: gcp\n")

    result_path = launch_mod._materialize_task_yaml(src, infra=None, api_key=None, use_spot=True)
    try:
        assert result_path != str(src)
        with open(result_path) as f:
            data = yaml.safe_load(f)
        assert data["resources"]["use_spot"] is True
    finally:
        os.unlink(result_path)


def test_materialize_task_yaml_sets_recipe_env(tmp_path):
    src = tmp_path / "v2.yaml"
    src.write_text("resources:\n  infra: gcp\n")

    result_path = launch_mod._materialize_task_yaml(
        src, infra=None, api_key=None, use_spot=False, recipe="modelA@v2"
    )
    try:
        assert result_path != str(src)
        with open(result_path) as f:
            data = yaml.safe_load(f)
        assert data["envs"]["IWANT_RECIPE"] == "modelA@v2"
    finally:
        os.unlink(result_path)


# --- _job_terminal_status / _wait_until_healthy ---


def _fake_job_status(monkeypatch, value):
    fake_sky = MagicMock()
    status = MagicMock()
    status.value = value
    fake_sky.job_status.return_value = {1: status}
    monkeypatch.setitem(sys.modules, "sky", fake_sky)
    fake_sky.get.side_effect = lambda v: v
    return fake_sky


def test_job_terminal_status_running_is_none(monkeypatch):
    _fake_job_status(monkeypatch, "RUNNING")
    assert launch_mod._job_terminal_status("cluster", 1) is None


def test_job_terminal_status_failed(monkeypatch):
    _fake_job_status(monkeypatch, "FAILED")
    assert launch_mod._job_terminal_status("cluster", 1) == "FAILED"


def test_job_terminal_status_no_job_id():
    assert launch_mod._job_terminal_status("cluster", None) is None


def test_job_terminal_status_none_on_exception(monkeypatch):
    fake_sky = MagicMock()
    fake_sky.job_status.side_effect = RuntimeError("boom")
    monkeypatch.setitem(sys.modules, "sky", fake_sky)
    assert launch_mod._job_terminal_status("cluster", 1) is None


def test_wait_until_healthy_stops_when_job_failed(monkeypatch):
    monkeypatch.setattr(launch_mod, "_tail_progress_line", lambda c, j: None)
    monkeypatch.setattr(launch_mod, "_job_terminal_status", lambda c, j: "FAILED")
    monkeypatch.setattr(
        launch_mod.requests, "get", MagicMock(side_effect=launch_mod.requests.ConnectionError())
    )
    monkeypatch.setattr(launch_mod.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError))

    healthy, _, job_status = launch_mod._wait_until_healthy("1.2.3.4:8000", "k", MagicMock(), "cluster", 1)
    assert healthy is False
    assert job_status == "FAILED"


# --- _run_launch ---


def test_run_launch_stops_on_launch_failure(monkeypatch):
    fake_sky = MagicMock()
    fake_sky.stream_and_get.side_effect = RuntimeError("quota exceeded")
    monkeypatch.setitem(sys.modules, "sky", fake_sky)
    endpoint = MagicMock()
    monkeypatch.setattr(launch_mod.sky_wrap, "endpoint", endpoint)

    code = launch_mod._run_launch(MagicMock(), "iwant-a-v1-abc123", 30, False, False, "k", False, "a@v1")
    assert code == 1
    endpoint.assert_not_called()
