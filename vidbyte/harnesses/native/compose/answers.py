"""FILE: vidbyte/harnesses/native/compose/answers.py

PURPOSE: Gets structured answers from steps: JsonAnswers.parse_json_answer asks a step for one JSON object described by a schema, turns it into a value through the caller's parse, and repairs a bad answer on the same thread; AnswerDecoders reads one answer turn and holds the four decoders the composites pass as parse (verdict, plan, round, selection).
ROLE IN CODEBASE: parse_json_answer is bound as a public name in vidbyte/harnesses/native/compose/__init__.py. verify.py (verdicts), ensemble.py (the plan) and selection.py (rounds and the selection) call JsonAnswers.wrapped and JsonAnswers.ask with a decoder from AnswerDecoders, bound with functools.partial where it needs the round's numbers.
ARCHITECTURE NOTE: The answer flow follows spec INV-19 and D-8: the first turn is json_answer wrapping the question and the schema text; JsonText.decode reads the answer strictly and parse turns the read-only mapping into a value. A cut answer (text_truncated) is never decoded. A problem is the cut, a decode ValueError, or a ValueError, TypeError, KeyError or ConfigurationError from parse; each gets a json_repair turn on the same thread through ThreadBinder.anchor, at most COMPOSE_JSON_REPAIR_TURNS of them, and a NativeThreadError on any turn ends the answer as its last turn. Every turn goes through ComposeCalls.call, so a Grok turn takes its workspace slot for that turn only, and through PromptFitter.fit, so a spliced problem is scrubbed of keys and cut only when the prompt would not fit. The decoders read member names from dataclasses.fields and refuse extra and missing members; the records refuse wrong types.
FUNCTION INVENTORY: JsonAnswers.parse_json_answer checks its arguments and the prompt fit, then asks; ask is the narrated main function of the turns; wrapped builds a first turn. AnswerDecoders.read turns one answer into a value or a problem; verdict, plan, round and selection build the composites' records; _checked is their member check.
COMMON MODIFICATION PATTERNS: A new structured answer in a composite is a record in vidbyte/lib/dataclasses/, a schema prompt file, and one decoder here that calls _checked and the record. A new code check on an answer raises ValueError with a constant from vidbyte/lib/constants/native_compose.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not decode an answer whose text_truncated is True. 2. Do not catch an exception from parse beyond the four problem types; anything else is the caller's defect and propagates. 3. Do not start a new thread for a repair; it continues the answer's own thread. 4. Do not import a composite module; this is plumbing.
KNOWN EDGE CASES: An exception whose text is blank gives its type name as the problem, so the record always names something. The record keeps the raw problem cut at COMPOSE_PROBLEM_MAX_CHARS, while the repair prompt gets the whole problem scrubbed of keys first, so a cap never leaves part of a key in a prompt. A parse that returns None leaves the answer without a value.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_answers.py, tests/features/harness_compose/test_harness_compose_verify.py, tests/features/harness_compose/test_harness_compose_ensemble.py
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from vidbyte.harnesses.native.compose.calls import ComposeCalls
from vidbyte.harnesses.native.compose.steps import StepRoles, ThreadBinder
from vidbyte.harnesses.native.compose.texts import ComposeTexts, PromptFitter
from vidbyte.lib.constants import native_compose, native_threads
from vidbyte.lib.dataclasses.native_compose import (
    AnswerT,
    JsonAnswer,
    PromptSegment,
    StepOutcome,
    ThreadStep,
    ThreadVerdict,
)
from vidbyte.lib.dataclasses.native_ensemble import (
    EnsemblePlan,
    EnsembleRole,
    EnsembleRound,
    EnsembleSelection,
)
from vidbyte.lib.dataclasses.native_threads import NativeThreadResult
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.enums.native_compose import ComposeField, ComposePrompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.util.json_text import JsonText


class JsonAnswers:
    """Structured answers from one step: a schema instruction, strict decoding, the caller's parse, and repair turns on the same thread."""

    @staticmethod
    async def parse_json_answer(step: ThreadStep, prompt: str, *, schema: str, parse: Callable[[Mapping[str, object]], AnswerT]) -> JsonAnswer[AnswerT]:
        """Ask step for one JSON object described by schema and turn it into a value with parse, repairing a bad answer on the same thread (spec INV-19)."""
        # Check every argument before anything runs: a step compose can
        # call that is not a fork with no thread, a parse it can call,
        # and a prompt and a schema a step can take.
        checked = ThreadBinder.require_step(step, native_compose.COMPOSE_STEP_ARGUMENT)
        StepRoles.anchored(checked, native_compose.COMPOSE_STEP_ARGUMENT)
        if not callable(parse):
            raise ConfigurationError(native_compose.COMPOSE_NOT_CALLABLE.format(argument=native_compose.COMPOSE_PARSE_ARGUMENT, type_name=type(parse).__name__), details={native_threads.NATIVE_FIELD_DETAIL_KEY: native_compose.COMPOSE_PARSE_ARGUMENT})
        RecordFieldValidator.require_text(prompt, native_compose.COMPOSE_PROMPT_PARAMETER, max_chars=native_threads.NATIVE_PROMPT_MAX_CHARS, pattern=native_threads.NATIVE_PROMPT_PATTERN, quote=False)
        RecordFieldValidator.require_text(schema, native_compose.COMPOSE_SCHEMA_ARGUMENT, max_chars=native_threads.NATIVE_PROMPT_MAX_CHARS, pattern=native_threads.NATIVE_PROMPT_PATTERN, quote=False)

        # Make sure every turn fits the step before the first one goes:
        # the longest repair turn and the question with no prompt blame
        # the schema, and the whole first turn blames the prompt.
        repair = await ComposeTexts.load(ComposePrompt.JSON_REPAIR)
        await PromptFitter.check(ComposeTexts.render(repair, {ComposeField.PROBLEM: ComposeTexts.spliced(""), ComposeField.SCHEMA: schema}), checked, argument=native_compose.COMPOSE_SCHEMA_ARGUMENT, receiver=native_compose.COMPOSE_STEP_ARGUMENT)
        await PromptFitter.check(await JsonAnswers.wrapped((), schema), checked, argument=native_compose.COMPOSE_SCHEMA_ARGUMENT, receiver=native_compose.COMPOSE_STEP_ARGUMENT)
        message = await JsonAnswers.wrapped(ComposeTexts.fixed(prompt), schema)
        await PromptFitter.check(message, checked, argument=native_compose.COMPOSE_PROMPT_PARAMETER, receiver=native_compose.COMPOSE_STEP_ARGUMENT)

        # Ask, and repair on the step's own thread; the step's key is
        # the one key its spliced problems could hold.
        return await JsonAnswers.ask(checked, message, schema, parse, (checked.api_key,))

    @staticmethod
    async def ask(step: ThreadStep, message: Sequence[PromptSegment], schema: str, parse: Callable[[Mapping[str, object]], AnswerT], keys: Sequence[str]) -> JsonAnswer[AnswerT]:
        """Send message, a question already wrapped with schema and checked to fit, and repair the answer on its own thread until parse accepts it."""
        # Load the repair prompt first, so a broken prompt file fails
        # before any step runs.
        repair = await ComposeTexts.load(ComposePrompt.JSON_REPAIR)
        turns: list[StepOutcome] = []
        problem: str | None = None
        current, frame = step, tuple(message)
        while len(turns) <= native_compose.COMPOSE_JSON_REPAIR_TURNS:
            # Send this turn, the first or one of the repairs; only
            # spliced values give way when the prompt is too long, and
            # keys never reach the step.
            outcome = await ComposeCalls.call(current, await PromptFitter.fit(frame, current, keys))
            turns.append(outcome)

            # A step's own failure ends the answer as its last turn.
            if outcome.result is None:
                break

            # Read the answer; one that parse accepts is the value.
            value, problem = AnswerDecoders.read(outcome.result, parse)
            if problem is None:
                return JsonAnswer(value=value, turns=tuple(turns))

            # Otherwise continue the same thread, naming the problem
            # and repeating the schema.
            current = ThreadBinder.anchor(step, outcome.result.thread_id)
            frame = ComposeTexts.render(repair, {ComposeField.PROBLEM: ComposeTexts.spliced(problem), ComposeField.SCHEMA: schema})

        # No turn gave a value: keep every turn and the last problem.
        last = problem[: native_compose.COMPOSE_PROBLEM_MAX_CHARS] if problem is not None else None
        return JsonAnswer(value=None, turns=tuple(turns), problem=last)

    @staticmethod
    async def wrapped(question: Sequence[PromptSegment], schema: str) -> tuple[PromptSegment, ...]:
        """question wrapped in json_answer with schema, the first turn of every structured answer."""
        template = await ComposeTexts.load(ComposePrompt.JSON_ANSWER)
        return ComposeTexts.render(template, {ComposeField.PROMPT: tuple(question), ComposeField.SCHEMA: schema})


class AnswerDecoders:
    """Reads one answer turn, and turns a decoded answer into the record a composite asked for."""

    @staticmethod
    def read(result: NativeThreadResult, parse: Callable[[Mapping[str, object]], AnswerT]) -> tuple[AnswerT | None, str | None]:
        """The value parse built from result's answer, or the problem that asks for a repair; a cut answer is never decoded (spec INV-19, EC-29)."""
        # @intent cut-answers-are-never-read-and-defects-propagate
        # A cut answer may still decode to a valid but wrong object, so
        # it is never decoded; only the four problem types are the
        # model's to fix, and any other exception is the caller's.
        if result.text_truncated:
            return None, native_compose.COMPOSE_TRUNCATED_PROBLEM
        try:
            return parse(JsonText.decode(result.text)), None
        except (ValueError, TypeError, KeyError, ConfigurationError) as error:
            text = str(error)
            return None, text if text.strip() else type(error).__name__

    @staticmethod
    def verdict(mapping: Mapping[str, object]) -> ThreadVerdict:
        """A verifier's answer as a ThreadVerdict."""
        return ThreadVerdict(**AnswerDecoders._checked(mapping, dataclasses.fields(ThreadVerdict)))

    @staticmethod
    def plan(mapping: Mapping[str, object], roles: int) -> EnsemblePlan:
        """The planner's answer as an EnsemblePlan with exactly roles roles, one per proposer (spec EC-49)."""
        # The plan's roles member shares its name with the {roles} field
        # of plan_schema. A list of objects becomes checked roles; any
        # other value is left for EnsemblePlan to refuse, naming roles.
        values = AnswerDecoders._checked(mapping, dataclasses.fields(EnsemblePlan))
        items = values[ComposeField.ROLES]
        if isinstance(items, list) and all(isinstance(item, Mapping) for item in items):
            if len(items) != roles:
                raise ValueError(native_compose.COMPOSE_ROLE_COUNT_PROBLEM.format(expected=roles, actual=len(items)))
            values[ComposeField.ROLES] = tuple(EnsembleRole(**AnswerDecoders._checked(item, dataclasses.fields(EnsembleRole))) for item in items)
        return EnsemblePlan(**values)

    @staticmethod
    def round(mapping: Mapping[str, object], offered: Sequence[int], target: int) -> EnsembleRound:
        """A narrowing round's answer as an EnsembleRound keeping at most target of the offered numbers (spec EC-50)."""
        narrowing = EnsembleRound(**AnswerDecoders._checked(mapping, dataclasses.fields(EnsembleRound)))
        if len(narrowing.kept) > target or not set(narrowing.kept) <= set(offered):
            listing = native_threads.NATIVE_LISTING_SEPARATOR
            raise ValueError(native_compose.COMPOSE_KEPT_PROBLEM.format(target=target, offered=listing.join(map(str, offered)), kept=listing.join(map(str, narrowing.kept))))
        return narrowing

    @staticmethod
    def selection(mapping: Mapping[str, object], offered: Sequence[int]) -> EnsembleSelection:
        """The final selection's answer as an EnsembleSelection naming one offered number (spec EC-50)."""
        chosen = EnsembleSelection(**AnswerDecoders._checked(mapping, dataclasses.fields(EnsembleSelection)))
        if chosen.proposal not in offered:
            raise ValueError(native_compose.COMPOSE_PROPOSAL_PROBLEM.format(offered=native_threads.NATIVE_LISTING_SEPARATOR.join(map(str, offered)), proposal=chosen.proposal))
        return chosen

    @staticmethod
    def _checked(mapping: Mapping[str, object], fields: Iterable[dataclasses.Field[Any]]) -> dict[str, Any]:
        # The answer's members as keyword arguments for the record, once
        # they are exactly the record's field names; the record itself
        # then refuses a wrongly typed value, naming the field.
        names = [field.name for field in fields]
        extra = [name for name in mapping if name not in names]
        if extra:
            raise ValueError(native_compose.COMPOSE_EXTRA_MEMBERS_PROBLEM.format(members=native_threads.NATIVE_LISTING_SEPARATOR.join(extra)))
        missing = [name for name in names if name not in mapping]
        if missing:
            raise ValueError(native_compose.COMPOSE_MISSING_MEMBERS_PROBLEM.format(members=native_threads.NATIVE_LISTING_SEPARATOR.join(missing)))
        values: dict[str, Any] = dict(mapping)
        return values


__all__ = ["AnswerDecoders", "JsonAnswers"]
