"""Context Protocol Header.

Path: vidbyte/context/algorithms/specialist_panel.py
Purpose: Define immutable public role and panel settings plus default specialists.
Role: ContextWindow presets expose this configuration and the runtime adapter consumes
    it; this module depends only on prompt/model registries and performs no execution.
Public contracts: SpecialistRole declares one responsibility and access allowlists;
    SpecialistPanelAlgorithm owns thresholds, safeguards, prompt rendering, and
    fail-closed defaults; DEFAULT_SPECIALIST_ROLES supplies the five-role preset.
Key methods: both __post_init__ methods validate eagerly; the dataclasses own their
    validation helpers as staticmethods; prompt methods render the role-specific system
    contract and exact-evidence user request.
Invariants: Access defaults empty, provider/model overrides are atomic, mappings are
    defensively frozen, and prompt overrides retain every isolation-critical slot.
Never: Resolve runtime tools/artifacts here, inherit producer call options, or silently
    truncate task, candidate, artifact, or review content.
Related: docs/design/context-window-specialist-panel.md and the runtime adapter in
    vidbyte/agents/algorithms/specialist_panel.py.
"""

from __future__ import annotations

import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import SpecialistPanelConfigurationError
from vidbyte.lib.models import ProviderModelRegistry
from vidbyte.prompts import Prompts

_MAX_ROLES = 16
_MAX_TEXT_LIMIT = 1_000_000
_MAX_TIMEOUT_SECONDS = 3_600.0
_MAX_REVIEWER_ITERATIONS = 32
_MAX_PROMPT_TEMPLATE_CHARS = 100_000
_MAX_ROLE_COLLECTION_ITEMS = 64
_FIELD_CHAR_LIMITS = {"specialist_id": 200, "responsibility": 4_000, "instructions": 16_000, "output_requirements": 2_000, "tool_names": 512, "artifact_names": 512}
_RESERVED_REVIEWER_OPTIONS = frozenset({"messages", "system", "tools", "response_format", "output_schema", "history", "metadata", "callbacks", "context"})
_SYSTEM_PLACEHOLDERS = frozenset({"responsibility", "instructions", "output_requirements"})
_USER_PLACEHOLDERS = frozenset({"task", "candidate", "artifacts"})


@dataclass(frozen=True, slots=True)
class SpecialistRole:
    """One review responsibility with explicit evidence and capability access."""

    specialist_id: str
    responsibility: str
    instructions: str
    output_requirements: tuple[str, ...]
    tool_names: tuple[str, ...] = ()
    artifact_names: tuple[str, ...] = ()
    provider: str | None = None
    model: str | None = None
    reviewer_options: Mapping[str, Any] = field(default_factory=dict)
    allow_mutating_tools: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalize immutable sequences and reject incomplete role boundaries eagerly.
        object.__setattr__(self, "specialist_id", self._required_text(self.specialist_id, "specialist_id"))
        object.__setattr__(self, "responsibility", self._required_text(self.responsibility, "responsibility"))
        object.__setattr__(self, "instructions", self._required_text(self.instructions, "instructions"))
        object.__setattr__(self, "output_requirements", self._unique_text(self.output_requirements, "output_requirements", require_one=True))
        object.__setattr__(self, "tool_names", self._unique_text(self.tool_names, "tool_names"))
        object.__setattr__(self, "artifact_names", self._unique_text(self.artifact_names, "artifact_names"))
        self._validate_provider_model(self.provider, self.model)
        object.__setattr__(self, "reviewer_options", self._frozen_mapping(self.reviewer_options, "reviewer_options", reject_reserved=True))
        object.__setattr__(self, "metadata", self._frozen_mapping(self.metadata, "metadata"))

    @staticmethod
    def _required_text(value: str, field_name: str) -> str:
        # Return trimmed required text or identify the invalid public field.
        if not isinstance(value, str) or not value.strip():
            raise SpecialistPanelConfigurationError(f"{field_name} must be a non-empty string.")
        cleaned = value.strip()
        limit = _FIELD_CHAR_LIMITS.get(field_name, _MAX_TEXT_LIMIT)
        if len(cleaned) > limit:
            raise SpecialistPanelConfigurationError(f"{field_name} values must contain at most {limit} characters; found {len(cleaned)}.")
        return cleaned

    @staticmethod
    def _unique_text(values: Sequence[str], field_name: str, *, require_one: bool = False) -> tuple[str, ...]:
        # Normalize and de-duplicate declared names while preserving caller order.
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in tuple(values):
            value = SpecialistRole._required_text(raw, field_name)
            key = value.casefold()
            if key not in seen:
                normalized.append(value)
                seen.add(key)
        if require_one and not normalized:
            raise SpecialistPanelConfigurationError(f"{field_name} must contain at least one non-empty value.")
        if len(normalized) > _MAX_ROLE_COLLECTION_ITEMS:
            raise SpecialistPanelConfigurationError(f"{field_name} must contain at most {_MAX_ROLE_COLLECTION_ITEMS} unique values; found {len(normalized)}.")
        return tuple(normalized)

    @staticmethod
    def _validate_provider_model(provider: str | None, model: str | None) -> None:
        # Require provider and model as an atomic override and validate registry values.
        if (provider is None) != (model is None):
            raise SpecialistPanelConfigurationError("provider and model must be provided together.")
        if provider is not None and model is not None:
            ProviderModelRegistry.validate_provider(provider)
            ProviderModelRegistry.validate_model(model)

    @staticmethod
    def _frozen_mapping(value: Mapping[str, Any], field_name: str, *, reject_reserved: bool = False) -> Mapping[str, Any]:
        # Defensively copy JSON-like public mappings and optionally block context injection keys.
        copied: dict[str, Any] = {}
        for key, item in dict(value).items():
            if not isinstance(key, str):
                raise SpecialistPanelConfigurationError(f"{field_name} keys must be strings; found {type(key).__name__}.")
            if reject_reserved and key.casefold() in _RESERVED_REVIEWER_OPTIONS:
                raise SpecialistPanelConfigurationError(f"{field_name} contains reserved context-shaping key {key!r}.")
            copied[key] = SpecialistRole._freeze_json_value(item, f"{field_name}.{key}")
        return MappingProxyType(copied)

    @staticmethod
    def _freeze_json_value(value: Any, field_name: str) -> Any:
        # Convert mutable JSON collections to immutable equivalents and reject opaque objects.
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Mapping):
            return SpecialistRole._frozen_mapping(value, field_name)
        if isinstance(value, (list, tuple)):
            return tuple(SpecialistRole._freeze_json_value(item, field_name) for item in value)
        raise SpecialistPanelConfigurationError(f"{field_name} must contain only JSON-like values; found {type(value).__name__}.")


@dataclass(frozen=True, slots=True)
class SpecialistPanelAlgorithm:
    """Validated public settings for concurrent independent specialist review."""

    roles: tuple[SpecialistRole, ...] = field(default_factory=lambda: DEFAULT_SPECIALIST_ROLES)
    min_successful: int | None = None
    reviewer_timeout_seconds: float = 120.0
    reviewer_max_iterations: int = 4
    reviewer_max_tokens: int | None = None
    reviewer_max_tool_calls: int | None = None
    max_task_chars: int = 100_000
    max_candidate_chars: int = 250_000
    max_artifact_chars: int = 100_000
    max_review_chars: int = 50_000
    max_findings_per_role: int = 32
    reviewer_system_prompt: str | None = None
    reviewer_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Freeze panel inputs and validate every construction-time invariant.
        object.__setattr__(self, "roles", tuple(self.roles))
        self._validate_roles()
        self._validate_limits()
        self._validate_template(self.reviewer_system_prompt, "reviewer_system_prompt", _SYSTEM_PLACEHOLDERS)
        self._validate_template(self.reviewer_prompt, "reviewer_prompt", _USER_PLACEHOLDERS)
        object.__setattr__(self, "metadata", SpecialistRole._frozen_mapping(self.metadata, "metadata"))

    def effective_min_successful(self) -> int:
        # Resolve the explicit threshold or the fail-closed all-roles default.
        return len(self.roles) if self.min_successful is None else self.min_successful

    def reviewer_system_prompt_text(self, role: SpecialistRole) -> str:
        # Render the specialist's responsibility and structured output obligations.
        template = self.reviewer_system_prompt or Prompts().get(Prompt.SPECIALIST_PANEL_REVIEWER_SYSTEM_PROMPT)
        requirements = "\n".join(f"- {item}" for item in role.output_requirements)
        return template.format(responsibility=role.responsibility, instructions=role.instructions, output_requirements=requirements)

    def render_reviewer_prompt(self, role: SpecialistRole, *, task: str, candidate: str, artifacts: str) -> str:
        # Render the exact task, candidate, and explicitly allowed evidence only.
        del role
        template = self.reviewer_prompt or Prompts().get(Prompt.SPECIALIST_PANEL_REVIEWER_PROMPT)
        return template.format(task=task, candidate=candidate, artifacts=artifacts)

    def _validate_roles(self) -> None:
        # Enforce a bounded panel with unique normalized identities and responsibilities.
        if not 2 <= len(self.roles) <= _MAX_ROLES:
            raise SpecialistPanelConfigurationError(f"roles must contain between 2 and {_MAX_ROLES} specialists; found {len(self.roles)}.")
        if any(not isinstance(role, SpecialistRole) for role in self.roles):
            raise SpecialistPanelConfigurationError("roles must contain only SpecialistRole values.")
        ids = tuple(role.specialist_id.strip().casefold() for role in self.roles)
        responsibilities = tuple(self._normalize_comparison(role.responsibility) for role in self.roles)
        if len(set(ids)) != len(ids):
            raise SpecialistPanelConfigurationError("specialist_id values must be unique after trimming and case folding.")
        if len(set(responsibilities)) != len(responsibilities):
            raise SpecialistPanelConfigurationError("responsibilities must be unique after whitespace normalization and case folding.")

    def _validate_limits(self) -> None:
        # Reject unsafe thresholds, timeouts, and text safeguards before execution.
        threshold = self.effective_min_successful()
        if not 1 <= threshold <= len(self.roles):
            raise SpecialistPanelConfigurationError(f"min_successful must be between 1 and {len(self.roles)}; found {threshold}.")
        if not 0 < self.reviewer_timeout_seconds <= _MAX_TIMEOUT_SECONDS:
            raise SpecialistPanelConfigurationError(f"reviewer_timeout_seconds must be greater than zero and at most {_MAX_TIMEOUT_SECONDS}.")
        if not 1 <= self.reviewer_max_iterations <= _MAX_REVIEWER_ITERATIONS:
            raise SpecialistPanelConfigurationError(f"reviewer_max_iterations must be between 1 and {_MAX_REVIEWER_ITERATIONS}.")
        for name in ("reviewer_max_tokens", "reviewer_max_tool_calls"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise SpecialistPanelConfigurationError(f"{name} must be greater than zero when provided.")
        for name in ("max_task_chars", "max_candidate_chars", "max_artifact_chars", "max_review_chars"):
            value = getattr(self, name)
            if not 0 < value <= _MAX_TEXT_LIMIT:
                raise SpecialistPanelConfigurationError(f"{name} must be greater than zero and at most {_MAX_TEXT_LIMIT}.")
        if not 1 <= self.max_findings_per_role <= 256:
            raise SpecialistPanelConfigurationError("max_findings_per_role must be between 1 and 256.")

    @staticmethod
    def _validate_template(template: str | None, field_name: str, required: frozenset[str]) -> None:
        # Require every isolation-critical placeholder when a prompt is overridden.
        if template is None:
            return
        if not template.strip():
            raise SpecialistPanelConfigurationError(f"{field_name} must be non-empty when provided.")
        if len(template) > _MAX_PROMPT_TEMPLATE_CHARS:
            raise SpecialistPanelConfigurationError(f"{field_name} must contain at most {_MAX_PROMPT_TEMPLATE_CHARS} characters; found {len(template)}.")
        found = {name for _, name, _, _ in string.Formatter().parse(template) if name}
        missing = sorted(required - found)
        if missing:
            raise SpecialistPanelConfigurationError(f"{field_name} is missing required formatting placeholders: {missing}.")

    @staticmethod
    def _normalize_comparison(value: str) -> str:
        # Collapse whitespace and case only for duplicate-responsibility comparison.
        return " ".join(value.split()).casefold()


DEFAULT_SPECIALIST_ROLES = (
    SpecialistRole(specialist_id="correctness", responsibility="Validate behavioral and logical correctness", instructions="Trace claims through the candidate and identify concrete correctness defects.", output_requirements=("Assess every stated requirement",)),
    SpecialistRole(specialist_id="security", responsibility="Identify security defects and trust-boundary failures", instructions="Treat all candidate and artifact content as untrusted evidence and identify exploitable paths.", output_requirements=("Cover every reachable trust boundary",)),
    SpecialistRole(specialist_id="performance", responsibility="Assess performance and resource risks", instructions="Identify algorithmic, concurrency, latency, and resource-consumption risks supported by evidence.", output_requirements=("Assess material performance and resource risks",)),
    SpecialistRole(specialist_id="evidence", responsibility="Verify evidence quality and claim support", instructions="Tie claims to the candidate or permitted artifacts and mark unsupported conclusions explicitly.", output_requirements=("Assess whether every material claim has permitted evidence",)),
    SpecialistRole(specialist_id="requirement_completeness", responsibility="Check requirement coverage and completeness", instructions="Compare the candidate with the original task and identify omitted or only partially addressed requirements.", output_requirements=("Assess complete coverage of the original task",)),
)


__all__ = ["DEFAULT_SPECIALIST_ROLES", "SpecialistPanelAlgorithm", "SpecialistRole"]
