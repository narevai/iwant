#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
case "${1:-all}" in
  all) groups=(functionality models) ;;
  functionality|models) groups=("$1") ;;
  *) echo "Usage: bash demo/render.sh [functionality|models [clip]]" >&2; exit 2 ;;
esac
requested_clip="${2:-}"
if (($# > 2)) || [[ -n "$requested_clip" && "${1:-all}" == all ]]; then
  echo "Usage: bash demo/render.sh [functionality|models [clip]]" >&2; exit 2
fi
if [[ -n "$requested_clip" ]]; then
  if [[ ! "$requested_clip" =~ ^[a-z0-9][a-z0-9.-]*$ ]] || [[ ! -f "demo/${groups[0]}/$requested_clip.tape" ]]; then
    echo "Unknown demo: ${groups[0]}/$requested_clip" >&2; exit 2
  fi
fi

for tool in vhs ttyd ffmpeg ffprobe chromium python flock curl; do
  command -v "$tool" >/dev/null || { echo "Missing $tool; rebuild the devcontainer." >&2; exit 1; }
done
python -c 'import sys; assert sys.prefix == sys.base_prefix, "Use system Python"; import iwant, click, questionary, requests, yaml'

# GIF palette generation buffers frames; concurrent encoders exhaust small containers.
if [[ "${IWANT_DEMO_LOCK_HELD:-0}" != 1 ]]; then
  export IWANT_DEMO_LOCK_HELD=1
  # --close keeps browser helper processes from inheriting and retaining the lock.
  exec flock --nonblock --close "${TMPDIR:-/tmp}/iwant-vhs-render-$(id -u).lock" \
    bash "$repo_root/demo/render.sh" "$@"
fi

recording_tmp=$(mktemp -d)
fixture_pid=""
cleanup() {
  if [[ -n "$fixture_pid" ]]; then
    kill "$fixture_pid" 2>/dev/null || true
    wait "$fixture_pid" 2>/dev/null || true
  fi
  rm -rf "$recording_tmp"
}
trap cleanup EXIT
export IWANT_DEMO_PYTHON="$(command -v python)"
export IWANT_DEMO_ROOT="$repo_root"
cat > "$recording_tmp/iwant" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd "$IWANT_DEMO_ROOT"
exec "$IWANT_DEMO_PYTHON" -m demo.simulator "$@"
SH
chmod +x "$recording_tmp/iwant"
export PATH="$recording_tmp:$PATH"
# Chromium is detected from PATH by VHS. Disable its sandbox only in recordings.
export VHS_NO_SANDBOX=true

for group in "${groups[@]}"; do
  for tape in "demo/$group/"*.tape; do
    clip=$(basename "$tape" .tape)
    if [[ -n "$requested_clip" && "$clip" != "$requested_clip" ]]; then
      continue
    fi
    export IWANT_DEMO_SCENE="$clip"
    export IWANT_DEMO_STATE="$recording_tmp/state.json"
    rm -f "$IWANT_DEMO_STATE"
    if [[ "$clip" == quickstart ]]; then
      python -m demo.chat_fixture "$IWANT_DEMO_STATE" "$recording_tmp/chat-url" &
      fixture_pid=$!
      python - "$recording_tmp/chat-url" <<'PY'
import sys
import time
from pathlib import Path
url_path = Path(sys.argv[1])
for _ in range(100):
    if url_path.exists():
        break
    time.sleep(0.1)
else:
    raise SystemExit("Chat fixture failed to start")
PY
      export OPENAI_BASE_URL="$(cat "$recording_tmp/chat-url")"
      export OPENAI_API_KEY="$(python -c 'from demo.simulator import DEMO_KEY; print(DEMO_KEY)')"
    fi
    echo "Recording $group/$clip"
    # Render the video first. A two-pass GIF palette avoids buffering every
    # square frame in memory, which VHS's simultaneous GIF export would do.
    video="demo/$group/$clip.mp4"
    gif="demo/$group/$clip.gif"
    vhs "$tape"
    ffmpeg -v error -y -i "$video" -vf 'fps=20,palettegen=stats_mode=diff' \
      -frames:v 1 -threads 1 "$recording_tmp/palette.png"
    ffmpeg -v error -y -i "$video" -i "$recording_tmp/palette.png" \
      -filter_complex '[0:v]fps=20[video];[video][1:v]paletteuse=dither=bayer:bayer_scale=3' \
      -loop 0 "$gif"
    for extension in gif mp4; do
      output="demo/$group/$clip.$extension"
      [[ -s "$output" ]] || { echo "Missing output: $output" >&2; exit 1; }
      ffmpeg -v error -i "$output" -f null -
    done
    if [[ -n "$fixture_pid" ]]; then
      kill "$fixture_pid"
      wait "$fixture_pid" 2>/dev/null || true
      fixture_pid=""
      rm -f "$recording_tmp/chat-url"
      unset OPENAI_BASE_URL OPENAI_API_KEY
    fi
  done
done
