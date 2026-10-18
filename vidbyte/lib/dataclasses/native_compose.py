"""FILE: vidbyte/lib/dataclasses/native_compose.py

PURPOSE: Defines the validated records of the composite thread functions: ThreadStep, one bound call of a thread function that is awaited as step(prompt); StepOutcome, what one step call gave; WorkspaceDiff, the change between two workspace snapshots; JsonAnswer, a structured answer with its repair turns; ThreadVerdict, a verifier's decision; ChainResult, VerifyResult, HandoffResult and StagedResult, what the composites return; and StageSpec, StageAttempt and StageOutcome, the parts of a staged run.
ROLE IN CODEBASE: Built and read by the composites under vidbyte/harnesses/native/compose/ (ThreadStep by the binders in steps.py, the results by chain.py, verify.py, handoff.py, stages.py and answers.py) and re-exported from vidbyte.harnesses.native.compose; callers build StageSpec themselves. The ensemble records live beside these in native_ensemble.py.
ARCHITECTURE NOTE: Every check lives in __post_init__, so a constructed record is always valid. Each field's own type, size and item count goes through RecordFieldValidator and RecordFieldConverter; only the rules that relate fields to each other (exactly one of result and error, a thread id for a continue step, a run step for a stage) and the callable checks of ThreadStep are written here. ThreadStep checks its key, workspace, model, skills and thread id by building the NativeThreadRequest the nine functions use, with a probe prompt that is never sent, and stores the resolved values. It only stores and awaits an injected invoker (spec D-2): calling a function in its verb's argument order is behavior of the compose layer, which also checks the function against its table of the nine. Flags such as ok and failed_step are properties derived from the stored outcomes, never stored beside them.
FUNCTION INVENTORY: ThreadStep.__post_init__ is the narrated main function, _checked_config stores the harness's own config record, and __call__ awaits the invoker. StepOutcome.ok, thread_id and text; JsonAnswer.ok, text and thread_id; ChainResult.failed_step; VerifyResult.agreement and failed_verifiers; HandoffResult.failed_step; StageOutcome.ok, text and thread_id; StagedResult.failed_stage. The other records have only __post_init__.
COMMON MODIFICATION PATTERNS: A new bound adds its constant to vidbyte/lib/constants/native_compose.py and one validator call to its record. A new derived flag is a property, never a stored field.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.harnesses; vidbyte/lib is the bottom layer, so ThreadStep checks only that function and invoker are callable. 2. Do not drop repr=False from ThreadStep.api_key or ThreadStep.invoker, or compare=False from invoker. 3. Do not dispatch on the verb or guard forks in ThreadStep.__call__; ThreadBinder.invoke owns that. 4. Do not build JsonAnswer[X](...); Python 3.11.0 refuses a subscripted call on this slotted generic record.
KNOWN EDGE CASES: ThreadStep.workspace is typed Path | str and skills Sequence[str | Path] because the record must see the raw values: a relative path is refused before it is resolved, and a bare string is a sequence of characters, not a list of skills. After __post_init__ workspace is the resolved Path, skills a tuple of resolved Paths and config the harness's own record. A fork step without a thread id is checked as a run, because compose anchors it later. The decoded JSON lists (ThreadVerdict.findings) are stored as tuples.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_binding.py, tests/features/harness_compose/test_harness_compose_answers.py
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar, Generic, TypeVar

from vidbyte.lib.constants.native_compose import (
    COMPOSE_ANSWER_TEXT_MAX_CHARS,
    COMPOSE_DIFF_MAX_CHARS,
    COMPOSE_DIFF_MAX_FILES,
    COMPOSE_JSON_REPAIR_TURNS,
    COMPOSE_MAX_STAGES,
    COMPOSE_MAX_STEPS,
    COMPOSE_MAX_VERIFIERS,
    COMPOSE_MIN_CHAIN_OUTCOMES,
    COMPOSE_MIN_JSON_TURNS,
    COMPOSE_MIN_STAGES,
    COMPOSE_PROBE_PROMPT,
    COMPOSE_PROBLEM_MAX_CHARS,
    COMPOSE_VERDICT_MAX_FINDINGS,
    STAGE_DEFAULT_RETRIES,
    STAGE_MAX_LADDER,
    STAGE_MAX_RETRIES,
    STAGE_MIN_RETRIES,
    STAGE_MIN_RUNG,
    STAGE_TEMPLATE_FIELDS,
)
from vidbyte.lib.constants.native_threads import NATIVE_CONFIG_ARGUMENT
from vidbyte.lib.dataclasses.native_threads import (
    GrokThreadConfig,
    MuseThreadConfig,
    NativeThreadRequest,
    NativeThreadResult,
    OpencodeThreadConfig,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_compose import StageDecision, VerdictDecision
from vidbyte.lib.enums.native_threads import NativeHarness, NativeThreadVerb
from vidbyte.lib.errors import ConfigurationError, NativeThreadError

AnswerT = TypeVar("AnswerT")


@dataclass(frozen=True, slots=True)
class ThreadStep:
    """One bound call of a thread function, awaited as step(prompt); the key and the invoker never show in repr.

    workspace is typed Path | str and skills Sequence[str | Path]
    because the record must see the raw values, as
    NativeThreadRequest does. After __post_init__ workspace is always
    the resolved Path, skills a tuple of resolved Paths and config the
    harness's own record.
    """

    CONFIG_TYPES: ClassVar[MappingProxyType[NativeHarness, type[GrokThreadConfig] | type[OpencodeThreadConfig] | type[MuseThreadConfig]]] = MappingProxyType(
        {NativeHarness.GROK: GrokThreadConfig, NativeHarness.OPENCODE: OpencodeThreadConfig, NativeHarness.MUSE: MuseThreadConfig}
    )

    function: Callable[..., Awaitable[NativeThreadResult]]
    harness: NativeHarness
    verb: NativeThreadVerb
    api_key: str = field(repr=False)
    workspace: Path | str
    model: str | None = None
    skills: Sequence[str | Path] = ()
    config: GrokThreadConfig | OpencodeThreadConfig | MuseThreadConfig | None = None
    thread_id: str | None = None
    invoker: Callable[..., Awaitable[NativeThreadResult]] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        # The function and the invoker belong to a higher layer, so only
        # their shape is checked here; compose checks the function
        # against its table of the nine thread functions.
        if not callable(self.function):
            raise ConfigurationError(f"ThreadStep.function must be callable; got a value of type {type(self.function).__name__}.", details={"field": "ThreadStep.function"})
        if self.invoker is not None and not callable(self.invoker):
            raise ConfigurationError(f"ThreadStep.invoker must be callable or None; got a value of type {type(self.invoker).__name__}.", details={"field": "ThreadStep.invoker"})
        object.__setattr__(self, "harness", RecordFieldConverter.to_enum(self.harness, NativeHarness, "ThreadStep.harness"))
        object.__setattr__(self, "verb", RecordFieldConverter.to_enum(self.verb, NativeThreadVerb, "ThreadStep.verb"))

        # A continue step needs the thread it continues; a fork without
        # a thread id waits for compose to anchor it.
        if self.verb is NativeThreadVerb.CONTINUE and self.thread_id is None:
            raise ConfigurationError("thread_id must name the thread a continue step continues.", details={"field": "thread_id"})

        # Check the key, workspace, model, skills and thread id with the
        # record the nine functions use, built with a probe prompt that
        # is never sent, and keep its resolved paths.
        probe = NativeThreadRequest(
            harness=self.harness,
            verb=NativeThreadVerb.RUN if self.thread_id is None else self.verb,
            prompt=COMPOSE_PROBE_PROMPT,
            api_key=self.api_key,
            workspace=self.workspace,
            model=self.model,
            skills=self.skills,
            thread_id=self.thread_id,
        )
        object.__setattr__(self, "workspace", probe.workspace)
        object.__setattr__(self, "skills", probe.skills)

        # No config means the harness's default record; a record of
        # another harness, or anything else, is refused naming config.
        object.__setattr__(self, "config", self._checked_config())

    def _checked_config(self) -> GrokThreadConfig | OpencodeThreadConfig | MuseThreadConfig:
        # The harness's own config record, or its default when None.
        expected = ThreadStep.CONFIG_TYPES[self.harness]
        if self.config is None:
            return expected()
        checked: GrokThreadConfig | OpencodeThreadConfig | MuseThreadConfig = RecordFieldConverter.require_instance(self.config, NATIVE_CONFIG_ARGUMENT, expected)
        return checked

    async def __call__(self, prompt: str) -> NativeThreadResult:
        """Run prompt through the invoker the binder stored (spec D-2)."""
        if self.invoker is None:
            raise ConfigurationError("ThreadStep.invoker is None, so this step cannot be awaited by itself; build it with bind_thread or bind_continue, or pass it to a composite.", details={"field": "ThreadStep.invoker"})
        return await self.invoker(self, prompt)


@dataclass(frozen=True, slots=True)
class WorkspaceDiff:
    """The change between two workspace snapshots: the changed paths in git's order, the unified diff text, and whether either was cut at its cap."""

    files: tuple[str, ...]
    text: str
    truncated: bool

    def __post_init__(self) -> None:
        files = RecordFieldConverter.to_tuple(self.files, "WorkspaceDiff.files", item_type=str, max_items=COMPOSE_DIFF_MAX_FILES)
        for name in files:
            RecordFieldValidator.require_text(name, "WorkspaceDiff.files", max_chars=COMPOSE_DIFF_MAX_CHARS, quote=False)
        object.__setattr__(self, "files", files)
        RecordFieldValidator.require_text(self.text, "WorkspaceDiff.text", max_chars=COMPOSE_DIFF_MAX_CHARS, allow_blank=True)
        RecordFieldValidator.require_bool(self.truncated, "WorkspaceDiff.truncated")


@dataclass(frozen=True, slots=True)
class StepOutcome:
    """What one step call gave: its result or the very error it raised, and the workspace diff it made when compose captured one."""

    result: NativeThreadResult | None = None
    error: NativeThreadError | None = None
    diff: WorkspaceDiff | None = None

    def __post_init__(self) -> None:
        if (self.result is None) == (self.error is None):
            raise ConfigurationError("StepOutcome must hold exactly one of result and error.", details={"field": "StepOutcome.result"})
        RecordFieldConverter.require_instance(self.result, "StepOutcome.result", NativeThreadResult, optional=True)
        RecordFieldConverter.require_instance(self.error, "StepOutcome.error", NativeThreadError, optional=True)
        RecordFieldConverter.require_instance(self.diff, "StepOutcome.diff", WorkspaceDiff, optional=True)

    @property
    def ok(self) -> bool:
        """Whether the step returned a result."""
        return self.result is not None

    @property
    def thread_id(self) -> str | None:
        """The result's thread id, else the error's, which may be None."""
        if self.result is not None:
            return self.result.thread_id
        return self.error.thread_id if self.error is not None else None

    @property
    def text(self) -> str:
        """The result's answer text, or empty after an error."""
        return self.result.text if self.result is not None else ""


@dataclass(frozen=True, slots=True)
class JsonAnswer(Generic[AnswerT]):
    """A structured answer: the value the caller's parse built (None when no turn gave a usable answer), every turn with its repairs, and the last problem found."""

    value: AnswerT | None
    turns: tuple[StepOutcome, ...]
    problem: str | None = None

    def __post_init__(self) -> None:
        turns = RecordFieldConverter.to_tuple(self.turns, "JsonAnswer.turns", item_type=StepOutcome, min_items=COMPOSE_MIN_JSON_TURNS, max_items=1 + COMPOSE_JSON_REPAIR_TURNS)
        object.__setattr__(self, "turns", turns)
        RecordFieldValidator.require_optional_text(self.problem, "JsonAnswer.problem", max_chars=COMPOSE_PROBLEM_MAX_CHARS)

    @property
    def ok(self) -> bool:
        """Whether a turn gave a value the caller's parse accepted."""
        return self.value is not None

    @property
    def text(self) -> str:
        """The last turn's answer text."""
        return self.turns[-1].text

    @property
    def thread_id(self) -> str | None:
        """The last turn's thread id."""
        return self.turns[-1].thread_id


@dataclass(frozen=True, slots=True)
class ThreadVerdict:
    """A verifier's decision about the writer's change, a summary of why, and its findings."""

    decision: VerdictDecision
    summary: str
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", RecordFieldConverter.to_enum(self.decision, VerdictDecision, "ThreadVerdict.decision"))
        RecordFieldValidator.require_text(self.summary, "ThreadVerdict.summary", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)
        findings = RecordFieldConverter.to_tuple(self.findings, "ThreadVerdict.findings", item_type=str, max_items=COMPOSE_VERDICT_MAX_FINDINGS)
        for index, finding in enumerate(findings):
            RecordFieldValidator.require_text(finding, f"ThreadVerdict.findings[{index}]", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS, allow_blank=True)
        object.__setattr__(self, "findings", findings)


@dataclass(frozen=True, slots=True)
class ChainResult:
    """What chain_threads returns: one outcome per step that ran, in order."""

    outcomes: tuple[StepOutcome, ...]

    def __post_init__(self) -> None:
        outcomes = RecordFieldConverter.to_tuple(self.outcomes, "ChainResult.outcomes", item_type=StepOutcome, min_items=COMPOSE_MIN_CHAIN_OUTCOMES, max_items=COMPOSE_MAX_STEPS)
        object.__setattr__(self, "outcomes", outcomes)

    @property
    def failed_step(self) -> int | None:
        """The index of the step that failed, or None when every step succeeded."""
        return next((index for index, outcome in enumerate(self.outcomes) if not outcome.ok), None)


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """What verify_with returns: the writer's outcome with its diff, and one structured verdict per verifier that ran."""

    writer: StepOutcome
    verdicts: tuple[JsonAnswer[ThreadVerdict], ...] = ()

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.writer, "VerifyResult.writer", StepOutcome)
        object.__setattr__(self, "verdicts", RecordFieldConverter.to_tuple(self.verdicts, "VerifyResult.verdicts", item_type=JsonAnswer, max_items=COMPOSE_MAX_VERIFIERS))

    @property
    def agreement(self) -> bool:
        """True when there is a verdict, every verdict parsed and every decision is the same (INV-25)."""
        decisions = {answer.value.decision for answer in self.verdicts if answer.value is not None}
        return bool(self.verdicts) and all(answer.ok for answer in self.verdicts) and len(decisions) == 1

    @property
    def failed_verifiers(self) -> tuple[int, ...]:
        """The index of every verifier whose step failed or whose verdict did not parse, in order."""
        return tuple(index for index, answer in enumerate(self.verdicts) if not answer.ok)


@dataclass(frozen=True, slots=True)
class HandoffResult:
    """What handoff_thread returns: the summary turn on from_thread, and the seeded turn on to_step, which is None when the summary failed."""

    summary: StepOutcome
    target: StepOutcome | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.summary, "HandoffResult.summary", StepOutcome)
        RecordFieldConverter.require_instance(self.target, "HandoffResult.target", StepOutcome, optional=True)

    @property
    def failed_step(self) -> int | None:
        """0 when the summary turn failed, 1 when the seeded turn failed, else None."""
        if not self.summary.ok:
            return 0
        if self.target is not None and not self.target.ok:
            return 1
        return None


@dataclass(frozen=True, slots=True)
class StageSpec:
    """One stage of run_staged_threads: a run step, the template its prompt is rendered from, the retries it may spend, and a ladder of stronger configs of the step's own harness."""

    step: ThreadStep
    template: str
    retries: int = STAGE_DEFAULT_RETRIES
    ladder: Sequence[GrokThreadConfig | OpencodeThreadConfig | MuseThreadConfig] = ()

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.step, "StageSpec.step", ThreadStep)
        if self.step.verb is not NativeThreadVerb.RUN:
            raise ConfigurationError("StageSpec.step must be a run step, because every attempt starts a fresh thread.", details={"field": "StageSpec.step"})
        RecordFieldValidator.require_template(self.template, "StageSpec.template", fields=STAGE_TEMPLATE_FIELDS)
        RecordFieldValidator.require_int(self.retries, "StageSpec.retries", minimum=STAGE_MIN_RETRIES, maximum=STAGE_MAX_RETRIES)
        object.__setattr__(self, "ladder", RecordFieldConverter.to_tuple(self.ladder, "StageSpec.ladder", item_type=type(self.step.config), max_items=STAGE_MAX_LADDER))


@dataclass(frozen=True, slots=True)
class StageAttempt:
    """One attempt of a stage: the ladder rung it ran on (0 is the step's own config), its outcome, and what the stage did next when it failed."""

    rung: int
    outcome: StepOutcome
    decision: StageDecision | None = None

    def __post_init__(self) -> None:
        RecordFieldValidator.require_int(self.rung, "StageAttempt.rung", minimum=STAGE_MIN_RUNG, maximum=STAGE_MAX_LADDER)
        RecordFieldConverter.require_instance(self.outcome, "StageAttempt.outcome", StepOutcome)
        if self.decision is not None:
            object.__setattr__(self, "decision", RecordFieldConverter.to_enum(self.decision, StageDecision, "StageAttempt.decision"))


@dataclass(frozen=True, slots=True)
class StageOutcome:
    """Every attempt one stage made, in order; a stage that never ran has none."""

    attempts: tuple[StageAttempt, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempts", RecordFieldConverter.to_tuple(self.attempts, "StageOutcome.attempts", item_type=StageAttempt, max_items=1 + STAGE_MAX_RETRIES))

    @property
    def ok(self) -> bool:
        """Whether the stage's last attempt succeeded."""
        return bool(self.attempts) and self.attempts[-1].outcome.ok

    @property
    def text(self) -> str:
        """The last attempt's answer text, or empty when the stage never ran."""
        return self.attempts[-1].outcome.text if self.attempts else ""

    @property
    def thread_id(self) -> str | None:
        """The last attempt's thread id, or None when the stage never ran."""
        return self.attempts[-1].outcome.thread_id if self.attempts else None


@dataclass(frozen=True, slots=True)
class StagedResult:
    """What run_staged_threads returns: one outcome per stage, in order; the stages after a failed one have no attempts."""

    stages: tuple[StageOutcome, ...]

    def __post_init__(self) -> None:
        stages = RecordFieldConverter.to_tuple(self.stages, "StagedResult.stages", item_type=StageOutcome, min_items=COMPOSE_MIN_STAGES, max_items=COMPOSE_MAX_STAGES)
        object.__setattr__(self, "stages", stages)

    @property
    def failed_stage(self) -> int | None:
        """The index of the stage that failed, or None when every stage succeeded."""
        return next((index for index, stage in enumerate(self.stages) if not stage.ok), None)


__all__ = ["AnswerT", "ChainResult", "HandoffResult", "JsonAnswer", "StageAttempt", "StageOutcome", "StageSpec", "StagedResult", "StepOutcome", "ThreadStep", "ThreadVerdict", "VerifyResult", "WorkspaceDiff"]
