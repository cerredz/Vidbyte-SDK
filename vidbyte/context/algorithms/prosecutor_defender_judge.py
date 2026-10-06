"""Context Protocol Header

FILE: vidbyte/context/algorithms/prosecutor_defender_judge.py
PURPOSE: Defines immutable public settings for the verdict-only prosecutor,
defender, and judge context-window protocol. Runtime execution belongs in
vidbyte/agents/algorithms/prosecutor_defender_judge.py.
ROLE IN CODEBASE: ContextWindowAlgorithm and presets expose these settings;
the runtime adapter consumes them to build three isolated review stages.
ARCHITECTURE NOTE: Configuration is validated eagerly so no review call can
start with an ambiguous provider, resource allowlist, prompt, or budget.
FUNCTION INVENTORY: DebateStageSettings validates one role; the algorithm
validates shared limits and renders the three model-visible payloads.
WHAT NOT TO DO: Do not add mutable transcript state, producer context, or
runtime orchestration here. Do not silently truncate exact review inputs.
KNOWN EDGE CASES: Provider and model are an all-or-nothing pair; prompt user
overrides accept only the payload_json placeholder.
RELATED DOCS: docs/design/context-window-prosecutor-defender-judge.md.
TEST FILES: No new tests are authorized by the approved no-tests design.
"""

from __future__ import annotations

import copy
import json
import string
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.models import ProviderModelRegistry
from vidbyte.prompts import Prompts

_MAX_COUNT = 100
_MAX_INPUT_CHARS = 2_000_000
_MAX_REPORT_CHARS = 2_000_000
_MAX_RUNTIME_VALUE = 1_000_000
_MAX_TIMEOUT_SECONDS = 3600.0
_MAX_RESOURCE_NAME_CHARS = 200
_MAX_RESOURCE_NAMES = 100
_MAX_METADATA_CHARS = 100_000
_MAX_PROMPT_CHARS = 200_000
_PAYLOAD_PLACEHOLDER = "payload_json"


class ProsecutorDefenderJudgeFailurePolicy(str, Enum):
    """Failure behavior after the immutable producer candidate exists."""

    RAISE = "raise"
    RETURN_CANDIDATE = "return_candidate"


@dataclass(frozen=True, slots=True)
class DebateStageSettings:
    """Immutable settings and positive capability allowlists for one role."""

    provider: str | None = None
    model: str | None = None
    artifact_names: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()
    max_iterations: int = 4
    max_tokens: int = 8000
    max_tool_calls: int = 4
    timeout_seconds: float = 120.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes immutable values and rejects ambiguous stage capabilities.
        _validate_provider_model_pair(self.provider, self.model)
        object.__setattr__(self, "artifact_names", _normalize_names(self.artifact_names, "artifact_names"))
        object.__setattr__(self, "tool_names", _normalize_names(self.tool_names, "tool_names"))
        _validate_positive_int(self.max_iterations, "max_iterations", _MAX_RUNTIME_VALUE)
        _validate_positive_int(self.max_tokens, "max_tokens", _MAX_RUNTIME_VALUE)
        _validate_positive_int(self.max_tool_calls, "max_tool_calls", _MAX_RUNTIME_VALUE)
        _validate_positive_number(self.timeout_seconds, "timeout_seconds", _MAX_TIMEOUT_SECONDS)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class ProsecutorDefenderJudgeAlgorithm:
    """Public immutable configuration for the three-stage debate review."""

    prosecutor: DebateStageSettings = field(default_factory=DebateStageSettings)
    defender: DebateStageSettings = field(default_factory=DebateStageSettings)
    judge: DebateStageSettings = field(default_factory=DebateStageSettings)
    failure_policy: ProsecutorDefenderJudgeFailurePolicy = ProsecutorDefenderJudgeFailurePolicy.RAISE
    max_task_chars: int = 20000
    max_candidate_chars: int = 100000
    max_artifact_chars: int = 50000
    max_total_artifact_chars: int = 100000
    max_allegations: int = 20
    max_evidence_per_item: int = 8
    max_field_chars: int = 4000
    max_stage_report_chars: int = 100000
    max_failure_message_chars: int = 1000
    prosecutor_system_prompt: str | None = None
    prosecutor_prompt: str | None = None
    defender_system_prompt: str | None = None
    defender_prompt: str | None = None
    judge_system_prompt: str | None = None
    judge_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates protocol limits and every caller-controlled prompt boundary.
        for field_name in ("prosecutor", "defender", "judge"):
            if not isinstance(getattr(self, field_name), DebateStageSettings):
                raise ConfigurationError(f"{field_name} must be a DebateStageSettings instance.")
        try:
            object.__setattr__(self, "failure_policy", ProsecutorDefenderJudgeFailurePolicy(self.failure_policy))
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported prosecutor/defender/judge failure_policy: {self.failure_policy!r}.") from exc
        for name in ("max_task_chars", "max_candidate_chars", "max_artifact_chars", "max_total_artifact_chars", "max_field_chars"):
            _validate_positive_int(getattr(self, name), name, _MAX_INPUT_CHARS)
        _validate_positive_int(self.max_allegations, "max_allegations", _MAX_COUNT)
        _validate_positive_int(self.max_evidence_per_item, "max_evidence_per_item", _MAX_COUNT)
        _validate_positive_int(self.max_stage_report_chars, "max_stage_report_chars", _MAX_REPORT_CHARS)
        _validate_positive_int(self.max_failure_message_chars, "max_failure_message_chars", _MAX_INPUT_CHARS)
        if self.max_total_artifact_chars < self.max_artifact_chars:
            raise ConfigurationError("max_total_artifact_chars must be greater than or equal to max_artifact_chars.")
        for field_name in ("prosecutor_system_prompt", "defender_system_prompt", "judge_system_prompt"):
            _validate_prompt_override(getattr(self, field_name), field_name, require_payload=False)
        for field_name in ("prosecutor_prompt", "defender_prompt", "judge_prompt"):
            _validate_prompt_override(getattr(self, field_name), field_name, require_payload=True)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata, "metadata"))

    def prosecutor_system_prompt_text(self) -> str:
        # Returns the algorithm-owned prosecutor instruction without producer context.
        return self.prosecutor_system_prompt or Prompts().get(Prompt.PROSECUTOR_DEFENDER_JUDGE_PROSECUTOR_SYSTEM_PROMPT)

    def defender_system_prompt_text(self) -> str:
        # Returns the algorithm-owned defender instruction without producer context.
        return self.defender_system_prompt or Prompts().get(Prompt.PROSECUTOR_DEFENDER_JUDGE_DEFENDER_SYSTEM_PROMPT)

    def judge_system_prompt_text(self) -> str:
        # Returns the algorithm-owned judge instruction without producer context.
        return self.judge_system_prompt or Prompts().get(Prompt.PROSECUTOR_DEFENDER_JUDGE_JUDGE_SYSTEM_PROMPT)

    def render_prosecutor_prompt(self, payload_json: str) -> str:
        # Renders the prosecutor's single untrusted-evidence payload.
        template = self.prosecutor_prompt or Prompts().get(Prompt.PROSECUTOR_DEFENDER_JUDGE_PROSECUTOR_PROMPT)
        return template.format(payload_json=payload_json)

    def render_defender_prompt(self, payload_json: str) -> str:
        # Renders the defender's single normalized-allegation payload.
        template = self.defender_prompt or Prompts().get(Prompt.PROSECUTOR_DEFENDER_JUDGE_DEFENDER_PROMPT)
        return template.format(payload_json=payload_json)

    def render_judge_prompt(self, payload_json: str) -> str:
        # Renders the judge's single normalized debate payload.
        template = self.judge_prompt or Prompts().get(Prompt.PROSECUTOR_DEFENDER_JUDGE_JUDGE_PROMPT)
        return template.format(payload_json=payload_json)


def _validate_provider_model_pair(provider: str | None, model: str | None) -> None:
    # Requires a complete dedicated-runner pair or an entirely inherited transport.
    if (provider is None) != (model is None):
        raise ConfigurationError("DebateStageSettings.provider and model must both be provided or both be omitted.")
    if provider is None or model is None:
        return
    ProviderModelRegistry.validate_provider(provider)
    ProviderModelRegistry.validate_model(model)


def _normalize_names(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    # Produces a deterministic nonblank tuple while rejecting duplicate grants.
    if isinstance(values, (str, bytes)):
        raise ConfigurationError(f"{field_name} must be a tuple of names, not a string.")
    normalized = tuple(str(value).strip() for value in values)
    if any(not value for value in normalized):
        raise ConfigurationError(f"{field_name} cannot contain blank names.")
    if any(len(value) > _MAX_RESOURCE_NAME_CHARS for value in normalized):
        raise ConfigurationError(f"{field_name} names cannot exceed {_MAX_RESOURCE_NAME_CHARS} characters.")
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError(f"{field_name} cannot contain duplicate names.")
    if len(normalized) > _MAX_RESOURCE_NAMES:
        raise ConfigurationError(f"{field_name} cannot contain more than {_MAX_RESOURCE_NAMES} names.")
    return normalized


def _validate_positive_int(value: object, field_name: str, maximum: int) -> None:
    # Rejects boolean, non-integer, non-positive, and safeguard-exceeding limits.
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"{field_name} must be a positive integer.")
    if value > maximum:
        raise ConfigurationError(f"{field_name} ({value}) exceeds the safeguard limit of {maximum}.")


def _validate_positive_number(value: object, field_name: str, maximum: float) -> None:
    # Rejects invalid stage timeout values before any provider work begins.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        raise ConfigurationError(f"{field_name} must be a positive number.")
    if float(value) > maximum:
        raise ConfigurationError(f"{field_name} ({value}) exceeds the safeguard limit of {maximum}.")


def _validate_prompt_override(value: str | None, field_name: str, *, require_payload: bool) -> None:
    # Restricts prompt overrides to nonblank text and the one supported placeholder.
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field_name} must be a non-empty string when provided.")
    if len(value) > _MAX_PROMPT_CHARS:
        raise ConfigurationError(f"{field_name} exceeds the prompt safeguard limit of {_MAX_PROMPT_CHARS} characters.")
    if not require_payload:
        return
    parsed = tuple(string.Formatter().parse(value))
    fields = tuple(name for _, name, _, _ in parsed if name is not None)
    if fields != (_PAYLOAD_PLACEHOLDER,):
        raise ConfigurationError(f"{field_name} must contain exactly one {{{_PAYLOAD_PLACEHOLDER}}} placeholder; found {fields}.")
    if any(format_spec or conversion for _, name, format_spec, conversion in parsed if name is not None):
        raise ConfigurationError(f"{field_name} cannot transform the {_PAYLOAD_PLACEHOLDER} placeholder.")


def _freeze_metadata(metadata: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    # Deep-copies and bounds public metadata before it can enter result provenance.
    if not isinstance(metadata, Mapping):
        raise ConfigurationError(f"{field_name} must be a mapping.")
    try:
        copied = copy.deepcopy(dict(metadata))
    except Exception as exc:
        raise ConfigurationError(f"{field_name} must contain copyable values.") from exc
    invalid = tuple(type(key).__name__ for key in copied if not isinstance(key, str))
    if invalid:
        raise ConfigurationError(f"{field_name} keys must be strings; found {invalid[0]}.")
    serialized = json.dumps(copied, ensure_ascii=False, sort_keys=True, default=str)
    if len(serialized) > _MAX_METADATA_CHARS:
        raise ConfigurationError(f"{field_name} exceeds the metadata safeguard limit of {_MAX_METADATA_CHARS} characters.")
    return MappingProxyType(copied)


__all__ = [
    "DebateStageSettings",
    "ProsecutorDefenderJudgeAlgorithm",
    "ProsecutorDefenderJudgeFailurePolicy",
]
