"""Context Protocol Header

Description:
    Defines VerifierRuntimeFeedback.
Purpose:
    Renders the corrective payload injected after a failed AggregatedVerdict,
    under one of four configurable content modes.
Architecture:
    - VerifierRuntimeFeedback: emit() dispatches to one private builder per
      mode, then applies max_diagnostics_chars truncation last.
    VerifierRuntimeFeedbackParams (validated dataclass: which
    FeedbackContentMode/FeedbackDelivery, plus the fields each mode
    requires) lives in vidbyte.lib.dataclasses.verifier, not here, per
    review feedback on PR #349.
Relations:
    Consumes vidbyte.agents.runtimes.verifier.types.AggregatedVerdict.
    Consumed by vidbyte.agents.runtimes.verifier.runtime.AgentVerifierRuntime.
Similar Files:
    - vidbyte/agents/contract.py: AgentLoopSettingsOutputContract.feedback(),
      the nearest existing "render corrective text from failed checks" logic.
"""

from __future__ import annotations

from vidbyte.agents.runtimes.verifier.types import AggregatedVerdict, FeedbackContentMode, VerifierVerdict
from vidbyte.lib.dataclasses.verifier import VerifierRuntimeFeedbackParams

_TRUNCATION_SUFFIX = "\n...[truncated]"


class _DefaultingMapping(dict):
    """A str.format_map mapping that renders unknown template keys as empty text instead of raising."""

    def __missing__(self, key: str) -> str:
        # A misconfigured template placeholder should degrade to blank text, not crash the loop.
        return ""


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
            FeedbackContentMode.RAW_AND_CUSTOM: self._build_raw_and_custom_payload,
        }
        return self._truncate(builders[self.params.content_mode](verdict))

    def _failed(self, verdict: AggregatedVerdict) -> tuple[VerifierVerdict, ...]:
        # The subset of verdicts every content mode renders from.
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

    def _build_raw_and_custom_payload(self, verdict: AggregatedVerdict) -> str:
        # Combines the framing of the custom message with the actionable detail of the raw payload.
        return f"{self._build_custom_payload(verdict)}\n\n{self._build_raw_payload(verdict)}"

    def _truncate(self, payload: str) -> str:
        # Applied last, regardless of content mode, so every mode respects the same character ceiling.
        limit = self.params.max_diagnostics_chars
        if limit is None or len(payload) <= limit:
            return payload
        if limit <= len(_TRUNCATION_SUFFIX):
            return payload[:limit]
        return payload[: limit - len(_TRUNCATION_SUFFIX)].rstrip() + _TRUNCATION_SUFFIX


__all__ = ["VerifierRuntimeFeedback", "VerifierRuntimeFeedbackParams"]
