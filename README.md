<div align="center">

<img src="docs/assets/banner.gif" alt="iwant up — animated command cycling through the available model recipes" width="960">

## Your next model is one command away.

Launch an open model on a cloud GPU. Get an OpenAI-compatible endpoint,<br>
an API key, and SSH access — all in your own cloud account.

[![CI](https://github.com/narevai/iwant/actions/workflows/ci.yml/badge.svg)](https://github.com/narevai/iwant/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

[Try it](#try-gpt-oss-20b) · [Models](#models) · [Commands](#commands) · [More demos](demo/README.md)

</div>

```bash
iwant up
```

Choose a model. iwant rents the GPU, sets up the server, and waits until the API
responds. Point your OpenAI-compatible app at the resulting URL and start sending
prompts.

<p align="center">
  <img src="demo/functionality/quickstart.gif" alt="Launch GPT OSS 20B, send a prompt with curl, receive a haiku, and tear down the cluster" width="800">
</p>

*Workflow demo: real CLI and curl, simulated cloud operations, a fixed sample answer,
and shortened waits. It is not a live inference recording or a startup benchmark.*

## Try GPT OSS 20B

One L4 GPU, one model, one prompt. You'll need the `gcloud` CLI and a GCP project
with billing enabled, L4 quota, and available capacity. GCP is currently the
supported cloud.

### 1. Install and connect

```bash
curl -fsSL https://raw.githubusercontent.com/narevai/iwant/main/install.sh | bash

gcloud config set project YOUR_PROJECT_ID
gcloud auth login
gcloud auth application-default login
iwant auth
```

<details>
<summary>Install location, telemetry, and installing from source</summary>

The installer puts iwant in `~/.iwant` and the command in `~/.local/bin`.
If your shell cannot find `iwant`, add `~/.local/bin` to `PATH`.
It sends an anonymous install event with OS, CPU architecture, and success/failure.
To opt out:

```bash
curl -fsSL https://raw.githubusercontent.com/narevai/iwant/main/install.sh -o /tmp/iwant-install.sh
IWANT_NO_TELEMETRY=1 bash /tmp/iwant-install.sh
```

From source, with Python 3.10+:

```bash
git clone https://github.com/narevai/iwant.git
cd iwant
pip install -e .
```

</details>

### 2. Preview, then launch

```bash
# Inspect the plan without renting a GPU.
iwant up gpt-oss-20b --infra gcp --dry-run --yes

# Launch on-demand capacity.
iwant up gpt-oss-20b --infra gcp --yes
```

Save the **Server** URL and **API key** printed during launch. iwant checks that
the models API responds before reporting the server ready. Provisioning, weight
downloads, and model loading take time; the GIF's timing is illustrative.

**Done experimenting? Run `iwant down`.** Resources bill in your account until
removed. Ctrl+C detaches from the launch; it does not stop the remote server.
The default 30-minute idle timer tracks cluster jobs, so a running server keeps
it active even when there are no API requests.

### 3. Ask it something

Paste your launch's URL and key below. This request prints just the answer:

```bash
export OPENAI_BASE_URL="http://<IP>:8000/v1"
export OPENAI_API_KEY="<generated-key>"

curl -fsS "$OPENAI_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-oss-20b","messages":[{"role":"user","content":"Write a haiku about GPUs."}],"max_tokens":256}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"])'
```

Your answer will vary. For an app, use the same base URL, API key, and model ID
in its OpenAI-compatible client settings.

### 4. Remove the GPU

```bash
iwant down              # pick your cluster interactively
iwant list              # confirm it is gone
```

For scripts, use `iwant down EXACT_CLUSTER_NAME` with the name from `iwant list`.

## Models

The GPU requests below come directly from the latest repository recipes.

| Model argument | GPUs | Recipe | Configuration evidence |
| --- | --- | --- | --- |
| `gpt-oss-20b` | 1 × L4 | [v1](iwant/recipes/gpt-oss-20b/v1.yaml) | First-run example; no verification report committed |
| `deepseek-v4-flash` | 8 × H100 | [v1](iwant/recipes/deepseek-v4-flash/v1.yaml) | Recipe records a working launch; about 24 min to ready |
| `deepseek-v4.1-flash` | 8 × H200 | [v2](iwant/recipes/deepseek-v4.1-flash/v2.yaml) | [Experimental TP8 configuration](iwant/recipes/deepseek-v4.1-flash/NOTES.md) |
| `mimo-v2.6-flash` | 8 × H200 | [v2](iwant/recipes/mimo-v2.6-flash/v2.yaml) | [Experimental TP8 configuration](iwant/recipes/mimo-v2.6-flash/NOTES.md) |
| `ling-3.0-flash-fp8` | 8 × H200 | [v1](iwant/recipes/ling-3.0-flash-fp8/v1.yaml) | [Chat response verified on TP8 + EP8](iwant/recipes/ling-3.0-flash-fp8/NOTES.md#verified) |
| `step-3.7-flash` | 8 × H200 | [v2](iwant/recipes/step-3.7-flash/v2.yaml) | [Matches upstream verified hardware/config](iwant/recipes/step-3.7-flash/NOTES.md) |
| `step-3.7-flash-optimized` | 8 × H200 | [v2](iwant/recipes/step-3.7-flash-optimized/v2.yaml) | [Throughput tuning and benchmark notes](iwant/recipes/step-3.7-flash-optimized/NOTES.md) |

Evidence describes what is recorded in this repository, rather than a guarantee
for every launch. The DeepSeek timing is an undated recipe note, not a current
benchmark. Hourly cost depends on region and spot/on-demand capacity; inspect the
launch plan and your cloud pricing before provisioning.

Recipes hold model IDs, machine requirements, setup steps, and serving flags.
`iwant up MODEL` uses the latest recipe and prints its version.
[Recipe versions and launch options →](docs/usage.md)

## Commands

| Command | What it does |
| --- | --- |
| `iwant up [MODEL]` | Launch a model; omit the name for an interactive picker |
| `iwant down [CLUSTER]` | Tear down a cluster; omit the name to pick one |
| `iwant auth` | Check cloud credentials and show login guidance |
| `iwant list [CLUSTER]` | Show deployments and endpoints |
| `iwant ssh [CLUSTER]` | Open SSH to a running cluster |

Preview with `--dry-run`, skip prompts with `--yes`, choose spot capacity with
`--spot`, or pass `HF_TOKEN` for authenticated model downloads.
Run `iwant up --help` for all options.

[Advanced usage](docs/usage.md) · [Development](docs/development.md) ·
[Demo gallery and GIF generation](demo/README.md)
