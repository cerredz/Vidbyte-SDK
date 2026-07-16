"""Context Protocol Header

FILE: vidbyte/context/algorithms/pairwise_tournament.py
PURPOSE: Owns the immutable public configuration, policies, defensive limits, and
    catalog-backed prompt rendering for the pairwise-tournament algorithm.
ROLE IN CODEBASE: ContextWindowAlgorithm stores this configuration; the runtime
    adapter consumes it; presets and public namespaces re-export it.
ARCHITECTURE NOTE: This file validates static policy only. Provider credentials,
    resolved source count, artifacts, tools, and live runner state are preflighted by
    vidbyte/agents/algorithms/pairwise_tournament.py.
FUNCTION INVENTORY: PairwiseTournamentAlgorithm renders the judge prompts and validates
    every bounded setting. Private validators each own one configuration invariant.
COMMON MODIFICATION PATTERNS: Add a setting here, document it in both READMEs, then
    consume it explicitly in the runtime adapter; never read undeclared metadata as policy.
WHAT NOT TO DO: Do not execute models, inspect producer context, build a bracket, or
    accept candidate IDs from model-authored payloads in this module.
KNOWN EDGE CASES: A missing provider map is valid until runtime environment resolution;
    zero tiebreak attempts is valid and makes the first disagreement final.
RELATED DOCS: docs/design/context-window-pairwise-tournament.md.
TESTS: Existing repository regressions plus manual configuration checks; no new tests
    are authorized by this design-doc-no-tests implementation.
"""

from __future__ import annotations

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

_MAX_CANDIDATES = 16
_MAX_CHARS = 1_000_000
_MAX_EVIDENCE_CHARS = 2_000_000
_MAX_TIMEOUT_SECONDS = 3600.0
_MAX_CONFIG_METADATA_CHARS = 20_000
_REQUIRED_JUDGE_PLACEHOLDERS = {"payload_json"}


class TournamentSeeding(str, Enum):
    """Deterministic seed-order strategies supported by the tournament."""

    INPUT_ORDER = "input_order"
    CONTENT_HASH = "content_hash"


class UnresolvedMatchPolicy(str, Enum):
    """Policy used after every bounded bidirectional attempt remains unresolved."""

    RAISE = "raise"
    LOWER_SEED = "lower_seed"


class MatchFailurePolicy(str, Enum):
    """Policy used after a leg or match fails and sibling work is settled."""

    RAISE = "raise"
    LOWER_SEED = "lower_seed"


@dataclass(frozen=True, slots=True)
class PairwiseTournamentAlgorithm:
    """Immutable public configuration for deterministic pairwise candidate selection."""

    provider_models: Mapping[str, str] | None = None
    require_all_candidates: bool = True
    seeding: TournamentSeeding = TournamentSeeding.INPUT_ORDER
    judge_provider: str | None = None
    judge_model: str | None = None
    judge_artifact_names: tuple[str, ...] = ()
    judge_tool_names: tuple[str, ...] = ()
    unresolved_policy: UnresolvedMatchPolicy = UnresolvedMatchPolicy.RAISE
    match_failure_policy: MatchFailurePolicy = MatchFailurePolicy.RAISE
    max_concurrency: int = 4
    max_tiebreak_attempts: int = 1
    leg_timeout_seconds: float = 120.0
    match_timeout_seconds: float = 300.0
    round_timeout_seconds: float | None = None
    max_candidate_chars: int = 100_000
    max_artifact_chars: int = 50_000
    max_total_artifact_chars: int = 100_000
    max_judge_output_chars: int = 20_000
    max_summary_chars: int = 4_000
    max_criteria: int = 12
    judge_system_prompt: str | None = None
    judge_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates static settings before any candidate or judge model can be invoked.
        if not isinstance(self.require_all_candidates, bool):
            raise ConfigurationError("require_all_candidates must be a boolean.")
        object.__setattr__(self, "seeding", _coerce_enum(self.seeding, TournamentSeeding, "seeding"))
        object.__setattr__(self, "unresolved_policy", _coerce_enum(self.unresolved_policy, UnresolvedMatchPolicy, "unresolved_policy"))
        object.__setattr__(self, "match_failure_policy", _coerce_enum(self.match_failure_policy, MatchFailurePolicy, "match_failure_policy"))
        self._validate_provider_models()
        self._validate_judge_transport()
        _validate_unique_names(self.judge_artifact_names, "judge_artifact_names")
        _validate_unique_names(self.judge_tool_names, "judge_tool_names")
        _validate_count(self.max_concurrency, "max_concurrency", minimum=1, maximum=_MAX_CANDIDATES)
        _validate_count(self.max_tiebreak_attempts, "max_tiebreak_attempts", minimum=0, maximum=3)
        _validate_timeout(self.leg_timeout_seconds, "leg_timeout_seconds")
        _validate_timeout(self.match_timeout_seconds, "match_timeout_seconds")
        _validate_optional_timeout(self.round_timeout_seconds, "round_timeout_seconds")
        _validate_count(self.max_candidate_chars, "max_candidate_chars", minimum=1, maximum=_MAX_CHARS)
        _validate_count(self.max_artifact_chars, "max_artifact_chars", minimum=1, maximum=_MAX_CHARS)
        _validate_count(self.max_total_artifact_chars, "max_total_artifact_chars", minimum=1, maximum=_MAX_EVIDENCE_CHARS)
        _validate_count(self.max_judge_output_chars, "max_judge_output_chars", minimum=1, maximum=_MAX_CHARS)
        _validate_count(self.max_summary_chars, "max_summary_chars", minimum=1, maximum=4_000)
        _validate_count(self.max_criteria, "max_criteria", minimum=0, maximum=16)
        _validate_prompt_override(self.judge_system_prompt, "judge_system_prompt")
        _validate_judge_prompt(self.judge_prompt)
        _validate_metadata(self.metadata)
        if self.provider_models is not None:
            object.__setattr__(self, "provider_models", MappingProxyType(dict(self.provider_models)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def judge_system_prompt_text(self) -> str:
        # Returns the isolated judge role prompt from an override or the prompt catalog.
        return self.judge_system_prompt or Prompts().get(Prompt.PAIRWISE_TOURNAMENT_JUDGE_SYSTEM_PROMPT)

    def render_judge_prompt(self, task: str, slot_a: str, slot_b: str) -> str:
        # Serializes the exact task and candidate strings into the validated user template.
        payload = {"original_task": task, "slot_A": slot_a, "slot_B": slot_b}
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        template = self.judge_prompt or Prompts().get(Prompt.PAIRWISE_TOURNAMENT_JUDGE_PROMPT)
        return template.format(payload_json=payload_json)

    def _validate_provider_models(self) -> None:
        # Ensures an explicit candidate-source map is ordered, distinct, and within bounds.
        if self.provider_models is None:
            return
        if not isinstance(self.provider_models, dict):
            raise ConfigurationError("provider_models must be an insertion-ordered dict when provided.")
        _validate_count(len(self.provider_models), "provider_models source count", minimum=2, maximum=_MAX_CANDIDATES)
        if any(not isinstance(provider, str) or not isinstance(model, str) for provider, model in self.provider_models.items()):
            raise ConfigurationError("provider_models keys and values must be strings.")
        ProviderModelRegistry.validate_provider_models_map(self.provider_models)

    def _validate_judge_transport(self) -> None:
        # Requires a complete optional judge provider/model pair and validates both values.
        if (self.judge_provider is None) != (self.judge_model is None):
            raise ConfigurationError("judge_provider and judge_model must be supplied together or both omitted.")
        if self.judge_provider is not None and self.judge_model is not None:
            if not isinstance(self.judge_provider, str) or not isinstance(self.judge_model, str):
                raise ConfigurationError("judge_provider and judge_model must be strings when provided.")
            ProviderModelRegistry.validate_provider(self.judge_provider)
            ProviderModelRegistry.validate_model(self.judge_model)


def _validate_count(value: int, field_name: str, *, minimum: int, maximum: int) -> None:
    # Rejects booleans and integers outside one named defensive range.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"{field_name} must be an integer, not {type(value).__name__}.")
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{field_name} must be between {minimum} and {maximum}, got {value}.")


def _coerce_enum(value: Any, enum_type: type[Enum], field_name: str) -> Enum:
    # Normalizes valid string policies and turns unknown values into ConfigurationError.
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = tuple(member.value for member in enum_type)
        raise ConfigurationError(f"{field_name} must be one of {allowed}.") from exc


def _validate_timeout(value: float, field_name: str) -> None:
    # Rejects booleans, non-numeric values, and unsafe timeout values.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{field_name} must be a positive number.")
    if not 0 < float(value) <= _MAX_TIMEOUT_SECONDS:
        raise ConfigurationError(f"{field_name} must be greater than zero and at most {_MAX_TIMEOUT_SECONDS}.")


def _validate_optional_timeout(value: float | None, field_name: str) -> None:
    # Applies timeout validation only when an optional timeout is configured.
    if value is not None:
        _validate_timeout(value, field_name)


def _validate_unique_names(values: tuple[str, ...], field_name: str) -> None:
    # Requires exact nonblank resource names with no duplicate selector ambiguity.
    if isinstance(values, str) or not isinstance(values, tuple):
        raise ConfigurationError(f"{field_name} must be a tuple of exact names.")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ConfigurationError(f"{field_name} entries must be exact nonblank strings without surrounding whitespace.")
        normalized.append(value)
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError(f"{field_name} cannot contain duplicate names.")


def _validate_prompt_override(value: str | None, field_name: str) -> None:
    # Rejects blank optional system-prompt overrides.
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ConfigurationError(f"{field_name} must be a non-empty string when provided.")


def _validate_judge_prompt(value: str | None) -> None:
    # Requires the sole payload placeholder so untrusted evidence is rendered as one unit.
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError("judge_prompt must be a non-empty string when provided.")
    found = {name for _, name, _, _ in string.Formatter().parse(value) if name is not None}
    if found != _REQUIRED_JUDGE_PLACEHOLDERS:
        raise ConfigurationError("judge_prompt must contain exactly the {payload_json} formatting placeholder.")


def _validate_metadata(metadata: Mapping[str, Any]) -> None:
    # Requires bounded JSON-safe configured metadata with string keys.
    if not isinstance(metadata, Mapping):
        raise ConfigurationError("metadata must be a mapping.")
    if any(not isinstance(key, str) for key in metadata):
        raise ConfigurationError("metadata keys must be strings.")
    try:
        encoded = json.dumps(dict(metadata), sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("metadata must contain only JSON-serializable values.") from exc
    if len(encoded) > _MAX_CONFIG_METADATA_CHARS:
        raise ConfigurationError(f"metadata exceeds the {_MAX_CONFIG_METADATA_CHARS}-character safeguard.")


__all__ = [
    "MatchFailurePolicy",
    "PairwiseTournamentAlgorithm",
    "TournamentSeeding",
    "UnresolvedMatchPolicy",
]
