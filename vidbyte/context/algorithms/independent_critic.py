"""Context Protocol Header

Description:
    Defines the public Independent Critic context-window configuration.
Purpose:
    Validates the critic isolation policy, renders the exact review payload,
    and normalizes untrusted reviewer JSON into bounded metadata.
Architecture:
    - CriticFailurePolicy: Controls fail-closed versus marked fail-open behavior.
    - IndependentCriticAlgorithm: Immutable configuration and pure normalization.
Key Functions:
    - render_review_prompt: Serializes only task, candidate, and permitted artifacts.
    - normalize_review: Validates and bounds an unadjudicated critic report.
Relations:
    Consumed by vidbyte.agents.algorithms.independent_critic and exported through
    vidbyte.context. This file performs no runner, tool, filesystem, or network I/O.
"""

from __future__ import annotations

import json
import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vidbyte.lib.dataclasses.context import ContextArtifact
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.models import ProviderModelRegistry
from vidbyte.prompts import Prompts

_MAX_CHARACTER_LIMIT = 1_000_000
_MAX_REVIEWER_ITERATIONS = 100
_MAX_REVIEWER_TOOL_CALLS = 1_000
_MAX_FINDINGS = 1_000
_REQUIRED_REVIEW_PLACEHOLDERS = {"review_payload"}
_VERDICTS = {"pass", "needs_changes", "uncertain"}
_SEVERITIES = {"critical", "major", "minor", "note"}


class CriticFailurePolicy(str, Enum):
    """Policy applied when the critic stage cannot produce a valid report."""

    RAISE = "raise"
    RETURN_CANDIDATE = "return_candidate"


@dataclass(frozen=True, slots=True)
class IndependentCriticAlgorithm:
    """Immutable public configuration for one isolated, review-only critic."""

    reviewer_provider: str | None = None
    reviewer_model: str | None = None
    reviewer_system_prompt: str | None = None
    review_prompt: str | None = None
    allowed_artifact_names: tuple[str, ...] = ()
    allowed_tool_names: tuple[str, ...] = ()
    reviewer_max_iterations: int = 4
    reviewer_max_tokens: int = 8000
    reviewer_max_tool_calls: int = 4
    max_candidate_chars: int = 100_000
    max_artifact_chars: int = 50_000
    max_total_artifact_chars: int = 100_000
    max_critique_chars: int = 20_000
    max_findings: int = 20
    max_finding_chars: int = 2_000
    failure_policy: CriticFailurePolicy = CriticFailurePolicy.RAISE
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalize public collections and reject invalid policy before runtime work begins.
        object.__setattr__(self, "allowed_artifact_names", _validate_names(self.allowed_artifact_names, "allowed_artifact_names"))
        object.__setattr__(self, "allowed_tool_names", _validate_names(self.allowed_tool_names, "allowed_tool_names"))
        object.__setattr__(self, "failure_policy", _validate_failure_policy(self.failure_policy))
        self._validate_reviewer_identity()
        self._validate_limits()
        _validate_prompt_override(self.reviewer_system_prompt, "reviewer_system_prompt")
        _validate_review_prompt(self.review_prompt)
        _validate_metadata(self.metadata)

    def reviewer_system_prompt_text(self) -> str:
        # Return the algorithm-owned critic instruction without producer prompt inheritance.
        return self.reviewer_system_prompt or Prompts().get(Prompt.INDEPENDENT_CRITIC_REVIEWER_SYSTEM_PROMPT)

    def render_review_prompt(self, task: str, candidate: str, artifacts: Sequence[ContextArtifact]) -> str:
        # Encode the exact allowlisted inputs as JSON so candidate text remains untrusted data.
        self._validate_exact_inputs(candidate, artifacts)
        payload = {
            "original_task": task,
            "candidate": candidate,
            "permitted_artifacts": [
                {"name": artifact.name, "artifact_type": artifact.artifact_type, "content": artifact.content}
                for artifact in artifacts
            ],
        }
        template = self.review_prompt or Prompts().get(Prompt.INDEPENDENT_CRITIC_REVIEW_PROMPT)
        return template.format(review_payload=json.dumps(payload, ensure_ascii=False))

    def normalize_review(self, value: object) -> dict[str, Any]:
        # Convert provider output into the bounded, explicitly unadjudicated metadata contract.
        raw = _review_mapping(value)
        verdict = _required_enum(raw, "verdict", _VERDICTS)
        summary, summary_truncated = _bounded_required_text(raw, "summary", self.max_critique_chars)
        findings, findings_truncated, fields_truncated = self._normalize_findings(raw.get("findings"))
        return {
            "verdict": verdict,
            "summary": summary,
            "findings": findings,
            "adjudicated": False,
            "truncation": {
                "summary": summary_truncated,
                "findings": findings_truncated,
                "finding_fields": fields_truncated,
            },
        }

    def review_output_schema(self) -> dict[str, Any]:
        # Provide a strict provider-facing schema while retaining deterministic local validation.
        finding = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "severity": {"type": "string", "enum": sorted(_SEVERITIES)},
                "category": {"type": "string"},
                "claim": {"type": "string"},
                "candidate_excerpt": {"type": "string"},
                "evidence": {"type": "string"},
                "recommendation": {"type": "string"},
            },
            "required": ["severity", "category", "claim", "candidate_excerpt", "evidence", "recommendation"],
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "verdict": {"type": "string", "enum": sorted(_VERDICTS)},
                "summary": {"type": "string"},
                "findings": {"type": "array", "items": finding},
            },
            "required": ["verdict", "summary", "findings"],
        }

    def _validate_reviewer_identity(self) -> None:
        # A dedicated reviewer is meaningful only when provider and model are supplied together.
        if (self.reviewer_provider is None) != (self.reviewer_model is None):
            raise ConfigurationError("reviewer_provider and reviewer_model must be provided together.")
        if self.reviewer_provider is None:
            return
        ProviderModelRegistry.validate_provider(self.reviewer_provider)
        ProviderModelRegistry.validate_model(self.reviewer_model or "")

    def _validate_limits(self) -> None:
        # Reject non-positive or unreasonably large budgets before constructing a reviewer runtime.
        _validate_limit(self.reviewer_max_iterations, "reviewer_max_iterations", _MAX_REVIEWER_ITERATIONS)
        _validate_limit(self.reviewer_max_tokens, "reviewer_max_tokens", _MAX_CHARACTER_LIMIT)
        _validate_limit(self.reviewer_max_tool_calls, "reviewer_max_tool_calls", _MAX_REVIEWER_TOOL_CALLS)
        _validate_limit(self.max_candidate_chars, "max_candidate_chars", _MAX_CHARACTER_LIMIT)
        _validate_limit(self.max_artifact_chars, "max_artifact_chars", _MAX_CHARACTER_LIMIT)
        _validate_limit(self.max_total_artifact_chars, "max_total_artifact_chars", _MAX_CHARACTER_LIMIT)
        _validate_limit(self.max_critique_chars, "max_critique_chars", _MAX_CHARACTER_LIMIT)
        _validate_limit(self.max_findings, "max_findings", _MAX_FINDINGS)
        _validate_limit(self.max_finding_chars, "max_finding_chars", _MAX_CHARACTER_LIMIT)

    def _validate_exact_inputs(self, candidate: str, artifacts: Sequence[ContextArtifact]) -> None:
        # Exact evidence is either admitted whole or rejected; it is never silently truncated.
        if len(candidate) > self.max_candidate_chars:
            raise ConfigurationError(f"candidate length {len(candidate)} exceeds max_candidate_chars={self.max_candidate_chars}.")
        total = 0
        for artifact in artifacts:
            length = len(artifact.content)
            if length > self.max_artifact_chars:
                raise ConfigurationError(f"artifact {artifact.name!r} length {length} exceeds max_artifact_chars={self.max_artifact_chars}.")
            total += length
        if total > self.max_total_artifact_chars:
            raise ConfigurationError(f"permitted artifact content length {total} exceeds max_total_artifact_chars={self.max_total_artifact_chars}.")

    def _normalize_findings(self, value: object) -> tuple[tuple[dict[str, str], ...], bool, bool]:
        # Normalize atomic findings in model order and expose every output truncation decision.
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ConfigurationError("critic findings must be a JSON array.")
        raw_findings = tuple(value)
        normalized = tuple(self._normalize_finding(item) for item in raw_findings[: self.max_findings])
        fields_truncated = any(item.pop("_truncated") == "true" for item in normalized)
        return normalized, len(raw_findings) > self.max_findings, fields_truncated

    def _normalize_finding(self, value: object) -> dict[str, str]:
        # Validate one proposed finding without granting it adjudicated status.
        if not isinstance(value, Mapping):
            raise ConfigurationError("each critic finding must be a JSON object.")
        severity = _required_enum(value, "severity", _SEVERITIES)
        fields: dict[str, str] = {"severity": severity}
        truncated = False
        for name in ("category", "claim", "candidate_excerpt", "evidence", "recommendation"):
            allow_empty = name == "candidate_excerpt"
            if name == "candidate_excerpt" and name not in value:
                fields[name] = ""
                continue
            text, was_truncated = _bounded_text(value, name, self.max_finding_chars, allow_empty=allow_empty)
            fields[name] = text
            truncated = truncated or was_truncated
        fields["_truncated"] = str(truncated).lower()
        return fields


def _validate_names(value: Sequence[str], field_name: str) -> tuple[str, ...]:
    # Normalize exact allowlists while rejecting blanks, non-strings, and duplicates.
    if isinstance(value, (str, bytes)):
        raise ConfigurationError(f"{field_name} must be a sequence of names, not a string.")
    names = tuple(value)
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ConfigurationError(f"{field_name} entries must be non-empty strings.")
    if len(set(names)) != len(names):
        raise ConfigurationError(f"{field_name} must not contain duplicate names.")
    return names


def _validate_failure_policy(value: CriticFailurePolicy | str) -> CriticFailurePolicy:
    # Coerce string policies into the public enum and report unsupported values clearly.
    try:
        return CriticFailurePolicy(value)
    except ValueError as exc:
        raise ConfigurationError(f"Unsupported critic failure_policy: {value!r}.") from exc


def _validate_limit(value: int, field_name: str, maximum: int) -> None:
    # Enforce integer, positive, safeguard-bounded configuration values.
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"{field_name} must be a positive integer.")
    if value > maximum:
        raise ConfigurationError(f"{field_name} ({value}) exceeds the safeguard limit of {maximum}.")


def _validate_prompt_override(value: str | None, field_name: str) -> None:
    # Reject blank prompt overrides because they erase an isolation instruction boundary.
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ConfigurationError(f"{field_name} must be a non-empty string when provided.")


def _validate_review_prompt(value: str | None) -> None:
    # Require the one exact payload placeholder in custom review templates.
    _validate_prompt_override(value, "review_prompt")
    if value is None:
        return
    found = {name for _, name, _, _ in string.Formatter().parse(value) if name is not None}
    missing = _REQUIRED_REVIEW_PLACEHOLDERS - found
    if missing:
        raise ConfigurationError(f"review_prompt is missing required formatting placeholders: {sorted(missing)}.")


def _validate_metadata(value: Mapping[str, Any]) -> None:
    # Keep configuration metadata structurally safe for result publication.
    if not isinstance(value, Mapping):
        raise ConfigurationError("metadata must be a mapping.")
    for key in value:
        if not isinstance(key, str):
            raise ConfigurationError(f"metadata keys must be strings, found {type(key).__name__}.")


def _review_mapping(value: object) -> Mapping[str, Any]:
    # Accept provider-structured objects or JSON text, stripping a single code fence.
    if hasattr(value, "model_dump") and callable(value.model_dump):
        value = value.model_dump()
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        raise ConfigurationError("critic output must be a JSON object or JSON object string.")
    text = value.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ConfigurationError(f"critic output is not valid JSON: {exc}.") from exc
    if not isinstance(parsed, Mapping):
        raise ConfigurationError("critic output JSON must be an object.")
    return parsed


def _required_enum(value: Mapping[str, Any], field_name: str, allowed: set[str]) -> str:
    # Validate exact machine-readable labels without coercing arbitrary model values.
    raw = value.get(field_name)
    if not isinstance(raw, str) or raw not in allowed:
        raise ConfigurationError(f"critic {field_name} must be one of {sorted(allowed)}, found {raw!r}.")
    return raw


def _bounded_required_text(value: Mapping[str, Any], field_name: str, maximum: int) -> tuple[str, bool]:
    # Bound required reviewer text while preserving an explicit truncation signal.
    return _bounded_text(value, field_name, maximum, allow_empty=False)


def _bounded_text(value: Mapping[str, Any], field_name: str, maximum: int, *, allow_empty: bool) -> tuple[str, bool]:
    # Validate one textual report field and apply only output-side metadata bounds.
    raw = value.get(field_name)
    if not isinstance(raw, str) or (not allow_empty and not raw.strip()):
        qualifier = "a string" if allow_empty else "a non-empty string"
        raise ConfigurationError(f"critic {field_name} must be {qualifier}.")
    if len(raw) <= maximum:
        return raw, False
    marker = "...[truncated]"
    return raw[: max(0, maximum - len(marker))] + marker, True


__all__ = [
    "CriticFailurePolicy",
    "IndependentCriticAlgorithm",
]
