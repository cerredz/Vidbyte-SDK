"""Context Protocol Header

FILE: vidbyte/context/algorithms/parallel_panel.py
PURPOSE: Defines the immutable public policy for independent, first-round
parallel review of one completed producer candidate. Runtime orchestration does
not belong here; it is owned by vidbyte/agents/algorithms/parallel_panel.py.
ROLE IN CODEBASE: ContextWindowPresets constructs this config, the wrapper in
tool_results.py admits it, and ParallelPanelRuntimeAlgorithm consumes it.
ARCHITECTURE NOTE: Validation keeps unsafe or ambiguous panel settings from
reaching asynchronous execution. See docs/design/context-window-parallel-panel.md.
FUNCTION INVENTORY: ParallelPanelAlgorithm validates limits, prompt overrides,
artifact allowlists, and caller metadata. Existing regression tests exercise the
shared configuration and prompt-catalog contracts; this no-tests feature adds no
dedicated test file.
COMMON MODIFICATION PATTERNS: Add a public field here, thread it through the
preset, then consume it in the runtime adapter and document its behavior.
WHAT NOT TO DO: 1. Do not execute reviewers here. 2. Do not add producer state
to reviewer inputs. 3. Do not silently truncate candidate or evidence content.
KNOWN EDGE CASES: bool is an int subclass and is rejected for integer fields;
custom prompts may repeat required placeholders but may not add new inputs.
COMMON ERRORS: ConfigurationError identifies the invalid public field.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/context-window-parallel-panel.md
TESTS: Existing configuration and prompt-catalog regression suites; no new test
file is permitted by the approved design-doc-no-tests manifest.
"""

from __future__ import annotations

import math
import string
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.prompts import Prompts

_MAX_REVIEWERS = 16
_MAX_TIMEOUT_SECONDS = 3_600.0
_MAX_CANDIDATE_CHARS = 100_000
_MAX_REVIEW_CHARS = 100_000
_MAX_ARTIFACT_CHARS = 100_000
_MAX_TOTAL_ARTIFACT_CHARS = 1_000_000
_MAX_ARTIFACT_NAME_CHARS = 256
_REQUIRED_REVIEW_PROMPT_FIELDS = {"task", "candidate", "artifacts"}


@dataclass(frozen=True, slots=True)
class ParallelPanelAlgorithm:
    """Validated public configuration for independent parallel candidate review."""

    reviewer_count: int = 3
    min_successful_reviews: int = 2
    max_concurrency: int | None = None
    per_reviewer_timeout_seconds: float | None = None
    panel_timeout_seconds: float | None = None
    max_candidate_chars: int = 50_000
    max_review_chars: int = 6_000
    artifact_names: tuple[str, ...] = ()
    max_artifact_chars: int = 4_000
    max_total_artifact_chars: int = 16_000
    reviewer_system_prompt: str | None = None
    reviewer_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Rejects invalid panel sizes, safety limits, prompt shapes, and metadata before execution.
        _validate_integer_range("reviewer_count", self.reviewer_count, 2, _MAX_REVIEWERS)
        _validate_integer_range("min_successful_reviews", self.min_successful_reviews, 2, self.reviewer_count)
        if self.max_concurrency is not None:
            _validate_integer_range("max_concurrency", self.max_concurrency, 2, self.reviewer_count)
        _validate_optional_timeout("per_reviewer_timeout_seconds", self.per_reviewer_timeout_seconds)
        _validate_optional_timeout("panel_timeout_seconds", self.panel_timeout_seconds)
        _validate_character_limit("max_candidate_chars", self.max_candidate_chars, _MAX_CANDIDATE_CHARS)
        _validate_character_limit("max_review_chars", self.max_review_chars, _MAX_REVIEW_CHARS)
        _validate_character_limit("max_artifact_chars", self.max_artifact_chars, _MAX_ARTIFACT_CHARS)
        _validate_character_limit("max_total_artifact_chars", self.max_total_artifact_chars, _MAX_TOTAL_ARTIFACT_CHARS)
        _validate_artifact_names(self.artifact_names)
        _validate_optional_prompt("reviewer_system_prompt", self.reviewer_system_prompt)
        _validate_optional_prompt("reviewer_prompt", self.reviewer_prompt)
        _validate_review_prompt_fields(self.reviewer_prompt)
        _validate_metadata(self.metadata)

    def reviewer_system_prompt_text(self) -> str:
        # Returns the caller override or the packaged independent-reviewer system prompt.
        return self.reviewer_system_prompt or Prompts().get(Prompt.PARALLEL_PANEL_REVIEWER_SYSTEM_PROMPT)

    def render_reviewer_prompt(self, *, task: str, candidate: str, artifacts: str) -> str:
        # Renders exactly the three approved reviewer inputs into one immutable prompt snapshot.
        template = self.reviewer_prompt or Prompts().get(Prompt.PARALLEL_PANEL_REVIEW_PROMPT)
        return template.format(task=task, candidate=candidate, artifacts=artifacts)


def _validate_integer_range(field_name: str, value: int, minimum: int, maximum: int) -> None:
    # Rejects bool and integer values outside the field's inclusive safety range.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"{field_name} must be an integer, not {type(value).__name__}.", details={"field": field_name})
    if value < minimum or value > maximum:
        raise ConfigurationError(f"{field_name} must be between {minimum} and {maximum}, inclusive.", details={"field": field_name, "minimum": minimum, "maximum": maximum, "actual": value})


def _validate_optional_timeout(field_name: str, value: float | None) -> None:
    # Rejects non-numeric, non-finite, non-positive, or excessively long optional timeouts.
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{field_name} must be a finite positive number when provided.", details={"field": field_name})
    if not math.isfinite(float(value)) or float(value) <= 0 or float(value) > _MAX_TIMEOUT_SECONDS:
        raise ConfigurationError(f"{field_name} must be greater than zero and no more than {_MAX_TIMEOUT_SECONDS:g} seconds.", details={"field": field_name, "actual": value})


def _validate_character_limit(field_name: str, value: int, maximum: int) -> None:
    # Rejects character limits that cannot bound content safely and predictably.
    _validate_integer_range(field_name, value, 1, maximum)


def _validate_artifact_names(names: tuple[str, ...]) -> None:
    # Requires an immutable, unique, nonblank allowlist so evidence selection is deterministic.
    if not isinstance(names, tuple):
        raise ConfigurationError("artifact_names must be a tuple of unique nonblank strings.", details={"field": "artifact_names"})
    normalized: list[str] = []
    for index, name in enumerate(names):
        if not isinstance(name, str) or not name.strip():
            raise ConfigurationError("artifact_names must contain only nonblank strings.", details={"field": "artifact_names", "index": index})
        if len(name) > _MAX_ARTIFACT_NAME_CHARS:
            raise ConfigurationError(f"artifact_names entries cannot exceed {_MAX_ARTIFACT_NAME_CHARS} characters.", details={"field": "artifact_names", "index": index, "actual_chars": len(name)})
        normalized.append(name)
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError("artifact_names must not contain duplicate names.", details={"field": "artifact_names"})


def _validate_optional_prompt(field_name: str, value: str | None) -> None:
    # Rejects provided prompt overrides that contain no usable instructions.
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ConfigurationError(f"{field_name} must be a nonblank string when provided.", details={"field": field_name})


def _validate_review_prompt_fields(template: str | None) -> None:
    # Restricts custom reviewer templates to the task, candidate, and permitted-artifact boundary.
    if template is None:
        return
    try:
        parsed = tuple(string.Formatter().parse(template))
    except ValueError as exc:
        raise ConfigurationError("reviewer_prompt contains invalid formatting syntax.", details={"field": "reviewer_prompt"}) from exc
    found = {name for _, name, _, _ in parsed if name is not None}
    if found != _REQUIRED_REVIEW_PROMPT_FIELDS:
        raise ConfigurationError("reviewer_prompt placeholders must be exactly {task}, {candidate}, and {artifacts}.", details={"field": "reviewer_prompt", "found": tuple(sorted(found))})
    if any(format_spec or conversion for _, name, format_spec, conversion in parsed if name is not None):
        raise ConfigurationError("reviewer_prompt placeholders cannot use conversion flags or format specifications.", details={"field": "reviewer_prompt"})


def _validate_metadata(metadata: Mapping[str, Any]) -> None:
    # Rejects non-mapping metadata and non-string keys before the runtime snapshots it.
    if not isinstance(metadata, Mapping):
        raise ConfigurationError("metadata must be a mapping.", details={"field": "metadata"})
    for key in metadata:
        if not isinstance(key, str):
            raise ConfigurationError(f"metadata keys must be strings, found {type(key).__name__}.", details={"field": "metadata"})


__all__ = ["ParallelPanelAlgorithm"]
