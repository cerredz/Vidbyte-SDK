"""Context Protocol Header

Description:
    Defines VerifierRuntimeFeedbackParams and VerifierRuntimeFeedback.
Purpose:
    Renders the corrective payload injected after a failed AggregatedVerdict,
    under one of six configurable content modes.
Architecture:
    - VerifierRuntimeFeedbackParams: which FeedbackContentMode/FeedbackDelivery,
      plus the fields each mode requires.
    - VerifierRuntimeFeedback: emit() dispatches to one private builder per
      mode, then applies max_diagnostics_chars truncation last.
Relations:
    Consumes vidbyte.agents.runtimes.verifier.types.AggregatedVerdict.
    Consumed by vidbyte.agents.runtimes.verifier.runtime.AgentVerifierRuntime.
Similar Files:
    - vidbyte/agents/contract.py: AgentLoopSettingsOutputContract.feedback(),
      the nearest existing "render corrective text from failed checks" logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.agents.runtimes.verifier.types import AggregatedVerdict, FeedbackContentMode, FeedbackDelivery, VerifierVerdict
from vidbyte.lib.errors import ConfigurationError

_TRUNCATION_SUFFIX = "\n...[truncated]"
_MODES_REQUIRING_TEMPLATE = (FeedbackContentMode.CUSTOM_MESSAGE, FeedbackContentMode.RAW_AND_CUSTOM)


class _DefaultingMapping(dict):
    """A str.format_map mapping that renders unknown template keys as empty text instead of raising."""

    def __missing__(self, key: str) -> str:
        # A misconfigured template placeholder should degrade to blank text, not crash the loop.
        return ""


@dataclass(frozen=True, slots=True)
class VerifierRuntimeFeedbackParams:
    """Validated configuration for one VerifierRuntimeFeedback."""

    content_mode: FeedbackContentMode = FeedbackContentMode.RAW_VERDICT
    delivery: FeedbackDelivery = FeedbackDelivery.USER_MESSAGE
    message_template: str | None = None
    structured_fields: tuple[str, ...] = ()
    minimize_counterexamples: bool = False
    max_diagnostics_chars: int | None = None

    def __post_init__(self) -> None:
        # Each content mode that needs a companion field must have it.
        self._validate_template_modes()
        self._validate_structured_mode()
        self._validate_max_chars()

    def _validate_template_modes(self) -> None:
        # CUSTOM_MESSAGE and RAW_AND_CUSTOM both need something to render.
        if self.content_mode in _MODES_REQUIRING_TEMPLATE and not self.message_template:
            raise ConfigurationError(f"VerifierRuntimeFeedbackParams: content_mode={self.content_mode.value} requires message_template.")

    def _validate_structured_mode(self) -> None:
        # Without named fields, STRUCTURED_PAYLOAD has nothing to render.
        if self.content_mode is FeedbackContentMode.STRUCTURED_PAYLOAD and not self.structured_fields:
            raise ConfigurationError("VerifierRuntimeFeedbackParams: content_mode=STRUCTURED_PAYLOAD requires structured_fields.")

    def _validate_max_chars(self) -> None:
        # A zero or negative cap would truncate every message to nothing.
        if self.max_diagnostics_chars is not None and self.max_diagnostics_chars <= 0:
            raise ConfigurationError("VerifierRuntimeFeedbackParams.max_diagnostics_chars must be greater than zero when provided.")


class VerifierRuntimeFeedback:
    """Renders the corrective payload injected after a failed AggregatedVerdict."""

    def __init__(self, params: VerifierRuntimeFeedbackParams) -> None:
        # Stores the already-validated configuration for this feedback instance.
        self.params = params

    def emit(self, verdict: AggregatedVerdict) -> str:
        """Renders the configured feedback payload for a failed AggregatedVerdict."""
        builders = {
            FeedbackContentMode.RAW_VERDICT: self._build_raw_payload,
            FeedbackContentMode.CUSTOM_MESSAGE: self._build_custom_payload,
            FeedbackContentMode.STRUCTURED_PAYLOAD: self._build_structured_payload,
            FeedbackContentMode.MINIMIZED_COUNTEREXAMPLE: self._build_minimized_payload,
            FeedbackContentMode.SCORE_TREND_ONLY: self._build_score_payload,
            FeedbackContentMode.RAW_AND_CUSTOM: self._build_raw_and_custom_payload,
        }
        return self._truncate(builders[self.params.content_mode](verdict))

    def _failed(self, verdict: AggregatedVerdict) -> tuple[VerifierVerdict, ...]:
        # The subset of verdicts every content mode except SCORE_TREND_ONLY renders from.
        return tuple(v for v in verdict.verdicts if not v.passed)

    def _build_raw_payload(self, verdict: AggregatedVerdict) -> str:
        # The richest signal: every failed verifier's own diagnostics, verbatim.
        failed = self._failed(verdict)
        lines = "\n".join(f"- {v.verifier_name}: {v.diagnostics}" for v in failed)
        return lines or "Verification failed with no diagnostic detail."

    def _build_custom_payload(self, verdict: AggregatedVerdict) -> str:
        # Renders only the user-authored template — deliberately less informative than raw diagnostics.
        failed = self._failed(verdict)
        mapping = _DefaultingMapping(failure_count=len(failed), verifier_names=", ".join(v.verifier_name for v in failed))
        return (self.params.message_template or "").format_map(mapping)

    def _build_structured_payload(self, verdict: AggregatedVerdict) -> str:
        # Renders only the named fields from each failed verdict, machine-shaped.
        failed = self._failed(verdict)
        lines = []
        for v in failed:
            rendered = ", ".join(f"{field}={getattr(v, field, '<absent>')}" for field in self.params.structured_fields)
            lines.append(f"- {v.verifier_name}: {rendered}")
        return "\n".join(lines)

    def _build_minimized_payload(self, verdict: AggregatedVerdict) -> str:
        # Surfaces only the smallest/most illustrative failing verdict, the counterexample-minimization idea.
        failed = self._failed(verdict)
        if not failed:
            return ""
        minimized = self._minimize(failed)
        return f"- {minimized.verifier_name}: {minimized.diagnostics}"

    def _build_score_payload(self, verdict: AggregatedVerdict) -> str:
        # Directional signal only — every verdict's score, no diagnostic detail, across pass and fail alike.
        return "\n".join(f"- {v.verifier_name}: score={v.score}" for v in verdict.verdicts)

    def _build_raw_and_custom_payload(self, verdict: AggregatedVerdict) -> str:
        # Combines the framing of the custom message with the actionable detail of the raw payload.
        return f"{self._build_custom_payload(verdict)}\n\n{self._build_raw_payload(verdict)}"

    def _minimize(self, verdicts: tuple[VerifierVerdict, ...]) -> VerifierVerdict:
        # Shortest diagnostics text stands in for "smallest counterexample" without needing domain-specific parsing.
        return min(verdicts, key=lambda v: len(v.diagnostics))

    def _truncate(self, payload: str) -> str:
        # Applied last, regardless of content mode, so every mode respects the same character ceiling.
        limit = self.params.max_diagnostics_chars
        if limit is None or len(payload) <= limit:
            return payload
        if limit <= len(_TRUNCATION_SUFFIX):
            return payload[:limit]
        return payload[: limit - len(_TRUNCATION_SUFFIX)].rstrip() + _TRUNCATION_SUFFIX


__all__ = ["VerifierRuntimeFeedback", "VerifierRuntimeFeedbackParams"]
