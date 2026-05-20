from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Sequence
from typing import Any

from vidbyte.harnesses.red_team.evaluator import StoppingConditionEvaluator
from vidbyte.harnesses.red_team.types import (
    AttackFinding,
    HarnessPipeline,
    RedTeamChallengeResult,
    RedTeamChallengeState,
    RedTeamHarnessConfig,
    ResilienceScore,
)
from vidbyte.lib.errors import ExploitSuccessError, HarnessExecutionError
from vidbyte.shared import ArtifactRevision, FilteredContextView, HarnessRole, LedgerEntry


class RedTeamChallengeHarness:
    """Turn-based coordinator for adversarial blue-team/red-team simulation."""

    def __init__(
        self,
        *,
        blue_pipeline: HarnessPipeline,
        red_pipeline: HarnessPipeline,
        evaluator: StoppingConditionEvaluator | None = None,
        config: RedTeamHarnessConfig | None = None,
    ) -> None:
        self.blue_pipeline = blue_pipeline
        self.red_pipeline = red_pipeline
        self.evaluator = evaluator or StoppingConditionEvaluator()
        self.config = config or RedTeamHarnessConfig()

    async def arun(self, prompt: str, *, initial_artifact: str = "") -> RedTeamChallengeResult:
        if not prompt.strip():
            raise HarnessExecutionError("prompt must not be empty")

        initial_revision = ArtifactRevision(revision=0, content=initial_artifact, metadata={"initial": True})
        state = RedTeamChallengeState(
            original_prompt=prompt,
            master_ledger=[
                LedgerEntry(role=HarnessRole.SYSTEM, kind="original_prompt", content=prompt),
            ],
            blue_view=FilteredContextView(role=HarnessRole.BLUE),
            red_view=FilteredContextView(role=HarnessRole.RED),
            artifacts=[initial_revision],
            findings=[],
            scores=[],
        )

        best_artifact = initial_revision
        best_score = ResilienceScore(
            exploit_severity=1.0,
            defensive_adaptability=0.0,
            equilibrium=0.0,
            consecutive_clean_attacks=0,
        )

        for round_index in range(1, self.config.max_rounds + 1):
            state.round_index = round_index
            self._enforce_step_budget(state)

            latest_artifact = state.artifacts[-1]
            blue_prompt = self._build_blue_prompt(state, latest_artifact)
            blue_output = await self._call_pipeline(
                self.blue_pipeline,
                blue_prompt,
                context=self._build_blue_context(state),
                role=HarnessRole.BLUE,
                state=state,
            )
            latest_artifact = self._parse_artifact(blue_output, revision=len(state.artifacts))
            state.artifacts.append(latest_artifact)

            self._enforce_step_budget(state)
            red_prompt = self._build_red_prompt(state, latest_artifact)
            red_output = await self._call_pipeline(
                self.red_pipeline,
                red_prompt,
                context=self._build_red_context(state, latest_artifact),
                role=HarnessRole.RED,
                state=state,
            )
            latest_findings = self._parse_findings(red_output)
            state.findings.extend(latest_findings)

            for finding in latest_findings:
                if self.evaluator.is_fatal(finding, self.config):
                    raise ExploitSuccessError(
                        "red team triggered a fatal exploit",
                        payload=finding.payload,
                        severity=str(finding.severity),
                        metadata={
                            "category": finding.category,
                            "description": finding.description,
                            "round": round_index,
                        },
                    )

            score = self.evaluator.evaluate_round(
                state=state,
                latest_artifact=latest_artifact,
                latest_findings=latest_findings,
                config=self.config,
            )
            state.scores.append(score)
            state.master_ledger.append(
                LedgerEntry(
                    role=HarnessRole.JUDGE,
                    kind="resilience_score",
                    content=str(score.equilibrium),
                    metadata={
                        "exploit_severity": score.exploit_severity,
                        "defensive_adaptability": score.defensive_adaptability,
                        "consecutive_clean_attacks": score.consecutive_clean_attacks,
                    },
                )
            )

            if score.equilibrium >= best_score.equilibrium:
                best_artifact = latest_artifact
                best_score = score

            if score.consecutive_clean_attacks >= self.config.consecutive_clean_attacks_for_win:
                return RedTeamChallengeResult(
                    outcome="defensive_win",
                    artifact=latest_artifact,
                    score=score,
                    rounds=round_index,
                    metadata={"termination_reason": "consecutive_clean_attacks"},
                )

        return RedTeamChallengeResult(
            outcome="exhausted",
            artifact=best_artifact if self.config.return_best_on_exhaustion else state.artifacts[-1],
            score=best_score if self.config.return_best_on_exhaustion else state.scores[-1],
            rounds=state.round_index,
            metadata={"termination_reason": "max_rounds"},
        )

    def run(self, prompt: str, *, initial_artifact: str = "") -> RedTeamChallengeResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(prompt, initial_artifact=initial_artifact))
        raise HarnessExecutionError("RedTeamChallengeHarness.run() cannot be called inside an active event loop")

    async def _call_pipeline(
        self,
        pipeline: HarnessPipeline,
        prompt: str,
        *,
        context: Sequence[LedgerEntry],
        role: HarnessRole,
        state: RedTeamChallengeState,
    ) -> str:
        state.step_index += 1
        state.master_ledger.append(
            LedgerEntry(role=role, kind="pipeline_input", content=prompt, metadata={"pipeline": pipeline.name})
        )
        try:
            result = pipeline.model_fn(prompt, context=context, tools=pipeline.tools)
            output = await result if inspect.isawaitable(result) else result
        except Exception as error:
            raise HarnessExecutionError(f"{pipeline.name} pipeline failed: {error}") from error

        output_text = str(output)
        state.master_ledger.append(
            LedgerEntry(role=role, kind="pipeline_output", content=output_text, metadata={"pipeline": pipeline.name})
        )
        return output_text

    def _enforce_step_budget(self, state: RedTeamChallengeState) -> None:
        if self.config.max_steps is not None and state.step_index >= self.config.max_steps:
            raise HarnessExecutionError("red-team harness exceeded max_steps before reaching a terminal outcome")

    def _build_blue_context(self, state: RedTeamChallengeState) -> list[LedgerEntry]:
        entries = [
            entry
            for entry in state.master_ledger
            if entry.role in {HarnessRole.SYSTEM, HarnessRole.BLUE, HarnessRole.JUDGE}
        ]
        if state.findings:
            entries.append(
                LedgerEntry(
                    role=HarnessRole.RED,
                    kind="finding_summary",
                    content=self._summarize_findings(state.findings),
                    metadata={"filtered": True},
                )
            )
        state.blue_view.entries = entries
        return entries

    def _build_red_context(
        self,
        state: RedTeamChallengeState,
        latest_artifact: ArtifactRevision,
    ) -> list[LedgerEntry]:
        entries = [
            entry
            for entry in state.master_ledger
            if entry.role in {HarnessRole.SYSTEM, HarnessRole.RED, HarnessRole.JUDGE}
        ]
        entries.append(
            LedgerEntry(
                role=HarnessRole.BLUE,
                kind="target_artifact",
                content=latest_artifact.content,
                metadata={"revision": latest_artifact.revision, "filtered": True},
            )
        )
        state.red_view.entries = entries
        return entries

    def _build_blue_prompt(self, state: RedTeamChallengeState, artifact: ArtifactRevision) -> str:
        return "\n\n".join(
            [
                "Blue team: improve the artifact against known red-team findings.",
                f"Original task:\n{state.original_prompt}",
                f"Current artifact revision {artifact.revision}:\n{artifact.content}",
                f"Known findings:\n{self._summarize_findings(state.findings)}",
            ]
        )

    def _build_red_prompt(self, state: RedTeamChallengeState, artifact: ArtifactRevision) -> str:
        return "\n\n".join(
            [
                "Red team: attack the target artifact and report warnings, exceptions, or contract violations.",
                f"Original task:\n{state.original_prompt}",
                f"Target artifact revision {artifact.revision}:\n{artifact.content}",
            ]
        )

    def _parse_artifact(self, output: str, *, revision: int) -> ArtifactRevision:
        payload = self._loads_object(output)
        if payload is not None:
            content = str(payload.get("artifact", payload.get("content", output)))
            metadata = payload.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {"raw_metadata": metadata}
            patched_findings = payload.get("patched_findings")
            if patched_findings is not None:
                metadata = {**metadata, "patched_findings": patched_findings}
            return ArtifactRevision(revision=revision, content=content, metadata=metadata)
        return ArtifactRevision(revision=revision, content=output, metadata={})

    def _parse_findings(self, output: str) -> list[AttackFinding]:
        payload = self._loads_object(output)
        raw_findings: Any
        if payload is None:
            lowered = output.lower()
            if not lowered.strip() or "no finding" in lowered or "no vulnerabilities" in lowered:
                return []
            severity = 1.0 if "fatal" in lowered else 0.5 if "warning" in lowered else 0.25
            return [
                AttackFinding(
                    payload=output,
                    severity=severity,
                    category="text",
                    description=output,
                    fatal="fatal" in lowered,
                )
            ]
        raw_findings = payload.get("findings", payload.get("finding", []))
        if isinstance(raw_findings, dict):
            raw_findings = [raw_findings]
        if not isinstance(raw_findings, list):
            return []

        findings: list[AttackFinding] = []
        for item in raw_findings:
            if not isinstance(item, dict):
                continue
            findings.append(
                AttackFinding(
                    payload=str(item.get("payload", "")),
                    severity=float(item.get("severity", 0.0)),
                    category=str(item.get("category", "unknown")),
                    description=str(item.get("description", "")),
                    fatal=bool(item.get("fatal", False)),
                    metadata=item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {},
                )
            )
        return findings

    def _summarize_findings(self, findings: Sequence[AttackFinding]) -> str:
        if not findings:
            return "No findings yet."
        return "\n".join(
            f"- {finding.category}: severity={finding.severity}; payload={finding.payload}; {finding.description}"
            for finding in findings
        )

    def _loads_object(self, text: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


__all__ = ["RedTeamChallengeHarness"]
