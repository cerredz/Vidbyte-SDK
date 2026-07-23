"""FILE: vidbyte/harnesses/schema.py

PURPOSE:
    Declares the harness behavior envelope as pydantic v2 models so structural
    validation of the config is declarative. It owns shape and required-field rules
    only: it performs no I/O, no $file resolution, and no content-addressed hashing.

ROLE IN CODEBASE:
    Consumed exclusively by HarnessConfigLoader (config.py), which parses and
    JSON-normalizes a source, validates it against HarnessConfigSchema, and then
    resolves references and computes identity. Nothing else imports these models.

ARCHITECTURE NOTE:
    The envelope is closed at the top level (extra="forbid") and at the per-agent
    `params` block (AgentParams, extra="forbid") so a hyperparameter is validated
    against the agent's real tunables instead of being accepted blindly. It stays
    open within the harness descriptor, each agent entry, and the remaining leaf maps
    (tools/metadata/orchestration): new per-harness knobs there do not require an SDK
    release, while a misspelled top-level key or an unknown/out-of-range agent
    hyperparameter fails fast. `params` mirrors BaseAgent's own budgets/temperature/
    runtime contract (vidbyte/agents/base.py, AgentRuntimeConfig) and `provider`/`model`
    are validated against the ProviderModelRegistry (vidbyte/lib/registries). Schema-
    version gating and credential rejection stay in the loader because they must raise
    the typed HarnessVersionError / HarnessCredentialConfigError rather than a
    ValidationError.

PUBLIC API INVENTORY:
    HarnessConfigSchema, HarnessDescriptor, AgentEntry, AgentParams.

WHAT NOT TO DO IN THIS FILE:
    1. Do not read files or resolve $file references; config.py owns that seam.
    2. Do not compute spec_id or hash anything; identity is not validation.
    3. Do not close the harness/agent-entry/tools/metadata surfaces; only the
       top-level envelope and the typed `params` block are intentionally closed.
    4. Do not raise Harness*Error here; validators raise ValueError so pydantic can
       aggregate, and config.py maps ValidationError to the typed error family.
       Registry helpers raise ConfigurationError, so wrap them and re-raise ValueError.

KNOWN EDGE CASES:
    An empty agents list is permitted (the loader historically allowed it). Present
    name/provider/model must be non-empty strings and are stripped; provider must be a
    ProviderModelRegistry-known provider; params fields must be positive integers (or a
    0.0-2.0 temperature, or an AgentRuntimeType runtime). Absent optional fields stay
    absent via exclude_unset (recursive, so an unset params field never enters the
    dump) so config identity is unchanged for configs that were already valid.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-config-pydantic-loader.md

TESTS:
    Exercised through HarnessConfigLoader's inline mapping/JSON/YAML/$file/identity
    smoke verification; no dedicated test file was added under the no-tests workflow.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries import ProviderModelRegistry

# Positive-integer agent budgets that mirror BaseAgent / AgentRuntimeConfig: each is
# optional, but a present value must be > 0 exactly as the runtime enforces at construction.
_POSITIVE_INT_PARAMS: tuple[str, ...] = (
    "max_iterations",
    "max_tokens",
    "max_tool_calls",
    "max_tool_rounds",
    "compaction_trigger_tokens",
    "compaction_target_tokens",
)


class HarnessDescriptor(BaseModel):
    """The implementation descriptor: a required `type` plus preserved extra fields."""

    model_config = ConfigDict(extra="allow")

    type: str

    @field_validator("type", mode="before")
    @classmethod
    def _require_non_empty_type(cls, value: Any) -> Any:
        # Mirrors the loader's required-text rule: a non-empty string, stripped of space.
        if not isinstance(value, str) or not value.strip():
            raise ValueError("harness.type must be a non-empty string.")
        return value.strip()


class AgentParams(BaseModel):
    """One agent's tunable hyperparameters, typed to BaseAgent's real construction knobs.

    Closed (extra="forbid") so a misspelled or unsupported hyperparameter fails at load
    instead of being silently carried into identity and later ignored by the agent. The
    fields and their bounds mirror BaseAgent.__init__ / AgentRuntimeConfig / AgentForkSettings
    so the config cannot promise a budget the runtime would reject at construction.
    """

    model_config = ConfigDict(extra="forbid")

    runtime: str | None = None
    temperature: float | None = None
    max_iterations: int | None = None
    max_tokens: int | None = None
    max_tool_calls: int | None = None
    max_tool_rounds: int | None = None
    compaction_trigger_tokens: int | None = None
    compaction_target_tokens: int | None = None

    @field_validator(*_POSITIVE_INT_PARAMS, mode="after")
    @classmethod
    def _require_positive_budget(cls, value: int | None, info: Any) -> int | None:
        # Mirrors AgentRuntimeConfig.__post_init__: a present budget must be strictly positive.
        if value is not None and value <= 0:
            raise ValueError(f"agents[].params.{info.field_name} must be greater than zero when provided.")
        return value

    @field_validator("temperature", mode="after")
    @classmethod
    def _require_temperature_range(cls, value: float | None) -> float | None:
        # Mirrors AgentForkSettings.__post_init__: temperature is bounded to [0.0, 2.0] when set.
        if value is not None and not 0.0 <= value <= 2.0:
            raise ValueError("agents[].params.temperature must be between 0 and 2 when provided.")
        return value

    @field_validator("runtime", mode="after")
    @classmethod
    def _require_known_runtime(cls, value: str | None) -> str | None:
        # Requires runtime to name a real AgentRuntimeType, matching BaseAgent's runtime contract.
        if value is None:
            return value
        try:
            AgentRuntimeType(value)
        except ValueError as exc:
            known = sorted(member.value for member in AgentRuntimeType)
            raise ValueError(f"agents[].params.runtime '{value}' is not a known runtime; known runtimes: {known}.") from exc
        return value


class AgentEntry(BaseModel):
    """One agent's declarative configuration; open at the entry level like the loader."""

    model_config = ConfigDict(extra="allow")

    name: str
    provider: str | None = None
    model: str | None = None
    system_prompt: str | dict[str, Any] | None = None
    params: AgentParams = Field(default_factory=AgentParams)
    tools: list[str | dict[str, Any]] | None = None

    @model_validator(mode="before")
    @classmethod
    def _require_text_fields(cls, data: Any) -> Any:
        # Requires any present name/provider/model to be a non-empty string and strips it.
        if not isinstance(data, Mapping):
            return data
        cleaned = dict(data)
        for field_name in ("name", "provider", "model"):
            if field_name in cleaned:
                cleaned[field_name] = cls._stripped_text(cleaned[field_name], field_name)
        return cleaned

    @staticmethod
    def _stripped_text(value: Any, field_name: str) -> str:
        # Rejects a non-string or blank text field and returns the stripped value.
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"agents[].{field_name} must be a non-empty string.")
        return value.strip()

    @field_validator("provider", mode="after")
    @classmethod
    def _require_known_provider(cls, value: str | None) -> str | None:
        # Requires provider to be a ProviderModelRegistry-known provider, per the reviewer's registry.
        if value is None:
            return value
        try:
            ProviderModelRegistry.validate_provider(value)
        except ConfigurationError as exc:
            # config.py maps ValidationError -> HarnessConfigurationError; keep the typed family intact.
            raise ValueError(str(exc)) from exc
        return value

    @field_validator("model", mode="after")
    @classmethod
    def _require_valid_model(cls, value: str | None) -> str | None:
        # Delegates non-empty model validation to the registry so this file is not the source of truth.
        if value is None:
            return value
        try:
            ProviderModelRegistry.validate_model(value)
        except ConfigurationError as exc:
            raise ValueError(str(exc)) from exc
        return value

    @field_validator("system_prompt", mode="after")
    @classmethod
    def _validate_system_prompt(cls, value: Any) -> Any:
        # Accepts inline prompt text or a lone {$file: ...} reference; rejects other shapes.
        if value is None or isinstance(value, str):
            return value
        if isinstance(value, dict) and set(value) == {"$file"}:
            return value
        raise ValueError("agents[].system_prompt must be a string or a {$file: ...} reference.")


class HarnessConfigSchema(BaseModel):
    """Closed top-level envelope over the harness descriptor and its agent entries."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    harness: HarnessDescriptor
    agents: list[AgentEntry]
    metadata: dict[str, Any] = Field(default_factory=dict)
    orchestration: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_unique_agent_names(self) -> "HarnessConfigSchema":
        # Duplicate agent names are almost always authoring mistakes, so reject them.
        names = [agent.name for agent in self.agents]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"Harness agent names must be unique; duplicates: {duplicates}.")
        return self


__all__ = ["AgentEntry", "AgentParams", "HarnessConfigSchema", "HarnessDescriptor"]
