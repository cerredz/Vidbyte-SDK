"""Context Protocol Header

FILE:
    vidbyte/lib/dataclasses/adversarial.py owns adversarial workflow policy and result records.
PURPOSE:
    Validates the immutable controls enforced by the sequential worker/reviewer
    workflow and stores full review artifacts without owning agent execution.
ROLE IN CODEBASE:
    Imported by vidbyte.agents.adversarial and re-exported through
    vidbyte.lib.dataclasses, vidbyte.agents.settings, and vidbyte.agents.
    The runtime calls the enforcement and forwarding-bound helpers here.
ARCHITECTURE NOTE:
    This is the low-level contract boundary: settings validation and enforcement
    stay separate from child-agent orchestration, prompt rendering, and tracing.
FUNCTION INVENTORY:
    AdversarialSettings validates workflow bounds, resolves specialties, enforces
    review thresholds, and bounds forwarded text. AdversarialReview,
    AdversarialRoundResult, and AdversarialResult are immutable output records.
COMMON MODIFICATION PATTERNS:
    Add only controls the current sequential controller can enforce; update the
    controller, context summary, public docs, and behavioral verification together.
WHAT NOT TO DO IN THIS FILE:
    Do not add provider/model objects, live agents, tools, prompts, or orchestration.
KNOWN EDGE CASES:
    One specialty is shared by every reviewer; an exact-length tuple is index-aligned.
    Duplicate specialties are valid. Forwarding bounds never truncate retained results.
RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/adversarial-agent.md
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/adversarial-agent-settings.md
TEST FILES:
    Existing repository tests and the design-document import/validation smoke checks.
CONCURRENCY MODEL:
    Settings and result records are immutable and safe to share; runtime concurrency
    remains owned by the adversarial controller.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite
from typing import Any

from vidbyte.lib.errors import AdversarialExecutionError, ConfigurationError

_MAX_SPECIALTY_CHARS = 500
_TRUNCATION_MARKER = "...[truncated]"


# @intent executable-settings-only
# These settings are a promise about behavior, not a catalog of possible ideas.
# Every accepted field is enforced by the current sequential controller; adding a
# setting without wiring its behavior would mislead callers about the workflow run.
@dataclass(frozen=True, slots=True)
class AdversarialSettings:
    """Validated controls and enforcement helpers for one adversarial workflow."""

    num_adversaries: int = 1
    adversarial_rounds: int = 1
    min_successful_adversaries: int = 1
    per_adversary_timeout: float | None = None
    max_review_chars: int = 4000
    max_worker_output_chars: int = 12000
    specialties: tuple[str, ...] = ()
    fresh_adversaries_each_round: bool = False
    run_timeout_seconds: float | None = None
    max_child_calls: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "specialties", self._normalize_specialties(self.specialties)
        )
        self._validate_positive_counts()
        self._validate_success_threshold()
        self._validate_timeouts()
        self._validate_specialty_shape()
        self._validate_freshness()
        self._validate_child_call_budget()

    @property
    def required_child_calls(self) -> int:
        """Return the exact child-agent call count for the configured workflow."""

        return 1 + self.adversarial_rounds * (self.num_adversaries + 1)

    def specialty_for(self, adversary_index: int) -> str | None:
        """Resolve the shared or one-based index-aligned reviewer specialty."""

        self._require_adversary_index(adversary_index)
        if not self.specialties:
            return None
        if len(self.specialties) == 1:
            return self.specialties[0]
        return self.specialties[adversary_index - 1]

    @classmethod
    def specialist_panel(
        cls, specialties: Sequence[str], **overrides: Any
    ) -> AdversarialSettings:
        """Build settings with one independent reviewer lens per specialty."""

        conflicts = tuple(
            sorted({"num_adversaries", "specialties"}.intersection(overrides))
        )
        if conflicts:
            raise ConfigurationError(
                "AdversarialSettings.specialist_panel derives reviewer shape from specialties; conflicting overrides are not allowed.",
                details={
                    "file": "vidbyte/lib/dataclasses/adversarial.py",
                    "function": "AdversarialSettings.specialist_panel",
                    "conflicting_fields": conflicts,
                    "expected": "omit num_adversaries and specialties from overrides",
                    "remediation": "Pass specialty lenses as the first argument and use overrides only for workflow controls.",
                },
            )
        normalized = cls._normalize_specialties(specialties)
        if not normalized:
            raise ConfigurationError(
                "AdversarialSettings.specialist_panel requires at least one specialty.",
                details={
                    "file": "vidbyte/lib/dataclasses/adversarial.py",
                    "function": "AdversarialSettings.specialist_panel",
                    "field": "specialties",
                    "actual_count": 0,
                    "expected": "one or more nonblank specialty strings",
                    "remediation": "Provide at least one review lens or construct AdversarialSettings() for generic review.",
                },
            )
        return cls(num_adversaries=len(normalized), specialties=normalized, **overrides)

    def is_review_threshold_met(self, successful: int) -> bool:
        """Return whether enough non-blank reviews permit a worker revision."""

        return successful >= self.min_successful_adversaries

    def enforce_review_threshold(
        self,
        successful: int,
        total: int,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        """Raise an actionable execution error when the configured review floor fails."""

        if self.is_review_threshold_met(successful):
            return
        details: dict[str, Any] = {
            "file": "vidbyte/lib/dataclasses/adversarial.py",
            "function": "AdversarialSettings.enforce_review_threshold",
            "phase": "adversarial_review",
            "successful_reviews": successful,
            "failed_reviews": max(total - successful, 0),
            "required_successful_reviews": self.min_successful_adversaries,
            "expected": "the configured minimum number of non-blank successful reviews",
            "remediation": "Inspect reviewer configuration/timeouts or lower min_successful_adversaries intentionally.",
        }
        if context:
            details.update(context)
        raise AdversarialExecutionError(
            f"Adversarial review produced {successful} successful review(s); {self.min_successful_adversaries} required.",
            details=details,
        )

    def bound_review_text(self, text: str) -> str:
        """Bound review content before it is forwarded to the worker."""

        return self._bound(text, self.max_review_chars)

    def bound_worker_output(self, text: str) -> str:
        """Bound a worker snapshot before it is forwarded to reviewers."""

        return self._bound(text, self.max_worker_output_chars)

    def _validate_positive_counts(self) -> None:
        for field_name in (
            "num_adversaries",
            "adversarial_rounds",
            "min_successful_adversaries",
            "max_review_chars",
            "max_worker_output_chars",
        ):
            self._require_positive_int(field_name, getattr(self, field_name))
        if self.max_child_calls is not None:
            self._require_positive_int("max_child_calls", self.max_child_calls)

    def _validate_success_threshold(self) -> None:
        if self.min_successful_adversaries <= self.num_adversaries:
            return
        raise ConfigurationError(
            "AdversarialSettings.min_successful_adversaries cannot exceed num_adversaries.",
            details={
                "file": "vidbyte/lib/dataclasses/adversarial.py",
                "function": "AdversarialSettings._validate_success_threshold",
                "field": "min_successful_adversaries",
                "actual": self.min_successful_adversaries,
                "num_adversaries": self.num_adversaries,
                "expected": "1 <= min_successful_adversaries <= num_adversaries",
                "remediation": "Lower the success floor or increase num_adversaries.",
            },
        )

    def _validate_timeouts(self) -> None:
        self._require_positive_number_or_none(
            "per_adversary_timeout", self.per_adversary_timeout
        )
        self._require_positive_number_or_none(
            "run_timeout_seconds", self.run_timeout_seconds
        )

    def _validate_specialty_shape(self) -> None:
        specialty_count = len(self.specialties)
        if specialty_count in (0, 1, self.num_adversaries):
            return
        raise ConfigurationError(
            "AdversarialSettings.specialties must be empty, contain one shared lens, or align exactly with num_adversaries.",
            details={
                "file": "vidbyte/lib/dataclasses/adversarial.py",
                "function": "AdversarialSettings._validate_specialty_shape",
                "field": "specialties",
                "actual_count": specialty_count,
                "num_adversaries": self.num_adversaries,
                "expected_counts": (0, 1, self.num_adversaries),
                "remediation": "Use no specialties, one shared specialty, or one specialty per reviewer index.",
            },
        )

    def _validate_freshness(self) -> None:
        if type(self.fresh_adversaries_each_round) is bool:
            return
        raise ConfigurationError(
            "AdversarialSettings.fresh_adversaries_each_round must be a boolean.",
            details={
                "file": "vidbyte/lib/dataclasses/adversarial.py",
                "function": "AdversarialSettings._validate_freshness",
                "field": "fresh_adversaries_each_round",
                "actual_type": type(self.fresh_adversaries_each_round).__name__,
                "expected": "bool",
                "remediation": "Pass True to fork reviewers per round or False to reuse them by index.",
            },
        )

    def _validate_child_call_budget(self) -> None:
        if (
            self.max_child_calls is None
            or self.max_child_calls >= self.required_child_calls
        ):
            return
        raise ConfigurationError(
            "AdversarialSettings.max_child_calls is below the exact child-agent call requirement.",
            details={
                "file": "vidbyte/lib/dataclasses/adversarial.py",
                "function": "AdversarialSettings._validate_child_call_budget",
                "field": "max_child_calls",
                "actual": self.max_child_calls,
                "required_child_calls": self.required_child_calls,
                "expected": "max_child_calls >= required_child_calls",
                "remediation": "Raise max_child_calls or reduce num_adversaries/adversarial_rounds.",
            },
        )

    def _require_adversary_index(self, adversary_index: int) -> None:
        if (
            type(adversary_index) is int
            and 1 <= adversary_index <= self.num_adversaries
        ):
            return
        raise ConfigurationError(
            "AdversarialSettings.specialty_for requires a one-based reviewer index within num_adversaries.",
            details={
                "file": "vidbyte/lib/dataclasses/adversarial.py",
                "function": "AdversarialSettings.specialty_for",
                "actual_index": adversary_index,
                "actual_type": type(adversary_index).__name__,
                "expected": f"integer in [1, {self.num_adversaries}]",
                "remediation": "Call specialty_for only for configured reviewer indices.",
            },
        )

    @staticmethod
    def _require_positive_int(field_name: str, value: int) -> None:
        if type(value) is int and value > 0:
            return
        raise ConfigurationError(
            f"AdversarialSettings.{field_name} must be a positive integer.",
            details={
                "file": "vidbyte/lib/dataclasses/adversarial.py",
                "function": "AdversarialSettings._require_positive_int",
                "field": field_name,
                "actual_type": type(value).__name__,
                "actual": value,
                "expected": "positive integer",
                "remediation": f"Pass a positive integer for {field_name}.",
            },
        )

    @staticmethod
    def _require_positive_number_or_none(field_name: str, value: float | None) -> None:
        finite_number = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and (not isinstance(value, float) or isfinite(value))
        )
        if value is None or (finite_number and value > 0):
            return
        raise ConfigurationError(
            f"AdversarialSettings.{field_name} must be a finite positive number when provided.",
            details={
                "file": "vidbyte/lib/dataclasses/adversarial.py",
                "function": "AdversarialSettings._require_positive_number_or_none",
                "field": field_name,
                "actual_type": type(value).__name__,
                "expected": "finite positive int or float, or None",
                "remediation": f"Pass a finite positive timeout in seconds for {field_name}, or omit it.",
            },
        )

    @staticmethod
    def _normalize_specialties(values: Sequence[str]) -> tuple[str, ...]:
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise ConfigurationError(
                "AdversarialSettings.specialties must be a sequence of strings, not a string or non-sequence value.",
                details={
                    "file": "vidbyte/lib/dataclasses/adversarial.py",
                    "function": "AdversarialSettings._normalize_specialties",
                    "field": "specialties",
                    "actual_type": type(values).__name__,
                    "expected": "sequence[str]",
                    "remediation": "Pass a tuple or list of specialty strings.",
                },
            )
        normalized: list[str] = []
        for index, value in enumerate(values, start=1):
            if not isinstance(value, str):
                raise ConfigurationError(
                    "AdversarialSettings.specialties entries must be strings.",
                    details={
                        "file": "vidbyte/lib/dataclasses/adversarial.py",
                        "function": "AdversarialSettings._normalize_specialties",
                        "field": "specialties",
                        "index": index,
                        "actual_type": type(value).__name__,
                        "expected": "nonblank string",
                        "remediation": "Replace the entry with a concise review specialty string.",
                    },
                )
            specialty = value.strip()
            if not specialty or len(specialty) > _MAX_SPECIALTY_CHARS:
                raise ConfigurationError(
                    "AdversarialSettings.specialties entries must be nonblank and at most 500 characters.",
                    details={
                        "file": "vidbyte/lib/dataclasses/adversarial.py",
                        "function": "AdversarialSettings._normalize_specialties",
                        "field": "specialties",
                        "index": index,
                        "actual_chars": len(specialty),
                        "max_chars": _MAX_SPECIALTY_CHARS,
                        "expected": "1..500 characters after trimming",
                        "remediation": "Provide a concise specialty label without surrounding whitespace.",
                    },
                )
            normalized.append(specialty)
        return tuple(normalized)

    @staticmethod
    def _bound(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + _TRUNCATION_MARKER


@dataclass(frozen=True, slots=True)
class AdversarialReview:
    """Outcome of one adversary's attempt to challenge a worker snapshot."""

    round_index: int
    adversary_index: int
    adversary_name: str
    content: str = ""
    specialty: str | None = None
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdversarialRoundResult:
    """Full successful artifacts from one review and worker-revision round."""

    round_index: int
    reviewed_worker_output: str
    reviews: tuple[AdversarialReview, ...]
    revised_worker_output: str


@dataclass(frozen=True, slots=True)
class AdversarialResult:
    """Detailed successful result retained on AdversarialAgent.last_result."""

    initial_worker_output: str
    rounds: tuple[AdversarialRoundResult, ...]
    final_output: str
    successful_review_count: int
    failed_review_count: int
    metadata: Mapping[str, Any] = field(default_factory=dict)


__all__ = [
    "AdversarialResult",
    "AdversarialReview",
    "AdversarialRoundResult",
    "AdversarialSettings",
]
