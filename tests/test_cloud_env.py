import os
import subprocess
from typing import NoReturn

import pytest

from iwant import cloud_env


def test_ensure_gcp_sets_env_from_gcloud_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["gcloud"], 0, stdout="my-project\n")

    monkeypatch.setattr(subprocess, "run", run)
    cloud_env.ensure_cloud_env()
    assert os.environ.get("GOOGLE_CLOUD_PROJECT") == "my-project"


def test_ensure_gcp_does_not_overwrite_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "already-set")
    calls = 0

    def unexpected_run(*_args: object, **_kwargs: object) -> NoReturn:
        nonlocal calls
        calls += 1
        raise AssertionError("gcloud should not run when the project is already set")

    monkeypatch.setattr(subprocess, "run", unexpected_run)
    cloud_env.ensure_cloud_env()
    assert calls == 0
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "already-set"


def test_ensure_gcp_handles_unset_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["gcloud"], 0, stdout="(unset)\n")

    monkeypatch.setattr(subprocess, "run", run)
    cloud_env.ensure_cloud_env()
    assert "GOOGLE_CLOUD_PROJECT" not in os.environ


def test_ensure_gcp_handles_missing_gcloud_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    def raise_not_found(*_args: object, **_kwargs: object) -> NoReturn:
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess, "run", raise_not_found)
    cloud_env.ensure_cloud_env()
    assert "GOOGLE_CLOUD_PROJECT" not in os.environ


def test_ensure_cloud_env_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    def boom(*_args: object, **_kwargs: object) -> NoReturn:
        raise RuntimeError("should be swallowed")

    monkeypatch.setattr(subprocess, "run", boom)
    cloud_env.ensure_cloud_env()
    assert "GOOGLE_CLOUD_PROJECT" not in os.environ
