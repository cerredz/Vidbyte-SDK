"""FILE: vidbyte/harnesses/native/compose/stages.py

PURPOSE: The staged composite: ThreadStages.run_staged_threads runs one to twenty-five stages one after another, each stage a run step whose template may splice the previous stage's answer, and after a failed attempt retries it, raises it to a stronger config from its ladder or stops, by the decision the failure's problem maps to; ThreadStages.classify makes that decision.
ROLE IN CODEBASE: run_staged_threads is bound as a public name in vidbyte/harnesses/native/compose/__init__.py. It builds on the plumbing modules: steps.py for the step checks and the ladder rungs, texts.py for the templates and the prompt fit, and calls.py for each attempt. Its decision table is STAGE_DECISIONS in vidbyte/lib/constants/native_compose.py.
ARCHITECTURE NOTE: A sequential pipeline (spec D-27) with no git, worktree or backstop (INV-6). Each stage is one run-then-route loop (D-14, the fallback-coordination pattern): run a fresh thread, then route on the failure's problem, found by a reverse lookup of the error's failure code in NATIVE_THREAD_FAILURE_CODES; a code with no problem gets STAGE_UNCLASSIFIED_DECISION. The loop has no sleep, no backoff and no deadline of its own, because every attempt is bounded by its own config's timeout (INV-22). Each attempt goes through ComposeCalls.call, so a Grok attempt takes its workspace's slot for that attempt only (INV-13). The module holds no literals (base spec INV-15).
FUNCTION INVENTORY: ThreadStages.run_staged_threads is the narrated main function, holding each stage's loop; classify gives the decision after one attempt; _stages checks the stages; _fit checks every template against its step; _values fills a stage's template.
COMMON MODIFICATION PATTERNS: A change to what a failure leads to is a change to STAGE_DECISIONS, never a branch here. A new stage value for templates is one ComposeField member in STAGE_TEMPLATE_FIELDS, filled in _values and measured in _fit.
WHAT NOT TO DO IN THIS FILE: 1. Do not sleep or back off between attempts (INV-21, INV-22). 2. Do not continue a failed attempt's thread; every attempt is a fresh run with the same prompt. 3. Do not change a step's permission mode; a rung only swaps in a ladder config the caller wrote (D-21). 4. Do not run a stage after a failed one.
KNOWN EDGE CASES: A stage with no ladder stays on rung 0 when its failure raises effort, so run_failed simply retries its config (EC-53). A failed attempt records its decision even when no attempt is left. Stage 1's template is rendered with no values, so a doubled brace in it reaches the step as one brace. A later stage's template made only of {previous} sends a blank prompt when the previous answer is empty, which the step refuses as its own failure.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_stages.py, tests/features/harness_compose/test_harness_compose_binding.py, tests/features/harness_compose/test_harness_compose_concurrency.py, tests/features/harness_compose/test_harness_compose_validation.py
"""

from __future__ import annotations

import string
from collections.abc import Sequence

from vidbyte.harnesses.native.compose.calls import ComposeCalls
from vidbyte.harnesses.native.compose.steps import StepRoles, ThreadBinder
from vidbyte.harnesses.native.compose.texts import ComposeTexts, PromptFitter
from vidbyte.lib.constants import native_compose, native_threads
from vidbyte.lib.dataclasses.native_compose import (
    StageAttempt,
    StagedResult,
    StageOutcome,
    StageSpec,
    StepOutcome,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_compose import ComposeField, StageDecision
from vidbyte.lib.errors import ConfigurationError


class ThreadStages:
    """Runs stages one after another, each a fresh run that is retried, raised to a stronger config or stopped by how its last attempt failed."""

    @staticmethod
    async def run_staged_threads(stages: Sequence[StageSpec]) -> StagedResult:
        """Run the stages in order, stage k+1 sent stage k's answer; within a stage, retry, raise effort or stop by the decision table, and stop the run after the first failed stage (spec INV-16, INV-17, INV-21)."""
        # Check every stage before anything runs, and that each template
        # fits its step with the previous answer at its longest.
        checked = ThreadStages._stages(stages)
        await ThreadStages._fit(checked)
        keys = tuple(stage.step.api_key for stage in checked)

        outcomes: list[StageOutcome] = []
        for stage in checked:
            # A stage after a failed one never runs and has no attempts.
            if outcomes and not outcomes[-1].ok:
                outcomes.append(StageOutcome())
                continue

            # Stage 1's template has no values; a later stage's template
            # gets the previous stage's answer, spliced.
            frame = ComposeTexts.render(stage.template, ThreadStages._values(outcomes))

            # @intent stage-attempts-follow-the-decision-table
            # Every attempt is a fresh run of the stage's step with the
            # same prompt, on rung 0 (the step's own config) or on a
            # ladder config. After a failure the decision table says what
            # comes next: RETRY keeps the rung, RAISE_EFFORT climbs one
            # rung and stays on the top one, ABORT ends the stage. Each
            # attempt is bounded by its own config's timeout, so there is
            # no sleep and no backoff between attempts.
            tried: list[StageAttempt] = []
            rung = 0
            while len(tried) <= stage.retries:
                step = ThreadBinder.rung(stage.step, stage.ladder[rung - 1]) if rung else stage.step
                outcome = await ComposeCalls.call(step, await PromptFitter.fit(frame, step, keys))
                decision = ThreadStages.classify(outcome)
                tried.append(StageAttempt(rung=rung, outcome=outcome, decision=decision))
                if decision is None or decision is StageDecision.ABORT:
                    break
                rung = min(rung + 1, len(stage.ladder)) if decision is StageDecision.RAISE_EFFORT else rung
            outcomes.append(StageOutcome(attempts=tuple(tried)))
        return StagedResult(stages=tuple(outcomes))

    @staticmethod
    def classify(outcome: StepOutcome) -> StageDecision | None:
        """What a stage does after an attempt: None after a success; after a failure, the STAGE_DECISIONS entry for the problem its failure code stands for, or STAGE_UNCLASSIFIED_DECISION for a code that stands for none (spec D-14)."""
        if outcome.error is None:
            return None
        code = outcome.error.failure_code
        problem = next((problem for (_harness, problem), known in native_threads.NATIVE_THREAD_FAILURE_CODES.items() if known == code), None)
        return native_compose.STAGE_UNCLASSIFIED_DECISION if problem is None else native_compose.STAGE_DECISIONS[problem]

    @staticmethod
    def _stages(stages: object) -> tuple[StageSpec, ...]:
        # One to twenty-five stages. Each step must be one of the nine
        # functions with its own arguments, each template must be text a
        # step can take, and the first template has no answer to splice.
        items = StepRoles.counted(stages, native_compose.COMPOSE_STAGES_ARGUMENT, minimum=native_compose.COMPOSE_MIN_STAGES, maximum=native_compose.COMPOSE_MAX_STAGES)
        checked: list[StageSpec] = []
        for index, item in enumerate(items):
            argument = StepRoles.item(native_compose.COMPOSE_STAGES_ARGUMENT, index)
            stage: StageSpec = RecordFieldConverter.require_instance(item, argument, StageSpec)
            ThreadBinder.require_step(stage.step, StepRoles.member(argument, native_compose.COMPOSE_STEP_ARGUMENT))
            template = StepRoles.member(argument, native_compose.COMPOSE_TEMPLATE_ARGUMENT)
            RecordFieldValidator.require_text(stage.template, template, max_chars=native_threads.NATIVE_PROMPT_MAX_CHARS, pattern=native_threads.NATIVE_PROMPT_PATTERN)
            names = {name for _literal, name, _spec, _conversion in string.Formatter().parse(stage.template)}
            if not index and ComposeField.PREVIOUS in names:
                raise ConfigurationError(native_compose.COMPOSE_FIRST_STAGE_RULE.format(argument=template), details={native_threads.NATIVE_FIELD_DETAIL_KEY: template})
            checked.append(stage)
        return tuple(checked)

    @staticmethod
    async def _fit(stages: Sequence[StageSpec]) -> None:
        # Each template must fit its step with the previous answer at its
        # longest truncation note; every rung is the same harness, so the
        # step's own config stands for its whole ladder.
        for index, stage in enumerate(stages):
            argument = StepRoles.item(native_compose.COMPOSE_STAGES_ARGUMENT, index)
            frame = ComposeTexts.render(stage.template, {ComposeField.PREVIOUS: ComposeTexts.spliced("")})
            await PromptFitter.check(frame, stage.step, argument=StepRoles.member(argument, native_compose.COMPOSE_TEMPLATE_ARGUMENT), receiver=StepRoles.member(argument, native_compose.COMPOSE_STEP_ARGUMENT))

    @staticmethod
    def _values(outcomes: Sequence[StageOutcome]) -> dict[ComposeField, str | tuple[tuple[str, bool], ...]]:
        # No values for stage 1, so a doubled brace becomes one; the
        # previous stage's answer, spliced, for every later stage.
        if not outcomes:
            return {}
        return {ComposeField.PREVIOUS: ComposeTexts.spliced(outcomes[-1].text)}


__all__ = ["ThreadStages"]
