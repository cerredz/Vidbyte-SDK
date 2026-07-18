"""Context Protocol Header

Description:
    Defines the immutable data contracts for the adversarial-review workflow:
    validated settings plus the review/round/result records a run produces.
Purpose:
    Keeps the adversarial data contracts in the central lib namespace so the
    agent, context, and runtime layers all depend on one source of truth. The
    settings object owns BOTH validation ("are these settings valid") AND
    enforcement ("does this runtime state satisfy them"): threshold decisions and
    forwarding-length bounds live here, not scattered into the run loop.
Architecture:
    - AdversarialSettings validates cardinality/bounds in __post_init__ and
      exposes enforce_review_threshold / is_review_threshold_met / bound_* helpers
      the agent and runtime call instead of re-deriving the rules inline.
    - AdversarialReview / AdversarialRoundResult / AdversarialResult are frozen
      pure-data records; they hold outputs, never behavior.
Relations:
    Imported by vidbyte.agents.adversarial (agent, context, runtime). Raises
    ConfigurationError (invalid settings) and AdversarialExecutionError (unmet
    review threshold) from vidbyte.lib.errors.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.errors import AdversarialExecutionError, ConfigurationError

_TRUNCATION_MARKER = "...[truncated]"


@dataclass(frozen=True, slots=True)
class AdversarialSettings:
    """Validated controls for one exact adversarial workflow, plus the enforcement helpers the agent calls."""

    num_adversaries: int = 1
    adversarial_rounds: int = 1
    min_successful_adversaries: int = 1
    per_adversary_timeout: float | None = None
    max_review_chars: int = 4000
    max_worker_output_chars: int = 12000

    def __post_init__(self) -> None:
        # Reject invalid workflow cardinality and bounds before any child is forked or called.
        self._require_positive_int("num_adversaries", self.num_adversaries)
        self._require_positive_int("adversarial_rounds", self.adversarial_rounds)
        self._require_positive_int("min_successful_adversaries", self.min_successful_adversaries)
        self._require_positive_int("max_review_chars", self.max_review_chars)
        self._require_positive_int("max_worker_output_chars", self.max_worker_output_chars)
        if self.min_successful_adversaries > self.num_adversaries:
            raise ConfigurationError(
                "AdversarialSettings.min_successful_adversaries cannot exceed num_adversaries.",
                details={
                    "field": "min_successful_adversaries",
                    "actual": self.min_successful_adversaries,
                    "num_adversaries": self.num_adversaries,
                    "expected": "1 <= min_successful_adversaries <= num_adversaries",
                },
            )
        if self.per_adversary_timeout is not None and (isinstance(self.per_adversary_timeout, bool) or not isinstance(self.per_adversary_timeout, (int, float)) or self.per_adversary_timeout <= 0):
            raise ConfigurationError(
                "AdversarialSettings.per_adversary_timeout must be a positive number when provided.",
                details={
                    "field": "per_adversary_timeout",
                    "actual_type": type(self.per_adversary_timeout).__name__,
                    "expected": "positive int or float, or None",
                },
            )

    # ── enforcement (runtime state satisfies the settings) ──
    # These make the settings object the single source of truth for the rules the
    # loop used to re-derive inline. The runtime calls settings.enforce_review_threshold(...)
    # rather than owning the threshold decision itself.
    def is_review_threshold_met(self, successful: int) -> bool:
        # True when enough non-blank reviews succeeded to permit a revision this round.
        return successful >= self.min_successful_adversaries

    def enforce_review_threshold(self, successful: int, total: int, *, context: Mapping[str, Any] | None = None) -> None:
        # Raise the rich adversarial error when the successful-review floor is unmet; the caller supplies run-local context.
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
        # Bound one reviewer challenge before it is forwarded into a later prompt; the limit lives with the setting.
        return self._bound(text, self.max_review_chars)

    def bound_worker_output(self, text: str) -> str:
        # Bound a forwarded worker snapshot; retained result artifacts stay complete elsewhere.
        return self._bound(text, self.max_worker_output_chars)

    @staticmethod
    def _bound(text: str, limit: int) -> str:
        # Apply the character limit; forwarding-only truncation never touches retained artifacts.
        if len(text) <= limit:
            return text
        return text[:limit] + _TRUNCATION_MARKER

    @staticmethod
    def _require_positive_int(field_name: str, value: int) -> None:
        # Keep count and character limits strict; booleans are not accepted as integer settings.
        if type(value) is int and value > 0:
            return
        raise ConfigurationError(
            f"AdversarialSettings.{field_name} must be a positive integer.",
            details={
                "field": field_name,
                "actual_type": type(value).__name__,
                "actual": value,
                "expected": "positive integer",
            },
        )


@dataclass(frozen=True, slots=True)
class AdversarialReview:
    """Outcome of one adversary's attempt to challenge a worker snapshot."""

    round_index: int
    adversary_index: int
    adversary_name: str
    content: str = ""
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
