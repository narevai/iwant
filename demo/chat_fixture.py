"""Loopback-only chat fixture for the quickstart recording; never runs a model."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar, Literal, Optional, TypedDict, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing_extensions import override

from demo.records import DemoState
from demo.simulator import DEMO_KEY

ANSWER = "Silicon hums low\nA thousand threads wake at once\nNight turns into dawn"


class RecordedMessage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, extra="forbid")

    role: Literal["user"]
    content: Literal["Write a haiku about GPUs."]


class RecordedChatRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, extra="forbid")

    model: Literal["openai/gpt-oss-20b"]
    messages: list[RecordedMessage] = Field(min_length=1, max_length=1)
    max_tokens: Optional[int] = Field(default=None, gt=0)


class ErrorResponse(TypedDict):
    error: str


class AssistantMessage(TypedDict):
    role: Literal["assistant"]
    content: str


class CompletionChoice(TypedDict):
    message: AssistantMessage
    finish_reason: Literal["stop"]


class CompletionResponse(TypedDict):
    object: Literal["chat.completion"]
    model: Literal["openai/gpt-oss-20b"]
    choices: list[CompletionChoice]


FixtureResponse = Union[ErrorResponse, CompletionResponse]


def completion(body: object, state_path: Path) -> tuple[int, FixtureResponse]:
    try:
        _ = RecordedChatRequest.model_validate(body)
    except ValidationError:
        return 400, {"error": "Use the GPT OSS 20B model and recorded demo prompt"}
    if not any(row.name.startswith("iwant-gpt-oss-20b-") for row in DemoState.read(state_path).root):
        return 503, {"error": "Launch the demo cluster first"}
    return 200, {
        "object": "chat.completion",
        "model": "openai/gpt-oss-20b",
        "choices": [{"message": {"role": "assistant", "content": ANSWER}, "finish_reason": "stop"}],
    }


def main() -> None:
    state_path, url_path = map(Path, sys.argv[1:])

    class Handler(BaseHTTPRequestHandler):
        @override
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            payload: FixtureResponse
            if self.path != "/v1/chat/completions":
                status, payload = 404, ErrorResponse(error="Unknown fixture route")
            elif self.headers.get("Authorization") != f"Bearer {DEMO_KEY}":
                status, payload = 401, ErrorResponse(error="Use the demo API key")
            else:
                try:
                    body = RecordedChatRequest.model_validate_json(
                        self.rfile.read(int(self.headers.get("Content-Length", "0")))
                    )
                    status, payload = completion(body, state_path)
                except (ValueError, OSError):
                    status, payload = 400, ErrorResponse(error="Invalid fixture request")
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            _ = self.wfile.write(data)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        _ = url_path.write_text(f"http://127.0.0.1:{server.server_port}/v1")
        server.serve_forever()


if __name__ == "__main__":
    main()
