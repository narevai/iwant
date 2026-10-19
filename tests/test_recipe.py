from pathlib import Path
from typing import Optional

import pytest
import yaml
from pydantic import SecretStr, ValidationError

from iwant.recipe import Recipe
from iwant.registry import RECIPES_DIR

RECIPE_PATHS = sorted(RECIPES_DIR.glob("*/*.yaml"))


@pytest.mark.parametrize(
    "path", RECIPE_PATHS, ids=[str(path.relative_to(RECIPES_DIR)) for path in RECIPE_PATHS]
)
def test_published_recipe_round_trip(path: Path) -> None:
    recipe = Recipe.from_yaml(path)
    assert yaml.safe_load(recipe.to_skypilot_yaml()) == yaml.safe_load(path.read_text())


@pytest.mark.parametrize(
    "content",
    [
        "",
        "null",
        "[]",
        "false",
        "1: value",
        "resources: null",
        "resources: []",
        "resources: {1: value}",
        "resources: {infra: 123}",
        "resources: {use_spot: 'true'}",
        "resources: {disk_size: -1}",
        "resources: {ports: [true]}",
        "resources: {accelerators: [L4]}",
        "envs: secret",
        "envs: {1: value}",
        "envs: {MODEL_NAME: 123}",
        "envs: {VLLM_API_KEY: [secret]}",
        "resources: {infar: gcp}",
        "envs: {VLLM_API_KEy: secret}",
        "unknown: value",
        "setup: [echo, hello]",
        "run: 123",
    ],
)
def test_invalid_recipe_rejected_even_without_overrides(tmp_path: Path, content: str) -> None:
    path = tmp_path / "recipe.yaml"
    _ = path.write_text(content)
    with pytest.raises(ValidationError):
        _ = Recipe.from_yaml(path)


def test_overrides_preserve_recipe_and_validate_missing_sections(tmp_path: Path) -> None:
    path = tmp_path / "recipe.yaml"
    original = "setup: echo hello\nrun: echo ready\n"
    _ = path.write_text(original)
    recipe = Recipe.from_yaml(path).with_overrides(
        infra="aws",
        api_key=SecretStr("key"),
        hf_token=SecretStr("token"),
        use_spot=True,
        recipe_id="model@v1",
    )
    with recipe.materialize() as output:
        loaded = Recipe.from_yaml(output)
        assert loaded.resources.infra == "aws"
        assert loaded.resources.use_spot is True
        assert loaded.envs.VLLM_API_KEY == SecretStr("key")
        assert loaded.envs.HF_TOKEN == SecretStr("token")
        assert loaded.envs.IWANT_RECIPE == "model@v1"
        assert loaded.setup == "echo hello"
        assert loaded.run == "echo ready"
        assert path.read_text() == original
    assert not output.exists()


def test_credentials_are_redacted_except_in_explicit_sdk_export() -> None:
    api_key = "private-api-key-123"
    hf_token = "private-hf-token-456"
    recipe = Recipe().with_overrides(api_key=SecretStr(api_key), hf_token=SecretStr(hf_token))
    for representation in (
        repr(recipe),
        str(recipe.model_dump()),
        recipe.model_dump_json(),
        recipe.to_yaml(),
    ):
        assert api_key not in representation
        assert hf_token not in representation
    sdk_yaml = recipe.to_skypilot_yaml()
    assert api_key in sdk_yaml
    assert hf_token in sdk_yaml


def test_overrides_do_not_mutate_original_recipe() -> None:
    original = Recipe()
    original.resources.infra = "gcp"
    original.envs.VLLM_API_KEY = SecretStr("original-key")
    updated = original.with_overrides(infra="aws", api_key=SecretStr("replacement-key"), use_spot=True)
    assert original.resources.infra == "gcp"
    assert original.resources.use_spot is None
    assert original.envs.VLLM_API_KEY == SecretStr("original-key")
    assert updated.resources.infra == "aws"
    assert updated.resources.use_spot is True
    assert updated.envs.VLLM_API_KEY == SecretStr("replacement-key")


def test_materialized_file_is_private_and_removed_on_failure() -> None:
    recipe = Recipe().with_overrides(api_key=SecretStr("private-key"))
    materialized_path: Optional[Path] = None
    with pytest.raises(RuntimeError, match="SDK parsing failed"):
        with recipe.materialize() as path:
            materialized_path = path
            assert path.stat().st_mode & 0o777 == 0o600
            assert "private-key" in path.read_text()
            raise RuntimeError("SDK parsing failed")
    assert materialized_path is not None
    assert not materialized_path.exists()
