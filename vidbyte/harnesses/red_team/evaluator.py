from __future__ import annotations

from collections.abc import Sequence

from vidbyte.lib.errors import EvaluationError
from vidbyte.shared import ArtifactRevision
from vidbyte.harnesses.red_team.types import (
    AttackFinding,
    RedTeamChallengeState,
    RedTeamHarnessConfig,
    ResilienceScore,
)


class StoppingConditionEvaluator:
    """Scores adversarial rounds and detects fatal exploit thresholds."""

    def evaluate_round(
        self,
        *,
        state: RedTeamChallengeState,
        latest_artifact: ArtifactRevision,
        latest_findings: Sequence[AttackFinding],
        config: RedTeamHarnessConfig,
    ) -> ResilienceScore:
        try:
            exploit_severity = max((finding.severity for finding in latest_findings), default=0.0)
            defensive_adaptability = self._defensive_adaptability(state, latest_artifact)
            equilibrium = defensive_adaptability * (1.0 - exploit_severity)
            previous_clean = state.scores[-1].consecutive_clean_attacks if state.scores else 0
            has_warning = exploit_severity >= config.warning_severity_threshold
            consecutive_clean_attacks = 0 if has_warning else previous_clean + 1
            return ResilienceScore(
                exploit_severity=exploit_severity,
                defensive_adaptability=defensive_adaptability,
                equilibrium=equilibrium,
                consecutive_clean_attacks=consecutive_clean_attacks,
            )
        except Exception as error:  # pragma: no cover - defensive wrapping
            raise EvaluationError(f"failed to evaluate red-team round: {error}") from error

    def is_fatal(self, finding: AttackFinding, config: RedTeamHarnessConfig) -> bool:
        return finding.fatal or finding.severity >= config.fatal_severity_threshold

    def _defensive_adaptability(
        self,
        state: RedTeamChallengeState,
        latest_artifact: ArtifactRevision,
    ) -> float:
        previous_findings = state.findings
        if not previous_findings:
            return 1.0

        patched = latest_artifact.metadata.get("patched_findings", ())
        if isinstance(patched, str):
            patched_values = {patched.lower()}
        else:
            patched_values = {str(value).lower() for value in patched}

        artifact_text = latest_artifact.content.lower()
        resolved = 0
        for finding in previous_findings:
            markers = {
                finding.category.lower(),
                finding.payload.lower(),
                finding.description.lower(),
            }
            if patched_values.intersection(markers) or any(marker and marker in artifact_text for marker in markers):
                resolved += 1

        return resolved / len(previous_findings)


__all__ = ["StoppingConditionEvaluator"]
