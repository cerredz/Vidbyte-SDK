"""Context Protocol Header

Description:
    Defines AgentIdentity and AgentSettingsSnapshot, the strictly validated
    data contracts vidbyte.agents.settings.keys.AgentKeys is built from and
    fed with on every record_settings() call.
Purpose:
    Replaces the six loose keyword arguments AgentKeys.__init__ previously
    accepted, and the raw dict BaseAgent._settings_snapshot() previously
    returned, with two provably-valid dataclasses. A constructed instance can
    never be observed half-validated, so AgentKeys no longer needs to
    re-check the shape of what it is handed.
Architecture:
    - AgentIdentity: one BaseAgent instance's write-once identity. provider,
      model_name, and run_id stay Optional by deliberate, documented
      exception (see the class docstring) — every other field is required.
    - AgentSettingsSnapshot: wraps one AgentIdentity plus every other setting
      AgentKeys.record_settings hashes each run. Fields with no natural
      non-Optional default (output_schema, tool_settings_repr,
      tool_error_policy_repr) use an empty-container sentinel instead of
      None so the dataclass carries no union ("or") fields at all.
Relations:
    Constructed by vidbyte.agents.base.BaseAgent and consumed by
    vidbyte.agents.settings.keys.AgentKeys.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.enums import AgentRuntimeType, ModelProvider
from vidbyte.lib.errors import ConfigurationError

_MAX_AGENT_NAME_CHARS = 256
_MAX_MODEL_NAME_CHARS = 256
_MAX_RUN_ID_CHARS = 256
_MAX_SYSTEM_PROMPT_CHARS = 500_000
_MAX_DESCRIPTION_CHARS = 2000
_MAX_ALGORITHM_CHARS = 128
_MAX_CAPABILITY_CHARS = 200
_MAX_CAPABILITIES = 64
_MAX_CONTRACT_NAME_CHARS = 128
_MAX_PERMISSION_CHARS = 128
_TEMPERATURE_MIN = 0.0
_TEMPERATURE_MAX = 2.0


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    """One BaseAgent instance's write-once identity fields.

    provider, model_name, and run_id stay Optional by deliberate exception:
    BaseAgent legitimately constructs agents before a provider/model is
    pinned (resolved later through Runner/AgentFallback) and before a run_id
    exists (most single-shot calls never set one). Every other field is
    always known at construction time and is therefore required and strict.
    """

    agent_name: str
    runtime_type: AgentRuntimeType
    system_prompt: str
    provider: ModelProvider | None = None
    model_name: str | None = None
    run_id: str | None = None

    def __post_init__(self) -> None:
        # Validates identity fields; provider/model_name/run_id are only checked when present.
        if not self.agent_name or not self.agent_name.strip():
            raise ConfigurationError(
                "AgentIdentity.agent_name must be a non-empty string.",
                details={"field": "agent_name"},
            )
        if len(self.agent_name) > _MAX_AGENT_NAME_CHARS:
            raise ConfigurationError(
                f"AgentIdentity.agent_name must be at most {_MAX_AGENT_NAME_CHARS} characters.",
                details={"field": "agent_name", "max_chars": _MAX_AGENT_NAME_CHARS, "actual_chars": len(self.agent_name)},
            )
        if not isinstance(self.runtime_type, AgentRuntimeType):
            raise ConfigurationError(
                f"AgentIdentity.runtime_type must be an AgentRuntimeType, got {type(self.runtime_type).__name__}.",
                details={"field": "runtime_type", "actual_type": type(self.runtime_type).__name__},
            )
        if not self.system_prompt or not self.system_prompt.strip():
            raise ConfigurationError(
                "AgentIdentity.system_prompt must be a non-empty string.",
                details={"field": "system_prompt"},
            )
        if len(self.system_prompt) > _MAX_SYSTEM_PROMPT_CHARS:
            raise ConfigurationError(
                f"AgentIdentity.system_prompt must be at most {_MAX_SYSTEM_PROMPT_CHARS} characters.",
                details={"field": "system_prompt", "max_chars": _MAX_SYSTEM_PROMPT_CHARS, "actual_chars": len(self.system_prompt)},
            )
        if self.provider is not None and not isinstance(self.provider, ModelProvider):
            raise ConfigurationError(
                f"AgentIdentity.provider must be a ModelProvider when provided, got {type(self.provider).__name__}.",
                details={"field": "provider", "actual_type": type(self.provider).__name__},
            )
        if self.model_name is not None:
            if not self.model_name.strip():
                raise ConfigurationError(
                    "AgentIdentity.model_name must be a non-empty string when provided.",
                    details={"field": "model_name"},
                )
            if len(self.model_name) > _MAX_MODEL_NAME_CHARS:
                raise ConfigurationError(
                    f"AgentIdentity.model_name must be at most {_MAX_MODEL_NAME_CHARS} characters.",
                    details={"field": "model_name", "max_chars": _MAX_MODEL_NAME_CHARS, "actual_chars": len(self.model_name)},
                )
        if self.run_id is not None:
            if not self.run_id.strip():
                raise ConfigurationError(
                    "AgentIdentity.run_id must be a non-empty string when provided.",
                    details={"field": "run_id"},
                )
            if len(self.run_id) > _MAX_RUN_ID_CHARS:
                raise ConfigurationError(
                    f"AgentIdentity.run_id must be at most {_MAX_RUN_ID_CHARS} characters.",
                    details={"field": "run_id", "max_chars": _MAX_RUN_ID_CHARS, "actual_chars": len(self.run_id)},
                )


@dataclass(frozen=True, slots=True)
class AgentSettingsSnapshot:
    """One full point-in-time snapshot of everything AgentKeys.record_settings hashes.

    output_schema, tool_settings_repr, and tool_error_policy_repr use an
    empty-container sentinel instead of None: "no schema"/"no override" and
    "an empty one" are the same observable state for a setting with no
    effect either way, so no field on this dataclass needs a union type.
    """

    identity: AgentIdentity
    temperature: float
    runtime_config: Mapping[str, Any]
    algorithm: str
    capabilities: tuple[str, ...]
    description: str
    metadata: Mapping[str, Any]
    loop_settings: Mapping[str, Any]
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    tool_settings_repr: str = ""
    tool_error_policy_repr: str = ""
    output_contracts: tuple[str, ...] = ()
    max_contract_rejections: int = 0
    permission_policy_allowed: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Validates every field's type, range, and length; identity validates itself.
        if not isinstance(self.identity, AgentIdentity):
            raise ConfigurationError(
                f"AgentSettingsSnapshot.identity must be an AgentIdentity, got {type(self.identity).__name__}.",
                details={"field": "identity", "actual_type": type(self.identity).__name__},
            )
        if not (_TEMPERATURE_MIN <= self.temperature <= _TEMPERATURE_MAX):
            raise ConfigurationError(
                f"AgentSettingsSnapshot.temperature must be between {_TEMPERATURE_MIN} and {_TEMPERATURE_MAX}.",
                details={"field": "temperature", "actual": self.temperature},
            )
        if not isinstance(self.runtime_config, Mapping):
            raise ConfigurationError(
                f"AgentSettingsSnapshot.runtime_config must be a mapping, got {type(self.runtime_config).__name__}.",
                details={"field": "runtime_config", "actual_type": type(self.runtime_config).__name__},
            )
        if not self.algorithm or not self.algorithm.strip():
            raise ConfigurationError(
                "AgentSettingsSnapshot.algorithm must be a non-empty string.",
                details={"field": "algorithm"},
            )
        if len(self.algorithm) > _MAX_ALGORITHM_CHARS:
            raise ConfigurationError(
                f"AgentSettingsSnapshot.algorithm must be at most {_MAX_ALGORITHM_CHARS} characters.",
                details={"field": "algorithm", "max_chars": _MAX_ALGORITHM_CHARS, "actual_chars": len(self.algorithm)},
            )
        if len(self.capabilities) > _MAX_CAPABILITIES:
            raise ConfigurationError(
                f"AgentSettingsSnapshot.capabilities must have at most {_MAX_CAPABILITIES} entries.",
                details={"field": "capabilities", "max_count": _MAX_CAPABILITIES, "actual_count": len(self.capabilities)},
            )
        if any(not capability or len(capability) > _MAX_CAPABILITY_CHARS for capability in self.capabilities):
            raise ConfigurationError(
                f"AgentSettingsSnapshot.capabilities entries must be non-empty and at most {_MAX_CAPABILITY_CHARS} characters.",
                details={"field": "capabilities", "max_chars": _MAX_CAPABILITY_CHARS},
            )
        if len(self.description) > _MAX_DESCRIPTION_CHARS:
            raise ConfigurationError(
                f"AgentSettingsSnapshot.description must be at most {_MAX_DESCRIPTION_CHARS} characters.",
                details={"field": "description", "max_chars": _MAX_DESCRIPTION_CHARS, "actual_chars": len(self.description)},
            )
        if not isinstance(self.metadata, Mapping):
            raise ConfigurationError(
                f"AgentSettingsSnapshot.metadata must be a mapping, got {type(self.metadata).__name__}.",
                details={"field": "metadata", "actual_type": type(self.metadata).__name__},
            )
        if not isinstance(self.loop_settings, Mapping):
            raise ConfigurationError(
                f"AgentSettingsSnapshot.loop_settings must be a mapping, got {type(self.loop_settings).__name__}.",
                details={"field": "loop_settings", "actual_type": type(self.loop_settings).__name__},
            )
        if not isinstance(self.output_schema, Mapping):
            raise ConfigurationError(
                f"AgentSettingsSnapshot.output_schema must be a mapping, got {type(self.output_schema).__name__}.",
                details={"field": "output_schema", "actual_type": type(self.output_schema).__name__},
            )
        if self.max_contract_rejections < 0:
            raise ConfigurationError(
                "AgentSettingsSnapshot.max_contract_rejections must be >= 0.",
                details={"field": "max_contract_rejections", "actual": self.max_contract_rejections},
            )
        if any(not name or len(name) > _MAX_CONTRACT_NAME_CHARS for name in self.output_contracts):
            raise ConfigurationError(
                f"AgentSettingsSnapshot.output_contracts entries must be non-empty and at most {_MAX_CONTRACT_NAME_CHARS} characters.",
                details={"field": "output_contracts", "max_chars": _MAX_CONTRACT_NAME_CHARS},
            )
        if any(not name or len(name) > _MAX_PERMISSION_CHARS for name in self.permission_policy_allowed):
            raise ConfigurationError(
                f"AgentSettingsSnapshot.permission_policy_allowed entries must be non-empty and at most {_MAX_PERMISSION_CHARS} characters.",
                details={"field": "permission_policy_allowed", "max_chars": _MAX_PERMISSION_CHARS},
            )


__all__ = ["AgentIdentity", "AgentSettingsSnapshot"]
