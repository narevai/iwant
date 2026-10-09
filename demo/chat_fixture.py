"""Loopback-only chat fixture for the quickstart recording; never runs a model."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import cast

from demo.simulator import DEMO_KEY

ANSWER = "Silicon hums low\nA thousand threads wake at once\nNight turns into dawn"


def completion(body: object, state_path: Path) -> tuple[int, dict[str, object]]:
    if not isinstance(body, dict):
        return 400, {"error": "Use the GPT OSS 20B demo model"}
    request = cast(Mapping[str, object], body)
    if request.get("model") != "openai/gpt-oss-20b":
        return 400, {"error": "Use the GPT OSS 20B demo model"}
    if request.get("messages") != [{"role": "user", "content": "Write a haiku about GPUs."}]:
        return 400, {"error": "This fixture only answers the recorded demo prompt"}
    rows: object = json.loads(state_path.read_text()) if state_path.exists() else []
    if not isinstance(rows, list) or not any(
        isinstance(row, dict)
        and str(cast(Mapping[str, object], row).get("name", "")).startswith("iwant-gpt-oss-20b-")
        for row in cast(list[object], rows)
    ):
        return 503, {"error": "Launch the demo cluster first"}
    return 200, {
        "object": "chat.completion",
        "model": "openai/gpt-oss-20b",
        "choices": [{"message": {"role": "assistant", "content": ANSWER}, "finish_reason": "stop"}],
    }


def main() -> None:
    state_path, url_path = map(Path, sys.argv[1:])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            if self.path != "/v1/chat/completions":
                status, payload = 404, {"error": "Unknown fixture route"}
            elif self.headers.get("Authorization") != f"Bearer {DEMO_KEY}":
                status, payload = 401, {"error": "Use the demo API key"}
            else:
                try:
                    body: object = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                    status, payload = completion(body, state_path)
                except (ValueError, OSError):
                    status, payload = 400, {"error": "Invalid fixture request"}
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        url_path.write_text(f"http://127.0.0.1:{server.server_port}/v1")
        server.serve_forever()


if __name__ == "__main__":
    main()
