"""Context Protocol Header

FILE:
    vidbyte/lib/dataclasses/adversarial.py owns portable adversarial workflow settings.
PURPOSE:
    Defines and validates the immutable controls the adversarial facade can enforce;
    keep agent execution, topology dispatch, provider ownership, and prompt rendering elsewhere.
ROLE IN CODEBASE:
    Imported by vidbyte.agents.adversarial for orchestration and re-exported through
    vidbyte.lib.dataclasses, vidbyte.agents.settings, vidbyte.agents, and vidbyte.
ARCHITECTURE NOTE:
    This low-level contract prevents future tools and context algorithms from importing
    the high-level agents package merely to share validated adversarial policy.
PUBLIC CONTRACT INVENTORY (reviewed 2026-07-16):
    AdversarialSettings validates exact rounds, reviewer shape, specialties, timeouts,
    forwarding bounds, reviewer freshness, and deterministic child-call budgets.
    required_child_calls reports child-agent invocations, excluding nested tool calls.
    specialty_for(index) resolves generic, shared, or index-aligned review lenses.
    specialist_panel(...) builds the homogeneous-prototype panel supported by the facade.
COMMON MODIFICATION PATTERNS:
    Add only controls the current controller can enforce, validate them before execution,
    then update facade summaries and skills/vidbyte-sdk/adversarial-agent.md together.
WHAT NOT TO DO IN THIS FILE:
    Do not add provider/model/runner objects, live agents, tools, topology strategies,
    prompt rendering, or orchestration state; those responsibilities belong to agents.
KNOWN EDGE CASES:
    A singleton specialty is shared by every reviewer; an exact-length tuple is aligned
    by one-based reviewer index. Duplicate specialties are intentional and permitted.
COMMON ERRORS RAISED BY THIS FILE:
    ConfigurationError reports invalid types, cardinality, bounds, or incompatible budgets
    before any child fork or model call can occur.
RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/adversarial-agent-settings.md
    Load the design before extending this contract with a new execution control.
TESTS:
    No dedicated files under the approved no-tests workflow; use the design document's
    import, validation, preset, orchestration, timeout, and package smoke commands.
CONCURRENCY:
    Immutable and safe to share. Reviewer concurrency remains an agent-controller concern.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Any

from vidbyte.lib.errors import ConfigurationError

_MAX_SPECIALTY_CHARS = 500


# @intent executable-settings-only
# Adversarial settings are a promise about behavior, not a catalog of possible ideas.
# Every accepted field below is enforced by the current sequential critique-and-revise
# controller. Future topologies must add their orchestration first or in the same change;
# adding an ignored debate, provider, or judge setting would mislead SDK callers into
# believing that a stronger review topology ran when the facade silently used its default.
@dataclass(frozen=True, slots=True)
class AdversarialSettings:
    """Validated controls for one exact adversarial workflow."""

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
        # Normalizes immutable specialty policy and rejects invalid workflow bounds before execution.
        object.__setattr__(self, "specialties", self._normalize_specialties(self.specialties))
        self._validate_positive_counts()
        self._validate_success_threshold()
        self._validate_timeouts()
        self._validate_specialty_shape()
        self._validate_freshness()
        self._validate_child_call_budget()

    @property
    def required_child_calls(self) -> int:
        # Reports exact child-agent invocations; nested model tool calls are intentionally excluded.
        return 1 + self.adversarial_rounds * (self.num_adversaries + 1)

    def specialty_for(self, adversary_index: int) -> str | None:
        # Resolves the generic, shared, or index-aligned lens for one one-based reviewer index.
        self._require_adversary_index(adversary_index)
        if not self.specialties:
            return None
        if len(self.specialties) == 1:
            return self.specialties[0]
        return self.specialties[adversary_index - 1]

    @classmethod
    def specialist_panel(cls, specialties: Sequence[str], **overrides: Any) -> AdversarialSettings:
        # Builds the supported panel shape: independent lenses over forks of one adversary prototype.
        conflicts = tuple(sorted({"num_adversaries", "specialties"}.intersection(overrides)))
        if conflicts:
            raise ConfigurationError(
                "AdversarialSettings.specialist_panel derives reviewer shape from specialties; conflicting overrides are not allowed.",
                details={
                    "file": "vidbyte/lib/dataclasses/adversarial.py",
                    "function": "AdversarialSettings.specialist_panel",
                    "conflicting_fields": conflicts,
                    "expected": "omit num_adversaries and specialties from overrides",
                    "remediation": "Pass specialty lenses as the first argument and use overrides only for round, timeout, freshness, threshold, or budget controls.",
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

    def _validate_positive_counts(self) -> None:
        # Applies strict integer validation to cardinality, forwarding, and optional call-budget fields.
        for field_name in ("num_adversaries", "adversarial_rounds", "min_successful_adversaries", "max_review_chars", "max_worker_output_chars"):
            self._require_positive_int(field_name, getattr(self, field_name))
        if self.max_child_calls is not None:
            self._require_positive_int("max_child_calls", self.max_child_calls)

    def _validate_success_threshold(self) -> None:
        # Requires every per-round success floor to be reachable by the configured reviewer count.
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
        # Accepts only positive numeric per-review and whole-workflow timeout values.
        self._require_positive_number_or_none("per_adversary_timeout", self.per_adversary_timeout)
        self._require_positive_number_or_none("run_timeout_seconds", self.run_timeout_seconds)

    def _validate_specialty_shape(self) -> None:
        # Allows generic, shared-lens, or exact index-aligned reviewer specialties only.
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
        # Rejects truthy substitutes so reviewer lifecycle policy is explicit and immutable.
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
        # Fails preflight when the configured ceiling cannot accommodate the exact workflow.
        if self.max_child_calls is None or self.max_child_calls >= self.required_child_calls:
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
        # Rejects non-integer or out-of-range one-based specialty lookups with safe diagnostics.
        if type(adversary_index) is int and 1 <= adversary_index <= self.num_adversaries:
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
        # Keeps count and character limits strict; booleans are not accepted as integer settings.
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
        # Validates finite optional timeout seconds without accepting booleans as numeric values.
        finite_number = isinstance(value, (int, float)) and not isinstance(value, bool) and (not isinstance(value, float) or isfinite(value))
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
        # Converts a non-string sequence into bounded nonblank specialty labels without coercion.
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
            normalized.append(AdversarialSettings._normalize_specialty(value, index))
        return tuple(normalized)

    @staticmethod
    def _normalize_specialty(value: str, index: int) -> str:
        # Trims one specialty and rejects invalid type, blank content, or oversized prompt input.
        if not isinstance(value, str):
            raise ConfigurationError(
                "AdversarialSettings.specialties entries must be strings.",
                details={
                    "file": "vidbyte/lib/dataclasses/adversarial.py",
                    "function": "AdversarialSettings._normalize_specialty",
                    "field": "specialties",
                    "index": index,
                    "actual_type": type(value).__name__,
                    "expected": "nonblank string",
                    "remediation": "Replace the entry with a concise review specialty string.",
                },
            )
        normalized = value.strip()
        if not normalized or len(normalized) > _MAX_SPECIALTY_CHARS:
            raise ConfigurationError(
                "AdversarialSettings.specialties entries must be nonblank and at most 500 characters.",
                details={
                    "file": "vidbyte/lib/dataclasses/adversarial.py",
                    "function": "AdversarialSettings._normalize_specialty",
                    "field": "specialties",
                    "index": index,
                    "actual_chars": len(normalized),
                    "max_chars": _MAX_SPECIALTY_CHARS,
                    "expected": "1..500 characters after trimming",
                    "remediation": "Provide a concise specialty label without surrounding whitespace.",
                },
            )
        return normalized


__all__ = ["AdversarialSettings"]
