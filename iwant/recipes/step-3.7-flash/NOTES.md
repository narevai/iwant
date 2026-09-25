# Step-3.7-Flash (StepFun) — working notes

Source: official [vllm-project/recipes](https://github.com/vllm-project/recipes),
file [`models/stepfun-ai/Step-3.7-Flash.yaml`](https://github.com/vllm-project/recipes/blob/main/models/stepfun-ai/Step-3.7-Flash.yaml).

## Model facts

- Vision-language MoE, 198B total / 11B active, 256k context, 3-way MTP.
- BF16 checkpoint ~376GB on disk. Recipe's own verified config: BF16, TP8+EP
  on 8x H200 - exactly this hardware, no extrapolation needed.
- `min_vllm_version` hasn't shipped a stable release yet - needs the
  dedicated `vllm/vllm-openai:stepfun37` image (pinned, not `:nightly`).
- Use `step3p7-flash` as the model name in requests (`--served-model-name`
  in the recipe), not the full `stepfun-ai/Step-3.7-Flash` HF id.
