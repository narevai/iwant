# Ling-3.0-flash (inclusionAI/Ant Group) — working notes

Source: official [vllm-project/recipes](https://github.com/vllm-project/recipes),
file [`models/inclusionAI/Ling-3.0-flash.yaml`](https://github.com/vllm-project/recipes/blob/main/models/inclusionAI/Ling-3.0-flash.yaml).

## Model facts

- MoE, 124.4B total / 5.5B active, hybrid MLA/KDA attention, native MTP head.
  262,144 context.
- `min_vllm_version: 0.28.0` - already shipped, plain `uv pip install vllm`
  works, no Docker/nightly needed.
- Recipe's own FP8 config is TP2 (or TP4+EP4 on H200).

## Why TP8+EP8, not the documented TP2/TP4

GCP's H200 shape (`a3-ultragpu-8g`) is a fixed 8-GPU node - there's no
smaller H200 SKU to request. Running the recipe's own TP2 or TP4+EP4 would
leave 6 or 4 of the 8 paid-for GPUs sitting idle, so this recipe uses TP8+EP8
across the whole node instead. **Untested at TP8 specifically** - don't
"fix" this back to TP2/TP4, it would just waste most of the node.


## Verified

8x H200, TP8+EP8, FP8. `system_fingerprint` containing `-tp8-ep-` confirms
the configuration. `curl .../v1/chat/completions` with `"model":
"inclusionAI/Ling-3.0-flash-fp8"` returns correct answers with reasoning.
