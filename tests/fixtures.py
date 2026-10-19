"""Typed, in-memory SDK and prompt doubles; no cloud or network operations."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from types import ModuleType
from typing import ClassVar, Generic, NoReturn, Optional, TypeVar, Union

import requests

from iwant.recipe import Recipe
from iwant.records import ClusterRecord

T = TypeVar("T")
CloudResponse = dict[str, dict[str, list[str]]]


def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
    raise AssertionError("Unexpected operation")


@dataclass(frozen=True)
class Request(Generic[T]):
    result: T


@dataclass(frozen=True)
class Task:
    recipe: Recipe

    @classmethod
    def from_yaml(cls, path: str) -> Task:
        return cls(Recipe.from_yaml(path))


@dataclass(frozen=True)
class LaunchCall:
    task: Task
    cluster_name: str
    idle_minutes: Optional[int]
    down: bool
    dry_run: bool


class JobStatus(Enum):
    RUNNING = "RUNNING"
    FAILED = "FAILED"


@dataclass
class CloudCheck:
    response: Union[CloudResponse, str] = field(default_factory=dict)
    error: Optional[Exception] = None
    calls: list[tuple[list[str], bool]] = field(default_factory=list)

    def check(self, *, clouds: list[str], quiet: bool) -> Union[CloudResponse, str]:
        self.calls.append((clouds, quiet))
        if self.error is not None:
            raise self.error
        return self.response


class FakeSky(ModuleType):
    Task: ClassVar[type[Task]] = Task

    def __init__(self) -> None:
        super().__init__("sky")
        self.check: CloudCheck = CloudCheck()
        self.rows: list[ClusterRecord] = []
        self.status_error: Optional[Exception] = None
        self.endpoint_result: dict[int, str] = {}
        self.endpoint_calls: list[tuple[str, int]] = []
        self.logs: list[Optional[str]] = []
        self.logs_error: Optional[Exception] = None
        self.log_calls: list[tuple[str, int, bool, int, bool]] = []
        self.job_state: Optional[JobStatus] = JobStatus.RUNNING
        self.job_error: Optional[Exception] = None
        self.job_calls: list[tuple[str, list[int]]] = []
        self.job_id: Optional[int] = 1
        self.launch_error: Optional[Exception] = None
        self.stream_error: Optional[Exception] = None
        self.launch_calls: list[LaunchCall] = []
        self.stream_calls: int = 0

    def get(self, request: Request[T]) -> T:
        return request.result

    def status(self) -> Request[list[ClusterRecord]]:
        if self.status_error is not None:
            raise self.status_error
        return Request(self.rows)

    def endpoints(self, cluster: str, *, port: int) -> Request[dict[int, str]]:
        self.endpoint_calls.append((cluster, port))
        return Request(self.endpoint_result)

    def tail_logs(
        self, cluster: str, job_id: int, *, follow: bool, tail: int, preload_content: bool
    ) -> Iterator[Optional[str]]:
        self.log_calls.append((cluster, job_id, follow, tail, preload_content))
        if self.logs_error is not None:
            raise self.logs_error
        return iter(self.logs)

    def job_status(self, cluster: str, *, job_ids: list[int]) -> Request[dict[int, Optional[JobStatus]]]:
        self.job_calls.append((cluster, job_ids))
        if self.job_error is not None:
            raise self.job_error
        return Request({job_id: self.job_state for job_id in job_ids})

    def launch(
        self,
        task: Task,
        *,
        cluster_name: str,
        idle_minutes_to_autostop: Optional[int],
        down: bool,
        dryrun: bool,
    ) -> Request[tuple[Optional[int], str]]:
        self.launch_calls.append(LaunchCall(task, cluster_name, idle_minutes_to_autostop, down, dryrun))
        if self.launch_error is not None:
            raise self.launch_error
        return Request((self.job_id, "test-handle"))

    def stream_and_get(self, request: Request[tuple[Optional[int], str]]) -> tuple[Optional[int], str]:
        self.stream_calls += 1
        if self.stream_error is not None:
            raise self.stream_error
        return request.result


@dataclass
class Prompts:
    model: Optional[str] = "modelA"
    infra: Optional[str] = "gcp"
    spot: Optional[bool] = False
    autostop: Optional[int] = 30
    dry_run: Optional[bool] = False
    calls: list[str] = field(default_factory=list)

    def pick_model(self, models: list[str]) -> Optional[str]:
        self.calls.append("model")
        assert self.model is None or self.model in models
        return self.model

    def pick_infra(self, clouds: list[str]) -> Optional[str]:
        self.calls.append("infra")
        assert self.infra is None or self.infra in clouds
        return self.infra

    def pick_spot(self) -> Optional[bool]:
        self.calls.append("spot")
        return self.spot

    def pick_autostop(self) -> Optional[int]:
        self.calls.append("autostop")
        return self.autostop

    def pick_dry_run(self) -> Optional[bool]:
        self.calls.append("dry_run")
        return self.dry_run


@dataclass
class Http:
    failures: int = 0
    calls: int = 0
    urls: list[str] = field(default_factory=list)
    auth_headers: list[dict[str, str]] = field(default_factory=list)

    def get(self, url: str, *, headers: dict[str, str], timeout: int) -> requests.Response:
        self.calls += 1
        self.urls.append(url)
        self.auth_headers.append(headers)
        assert timeout == 5
        if self.failures > 0:
            self.failures -= 1
            raise requests.ConnectionError("Server is not ready")
        response = requests.Response()
        response.status_code = 200
        return response
