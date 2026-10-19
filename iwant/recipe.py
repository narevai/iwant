"""Validated schema for the SkyPilot recipes shipped with iwant."""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, SerializationInfo, field_serializer


class RecipeModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class RecipeResources(RecipeModel):
    infra: Optional[str] = None
    accelerators: Optional[str] = None
    cpus: Optional[str | int | float] = None
    memory: Optional[str | int | float] = None
    disk_size: Optional[int] = Field(default=None, gt=0)
    ports: Optional[list[int | str]] = None
    use_spot: Optional[bool] = None


class RecipeEnvironment(RecipeModel):
    MODEL_NAME: Optional[str] = None
    VLLM_API_KEY: Optional[SecretStr] = None
    HF_TOKEN: Optional[SecretStr] = None
    IWANT_RECIPE: Optional[str] = None
    VLLM_ENGINE_READY_TIMEOUT_S: Optional[str] = None

    @field_serializer("VLLM_API_KEY", "HF_TOKEN")
    def serialize_secret(self, value: Optional[SecretStr], info: SerializationInfo) -> Optional[str]:
        if value is None:
            return None
        return value.get_secret_value() if info.context == "skypilot" else str(value)


class Recipe(RecipeModel):
    resources: RecipeResources = Field(default_factory=RecipeResources)
    envs: RecipeEnvironment = Field(default_factory=RecipeEnvironment)
    setup: Optional[str] = None
    run: Optional[str] = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> Recipe:
        with open(path) as stream:
            return cls.model_validate(yaml.safe_load(stream))

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json", exclude_none=True))

    def with_overrides(
        self,
        *,
        infra: Optional[str] = None,
        api_key: Optional[SecretStr] = None,
        hf_token: Optional[SecretStr] = None,
        use_spot: bool = False,
        recipe_id: Optional[str] = None,
    ) -> Recipe:
        updated = self.model_copy(deep=True)
        if infra:
            updated.resources.infra = infra
        if api_key is not None:
            updated.envs.VLLM_API_KEY = api_key
        if hf_token is not None:
            updated.envs.HF_TOKEN = hf_token
        if use_spot:
            updated.resources.use_spot = True
        if recipe_id:
            updated.envs.IWANT_RECIPE = recipe_id
        return updated

    def to_skypilot_yaml(self) -> str:
        """Export plaintext credentials only for the SDK task document."""
        return yaml.safe_dump(self.model_dump(mode="json", exclude_none=True, context="skypilot"))

    @contextmanager
    def materialize(self) -> Generator[Path, None, None]:
        """Keep the SDK task file private and delete it even when parsing fails."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", prefix="iwant-task-", delete=False
        ) as stream:
            path = Path(stream.name)
            try:
                _ = stream.write(self.to_skypilot_yaml())
                stream.flush()
                yield path
            finally:
                path.unlink(missing_ok=True)
