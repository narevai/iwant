# MiMo-V2.6-Flash-RL (Xiaomi) — working notes

Source: official [vllm-project/recipes](https://github.com/vllm-project/recipes),
file [`models/XiaomiMiMo/MiMo-V2.6-Flash-RL.yaml`](https://github.com/vllm-project/recipes/blob/main/models/XiaomiMiMo/MiMo-V2.6-Flash-RL.yaml).

## Model facts

- Omnimodal MoE (text/image/video/audio), 309B total / 15B active, 1M context.
- Weights stored as mxfp4, computed as FP8 - only 173GB on disk.
- Stable vLLM (<=0.29.0) can't load the mxfp4 format - needs the dedicated
  `vllm/vllm-openai:mimo-v26` image.
- Recipe's own config is TP4 (`vram_minimum_gb: 208`, comfortably fits 4x H200).

## Why TP8, not the documented TP4

GCP's H200 shape (`a3-ultragpu-8g`) is a fixed 8-GPU node - there's no
smaller H200 SKU to request. Running the recipe's own TP4 would leave 4 of
the 8 paid-for GPUs sitting idle, so this recipe uses TP8 across the whole
node instead. **Untested at TP8 specifically** - don't "fix" this back to
TP4, it would just waste half the node.

## Adding DFlash speculative decoding later

Left out of the recipe because its `--speculative-config` needs a concrete
path to the checkpoint's `dflash/` subfolder, which only exists after the
checkpoint has already been downloaded once - it can't be a static flag on
first launch. To add it on a second launch of an instance whose local SSD
cache survived from a first run:
```bash
DFLASH_DIR=$(ls -d /mnt/localssd/huggingface/hub/models--XiaomiMiMo--MiMo-V2.6-Flash-RL/snapshots/*/dflash)
```
then splice `$DFLASH_DIR` into `--speculative-config
'{"method":"dflash","model":"<path>","num_speculative_tokens":7}'` in `run:`.
