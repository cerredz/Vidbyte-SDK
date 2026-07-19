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
    The envelope is closed at the top level (extra="forbid") but open within the
    harness descriptor, each agent entry, and the leaf maps (params/tools/metadata/
    orchestration). This preserves the loader's original property that the YAML is a
    forward-compatible single source of truth: new per-harness knobs do not require an
    SDK release, while misspelled top-level keys still fail fast. Schema-version gating
    and credential rejection stay in the loader because they must raise the typed
    HarnessVersionError / HarnessCredentialConfigError rather than a ValidationError.

PUBLIC API INVENTORY:
    HarnessConfigSchema, HarnessDescriptor, AgentEntry.

WHAT NOT TO DO IN THIS FILE:
    1. Do not read files or resolve $file references; config.py owns that seam.
    2. Do not compute spec_id or hash anything; identity is not validation.
    3. Do not close the harness/agent/leaf surfaces; they are intentionally open.
    4. Do not raise Harness*Error here; validators raise ValueError so pydantic can
       aggregate, and config.py maps ValidationError to the typed error family.

KNOWN EDGE CASES:
    An empty agents list is permitted (the loader historically allowed it). Present
    name/provider/model must be non-empty strings and are stripped; absent optional
    fields stay absent via exclude_unset so config identity is unchanged.

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


class AgentEntry(BaseModel):
    """One agent's declarative configuration; open at the entry level like the loader."""

    model_config = ConfigDict(extra="allow")

    name: str
    provider: str | None = None
    model: str | None = None
    system_prompt: str | dict[str, Any] | None = None
    params: dict[str, Any] = Field(default_factory=dict)
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


__all__ = ["AgentEntry", "HarnessConfigSchema", "HarnessDescriptor"]
