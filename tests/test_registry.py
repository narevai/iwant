import pytest

from iwant import registry


@pytest.fixture
def recipes_dir(tmp_path, monkeypatch):
    recipes = tmp_path / "recipes"
    recipes.mkdir()
    monkeypatch.setattr(registry, "RECIPES_DIR", recipes)
    return recipes


def test_list_models_empty_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "RECIPES_DIR", tmp_path / "does-not-exist")
    assert registry.list_models() == []


def test_list_models_only_dirs_with_versions(recipes_dir):
    (recipes_dir / "modelA").mkdir()
    (recipes_dir / "modelA" / "v1.yaml").write_text("resources: {}")
    (recipes_dir / "modelB-no-yaml").mkdir()
    (recipes_dir / "not-a-dir.txt").write_text("x")

    assert registry.list_models() == ["modelA"]


def test_list_models_sorted(recipes_dir):
    for name in ["zeta", "alpha", "mid"]:
        d = recipes_dir / name
        d.mkdir()
        (d / "v1.yaml").write_text("resources: {}")

    assert registry.list_models() == ["alpha", "mid", "zeta"]


def test_resolve_task_yaml_returns_path(recipes_dir):
    d = recipes_dir / "modelA"
    d.mkdir()
    (d / "v1.yaml").write_text("resources: {}")

    assert registry.resolve_task_yaml("modelA") == (d / "v1.yaml", 1)


def test_resolve_task_yaml_raises_for_unknown_model(recipes_dir):
    with pytest.raises(registry.ModelNotFoundError, match="unknown-model"):
        registry.resolve_task_yaml("unknown-model")


def test_resolve_task_yaml_error_lists_available(recipes_dir):
    d = recipes_dir / "gpt-oss-20b"
    d.mkdir()
    (d / "v1.yaml").write_text("resources: {}")

    with pytest.raises(registry.ModelNotFoundError, match="gpt-oss-20b"):
        registry.resolve_task_yaml("nope")


def test_resolve_task_yaml_picks_highest_version_numerically(recipes_dir):
    d = recipes_dir / "modelA"
    d.mkdir()
    for n in (1, 2, 9, 10):
        (d / f"v{n}.yaml").write_text("resources: {}")

    assert registry.resolve_task_yaml("modelA") == (d / "v10.yaml", 10)


def test_resolve_task_yaml_ignores_non_version_files(recipes_dir):
    d = recipes_dir / "modelA"
    d.mkdir()
    (d / "v1.yaml").write_text("resources: {}")
    for name in ("NOTES.md", "v2.yaml.bak", "server.yaml", "v3.yml"):
        (d / name).write_text("x")

    assert registry.resolve_task_yaml("modelA") == (d / "v1.yaml", 1)


def test_list_models_skips_dir_without_versions(recipes_dir):
    (recipes_dir / "old-style").mkdir()
    (recipes_dir / "old-style" / "server.yaml").write_text("resources: {}")

    assert registry.list_models() == []


def test_new_cluster_name_uses_model_and_version_prefix():
    assert registry.new_cluster_name("gpt-oss-20b", 3).startswith("iwant-gpt-oss-20b-v3-")


def test_new_cluster_name_is_unique_per_call():
    assert registry.new_cluster_name("gpt-oss-20b", 1) != registry.new_cluster_name("gpt-oss-20b", 1)
