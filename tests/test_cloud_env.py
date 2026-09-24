from unittest.mock import MagicMock

from iwant import cloud_env


def test_ensure_gcp_sets_env_from_gcloud_config(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(cloud_env.subprocess, "run", lambda *a, **k: MagicMock(stdout="my-project\n"))

    cloud_env._ensure_gcp()
    assert cloud_env.os.environ.get("GOOGLE_CLOUD_PROJECT") == "my-project"


def test_ensure_gcp_does_not_overwrite_existing(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "already-set")
    monkeypatch.setattr(
        cloud_env.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call gcloud")),
    )
    cloud_env._ensure_gcp()
    assert cloud_env.os.environ["GOOGLE_CLOUD_PROJECT"] == "already-set"


def test_ensure_gcp_handles_unset_project(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(cloud_env.subprocess, "run", lambda *a, **k: MagicMock(stdout="(unset)\n"))

    cloud_env._ensure_gcp()
    assert "GOOGLE_CLOUD_PROJECT" not in cloud_env.os.environ


def test_ensure_gcp_handles_missing_gcloud_binary(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    def raise_not_found(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(cloud_env.subprocess, "run", raise_not_found)
    cloud_env._ensure_gcp()  # must not raise
    assert "GOOGLE_CLOUD_PROJECT" not in cloud_env.os.environ


def test_ensure_cloud_env_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("should be swallowed")

    monkeypatch.setattr(cloud_env, "_FIXERS", (boom,))
    cloud_env.ensure_cloud_env()  # must not raise
