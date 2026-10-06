"""Local fixtures for recordings; never imported by the installed iwant CLI."""

import ast
import json
import os
import re
import sys
import textwrap
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

import questionary
import requests
import yaml

from iwant import cli, launch, registry, sky_wrap, tui

DEMO_KEY = "a6ed31c540fb85d279ca06b83d97f204e6518bc72a4f093d"

# Recording presentation only; the installed CLI's output is unchanged.
COLORS = {"cyan": "#89dceb", "green": "#a6e3a1", "purple": "#cba6f7", "muted": "#9399b2"}


def color(text, name):
    value = COLORS[name].lstrip("#")
    red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return f"\033[38;2;{red};{green};{blue}m{text}\033[0m"


class RecordingOutput:
    """Accent CLI output and fit wide status rows into the square recording."""

    def __init__(self, stream):
        self.stream = stream

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def write(self, text):
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
        elif text.startswith("{'recipe':"):
            plan = ast.literal_eval(text)
            resources = plan["resources"]
            text = (
                "\033[2J\033[H"
                + color("Launch plan", "purple")
                + "\n\n"
                + color(
                    f"Recipe: {plan['recipe']}\nGPU: {resources['accelerators']}\n"
                    f"Cloud: {resources['infra']}\nIdle teardown: {plan['idle_minutes']}m",
                    "cyan",
                )
            )
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
        return self.stream.write(text)


def style_prompts():
    select = questionary.select
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

    def wrapped_select(message, choices, **kwargs):
        wrapped = []
        for choice in choices:
            if isinstance(choice, str):
                choice = questionary.Choice(title=textwrap.fill(choice, width=28), value=choice)
            else:
                choice.title = textwrap.fill(choice.title, width=28)
            wrapped.append(choice)
        return select(textwrap.fill(message, width=28), wrapped, **kwargs, style=style)

    tui.questionary = SimpleNamespace(Choice=questionary.Choice, select=wrapped_select)


class Simulator:
    def __init__(self, state_path: Path, scene: str, delay: float):
        self.state_path = state_path
        self.scene = scene
        self.delay = delay
        self.health_checks = 0
        if not state_path.exists():
            seeded = [self.row("gpt-oss-20b")]
            if scene == "list":
                seeded.append(self.row("deepseek-v4.1-flash"))
            self.save(seeded if scene in {"list", "ssh", "down"} else [])

    def pause(self):
        time.sleep(self.delay)

    def save(self, rows):
        self.state_path.write_text(json.dumps(rows))

    def rows(self):
        return json.loads(self.state_path.read_text())

    @staticmethod
    def cluster_name(model, version):
        return f"iwant-{model}-v{version}-a1b2c3"

    def row(self, model, task=None, idle_minutes=30):
        path, version = registry.resolve_task_yaml(model)
        data = task or yaml.safe_load(path.read_text())
        return {
            "name": self.cluster_name(model, version),
            "cloud": "GCP",
            "region": "us-central1",
            "resources_str": str(data["resources"]["accelerators"]),
            "status": "UP",
            "autostop": idle_minutes,
            "to_down": idle_minutes is not None,
            "launched_at": 0,
        }

    def submit(self, task, cluster_name, idle_minutes_to_autostop, down, dryrun):
        self.pause()
        if dryrun:
            return {
                "recipe": task["envs"]["IWANT_RECIPE"],
                "resources": task["resources"],
                "idle_minutes": idle_minutes_to_autostop,
            }
        model = task["envs"]["IWANT_RECIPE"].split("@")[0]
        rows = [r for r in self.rows() if r["name"] != cluster_name]
        rows.append(self.row(model, task, idle_minutes_to_autostop))
        self.save(rows)
        return 1, cluster_name

    def stream(self, result):
        row = next(r for r in self.rows() if r["name"] == result[1])
        for line in (
            f"Provisioning {row['resources_str']} on GCP...",
            "Preparing vLLM and downloading model weights...",
            "Starting the OpenAI-compatible server...",
        ):
            print(line, flush=True)
            self.pause()
        return result

    def check(self, **kwargs):
        self.pause()
        return {"demo": {} if self.scene == "auth-unconfigured" else {"gcp": []}}

    def status(self):
        self.pause()
        return self.rows()

    def endpoints(self, cluster, port):
        self.pause()
        return {port: "192.0.2.10:8000"}

    def down(self, cluster):
        self.pause()
        self.save([r for r in self.rows() if r["name"] != cluster])

    def health(self, url, **kwargs):
        if url != "http://192.0.2.10:8000/v1/models":
            raise AssertionError(f"Unexpected demo health URL: {url}")
        self.health_checks += 1
        return SimpleNamespace(status_code=200 if self.health_checks >= 3 else 503)

    def logs(self, *args, **kwargs):
        lines = ["Loading model weights...", "Warming up vLLM...", "Server ready."]
        return [lines[min(self.health_checks, 2)]]

    def ssh(self, cluster):
        print(f"Connected to {cluster}.")
        print("vscode@gpu:~$ echo $IWANT_RECIPE")
        print(
            cluster.removeprefix("iwant-").rsplit("-v", 1)[0]
            + "@v"
            + cluster.rsplit("-v", 1)[1].split("-")[0]
        )
        print("vscode@gpu:~$ exit")
        self.pause()
        print("Connection closed.")
        return 0


def install(state_path, scene="up", delay=0.6, patcher=None):
    """Install fixtures before Click starts its SkyPilot prefetch thread."""
    simulation = Simulator(Path(state_path), scene, delay)
    sky = ModuleType("sky")
    sky.Task = SimpleNamespace(from_yaml=lambda path: yaml.safe_load(Path(path).read_text()))
    sky.launch = simulation.submit
    sky.get = lambda result: result
    sky.stream_and_get = simulation.stream
    sky.check = SimpleNamespace(check=simulation.check)
    sky.status = simulation.status
    sky.endpoints = simulation.endpoints
    sky.down = simulation.down
    sky.tail_logs = simulation.logs
    sky.job_status = lambda *args, **kwargs: {1: "RUNNING"}
    if patcher:
        patcher.setitem(sys.modules, "sky", sky)
        replace = patcher.setattr
    else:
        sys.modules["sky"] = sky
        replace = setattr
    replace(cli, "ensure_cloud_env", lambda: None)
    replace(cli, "_prefetch_sky", lambda: None)
    replace(launch, "new_cluster_name", simulation.cluster_name)
    replace(launch, "secrets", SimpleNamespace(token_hex=lambda size: DEMO_KEY))
    replace(
        launch, "requests", SimpleNamespace(get=simulation.health, RequestException=requests.RequestException)
    )
    replace(launch, "HEALTH_CHECK_INTERVAL", delay)
    replace(sky_wrap, "ssh", simulation.ssh)
    return simulation


def main():
    state = os.environ.get("IWANT_DEMO_STATE")
    if not state:
        raise SystemExit("Use demo/render.sh to run the isolated recording environment.")
    install(state, scene=os.environ.get("IWANT_DEMO_SCENE", "up"))
    # Do not copy a user's Hugging Face token into even temporary demo recipes.
    os.environ.pop("HF_TOKEN", None)
    original_questionary = tui.questionary
    style_prompts()
    original_stdout = sys.stdout
    if sys.stdout.isatty():
        sys.stdout = RecordingOutput(sys.stdout)
    title = "iwant  ·  one command"
    print(color(title, "purple") if sys.stdout.isatty() else title)
    print()
    try:
        cli.main(prog_name="iwant")
    finally:
        sys.stdout = original_stdout
        tui.questionary = original_questionary


if __name__ == "__main__":
    main()
