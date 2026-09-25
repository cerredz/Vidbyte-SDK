"""FILE: vidbyte/agents/jev/compaction/agent.py

PURPOSE: Implements JevDynamicCompaction, the agent JevAgent uses to find finished units of work with Jev and replace them in the canonical history with short written records.
ROLE IN CODEBASE: JevAgent builds one instance when JevAgentSettings.dynamic_compaction enables a trigger; each run's JevRuntime calls prepare() from AgentRuntime.prepare_iteration_history before every model call.
ARCHITECTURE NOTE: Jev only recognizes boundaries (one batched request per step across all enabled triggers). Code owns the ledger, the reclaim threshold, and the splice. The record writer is this BaseAgent itself: tool-free, same provider and model as the main agent, sharing its usage tracker.
COMMON MODIFICATION PATTERNS: Add a way to find boundaries in triggers.py; change what replaces a unit in _record_for or the jev_compaction prompt assets; keep policy constants in vidbyte/lib/constants/jev_compaction.py.
KNOWN EDGE CASES: A missing TypeSafe key disables the capability for the run; three consecutive Jev errors stop the questions; a writer failure falls back to a deterministic record; a history the ledger cannot account for disables compaction. None of these raise into the loop.
RELATED DOCS: docs/design/jev-dynamic-compaction.md, skills/asking-jev-questions/SKILL.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_dynamic_compaction.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.compaction.ledger import JevWorkUnit
from vidbyte.agents.jev.compaction.report import (
    JevCompactionRun,
    JevUnitBoundary,
    JevUnitCompaction,
)
from vidbyte.agents.jev.compaction.steps import JevRunStep, JevRunSteps
from vidbyte.agents.jev.compaction.triggers import (
    JEV_COMPACTION_TRIGGERS,
    JevCompactionTrigger,
    JevStepView,
)
from vidbyte.agents.jev.settings import JevAgentSettings, JevDynamicCompactionSettings
from vidbyte.agents.pricing import JevUsage
from vidbyte.agents.runtime import BaseAgentRuntimeLoopState
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.jev_compaction import (
    JEV_COMPACTION_KEEP_RECENT_CLOSED_UNITS,
    JEV_COMPACTION_MAX_CONSECUTIVE_JEV_ERRORS,
    JEV_COMPACTION_RECORD_TOKEN_ALLOWANCE,
    JEV_COMPACTION_WRITER_MAX_ITERATIONS,
    JEV_COMPACTION_WRITER_TASK_CHARS,
)
from vidbyte.lib.dataclasses.jev import JevDecisionRequest, JevQuestion
from vidbyte.lib.enums import JevCompactionDisabledReason, JevCompactionRecordSource
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.prompts.catalog import Prompts

_RECORD_ROLE = "user"


class JevDynamicCompaction(BaseAgent):
    """Finds finished units of work with Jev and compacts them into records; also writes those records."""

    def __init__(self, settings: JevAgentSettings) -> None:
        # Reuses the main agent's generative model and decision config; the writer's prompt is fixed and it has no tools.
        # @intent writer-shares-model-not-prompt
        # The record must be written by the model the owner configured and paid for, but its prompt and tool-free
        # shape are fixed here so the capability cannot be turned into a general agent.
        compaction = settings.dynamic_compaction if isinstance(settings, JevAgentSettings) else None
        if compaction is None or not compaction.is_enabled():
            raise ConfigurationError(
                "JevDynamicCompaction requires JevAgentSettings whose dynamic_compaction enables at least one trigger.",
                details={"dynamic_compaction": repr(compaction)},
            )
        self.agent_settings = settings
        self.compaction_settings: JevDynamicCompactionSettings = compaction
        self.triggers: tuple[JevCompactionTrigger, ...] = tuple(JEV_COMPACTION_TRIGGERS[key]() for key in compaction.enabled_triggers())
        self._decision_runner: DecisionModelRunner | None = None
        self._decision_unavailable = False
        super().__init__(
            name=f"{settings.name}-compaction",
            system_prompt=Prompts().get(Prompt.JEV_COMPACTION_RECORD_WRITER_SYSTEM_PROMPT),
            tools=(),
            agent_loop_settings=AgentLoopSettings(max_iterations=JEV_COMPACTION_WRITER_MAX_ITERATIONS),
            api_key=settings.api_key,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
        )

    def start_run(self) -> JevCompactionRun:
        """Return fresh run-local state: an empty ledger and zeroed counters."""
        return JevCompactionRun(triggers=self.compaction_settings.enabled_triggers())

    async def prepare(self, run: JevCompactionRun, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
        """Record the latest step, ask Jev whether it began a new unit, and compact finished units when worth it."""
        if not run.active() or not run.ledger.observe(messages, state.iteration_count) or not run.active():
            return
        await self._detect_boundary(run, state)
        if run.active():
            await self._compact_if_worth_it(run, state, messages)

    async def _detect_boundary(self, run: JevCompactionRun, state: BaseAgentRuntimeLoopState) -> None:
        # Asks every enabled trigger's questions in one Jev request and splits the ledger on the first boundary.
        latest = state.iteration_count
        unit = run.ledger.open_unit()
        if unit is None or unit.first_iteration >= latest:
            return
        runner = self._decision()
        if runner is None:
            run.disable(JevCompactionDisabledReason.JEV_UNAVAILABLE)
            return
        view = JevStepView(open_unit=JevRunSteps.collect(state, unit.first_iteration, latest - 1), latest_step=JevRunSteps.collect(state, latest, latest)[0])
        request = self._request(view)
        try:
            response = await runner.arun(request)
        except VidbyteSdkError:
            # @intent jev-errors-mean-no-boundary
            # A failed question must never compact anything, so the step counts as a continuation; repeated
            # failures stop asking instead of adding a failed request to every remaining step.
            run.record_jev_error()
            if run.consecutive_jev_errors >= JEV_COMPACTION_MAX_CONSECUTIVE_JEV_ERRORS:
                run.disable(JevCompactionDisabledReason.JEV_ERRORS)
            return
        run.record_jev_call(JevUsage.from_usage_payload(response.usage or {}))
        for trigger in self.triggers:
            probability = trigger.boundary_probability(response.answers)
            if probability is not None and probability >= trigger.threshold:
                run.ledger.split_before(latest)
                run.boundaries.append(JevUnitBoundary(iteration=latest, trigger=trigger.key, probability=probability))
                return

    def _request(self, view: JevStepView) -> JevDecisionRequest:
        # Merges every enabled trigger's state fields and questions into one request.
        fields: dict[str, str] = {}
        questions: list[JevQuestion] = []
        for trigger in self.triggers:
            fields.update(trigger.state_fields(view))
            questions.extend(trigger.questions())
        return JevDecisionRequest(state=fields, questions=tuple(questions))

    async def _compact_if_worth_it(self, run: JevCompactionRun, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
        # Compacts every eligible unit in one rewrite once their estimated saving pays for one cache miss.
        # @intent batch-rewrites-to-one-cache-miss
        # Each rewrite invalidates the provider's cached prefix, so finished units wait until together they
        # reclaim min_reclaim_tokens, and then all of them go at once.
        eligible = run.ledger.eligible_units(JEV_COMPACTION_KEEP_RECENT_CLOSED_UNITS)
        estimates = {unit.number: run.ledger.estimate_tokens(messages, unit) for unit in eligible}
        reclaim = sum(tokens - JEV_COMPACTION_RECORD_TOKEN_ALLOWANCE for tokens in estimates.values() if tokens > JEV_COMPACTION_RECORD_TOKEN_ALLOWANCE)
        if not eligible or reclaim < self.compaction_settings.min_reclaim_tokens:
            return
        records = [(unit, *await self._record_for(run, state, unit)) for unit in eligible]
        for unit, record, source in records:
            removed = run.ledger.replace_unit(messages, unit, {"role": _RECORD_ROLE, "content": record})
            run.compactions.append(
                JevUnitCompaction(
                    unit=unit.number,
                    first_iteration=unit.first_iteration,
                    last_iteration=unit.last_iteration or unit.first_iteration,
                    messages_removed=removed,
                    estimated_tokens_removed=estimates[unit.number],
                    record_source=source,
                )
            )

    async def _record_for(self, run: JevCompactionRun, state: BaseAgentRuntimeLoopState, unit: JevWorkUnit) -> tuple[str, JevCompactionRecordSource]:
        # Writes one unit's record with the writer model, falling back to a deterministic record.
        last = unit.last_iteration or unit.first_iteration
        steps = JevRunSteps.collect(state, unit.first_iteration, last)
        body, source = await self._write(state.message, steps)
        if body is None:
            run.writer_failures += 1
            body, source = JevRunSteps.render_fallback(steps), JevCompactionRecordSource.FALLBACK
        header = Prompts().get(Prompt.JEV_COMPACTION_RECORD_HEADER)
        return header.format(unit=unit.number, first_step=unit.first_iteration, last_step=last, record=body), source

    async def _write(self, task: str, steps: tuple[JevRunStep, ...]) -> tuple[str | None, JevCompactionRecordSource]:
        # Runs this agent once as the record writer; None when the model call fails or returns nothing.
        template = Prompts().get(Prompt.JEV_COMPACTION_RECORD_WRITER_PROMPT)
        prompt = template.format(task=task[:JEV_COMPACTION_WRITER_TASK_CHARS], steps=JevRunSteps.render_for_writer(steps))
        self.history.clear()
        try:
            reply = await self.arun(prompt)
        except Exception:
            # @intent writer-failure-keeps-a-record
            # The writer calls whatever provider the owner configured, which can fail in provider-specific ways;
            # any failure falls back to the deterministic record, and the report counts it.
            return None, JevCompactionRecordSource.WRITER
        text = reply.content.strip()
        return (text or None), JevCompactionRecordSource.WRITER

    def _decision(self) -> DecisionModelRunner | None:
        # Builds the Jev runner once; a missing key marks Jev unavailable instead of failing every step.
        if self._decision_runner is None and not self._decision_unavailable:
            try:
                self._decision_runner = DecisionModelRunner(self.agent_settings.decision)
            except ConfigurationError:
                self._decision_unavailable = True
        return self._decision_runner


__all__ = ["JevDynamicCompaction"]
