# DeepSeek-V4.1-Flash — working notes

Source: official [vllm-project/recipes](https://github.com/vllm-project/recipes),
file [`models/deepseek-ai/DeepSeek-V4.1-Flash.yaml`](https://github.com/vllm-project/recipes/blob/main/models/deepseek-ai/DeepSeek-V4.1-Flash.yaml).

## Model facts

- Vision-language MoE, 552B backbone + 196B Engram memory. Checkpoint ~511GB
  on disk. `vram_minimum_gb: 614` - fits 8x H200 (1128GB) comfortably.
- `min_vllm_version: 0.30.0` hasn't shipped a pip wheel yet - Docker only
  (`vllm/vllm-openai:nightly`).

## Why TP8, not the documented TP4

The source recipe's H200 config is **TP4 run as two independent replicas**
on one 8-GPU node (for aggregate throughput). GCP's H200 shape
(`a3-ultragpu-8g`) is a fixed 8-GPU node - there's no smaller H200 SKU to
request - and `iwant` launches exactly one server per recipe, not two. A
single TP4 replica would leave 4 of the 8 paid-for GPUs sitting idle, so
this recipe scales that one replica up to TP8 across the whole node instead.
**Untested at TP8 specifically** - don't "fix" this back to TP4, it would
just waste half the node.

## Troubleshooting cookbook

Empty so far - fill in only real recipe-vs-reality mismatches that block a
launch (not operator error, not leftover state from a different recipe).
