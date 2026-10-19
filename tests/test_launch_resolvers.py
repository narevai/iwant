import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest
import requests

from iwant import launch as launch_mod
from iwant import registry, tui
from iwant.spinner import Spinner
from tests.fixtures import FakeSky, Http, JobStatus, LaunchCall, Prompts, forbidden


@dataclass
class LaunchCase:
    monkeypatch: pytest.MonkeyPatch
    recipes: Path
    sky: FakeSky
    prompts: Prompts
    http: Http
    spinners: list[Spinner] = field(default_factory=list)
    sleeps: list[float] = field(default_factory=list)

    def run(
        self,
        model: Optional[str] = "modelA",
        *,
        interactive: bool = False,
        idle_minutes: Optional[int] = None,
        autostop_given: bool = False,
        dry_run: bool = False,
        infra: Optional[str] = None,
        use_spot: bool = False,
    ) -> int:
        self.monkeypatch.setattr(sys.stdin, "isatty", lambda: interactive)
        return launch_mod.launch(
            model,
            idle_minutes=idle_minutes,
            autostop_given=autostop_given,
            dry_run=dry_run,
            yes=not interactive,
            infra=infra,
            api_key="test-key",
            use_spot=use_spot,
        )

    @property
    def submission(self) -> LaunchCall:
        assert len(self.sky.launch_calls) == 1
        return self.sky.launch_calls[0]


@pytest.fixture
def launch_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LaunchCase:
    recipes = tmp_path / "recipes"
    model = recipes / "modelA"
    model.mkdir(parents=True)
    _ = (model / "v1.yaml").write_text("resources: {}\n")
    monkeypatch.setattr(registry, "RECIPES_DIR", recipes)
    sky = FakeSky()
    sky.check.response = {"default": {"gcp": [], "aws": []}}
    sky.endpoint_result = {8000: "1.2.3.4:8000"}
    prompts = Prompts()
    http = Http()
    case = LaunchCase(monkeypatch, recipes, sky, prompts, http)

    def spinner(message: str) -> Spinner:
        instance = Spinner(message)
        case.spinners.append(instance)
        return instance

    def sleep(seconds: float) -> None:
        case.sleeps.append(seconds)

    monkeypatch.setitem(sys.modules, "sky", sky)
    monkeypatch.setattr(tui, "pick_model", prompts.pick_model)
    monkeypatch.setattr(tui, "pick_infra", prompts.pick_infra)
    monkeypatch.setattr(tui, "pick_spot", prompts.pick_spot)
    monkeypatch.setattr(tui, "pick_autostop", prompts.pick_autostop)
    monkeypatch.setattr(tui, "pick_dry_run", prompts.pick_dry_run)
    monkeypatch.setattr(launch_mod, "Spinner", spinner)
    monkeypatch.setattr(requests, "get", http.get)
    monkeypatch.setattr(time, "sleep", sleep)
    return case


def test_progress_no_job_id_skips_log_lookup(launch_case: LaunchCase) -> None:
    launch_case.sky.job_id = None
    assert launch_case.run() == 0
    assert launch_case.sky.log_calls == []


def test_progress_displays_last_log_segment(launch_case: LaunchCase) -> None:
    launch_case.sky.logs = ["line one\n", "line two\n"]
    assert launch_case.run() == 0
    assert launch_case.spinners[-1].message.startswith("line two (")


def test_progress_splits_carriage_return_progress_bars(launch_case: LaunchCase) -> None:
    launch_case.sky.logs = ["Capturing: 1%\rCapturing: 50%\rCapturing: 99%"]
    assert launch_case.run() == 0
    assert launch_case.spinners[-1].message.startswith("Capturing: 99% (")


def test_progress_truncates_long_lines(launch_case: LaunchCase) -> None:
    launch_case.sky.logs = ["x" * 200]
    assert launch_case.run() == 0
    assert launch_case.spinners[-1].message.startswith("x" * 97 + "... (")


def test_progress_log_exception_does_not_abort_launch(launch_case: LaunchCase) -> None:
    launch_case.sky.logs_error = RuntimeError("boom")
    assert launch_case.run() == 0
    assert launch_case.spinners[-1].message.startswith("Waiting for the server to respond...")


def test_progress_empty_log_uses_waiting_message(launch_case: LaunchCase) -> None:
    launch_case.sky.logs = ["", None, "  \n"]
    assert launch_case.run() == 0
    assert launch_case.spinners[-1].message.startswith("Waiting for the server to respond...")


def test_autostop_explicit_value_skips_picker(launch_case: LaunchCase) -> None:
    assert launch_case.run(interactive=True, idle_minutes=45) == 0
    assert launch_case.submission.idle_minutes == 45
    assert "autostop" not in launch_case.prompts.calls


def test_no_autostop_flag_skips_picker(launch_case: LaunchCase) -> None:
    assert launch_case.run(interactive=True, autostop_given=True) == 0
    assert launch_case.submission.idle_minutes is None
    assert launch_case.submission.down is False
    assert "autostop" not in launch_case.prompts.calls


def test_autostop_non_interactive_defaults(launch_case: LaunchCase) -> None:
    assert launch_case.run() == 0
    assert launch_case.submission.idle_minutes == launch_mod.DEFAULT_IDLE_MINUTES
    assert launch_case.submission.down is True
    assert launch_case.prompts.calls == []


def test_autostop_picker_disables_autostop(launch_case: LaunchCase) -> None:
    launch_case.prompts.autostop = -1
    assert launch_case.run(interactive=True) == 0
    assert launch_case.submission.idle_minutes is None
    assert launch_case.submission.down is False


def test_autostop_picker_value_is_submitted(launch_case: LaunchCase) -> None:
    launch_case.prompts.autostop = 90
    assert launch_case.run(interactive=True) == 0
    assert launch_case.submission.idle_minutes == 90


def test_autostop_picker_cancel_prevents_submission(launch_case: LaunchCase) -> None:
    launch_case.prompts.autostop = None
    assert launch_case.run(interactive=True) == 1
    assert launch_case.sky.launch_calls == []


def test_model_explicit_skips_picker(launch_case: LaunchCase) -> None:
    assert launch_case.run(interactive=True) == 0
    assert launch_case.submission.task.recipe.envs.IWANT_RECIPE == "modelA@v1"
    assert "model" not in launch_case.prompts.calls


def test_model_missing_non_interactive_fails(
    launch_case: LaunchCase, capsys: pytest.CaptureFixture[str]
) -> None:
    assert launch_case.run(model=None) == 1
    assert "No model given" in capsys.readouterr().out
    assert launch_case.sky.launch_calls == []


def test_model_missing_recipes_fails(launch_case: LaunchCase, capsys: pytest.CaptureFixture[str]) -> None:
    (launch_case.recipes / "modelA" / "v1.yaml").unlink()
    assert launch_case.run(model=None, interactive=True) == 1
    assert "No model configs found" in capsys.readouterr().out
    assert launch_case.sky.launch_calls == []


def test_model_picker_selection_is_submitted(launch_case: LaunchCase) -> None:
    assert launch_case.run(model=None, interactive=True) == 0
    assert "model" in launch_case.prompts.calls
    assert launch_case.submission.task.recipe.envs.IWANT_RECIPE == "modelA@v1"


def test_model_picker_cancel_prevents_submission(launch_case: LaunchCase) -> None:
    launch_case.prompts.model = None
    assert launch_case.run(model=None, interactive=True) == 1
    assert launch_case.sky.launch_calls == []


def test_infra_explicit_skips_picker(launch_case: LaunchCase) -> None:
    assert launch_case.run(interactive=True, infra="aws") == 0
    assert launch_case.submission.task.recipe.resources.infra == "aws"
    assert "infra" not in launch_case.prompts.calls


def test_infra_non_interactive_uses_recipe(launch_case: LaunchCase) -> None:
    _ = (launch_case.recipes / "modelA" / "v1.yaml").write_text("resources: {infra: gcp}\n")
    assert launch_case.run() == 0
    assert launch_case.submission.task.recipe.resources.infra == "gcp"
    assert "infra" not in launch_case.prompts.calls


def test_infra_unconfigured_prevents_submission(
    launch_case: LaunchCase, capsys: pytest.CaptureFixture[str]
) -> None:
    launch_case.sky.check.response = {}
    assert launch_case.run(interactive=True) == 1
    assert "No cloud is set up" in capsys.readouterr().out
    assert launch_case.sky.launch_calls == []


def test_infra_picker_selection_is_submitted(launch_case: LaunchCase) -> None:
    # Only GCP is currently enabled by iwant, even if the SDK reports more clouds.
    assert launch_case.run(interactive=True) == 0
    assert launch_case.submission.task.recipe.resources.infra == "gcp"
    assert "infra" in launch_case.prompts.calls


def test_infra_picker_cancel_prevents_submission(launch_case: LaunchCase) -> None:
    launch_case.prompts.infra = None
    assert launch_case.run(interactive=True) == 1
    assert launch_case.sky.launch_calls == []


def test_dry_run_explicit_skips_picker(launch_case: LaunchCase) -> None:
    assert launch_case.run(interactive=True, dry_run=True) == 0
    assert launch_case.submission.dry_run is True
    assert launch_case.sky.stream_calls == 0
    assert launch_case.sky.endpoint_calls == []
    assert "dry_run" not in launch_case.prompts.calls


def test_dry_run_non_interactive_defaults_to_launch(launch_case: LaunchCase) -> None:
    assert launch_case.run() == 0
    assert launch_case.submission.dry_run is False


def test_dry_run_picker_selection_is_submitted(launch_case: LaunchCase) -> None:
    launch_case.prompts.dry_run = True
    assert launch_case.run(interactive=True) == 0
    assert launch_case.submission.dry_run is True
    assert launch_case.sky.stream_calls == 0


def test_dry_run_picker_cancel_prevents_submission(launch_case: LaunchCase) -> None:
    launch_case.prompts.dry_run = None
    assert launch_case.run(interactive=True) == 1
    assert launch_case.sky.launch_calls == []


def test_spot_explicit_skips_picker(launch_case: LaunchCase) -> None:
    assert launch_case.run(interactive=True, use_spot=True) == 0
    assert launch_case.submission.task.recipe.resources.use_spot is True
    assert "spot" not in launch_case.prompts.calls


def test_spot_non_interactive_defaults(launch_case: LaunchCase) -> None:
    assert launch_case.run() == 0
    assert launch_case.submission.task.recipe.resources.use_spot is None


def test_spot_picker_selection_is_submitted(launch_case: LaunchCase) -> None:
    launch_case.prompts.spot = True
    assert launch_case.run(interactive=True) == 0
    assert launch_case.submission.task.recipe.resources.use_spot is True


def test_spot_picker_cancel_prevents_submission(launch_case: LaunchCase) -> None:
    launch_case.prompts.spot = None
    assert launch_case.run(interactive=True) == 1
    assert launch_case.sky.launch_calls == []


def test_running_job_keeps_polling(launch_case: LaunchCase) -> None:
    launch_case.http.failures = 1
    assert launch_case.run() == 0
    assert len(launch_case.sky.job_calls) == 1
    assert launch_case.http.calls == 2
    assert launch_case.sleeps == [launch_mod.HEALTH_CHECK_INTERVAL]


def test_failed_job_stops_polling(launch_case: LaunchCase, capsys: pytest.CaptureFixture[str]) -> None:
    launch_case.sky.job_state = JobStatus.FAILED
    launch_case.http.failures = 1
    assert launch_case.run() == 1
    assert "server job ended (FAILED)" in capsys.readouterr().out
    assert launch_case.http.calls == 1
    assert launch_case.sleeps == []


def test_no_job_id_skips_status_lookup(launch_case: LaunchCase) -> None:
    launch_case.sky.job_id = None
    launch_case.http.failures = 1
    assert launch_case.run() == 0
    assert launch_case.sky.job_calls == []


def test_job_status_exception_does_not_abort_polling(launch_case: LaunchCase) -> None:
    launch_case.sky.job_error = RuntimeError("boom")
    launch_case.http.failures = 1
    assert launch_case.run() == 0
    assert len(launch_case.sky.job_calls) == 1


def test_failed_job_does_not_sleep(launch_case: LaunchCase, monkeypatch: pytest.MonkeyPatch) -> None:
    launch_case.sky.job_state = JobStatus.FAILED
    launch_case.http.failures = 1
    monkeypatch.setattr(time, "sleep", forbidden)
    assert launch_case.run() == 1


def test_launch_failure_stops_before_endpoint_lookup(
    launch_case: LaunchCase, capsys: pytest.CaptureFixture[str]
) -> None:
    launch_case.sky.stream_error = RuntimeError("quota exceeded")
    assert launch_case.run() == 1
    assert "quota exceeded" in capsys.readouterr().out
    assert launch_case.sky.endpoint_calls == []
