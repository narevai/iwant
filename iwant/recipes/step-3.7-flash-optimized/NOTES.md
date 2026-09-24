# Step-3.7-Flash optimized — working notes

Throughput variant of `step-3.7-flash` (same BF16 checkpoint, same 8x H200,
same `vllm/vllm-openai:stepfun37` image). Official serve command is unchanged
in `step-3.7-flash`; this recipe only adds the flags that keep MTP-3 on the
CUDA-graph path at high concurrency.

## Why this exists

MTP-3 makes a uniform decode step 4 tokens per request (`1 +
num_speculative_tokens`). vLLM's Hopper default `max_cudagraph_capture_size`
is 512 tokens. `128 × 4 = 512` is the last graphed batch; 129+ goes eager
and output tok/s drops ~50%. A fry `step-standard-long` sweep (9-user steps)
measured that as 126 → 135 users: ~9,863 tok/s → ~4,804 tok/s. Waiting,
preemptions, and KV-cache (~3%) were all fine — it is not a capacity cliff.

`--max-cudagraph-capture-size 2048` and `--max-num-seqs 512` keep MTP graphed
through 512 concurrent requests (`512 × 4 = 2048`). No `--max-model-len`:
coding clients still get the 256k window. fry `--max-output-tokens` only
caps the load-test payload, not this server.

Tradeoff vs the official recipe: longer CUDA-graph capture at startup and
more graph memory. On 8x H200 that is the right trade for min cost/token.

If `stepfun37` rejects `--max-cudagraph-capture-size`, same meaning via
`--compilation-config '{"max_cudagraph_capture_size": 2048}'`.

## Troubleshooting cookbook

Empty so far - fill in only real recipe-vs-reality mismatches that block a
launch (not operator error, not leftover state from a different recipe).
