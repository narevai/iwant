import io
import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import NoReturn, Protocol

import pytest
import requests
from click.testing import CliRunner

from demo import chat_fixture, simulator
from demo.records import DemoRequest, DemoTask, LaunchPlan, LaunchResult, Resources
from iwant import cli, registry
from iwant.records import ClusterRecord


class DemoFactory(Protocol):
    def __call__(self, scene: str = "up") -> simulator.Simulator: ...


@pytest.fixture
def demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DemoFactory:
    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("The recording attempted external I/O")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "call", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(requests, "get", forbidden)

    def setup(scene: str = "up") -> simulator.Simulator:
        return simulator.install(tmp_path / "state.json", scene, delay=0, patcher=monkeypatch)

    return setup


@pytest.mark.parametrize("model", registry.list_models())
def test_demo_launch_uses_real_recipe_and_cli(model: str, demo: DemoFactory) -> None:
    fixture = demo()
    result = CliRunner().invoke(cli.main, ["up", model, "--yes", "--infra", "gcp"])
    assert result.exit_code == 0, result.output
    path, version = registry.resolve_task_yaml(model)
    resources = DemoTask.from_yaml(path).resources
    assert f"Recipe:  {model}@v{version}" in result.output
    assert "Server:  http://192.0.2.10:8000/v1" in result.output
    assert f"API key: {simulator.DEMO_KEY}" in result.output
    assert resources.accelerators in result.output
    assert fixture.rows()[0].autostop == 30
    assert fixture.health_checks == 3
    sky = sys.modules["sky"]
    assert isinstance(sky, simulator.DemoSky)
    assert sky.simulator is fixture


def test_demo_dry_run_does_not_create_cluster(demo: DemoFactory) -> None:
    fixture = demo()
    result = CliRunner().invoke(cli.main, ["up", "gpt-oss-20b", "--dry-run", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Dry run plan:" in result.output
    assert "L4:1" in result.output
    assert "API key" not in result.output
    assert fixture.rows() == []
    assert fixture.health_checks == 0


@pytest.mark.parametrize(
    "scene,expected", [("auth", "gcp: enabled"), ("auth-unconfigured", "gcloud auth login")]
)
def test_demo_auth(scene: str, expected: str, demo: DemoFactory) -> None:
    demo(scene)
    result = CliRunner().invoke(cli.main, ["auth"])
    assert result.exit_code == 0, result.output
    assert expected in result.output


def test_demo_list_shows_real_table_with_fixture_endpoints(demo: DemoFactory) -> None:
    fixture = demo("list")
    result = CliRunner().invoke(cli.main, ["list"])
    assert result.exit_code == 0, result.output
    assert "AUTOSTOP" in result.output
    assert "30m (down)" in result.output
    assert "http://192.0.2.10:8000/v1" in result.output
    assert len(fixture.rows()) == 2
    for row in fixture.rows():
        assert row.name in result.output


def test_demo_ssh_is_simulated(demo: DemoFactory) -> None:
    fixture = demo("ssh")
    result = CliRunner().invoke(cli.main, ["ssh", fixture.rows()[0].name])
    assert result.exit_code == 0, result.output
    assert "Connected to" in result.output
    assert "gpt-oss-20b@v1" in result.output
    assert "Connection closed" in result.output


def test_demo_down_persists_between_commands(demo: DemoFactory) -> None:
    fixture = demo("down")
    cluster = fixture.rows()[0].name
    result = CliRunner().invoke(cli.main, ["down", cluster])
    assert result.exit_code == 0, result.output
    assert f"Torn down {cluster}" in result.output
    # A second process opens the same session state without reseeding it.
    simulator.Simulator(fixture.state_path, "down", delay=0)
    result = CliRunner().invoke(cli.main, ["list"])
    assert result.exit_code == 0, result.output
    assert "No clusters found." in result.output


def test_demo_entrypoint_requires_isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IWANT_DEMO_STATE", raising=False)
    with pytest.raises(SystemExit, match="demo/render.sh"):
        simulator.main()


def test_demo_entrypoint_hides_scaffolding_and_clears_hf_token(
    demo: DemoFactory, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = demo()
    monkeypatch.setenv("IWANT_DEMO_STATE", str(fixture.state_path))
    monkeypatch.setenv("HF_TOKEN", "private-test-token")
    monkeypatch.setattr(simulator, "install", lambda *args, **kwargs: fixture)
    monkeypatch.setattr(cli, "main", lambda **kwargs: None)
    simulator.main()
    output = capsys.readouterr().out
    assert "iwant" in output
    assert "Simulated" not in output
    assert "IWANT_DEMO" not in output
    assert "HF_TOKEN" not in os.environ


def test_recording_status_preserves_details_in_readable_lines(demo: DemoFactory) -> None:
    fixture = demo("list")
    result = CliRunner().invoke(cli.main, ["list"])
    stream = io.StringIO()
    styled = simulator.RecordingOutput(stream)
    for line in result.output.splitlines():
        styled.write(line)
        styled.write("\n")
    output = re.sub(r"\x1b\[[0-9;]*m", "", stream.getvalue())
    assert "Active deployments" in output
    for row in fixture.rows():
        assert row.name in output
        assert row.resources_str in output
    assert "http://192.0.2.10:8000/v1" in output
    assert "Idle teardown: 30m (down)" in output
    assert max(map(len, output.splitlines())) <= 72


def test_recording_launch_keeps_endpoint_and_recipe_on_result_screen(demo: DemoFactory) -> None:
    demo()
    result = CliRunner().invoke(cli.main, ["up", "step-3.7-flash-optimized", "--yes", "--infra", "gcp"])
    stream = io.StringIO()
    output = simulator.RecordingOutput(stream)
    for line in result.output.splitlines():
        output.write(line)
        output.write("\n")
    rendered = re.sub(r"\x1b\[[0-9;]*m", "", stream.getvalue()).split("\033[2J\033[H")[-1]
    assert "Model ready" in rendered
    assert "Endpoint\nhttp://192.0.2.10:8000/v1" in rendered
    assert "step-3.7-flash-optimized@v2" in rendered
    assert "Pricing\non-demand" in rendered
    assert simulator.DEMO_KEY not in rendered
    assert "Test:" not in rendered
    assert len(rendered.splitlines()) <= 18


def test_cluster_state_round_trip_preserves_typed_fields(demo: DemoFactory) -> None:
    fixture = demo()
    record = ClusterRecord(
        "iwant-gpt-oss-20b-v1-a1b2c3", "STOPPED", "L4:1", "GCP", "us-central1", 90, True, 1000.5
    )
    fixture.save([record])
    assert fixture.rows() == [record]


def test_demo_request_results_keep_their_domain_types(demo: DemoFactory) -> None:
    fixture = demo()
    task = DemoTask("gpt-oss-20b@v1", Resources("gcp", "L4:1"))
    request = fixture.submit(task, fixture.cluster_name("gpt-oss-20b", 1), 30, True, True)
    assert isinstance(request, DemoRequest)
    sky = simulator.DemoSky(fixture)
    plan = sky.get(request)
    assert isinstance(plan, LaunchPlan)
    assert plan.resources.accelerators == "L4:1"
    with pytest.raises(TypeError, match="Only a model launch"):
        sky.stream_and_get(request)
    launch_request = fixture.submit(task, fixture.cluster_name("gpt-oss-20b", 1), 30, True, False)
    launched = sky.stream_and_get(launch_request)
    assert isinstance(launched, LaunchResult)
    assert launched.cluster_name == fixture.cluster_name("gpt-oss-20b", 1)


def test_invalid_yaml_resource_type_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("envs: {}\nresources:\n  accelerators: [L4]\n")
    with pytest.raises(ValueError, match="Expected a string for accelerators"):
        DemoTask.from_yaml(path)


def test_output_write_reports_consumed_input_length() -> None:
    stream = io.StringIO()
    output = simulator.RecordingOutput(stream)
    text = "Server: http://192.0.2.10:8000/v1"
    assert output.write(text) == len(text)
    assert "Endpoint" in stream.getvalue()


def test_chat_fixture_requires_launch_and_stops_after_teardown(demo: DemoFactory) -> None:
    fixture = demo("quickstart")
    request = {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": "Write a haiku about GPUs."}],
    }
    assert chat_fixture.completion(request, fixture.state_path)[0] == 503
    runner = CliRunner()
    result = runner.invoke(cli.main, ["up", "gpt-oss-20b", "--yes", "--infra", "gcp"])
    assert result.exit_code == 0, result.output
    status, response = chat_fixture.completion(request, fixture.state_path)
    assert status == 200
    assert response["choices"] == [
        {"message": {"role": "assistant", "content": chat_fixture.ANSWER}, "finish_reason": "stop"}
    ]
    result = runner.invoke(cli.main, ["down", fixture.rows()[0].name])
    assert result.exit_code == 0, result.output
    assert chat_fixture.completion(request, fixture.state_path)[0] == 503


@pytest.mark.parametrize(
    "body",
    [None, {"model": "another-model"}, {"model": "openai/gpt-oss-20b", "messages": []}],
)
def test_chat_fixture_rejects_requests_outside_recorded_demo(body: object, demo: DemoFactory) -> None:
    fixture = demo("quickstart")
    assert chat_fixture.completion(body, fixture.state_path)[0] == 400
