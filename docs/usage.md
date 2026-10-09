# Launch options and recipes

Omit the model or cluster argument for an interactive picker. For scripts, pass
`--yes` with a model and exact cluster names from `iwant list`.

```bash
# Choose a region and skip prompts.
iwant up gpt-oss-20b --infra gcp/us-central1 --yes

# Use spot capacity, which can be reclaimed at any time.
iwant up gpt-oss-20b --spot

# Authenticate model downloads; gated models also require granted access.
HF_TOKEN=hf_xxx iwant up gpt-oss-20b

# Set the cluster idle teardown timer, or disable it.
iwant up gpt-oss-20b --idle-minutes 60
iwant up gpt-oss-20b --no-autostop

# Hide streamed setup logs and print the final result.
iwant up gpt-oss-20b --quiet
```

Use `--api-key` to supply your own server key, or let iwant generate one.
Run `iwant up --help` for the complete option list.


## Recipe versions

`iwant up MODEL` selects the highest `v<N>.yaml` in `iwant/recipes/MODEL/`.
Published files stay unchanged; updates go into the next version. Launch output
records a label such as `step-3.7-flash@v2`. The CLI accepts `step-3.7-flash`,
not the version label. Dependencies follow the pins, ranges, or image tags in
the recipe; a recipe version does not freeze all upstream packages.

## Billing and teardown

Cloud resources bill in your account until removed. Ctrl+C detaches from the
launch; it does not cancel the remote job. Check `iwant list` after an interrupted
or failed launch, then use `iwant down EXACT_CLUSTER_NAME` when done.

The default teardown setting is 30 minutes of cluster idleness. The timer tracks
job activity, not API requests. A running server keeps the cluster active, so
explicitly tear it down when finished. `--idle-minutes N` changes the timer;
`--no-autostop` disables it.

## Other models

Use the URL and key printed by your launch. Find the served model ID with:

```bash
curl "$OPENAI_BASE_URL/models" -H "Authorization: Bearer $OPENAI_API_KEY"
```

Use that ID with `/chat/completions` or your OpenAI-compatible client.
