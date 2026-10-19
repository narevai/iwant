from pathlib import Path

import pytest

from iwant import registry


@pytest.fixture
def recipes_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    recipes = tmp_path / "recipes"
    recipes.mkdir()
    monkeypatch.setattr(registry, "RECIPES_DIR", recipes)
    return recipes


def test_list_models_empty_when_dir_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "RECIPES_DIR", tmp_path / "does-not-exist")
    assert registry.list_models() == []


def test_list_models_only_dirs_with_versions(recipes_dir: Path) -> None:
    (recipes_dir / "modelA").mkdir()
    _ = (recipes_dir / "modelA" / "v1.yaml").write_text("resources: {}")
    (recipes_dir / "modelB-no-yaml").mkdir()
    _ = (recipes_dir / "not-a-dir.txt").write_text("x")

    assert registry.list_models() == ["modelA"]


def test_list_models_sorted(recipes_dir: Path) -> None:
    for name in ["zeta", "alpha", "mid"]:
        d = recipes_dir / name
        d.mkdir()
        _ = (d / "v1.yaml").write_text("resources: {}")

    assert registry.list_models() == ["alpha", "mid", "zeta"]


def test_resolve_task_yaml_returns_path(recipes_dir: Path) -> None:
    d = recipes_dir / "modelA"
    d.mkdir()
    _ = (d / "v1.yaml").write_text("resources: {}")

    assert registry.resolve_task_yaml("modelA") == (d / "v1.yaml", 1)


def test_resolve_task_yaml_raises_for_unknown_model(recipes_dir: Path) -> None:
    assert recipes_dir.is_dir()
    with pytest.raises(registry.ModelNotFoundError, match="unknown-model"):
        _ = registry.resolve_task_yaml("unknown-model")


def test_resolve_task_yaml_error_lists_available(recipes_dir: Path) -> None:
    d = recipes_dir / "gpt-oss-20b"
    d.mkdir()
    _ = (d / "v1.yaml").write_text("resources: {}")

    with pytest.raises(registry.ModelNotFoundError, match="gpt-oss-20b"):
        _ = registry.resolve_task_yaml("nope")


def test_resolve_task_yaml_picks_highest_version_numerically(recipes_dir: Path) -> None:
    d = recipes_dir / "modelA"
    d.mkdir()
    for n in (1, 2, 9, 10):
        _ = (d / f"v{n}.yaml").write_text("resources: {}")

    assert registry.resolve_task_yaml("modelA") == (d / "v10.yaml", 10)


def test_resolve_task_yaml_ignores_non_version_files(recipes_dir: Path) -> None:
    d = recipes_dir / "modelA"
    d.mkdir()
    _ = (d / "v1.yaml").write_text("resources: {}")
    for name in ("NOTES.md", "v2.yaml.bak", "server.yaml", "v3.yml"):
        _ = (d / name).write_text("x")

    assert registry.resolve_task_yaml("modelA") == (d / "v1.yaml", 1)


def test_list_models_skips_dir_without_versions(recipes_dir: Path) -> None:
    (recipes_dir / "old-style").mkdir()
    _ = (recipes_dir / "old-style" / "server.yaml").write_text("resources: {}")

    assert registry.list_models() == []


def test_new_cluster_name_uses_model_and_version_prefix() -> None:
    assert registry.new_cluster_name("gpt-oss-20b", 3).startswith("iwant-gpt-oss-20b-v3-")


def test_new_cluster_name_is_unique_per_call() -> None:
    assert registry.new_cluster_name("gpt-oss-20b", 1) != registry.new_cluster_name("gpt-oss-20b", 1)
