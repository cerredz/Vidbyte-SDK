"""FILE: vidbyte/harnesses/schema.py

PURPOSE:
    Declares the harness behavior envelope as pydantic v2 models so structural
    validation of the config is declarative. It owns the top-level shape and
    harness-descriptor rules only; per-agent entries are validated by the dataclass
    AgentSettings (vidbyte.lib.dataclasses.config) inside the loader, not by this
    file. $file resolution, credential rejection, and content-addressed hashing
    remain in config.py.

ROLE IN CODEBASE:
    Consumed exclusively by HarnessConfigLoader (config.py), which parses and
    JSON-normalizes a source, validates it against HarnessConfigSchema, validates
    each agent entry through AgentSettings.from_mapping(), and then resolves
    references and computes identity. Nothing else imports these models.

ARCHITECTURE NOTE:
    The envelope is closed at the top level (extra="forbid") but the agents list
    carries raw dicts because per-agent validation is the job of AgentSettings, a
    dataclass that validates provider, model, temperature, and params against the
    SDK's canonical registries. This keeps structural shape checks on pydantic (a
    first-class SDK dependency) while the deep per-field contract lives on one
    dataclass with __post_init__ validation — satisfying both concerns without
    duplicating logic. Schema-version gating and credential rejection stay in the
    loader because they must raise the typed HarnessVersionError /
    HarnessCredentialConfigError rather than a ValidationError.

PUBLIC API INVENTORY:
    HarnessConfigSchema, HarnessDescriptor.

WHAT NOT TO DO IN THIS FILE:
    1. Do not read files or resolve $file references; config.py owns that seam.
    2. Do not compute spec_id or hash anything; identity is not validation.
    3. Do not validate provider/model/params per agent; AgentSettings owns that.
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
        if not isinstance(value, str) or not value.strip():
            raise ValueError("harness.type must be a non-empty string.")
        return value.strip()


class HarnessConfigSchema(BaseModel):
    """Closed top-level envelope; per-agent entries validated by AgentSettings."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    harness: HarnessDescriptor
    agents: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)
    orchestration: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _reject_bool_version(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("schema_version must be an integer, not a boolean.")
        return value

    @model_validator(mode="after")
    def _require_unique_agent_names(self) -> "HarnessConfigSchema":
        names: list[str] = []
        for agent in self.agents:
            if isinstance(agent, Mapping):
                name = agent.get("name")
                if isinstance(name, str):
                    names.append(name.strip())
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"Harness agent names must be unique; duplicates: {duplicates}.")
        return self


__all__ = ["HarnessConfigSchema", "HarnessDescriptor"]
