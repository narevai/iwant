<div align="center">

<h1>iwant</h1>

Name a model, get an OpenAI-compatible endpoint on a cloud GPU.

<h3>

[Recipes](iwant/recipes) | [SkyPilot](https://docs.skypilot.co) | [vLLM](https://github.com/vllm-project/vllm)

</h3>

[![Unit Tests](https://github.com/narevai/iwant/actions/workflows/ci.yml/badge.svg)](https://github.com/narevai/iwant/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

</div>

---

One command rents a cloud GPU box, starts vLLM on it with a tested recipe, and gives you back an
OpenAI-compatible endpoint.

```console
$ iwant launch
? What do you want to launch? gpt-oss-20b
Recipe: gpt-oss-20b@v1 (latest)
? Where do you want to launch it? GCP
? On-demand or spot? On-demand (default, won't get reclaimed)
? Autostop after how long idle? 30 minutes (default)
? Ready to launch? Launch for real
...
Server:  http://<IP>:8000/v1
API key: <generated>
SSH:     ssh iwant-gpt-oss-20b-v1-a1b2c3
Recipe:  gpt-oss-20b@v1
```

Idle instances shut down after 30 minutes by default (`--idle-minutes N`, `--no-autostop`).

## Install

```bash
pip install -e .          # or: uv pip install -e .
gcloud auth login && gcloud auth application-default login
iwant setup               # which clouds are ready, and how to enable the rest
```

GPU quota (e.g. `NVIDIA_L4_GPUS`) usually has to be requested in the GCP Console first.

## Usage

```bash
iwant list                        # available models
iwant launch [MODEL]              # interactive if MODEL is omitted
iwant launch MODEL --dry-run      # show the plan, spend nothing
iwant launch MODEL --yes          # no prompts (scripts/CI)

iwant status [MODEL|CLUSTER]      # running instances
iwant ssh | endpoint | stop | down [CLUSTER]
```

## Recipes

Each model lives in `iwant/recipes/<model>/v<N>.yaml` and `launch` always takes the highest `N`.
Published versions are never edited: any change goes into `v<N+1>.yaml`, so `<model>@v<N>` always
points at the exact config a benchmark ran against.

## Development

```bash
pip install -e ".[dev]"
pytest && ruff check . && ruff format --check .
```

A devcontainer with `gcloud` preinstalled lives in `.devcontainer/`.
