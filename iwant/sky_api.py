"""Consumed SDK signatures, checked against SkyPilot at each call boundary.

SkyPilot exposes check dynamically and launch has an unrelated unparameterized
Backend argument. These protocols describe the arguments iwant actually uses,
while retaining the SDK's native request and result types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sky import Task
    from sky.backends import ResourceHandle
    from sky.server.common import RequestId


class CloudCheckApi(Protocol):
    def check(self, *, clouds: list[str], quiet: bool) -> dict[str, dict[str, list[str]]]: ...


@runtime_checkable
class SkyCloudApi(Protocol):
    @property
    def check(self) -> CloudCheckApi: ...


class SkyLaunchApi(Protocol):
    def launch(
        self,
        task: Task,
        *,
        cluster_name: str,
        idle_minutes_to_autostop: Optional[int],
        down: bool,
        dryrun: bool,
    ) -> RequestId[tuple[Optional[int], Optional[ResourceHandle]]]: ...


def submit_launch(
    sdk: SkyLaunchApi,
    task: Task,
    *,
    cluster_name: str,
    idle_minutes_to_autostop: Optional[int],
    down: bool,
    dryrun: bool,
) -> RequestId[tuple[Optional[int], Optional[ResourceHandle]]]:
    return sdk.launch(
        task,
        cluster_name=cluster_name,
        idle_minutes_to_autostop=idle_minutes_to_autostop,
        down=down,
        dryrun=dryrun,
    )


def check_clouds(sdk: SkyCloudApi, clouds: list[str]) -> dict[str, dict[str, list[str]]]:
    return sdk.check.check(clouds=clouds, quiet=True)
