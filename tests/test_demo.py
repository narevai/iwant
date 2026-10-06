"""Exercise real CLI behavior with the recording fixtures and forbid external I/O."""

import io
import os
import re
import socket
import subprocess
import sys

import pytest
import requests
import yaml
from click.testing import CliRunner

from demo import simulator
from iwant import cli, registry


@pytest.fixture
def demo(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("The recording attempted external I/O")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "call", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(requests, "get", forbidden)

    def setup(scene="up"):
        return simulator.install(tmp_path / "state.json", scene, delay=0, patcher=monkeypatch)

    return setup


@pytest.mark.parametrize("model", registry.list_models())
def test_demo_launch_uses_real_recipe_and_cli(model, demo):
    fixture = demo()
    result = CliRunner().invoke(cli.main, ["up", model, "--yes", "--infra", "gcp"])
    assert result.exit_code == 0, result.output
    path, version = registry.resolve_task_yaml(model)
    resources = yaml.safe_load(path.read_text())["resources"]
    assert f"Recipe:  {model}@v{version}" in result.output
    assert "Server:  http://192.0.2.10:8000/v1" in result.output
    assert f"API key: {simulator.DEMO_KEY}" in result.output
    assert str(resources["accelerators"]) in result.output
    assert fixture.rows()[0]["autostop"] == 30
    assert fixture.health_checks == 3
    assert sys.modules["sky"].launch == fixture.submit


def test_demo_dry_run_does_not_create_cluster(demo):
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
def test_demo_auth(scene, expected, demo):
    demo(scene)
    result = CliRunner().invoke(cli.main, ["auth"])
    assert result.exit_code == 0, result.output
    assert expected in result.output


def test_demo_list_shows_real_table_with_fixture_endpoints(demo):
    fixture = demo("list")
    result = CliRunner().invoke(cli.main, ["list"])
    assert result.exit_code == 0, result.output
    assert "AUTOSTOP" in result.output
    assert "30m (down)" in result.output
    assert "http://192.0.2.10:8000/v1" in result.output
    assert len(fixture.rows()) == 2
    for row in fixture.rows():
        assert row["name"] in result.output


def test_demo_ssh_is_simulated(demo):
    fixture = demo("ssh")
    result = CliRunner().invoke(cli.main, ["ssh", fixture.rows()[0]["name"]])
    assert result.exit_code == 0, result.output
    assert "Connected to" in result.output
    assert "gpt-oss-20b@v1" in result.output
    assert "Connection closed" in result.output


def test_demo_down_persists_between_commands(demo):
    fixture = demo("down")
    cluster = fixture.rows()[0]["name"]
    result = CliRunner().invoke(cli.main, ["down", cluster])
    assert result.exit_code == 0, result.output
    assert f"Torn down {cluster}" in result.output
    # A second process opens the same session state without reseeding it.
    simulator.Simulator(fixture.state_path, "down", delay=0)
    result = CliRunner().invoke(cli.main, ["list"])
    assert result.exit_code == 0, result.output
    assert "No clusters found." in result.output


def test_demo_entrypoint_requires_isolated_environment(monkeypatch):
    monkeypatch.delenv("IWANT_DEMO_STATE", raising=False)
    with pytest.raises(SystemExit, match="demo/render.sh"):
        simulator.main()


def test_demo_entrypoint_hides_scaffolding_and_clears_hf_token(demo, monkeypatch, capsys):
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


def test_recording_status_preserves_details_in_readable_lines(demo):
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
        assert row["name"] in output
        assert row["resources_str"] in output
    assert "http://192.0.2.10:8000/v1" in output
    assert "Idle teardown: 30m (down)" in output
    assert max(map(len, output.splitlines())) <= 72


def test_recording_launch_keeps_endpoint_and_recipe_on_result_screen(demo):
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
