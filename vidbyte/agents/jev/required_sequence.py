"""FILE: vidbyte/agents/jev/required_sequence.py

PURPOSE: Implements done check #15 as a JevRunSection: derive the ordered stages a request requires, and accept a finish attempt only when the recorded run shows every stage done, in order.
ROLE IN CODEBASE: JevRuntime enables JevRequiredSequence when JevAgentSettings.required_sequence is true; the builders add its state and handoff parts, and its areview decides each finish attempt.
ARCHITECTURE NOTE: Code owns every fact: stage IDs, the source-text check, cited-event validation, the order rule, and the combination of answers. Jev only answers two recognition questions per stage (work shown, previous output used) over the handoff's descriptions, following skills/asking-jev-questions/SKILL.md.
COMMON MODIFICATION PATTERNS: Change question wording in _work_question or _previous_question and keep the named state fields they point at in _jev_state in sync.
KNOWN EDGE CASES: A stage with no located work fails in code and is never sent to Jev; the order rule forbids interleaving, so going back to an earlier stage after a later one began is out of order until every later stage is redone.
RELATED DOCS: docs/design/jev-required-sequence.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_required_sequence.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from vidbyte.agents.jev.run_state import (
    JevPayload,
    JevRunEvent,
    JevRunSection,
    JevSchema,
    JevSectionHandoff,
    JevSectionReview,
    JevSectionState,
    JsonPayload,
    JsonSchema,
)
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.constants.jev import (
    JEV_NOUL_TRUE,
    JEV_NOUL_YES_THRESHOLD,
    JEV_REQUIRED_SEQUENCE_MAX_STAGES,
    JEV_REQUIRED_SEQUENCE_MIN_STAGES,
    JEV_STAGE_ID_PREFIX,
)
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest, JevQuestion
from vidbyte.lib.enums import JevQuestionType
from vidbyte.lib.enums.jev_run_state import (
    JevRunSectionKey,
    JevSectionStatus,
    JevStageFailure,
)
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import AgentExecutionError, VidbyteSdkError
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.prompts.catalog import Prompts

_SOURCE_TRIM = " \t\r\n\"'`.,;:“”‘’"
_STATE_WHERE = "run_state.sections.required_sequence"
_HANDOFF_WHERE = "handoff.sections.required_sequence"
_NO_ORDER = "request_has_no_required_order"
_TOO_FEW = "fewer_than_min_stages"
_TOO_MANY = "more_than_max_stages"
_BLANK_FIELD = "stage_field_blank"
_SOURCE_NOT_IN_REQUEST = "stage_source_not_in_request"


@dataclass(frozen=True, slots=True)
class JevStage:
    """One required stage, derived from the request by the run-state builder and numbered by code."""

    stage_id: str
    position: int
    name: str
    source_text: str
    completion_criterion: str
    produces: str
    depends_on_previous: bool

    def label(self) -> str:
        """Return the name used in feedback, such as 'Stage 2 (Draft)'."""
        return f"Stage {self.position} ({self.name})"

    def to_payload(self) -> dict[str, Any]:
        """Render the stage for the handoff builder."""
        return {
            "stage_id": self.stage_id,
            "name": self.name,
            "source_text": self.source_text,
            "completion_criterion": self.completion_criterion,
            "produces": self.produces,
            "depends_on_previous": self.depends_on_previous,
        }


@dataclass(frozen=True, slots=True)
class JevRequiredSequenceState(JevSectionState):
    """The required_sequence section of the run state."""

    stages: tuple[JevStage, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        """Render the section, including its stages, for the handoff builder."""
        return {"status": self.status.value, "reason": self.reason, "stages": [stage.to_payload() for stage in self.stages]}


@dataclass(frozen=True, slots=True)
class JevWorkItem:
    """One piece of work or failure the handoff found, with the events that show it."""

    description: str
    event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JevStageHandoff:
    """What the handoff builder found in the event log for one stage."""

    stage_id: str
    observed_work: tuple[JevWorkItem, ...]
    outputs_produced: tuple[str, ...]
    inputs_used: tuple[str, ...]
    first_event_id: str
    last_work_event_id: str
    failures: tuple[JevWorkItem, ...]
    missing_or_uncertain: tuple[str, ...]

    def has_work(self) -> bool:
        """Return whether the log shows any work for this stage."""
        return bool(self.observed_work)


@dataclass(frozen=True, slots=True)
class JevRequiredSequenceHandoff(JevSectionHandoff):
    """The required_sequence section of the handoff, one entry per stage in state order."""

    stages: tuple[JevStageHandoff, ...] = ()


@dataclass(frozen=True, slots=True)
class JevStageVerdict:
    """Code's decision for one stage, with the Jev probabilities it used."""

    stage_id: str
    failure: JevStageFailure | None
    work_shown_probability: float | None = None
    uses_previous_probability: float | None = None


@dataclass(frozen=True, slots=True)
class JevRequiredSequenceReview(JevSectionReview):
    """Review of the required_sequence section at one finish attempt."""

    stages: tuple[JevStageVerdict, ...] = ()

    @property
    def required_sequence_complete(self) -> bool:
        """Return whether every stage finished in the required order (the done check's state)."""
        return self.passed


_StagePair = tuple[JevStage, JevStageHandoff]


class JevRequiredSequence(JevRunSection):
    """Done check #15: the request's stages happened, each in order."""

    key = JevRunSectionKey.REQUIRED_SEQUENCE

    def state_instructions(self) -> str:
        """Return the run-state builder's instructions for deriving stages."""
        return Prompts().get(Prompt.JEV_RUN_STATE_REQUIRED_SEQUENCE_STATE)

    def state_schema(self) -> JsonSchema:
        """Return the builder schema for the stage list."""
        stage = JevSchema.closed_object(
            {
                "name": JevSchema.string("A short name of one to three words."),
                "source_text": JevSchema.string("The exact words from the request that ask for this stage."),
                "completion_criterion": JevSchema.string("What finishing this stage visibly looks like."),
                "produces": JevSchema.string("What this stage outputs for later stages, or an empty string."),
                "depends_on_previous": JevSchema.boolean("Whether this stage works from the previous stage's output."),
            }
        )
        return JevSchema.closed_object({"stages": {"type": "array", "items": stage, "description": "Required stages in order, or an empty list."}})

    def parse_state(self, payload: JsonPayload, *, request: str) -> JevSectionState:
        """Number the stages and keep the section active only when every stage is real and quoted from the request."""
        # @intent invented-stages-disable-the-gate
        # A stage the user never asked for would block every correct run, so any stage whose words are
        # not in the request turns the section off for the run (recorded) instead of gating on a guess.
        raw_stages = JevPayload.objects(payload, "stages", where=_STATE_WHERE)
        if not raw_stages:
            return JevSectionState(JevSectionStatus.INACTIVE, _NO_ORDER)
        if len(raw_stages) < JEV_REQUIRED_SEQUENCE_MIN_STAGES:
            return JevSectionState(JevSectionStatus.INACTIVE, _TOO_FEW)
        if len(raw_stages) > JEV_REQUIRED_SEQUENCE_MAX_STAGES:
            return JevSectionState(JevSectionStatus.INACTIVE, _TOO_MANY)
        stages = tuple(self._parse_stage(raw, position) for position, raw in enumerate(raw_stages, start=1))
        if any(not (stage.name and stage.source_text and stage.completion_criterion) for stage in stages):
            return JevSectionState(JevSectionStatus.INACTIVE, _BLANK_FIELD)
        request_text = self._normalized(request)
        if any(self._normalized(stage.source_text) not in request_text for stage in stages):
            return JevSectionState(JevSectionStatus.INACTIVE, _SOURCE_NOT_IN_REQUEST)
        return JevRequiredSequenceState(JevSectionStatus.ACTIVE, stages=stages)

    def agent_instructions(self, state: JevSectionState) -> str:
        """Return the stage list appended to the main agent's system prompt."""
        lines = [f"{stage.label()}: {stage.completion_criterion}" for stage in self._state(state).stages]
        return Prompts().get(Prompt.JEV_RUN_STATE_REQUIRED_SEQUENCE_AGENT).rstrip() + "\n\n" + "\n".join(lines)

    def handoff_instructions(self) -> str:
        """Return the handoff builder's instructions for this section."""
        return Prompts().get(Prompt.JEV_RUN_STATE_REQUIRED_SEQUENCE_HANDOFF)

    def handoff_schema(self, state: JevSectionState) -> JsonSchema:
        """Return a schema with exactly one entry per stage ID."""
        stage_ids = [stage.stage_id for stage in self._state(state).stages]
        work = {"type": "array", "items": JevSchema.closed_object({"description": JevSchema.string("One sentence."), "event_ids": JevSchema.strings("Event IDs that show it.")})}
        entry = JevSchema.closed_object(
            {
                "stage_id": {"type": "string", "enum": stage_ids, "description": "The stage's ID from the run state."},
                "observed_work": {**work, "description": "Work the log shows for this stage."},
                "outputs_produced": JevSchema.strings("What this stage produced."),
                "inputs_used": JevSchema.strings("What this stage worked from."),
                "first_event_id": JevSchema.string("First event performing this stage's work, or an empty string."),
                "last_work_event_id": JevSchema.string("Last event performing this stage's work, or an empty string."),
                "failures": {**work, "description": "Failed or abandoned attempts at this stage's work."},
                "missing_or_uncertain": JevSchema.strings("Parts of the completion criterion the log does not show."),
            }
        )
        stages = {"type": "array", "items": entry, "minItems": len(stage_ids), "maxItems": len(stage_ids)}
        return JevSchema.closed_object({"stages": stages})

    def parse_handoff(self, payload: JsonPayload, *, state: JevSectionState, event_ids: frozenset[str]) -> JevSectionHandoff:
        """Require exactly the state's stages and only events that exist in the log."""
        stages = self._state(state).stages
        known = {stage.stage_id for stage in stages}
        entries: dict[str, JevStageHandoff] = {}
        for raw in JevPayload.objects(payload, "stages", where=_HANDOFF_WHERE):
            entry = self._parse_entry(raw, event_ids)
            if entry.stage_id not in known or entry.stage_id in entries:
                raise self._handoff_error(f"stage_id {entry.stage_id!r} is unknown or listed twice; list each of {sorted(known)} exactly once.", stage_id=entry.stage_id)
            entries[entry.stage_id] = entry
        missing = sorted(known - set(entries))
        if missing:
            raise self._handoff_error(f"The handoff has no entry for {missing}; include every stage, even one with no work.", missing=missing)
        return JevRequiredSequenceHandoff(stages=tuple(entries[stage.stage_id] for stage in stages))

    async def areview(self, *, state: JevSectionState, handoff: JevSectionHandoff, decider: DecisionModelRunner | None) -> JevSectionReview:
        """Apply the code checks, ask Jev about stages with work, and name the first failing stage."""
        if not isinstance(handoff, JevRequiredSequenceHandoff):
            raise AgentExecutionError("The required_sequence review needs a required_sequence handoff.", details={"received": type(handoff).__name__})
        pairs: tuple[_StagePair, ...] = tuple(zip(self._state(state).stages, handoff.stages, strict=True))
        questions = self._questions(pairs)
        answers, jev_available, usage = await self._aask(decider, pairs, questions)
        verdicts = tuple(self._verdict(index, pairs, answers) for index in range(len(pairs)))
        failing = next((index for index, verdict in enumerate(verdicts) if verdict.failure is not None), None)
        feedback = "" if failing is None else self._feedback(failing, pairs, verdicts[failing])
        return JevRequiredSequenceReview(section=self.key, passed=failing is None, feedback=feedback, jev_available=jev_available, jev_usage=usage, stages=verdicts)

    @staticmethod
    def _state(state: JevSectionState) -> JevRequiredSequenceState:
        # Narrows the shared section type; an inactive or foreign state is a runtime wiring bug.
        if not isinstance(state, JevRequiredSequenceState):
            raise AgentExecutionError("The required_sequence section is not active for this run.", details={"received": type(state).__name__})
        return state

    @staticmethod
    def _parse_stage(raw: JsonPayload, position: int) -> JevStage:
        # Numbers the stage in code and forces the first stage to depend on nothing.
        where = f"{_STATE_WHERE}.stages[{position - 1}]"
        return JevStage(
            stage_id=f"{JEV_STAGE_ID_PREFIX}{position}",
            position=position,
            name=JevPayload.text(raw, "name", where=where),
            source_text=JevPayload.text(raw, "source_text", where=where).strip(_SOURCE_TRIM),
            completion_criterion=JevPayload.text(raw, "completion_criterion", where=where),
            produces=JevPayload.text(raw, "produces", where=where),
            depends_on_previous=JevPayload.flag(raw, "depends_on_previous", where=where) and position > 1,
        )

    @staticmethod
    def _normalized(text: str) -> str:
        # Compares quotes case- and whitespace-insensitively; nothing else may differ.
        return " ".join(text.casefold().split())

    def _parse_entry(self, raw: JsonPayload, event_ids: frozenset[str]) -> JevStageHandoff:
        # Reads one entry and checks every cited event exists and the stage's span is well formed.
        stage_id = JevPayload.text(raw, "stage_id", where=_HANDOFF_WHERE)
        where = f"{_HANDOFF_WHERE}.{stage_id}"
        entry = JevStageHandoff(
            stage_id=stage_id,
            observed_work=self._work_items(raw, "observed_work", where, event_ids),
            outputs_produced=JevPayload.texts(raw, "outputs_produced", where=where),
            inputs_used=JevPayload.texts(raw, "inputs_used", where=where),
            first_event_id=JevPayload.text(raw, "first_event_id", where=where),
            last_work_event_id=JevPayload.text(raw, "last_work_event_id", where=where),
            failures=self._work_items(raw, "failures", where, event_ids),
            missing_or_uncertain=JevPayload.texts(raw, "missing_or_uncertain", where=where),
        )
        self._check_span(entry, event_ids)
        return entry

    def _work_items(self, raw: JsonPayload, key: str, where: str, event_ids: frozenset[str]) -> tuple[JevWorkItem, ...]:
        # Reads work or failure items and rejects any event ID the log does not contain.
        items: list[JevWorkItem] = []
        for index, item in enumerate(JevPayload.objects(raw, key, where=where)):
            item_where = f"{where}.{key}[{index}]"
            cited = JevPayload.texts(item, "event_ids", where=item_where)
            unknown = sorted(set(cited) - event_ids)
            if unknown:
                raise self._handoff_error(f"{item_where} cites event IDs that are not in the event log: {unknown}.", unknown_event_ids=unknown)
            items.append(JevWorkItem(description=JevPayload.text(item, "description", where=item_where), event_ids=cited))
        return tuple(items)

    def _check_span(self, entry: JevStageHandoff, event_ids: frozenset[str]) -> None:
        # A stage with work needs a known first and last event in order; a stage without work needs neither.
        span = (entry.first_event_id, entry.last_work_event_id)
        if not entry.has_work():
            if any(span):
                raise self._handoff_error(f"{entry.stage_id} lists no observed_work but cites a first or last event; leave both empty or list the work.", stage_id=entry.stage_id)
            return
        if not all(event_id in event_ids for event_id in span):
            raise self._handoff_error(f"{entry.stage_id} lists observed_work, so first_event_id and last_work_event_id must both be event IDs from the log.", stage_id=entry.stage_id)
        if JevRunEvent.position(span[0]) > JevRunEvent.position(span[1]):
            raise self._handoff_error(f"{entry.stage_id} has first_event_id after last_work_event_id.", stage_id=entry.stage_id)

    @staticmethod
    def _handoff_error(message: str, **details: object) -> AgentExecutionError:
        # One error type for every handoff defect; its message becomes the rebuild's correction text.
        return AgentExecutionError(f"Invalid required_sequence handoff: {message}", details={"section": JevRunSectionKey.REQUIRED_SEQUENCE.value, **details})

    def _questions(self, pairs: Sequence[_StagePair]) -> tuple[JevQuestion, ...]:
        # Asks only what code cannot decide: stages without work already failed and are not sent.
        questions: list[JevQuestion] = []
        for index, (stage, entry) in enumerate(pairs):
            if not entry.has_work():
                continue
            questions.append(self._work_question(stage))
            if stage.depends_on_previous and pairs[index - 1][1].has_work():
                questions.append(self._previous_question(stage, pairs[index - 1][0]))
        return tuple(questions)

    @staticmethod
    def _work_question(stage: JevStage) -> JevQuestion:
        # Definition first, fields by name, and "does it show" rather than "is it true" (skill strategies 1, 6, 18).
        field = f"stages.{stage.stage_id}"
        return JevQuestion(
            name=f"{stage.stage_id}_work_shown",
            question_type=JevQuestionType.NOUL,
            instructions=(
                f"`{field}` describes the {stage.name} stage of a task. Its `completion_criterion` defines what finishing this stage looks like. "
                f"Its `observed_work` lists the work a reviewer found in the agent's recorded actions for this stage. "
                f"Items in its `failures` did not succeed and do not count as work. Its `missing_or_uncertain` lists what the reviewer could not find. "
                f"Does `{field}.observed_work` show the work that `{field}.completion_criterion` describes?"
            ),
        )

    @staticmethod
    def _previous_question(stage: JevStage, previous: JevStage) -> JevQuestion:
        # A matching question over named fields; code decides when it applies (depends_on_previous).
        field, prior = f"stages.{stage.stage_id}", f"stages.{previous.stage_id}"
        return JevQuestion(
            name=f"{stage.stage_id}_uses_previous_output",
            question_type=JevQuestionType.NOUL,
            instructions=(
                f"`{prior}.outputs_produced` lists what the {previous.name} stage produced, and `{prior}.produces` names the output it was meant to produce. "
                f"`{field}.inputs_used` lists what the {stage.name} stage worked from. "
                f"Does `{field}.inputs_used` include an output of the {previous.name} stage, as listed in `{prior}.outputs_produced` or named in `{prior}.produces`?"
            ),
        )

    @staticmethod
    def _jev_state(pairs: Sequence[_StagePair]) -> dict[str, Any]:
        # Only the fields the questions point at; event IDs and request text are not needed for recognition.
        return {
            "stages": {
                stage.stage_id: {
                    "name": stage.name,
                    "completion_criterion": stage.completion_criterion,
                    "produces": stage.produces,
                    "observed_work": [item.description for item in entry.observed_work],
                    "outputs_produced": list(entry.outputs_produced),
                    "inputs_used": list(entry.inputs_used),
                    "failures": [item.description for item in entry.failures],
                    "missing_or_uncertain": list(entry.missing_or_uncertain),
                }
                for stage, entry in pairs
            }
        }

    async def _aask(self, decider: DecisionModelRunner | None, pairs: Sequence[_StagePair], questions: tuple[JevQuestion, ...]) -> tuple[Mapping[str, JevAnswer], bool, JevUsage | None]:
        # One batched Jev request; without a decider or on a provider failure only the code checks decide.
        if not questions:
            return {}, True, None
        if decider is None:
            return {}, False, None
        try:
            response = await decider.arun(JevDecisionRequest(state=self._jev_state(pairs), questions=questions))
        except VidbyteSdkError:
            return {}, False, None
        return dict(response.answers), True, JevUsage.from_usage_payload(response.usage or {})

    def _verdict(self, index: int, pairs: Sequence[_StagePair], answers: Mapping[str, JevAnswer]) -> JevStageVerdict:
        # Combines code facts and Jev answers for one stage; code facts always win.
        stage, entry = pairs[index]
        work = self._true_probability(answers, f"{stage.stage_id}_work_shown")
        previous = self._true_probability(answers, f"{stage.stage_id}_uses_previous_output")
        return JevStageVerdict(stage_id=stage.stage_id, failure=self._first_failure(index, pairs, work, previous), work_shown_probability=work, uses_previous_probability=previous)

    @staticmethod
    def _first_failure(index: int, pairs: Sequence[_StagePair], work: float | None, previous: float | None) -> JevStageFailure | None:
        # Order of checks: located work, strict order after the previous stage, then Jev's two recognitions.
        entry = pairs[index][1]
        if not entry.has_work():
            return JevStageFailure.NO_WORK
        prior = pairs[index - 1][1] if index > 0 else None
        if prior is not None and prior.has_work() and JevRunEvent.position(entry.first_event_id) <= JevRunEvent.position(prior.last_work_event_id):
            return JevStageFailure.OUT_OF_ORDER
        if work is not None and work < JEV_NOUL_YES_THRESHOLD:
            return JevStageFailure.WORK_NOT_SHOWN
        if previous is not None and previous < JEV_NOUL_YES_THRESHOLD:
            return JevStageFailure.PREVIOUS_OUTPUT_NOT_USED
        return None

    @staticmethod
    def _true_probability(answers: Mapping[str, JevAnswer], name: str) -> float | None:
        # A missing answer means the question was not asked or Jev was unavailable.
        answer = answers.get(name)
        return None if answer is None else answer.probabilities.get(JEV_NOUL_TRUE)

    @staticmethod
    def _feedback(index: int, pairs: Sequence[_StagePair], verdict: JevStageVerdict) -> str:
        # Names the first failing stage and the concrete next step, so the same loop can continue from it.
        stage, entry = pairs[index]
        previous = pairs[index - 1] if index > 0 else None
        redo_later = "then continue with every later stage in order."
        if verdict.failure is JevStageFailure.NO_WORK:
            detail = f"{stage.label()} has no recorded work. Finishing it means: {stage.completion_criterion} Do this stage, {redo_later}"
        elif verdict.failure is JevStageFailure.OUT_OF_ORDER and previous is not None:
            detail = (
                f"{stage.label()} began at {entry.first_event_id}, before {previous[0].label()} finished at {previous[1].last_work_event_id}. "
                f"Finish all {previous[0].name} work first, then redo {stage.label()} and every later stage in order."
            )
        elif verdict.failure is JevStageFailure.PREVIOUS_OUTPUT_NOT_USED and previous is not None:
            output = previous[0].produces or "its output"
            detail = f"{stage.label()} does not show that it worked from {previous[0].label()}'s output ({output}). Redo {stage.label()} using that output, {redo_later}"
        else:
            detail = f"{stage.label()}: the recorded work does not show this: {stage.completion_criterion} Complete this stage, {redo_later}"
        missing = f" Not found in the run: {'; '.join(entry.missing_or_uncertain)}." if entry.missing_or_uncertain else ""
        return f"Not finished yet. The request requires its stages in order. {detail}{missing}"


__all__ = [
    "JevRequiredSequence",
    "JevRequiredSequenceHandoff",
    "JevRequiredSequenceReview",
    "JevRequiredSequenceState",
    "JevStage",
    "JevStageHandoff",
    "JevStageVerdict",
    "JevWorkItem",
]
