"""Typed local fixtures for recordings; never loaded by the installed CLI."""

from __future__ import annotations

import json
import os
import re
import sys
import textwrap
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import redirect_stdout
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Literal, Protocol, TypeVar, cast

import questionary
import requests

from demo.records import DemoRequest, DemoTask, HealthResponse, LaunchPlan, LaunchResult
from iwant import cli, launch, registry, sky_wrap, tui
from iwant.records import CloudStatus, ClusterRecord

if TYPE_CHECKING:
    from pytest import MonkeyPatch

DEMO_KEY = "a6ed31c540fb85d279ca06b83d97f204e6518bc72a4f093d"

# Recording presentation only; the installed CLI's output is unchanged.
ColorName = Literal["cyan", "green", "purple", "muted"]
COLORS: Mapping[ColorName, str] = {
    "cyan": "#89dceb",
    "green": "#a6e3a1",
    "purple": "#cba6f7",
    "muted": "#9399b2",
}


def color(text: str, name: ColorName) -> str:
    value = COLORS[name].lstrip("#")
    red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return f"\033[38;2;{red};{green};{blue}m{text}\033[0m"


class TextStream(Protocol):
    def write(self, text: str, /) -> int: ...
    def flush(self) -> None: ...
    def isatty(self) -> bool: ...
    def fileno(self) -> int: ...

    @property
    def encoding(self) -> str | None: ...


class RecordingOutput:
    """Accent CLI output and fit wide status rows into the square recording."""

    def __init__(self, stream: TextStream) -> None:
        self.stream = stream

    def flush(self) -> None:
        self.stream.flush()

    def isatty(self) -> bool:
        return self.stream.isatty()

    def fileno(self) -> int:
        return self.stream.fileno()

    @property
    def encoding(self) -> str:
        return self.stream.encoding or "utf-8"

    def write(self, text: str) -> int:
        original_length = len(text)
        if text.startswith("Server started"):
            text = "\033[2J\033[H" + color("✓ Model ready", "green") + "\n"
        elif text.startswith("API key"):
            text = color("API key", "purple") + "\n" + color(DEMO_KEY[:8] + "…" + DEMO_KEY[-8:], "cyan")
        elif text.startswith("SSH:"):
            return len(text)
        elif text.startswith(("Server:", "Recipe:", "Pricing:")):
            label, value = text.split(":", 1)
            label = "Endpoint" if label == "Server" else label
            text = color(label, "purple") + "\n" + color(value.strip().removesuffix(" (latest)"), "cyan")
        elif text.startswith(("Launch submitted", "Job ", "Test:")):
            return len(text)
        elif text.startswith("Launch plan\n"):
            title, details = text.split("\n\n", 1)
            text = "\033[2J\033[H" + color(title, "purple") + "\n\n" + color(details, "cyan")
        elif text.startswith("NAME") and "AUTOSTOP" in text:
            text = color("Active deployments", "purple")
        elif text.startswith("iwant-") and "  " in text:
            fields = re.split(r" {2,}", text.strip())
            if len(fields) == 7:
                name, infra, resources, status, endpoint, autostop, _ = fields
                text = (
                    color(name, "purple")
                    + "\n  "
                    + color(textwrap.fill(f"{infra}  ·  {resources}  ·  {status}", width=32), "green")
                    + "\n  "
                    + color(endpoint, "cyan")
                    + "\n  "
                    + color(f"Idle teardown: {autostop}", "muted")
                    + "\n"
                )
        elif text.startswith("Torn down"):
            text = color("✓ Cluster removed", "green")
        elif text.startswith("gcp: already"):
            text = color("✓ GCP is ready", "green")
        elif text.startswith("No clusters"):
            text = color(text, "green")
        elif text.startswith(("Recipe:", "SSH:", "Pricing:", "Test:", "Dry run plan:")):
            text = color(text, "purple")
        elif text.startswith(("Server:", "API key", "Provisioning", "Preparing", "Starting", "Connected")):
            text = color(textwrap.fill(text, width=32), "cyan")
        elif text.startswith(("Launch submitted", "Job ", "Connection closed")):
            text = color(text, "muted")
        self.stream.write(text)
        return original_length


def style_prompts() -> tui.SelectPrompt:
    original_select = tui.select_prompt
    style = questionary.Style(
        [
            ("qmark", "fg:#89dceb bold"),
            ("question", "fg:#cdd6f4 bold"),
            ("answer", "fg:#a6e3a1 bold"),
            ("pointer", "fg:#89dceb bold"),
            ("highlighted", "fg:#89dceb bold"),
            ("selected", "fg:#a6e3a1"),
            ("instruction", "fg:#9399b2"),
        ]
    )

    def wrapped_select(
        message: str, choices: Sequence[tui.SelectChoice], default: tui.SelectDefault = None
    ) -> questionary.Question:
        wrapped: list[questionary.Choice] = []
        for choice in choices:
            if isinstance(choice, str):
                choice = questionary.Choice(title=textwrap.fill(choice, width=28), value=choice)
            else:
                if not isinstance(choice.title, str):
                    raise TypeError("Recording choices must have plain text titles")
                choice.title = textwrap.fill(choice.title, width=28)
            wrapped.append(choice)
        return questionary.select(textwrap.fill(message, width=28), wrapped, default=default, style=style)

    tui.select_prompt = wrapped_select
    return original_select


class Simulator:
    def __init__(self, state_path: Path, scene: str, delay: float) -> None:
        self.state_path = state_path
        self.scene = scene
        self.delay = delay
        self.health_checks = 0
        if not state_path.exists():
            seeded = [self.row("gpt-oss-20b")]
            if scene == "list":
                seeded.append(self.row("deepseek-v4.1-flash"))
            self.save(seeded if scene in {"list", "ssh", "down"} else [])

    def pause(self) -> None:
        time.sleep(self.delay)

    def save(self, rows: Sequence[ClusterRecord]) -> None:
        # JSON dictionaries are serialization only; callers exchange records.
        self.state_path.write_text(json.dumps([asdict(row) for row in rows]))

    def rows(self) -> list[ClusterRecord]:
        data: object = json.loads(self.state_path.read_text())
        if not isinstance(data, list):
            raise ValueError("Expected a list of cluster records in demo state")
        return [ClusterRecord.from_sdk(row) for row in cast(list[object], data)]

    @staticmethod
    def cluster_name(model: str, version: int) -> str:
        return f"iwant-{model}-v{version}-a1b2c3"

    def row(self, model: str, task: DemoTask | None = None, idle_minutes: int | None = 30) -> ClusterRecord:
        path, version = registry.resolve_task_yaml(model)
        task = task or DemoTask.from_yaml(path)
        return ClusterRecord(
            name=self.cluster_name(model, version),
            status="UP",
            cloud="GCP",
            region="us-central1",
            resources_str=task.resources.accelerators,
            autostop=idle_minutes,
            to_down=idle_minutes is not None,
            launched_at=0,
        )

    def submit(
        self,
        task: DemoTask,
        cluster_name: str,
        idle_minutes_to_autostop: int | None,
        down: bool,
        dryrun: bool,
    ) -> DemoRequest[LaunchPlan | LaunchResult]:
        self.pause()
        if dryrun:
            return DemoRequest(LaunchPlan(task.recipe, task.resources, idle_minutes_to_autostop))
        model = task.recipe.split("@")[0]
        rows = [row for row in self.rows() if row.name != cluster_name]
        rows.append(self.row(model, task, idle_minutes_to_autostop))
        self.save(rows)
        return DemoRequest(LaunchResult(1, cluster_name))

    def stream(self, result: LaunchResult) -> LaunchResult:
        row = next(row for row in self.rows() if row.name == result.cluster_name)
        for line in (
            f"Provisioning {row.resources_str} on GCP...",
            "Preparing vLLM and downloading model weights...",
            "Starting the OpenAI-compatible server...",
        ):
            print(line, flush=True)
            self.pause()
        return result

    def check(self) -> list[CloudStatus]:
        self.pause()
        return [CloudStatus("gcp", self.scene != "auth-unconfigured")]

    def status(self) -> list[ClusterRecord]:
        self.pause()
        return self.rows()

    def endpoints(self, cluster: str, port: int) -> dict[int, str]:
        self.pause()
        return {port: "192.0.2.10:8000"}

    def down(self, cluster: str) -> None:
        self.pause()
        self.save([row for row in self.rows() if row.name != cluster])

    def health(self, url: str) -> HealthResponse:
        if url != "http://192.0.2.10:8000/v1/models":
            raise AssertionError(f"Unexpected demo health URL: {url}")
        self.health_checks += 1
        return HealthResponse(200 if self.health_checks >= 3 else 503)

    def logs(self) -> Iterator[str]:
        lines = ["Loading model weights...", "Warming up vLLM...", "Server ready."]
        return iter([lines[min(self.health_checks, 2)]])

    def ssh(self, cluster: str) -> int:
        print(f"Connected to {cluster}.")
        print("vscode@gpu:~$ echo $IWANT_RECIPE")
        model, version_suffix = cluster.removeprefix("iwant-").rsplit("-v", 1)
        print(f"{model}@v{version_suffix.split('-')[0]}")
        print("vscode@gpu:~$ exit")
        self.pause()
        print("Connection closed.")
        return 0


class DemoCloudCheck:
    def __init__(self, simulator: Simulator) -> None:
        self.simulator = simulator

    def check(self, clouds: Sequence[str], quiet: bool = True) -> dict[str, dict[str, list[str]]]:
        # Match SkyPilot's wire format only at its API boundary.
        return {"demo": {status.name: [] for status in self.simulator.check() if status.enabled}}


T = TypeVar("T")


class DemoSky(ModuleType):
    """Explicitly typed SkyPilot test adapter, installed only in recorder processes."""

    Task = DemoTask

    def __init__(self, simulator: Simulator) -> None:
        super().__init__("sky")
        self.simulator = simulator
        self.check = DemoCloudCheck(simulator)

    def launch(
        self,
        task: DemoTask,
        *,
        cluster_name: str,
        idle_minutes_to_autostop: int | None,
        down: bool,
        dryrun: bool,
    ) -> DemoRequest[LaunchPlan | LaunchResult]:
        return self.simulator.submit(task, cluster_name, idle_minutes_to_autostop, down, dryrun)

    def get(self, request: DemoRequest[T]) -> T:
        return request.result

    def stream_and_get(self, request: DemoRequest[LaunchPlan | LaunchResult]) -> LaunchResult:
        result = self.get(request)
        if not isinstance(result, LaunchResult):
            raise TypeError("Only a model launch can stream provisioning logs")
        return self.simulator.stream(result)

    def status(self) -> DemoRequest[list[ClusterRecord]]:
        return DemoRequest(self.simulator.status())

    def endpoints(self, cluster: str, port: int) -> DemoRequest[dict[int, str]]:
        return DemoRequest(self.simulator.endpoints(cluster, port))

    def down(self, cluster: str) -> DemoRequest[None]:
        return DemoRequest(self.simulator.down(cluster))

    def tail_logs(
        self, cluster: str, job_id: int, *, follow: bool, tail: int, preload_content: bool
    ) -> Iterator[str]:
        return self.simulator.logs()

    def job_status(self, cluster: str, job_ids: Sequence[int]) -> DemoRequest[dict[int, str]]:
        return DemoRequest({job_id: "RUNNING" for job_id in job_ids})


class DemoSecrets:
    @staticmethod
    def token_hex(nbytes: int | None = None) -> str:
        return DEMO_KEY


class DemoHttp:
    RequestException = requests.RequestException

    def __init__(self, simulator: Simulator) -> None:
        self.simulator = simulator

    def get(self, url: str, *, headers: Mapping[str, str], timeout: float) -> HealthResponse:
        return self.simulator.health(url)


def install(
    state_path: str | Path, scene: str = "up", delay: float = 0.6, patcher: MonkeyPatch | None = None
) -> Simulator:
    """Install fixtures before Click starts its SkyPilot prefetch thread."""
    simulation = Simulator(Path(state_path), scene, delay)
    sky = DemoSky(simulation)
    replace: Callable[[object, str, object], None]
    if patcher is not None:
        patcher.setitem(sys.modules, "sky", sky)
        replace = patcher.setattr
    else:
        sys.modules["sky"] = sky
        replace = setattr
    replace(cli, "ensure_cloud_env", lambda: None)
    replace(cli, "_prefetch_sky", lambda: None)
    replace(launch, "new_cluster_name", simulation.cluster_name)
    replace(launch, "secrets", DemoSecrets)
    replace(launch, "requests", DemoHttp(simulation))
    replace(launch, "HEALTH_CHECK_INTERVAL", delay)
    replace(sky_wrap, "ssh", simulation.ssh)
    return simulation


def main() -> None:
    state = os.environ.get("IWANT_DEMO_STATE")
    if not state:
        raise SystemExit("Use demo/render.sh to run the isolated recording environment.")
    install(state, scene=os.environ.get("IWANT_DEMO_SCENE", "up"))
    os.environ.pop("HF_TOKEN", None)
    original_select = style_prompts()
    output = RecordingOutput(sys.stdout) if sys.stdout.isatty() else sys.stdout
    try:
        with redirect_stdout(output):
            title = "iwant  ·  one command"
            print(color(title, "purple") if sys.stdout.isatty() else title)
            print()
            cli.main(prog_name="iwant")
    finally:
        tui.select_prompt = original_select


if __name__ == "__main__":
    main()
