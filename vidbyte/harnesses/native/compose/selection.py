"""FILE: vidbyte/harnesses/native/compose/selection.py

PURPOSE: The selector stage of run_ensemble: EnsembleSelector.select narrows the successful proposals in rounds while more than one may survive, then has the selector name the one proposal the implementer builds, every turn on one selector thread; EnsembleSelector.check makes sure before any I/O that every turn the selector can be sent fits its step.
ROLE IN CODEBASE: Called only by ThreadEnsembles in vidbyte/harnesses/native/compose/ensemble.py: check among its up-front checks, and select between the proposers and the backstop. It builds on the plumbing modules: steps.py for the anchors and the relocation, texts.py for the prompt files and the fit, answers.py for the round and selection answers, and workspace.py for the selector's worktree.
ARCHITECTURE NOTE: The CLI ensemble's selection shape (services/ensemble/service.py:193-217) on one native thread (spec INV-23, INV-9). The candidates are the successful proposals, numbered by their 1-based proposer position. While target = max(ceil(alive / ENSEMBLE_NARROWING_FACTOR), 1) is above 1, the selector answers an EnsembleRound keeping at most target of the numbers offered, and the numbers it kept, in proposer order, are offered next; then it always answers an EnsembleSelection naming one offered number. Each answer goes through JsonAnswers.ask with a decoder from AnswerDecoders bound to the numbers offered, so a bad answer is repaired on the same thread. The first turn carries selector_system, or fork_turn for an unanchored Grok fork, which branches the planner's thread; every later turn continues the selector's own thread. A Grok selector runs in place; an opencode or Muse selector runs every turn in one worktree filled from the snapshot taken before the planner. The module holds no literals (base spec INV-15).
FUNCTION INVENTORY: EnsembleSelector.select is the narrated main function of the selector stage; check is the up-front fit check of every selector turn; _blocks renders the candidates; _message builds one selector turn wrapped with its schema.
COMMON MODIFICATION PATTERNS: How fast the rounds narrow is ENSEMBLE_NARROWING_FACTOR, not a branch here. A new fact for the selector is one field in selector_round_turn.md or selector_final_turn.md and COMPOSE_PROMPT_FIELDS, filled in select and in check, spliced when it holds model output.
WHAT NOT TO DO IN THIS FILE: 1. Do not offer a failed proposal or renumber the others; a number is its proposer's position. 2. Do not start a new thread for a later turn; every round and the selection continue the selector's thread, so it keeps what it already weighed. 3. Do not run an opencode or Muse selector in place, or change a Grok selector's permission mode (D-21). 4. Do not import ensemble.py; it imports this module.
KNOWN EDGE CASES: With one to five successful proposals the target is 1 from the start, so there is no round and the first turn is the final selection (EC-70). A round that keeps fewer numbers than its target offers fewer next. Role names and proposals too long for the selector's prompt are cut to one fair share each (EC-23). The up-front check measures every turn as a first turn holding one block per proposer, with the round number and the survivors counted as the number of proposers, which no real turn exceeds. A worktree that cannot be removed after the last turn raises WORKTREE_FAILED with the rounds and the selection so far in its result (EC-16).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_ensemble.py, tests/features/harness_compose/test_harness_compose_keys.py, tests/features/harness_compose/test_harness_compose_validation.py
"""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from vidbyte.harnesses.native.compose.answers import AnswerDecoders, JsonAnswers
from vidbyte.harnesses.native.compose.git import ComposeGit
from vidbyte.harnesses.native.compose.steps import StepRoles, ThreadBinder
from vidbyte.harnesses.native.compose.texts import ComposeTexts, PromptFitter
from vidbyte.harnesses.native.compose.workspace import DisposableWorktree
from vidbyte.lib.constants import native_compose
from vidbyte.lib.dataclasses.native_compose import JsonAnswer, PromptSegment, ThreadStep
from vidbyte.lib.dataclasses.native_ensemble import (
    EnsembleResult,
    EnsembleRound,
    EnsembleSelection,
)
from vidbyte.lib.enums.native_compose import ComposeField, ComposePrompt
from vidbyte.lib.enums.native_threads import NativeThreadVerb
from vidbyte.lib.errors import ThreadComposeError


class EnsembleSelector:
    """The selector stage of an ensemble: narrowing rounds, then the selection of one proposal, every turn on one selector thread."""

    @staticmethod
    async def select(git: ComposeGit, tree: str, selector: ThreadStep, record: EnsembleResult, task: str, keys: Sequence[str]) -> EnsembleResult:
        """record with the selector's rounds and selection added: a round while more than one proposal may survive, then the selection of one offered number, every turn on the selector's own thread (spec INV-23)."""
        # The candidates are the successful proposals, numbered by their
        # proposer's position and shown under their role's name; a
        # failed proposal's number is skipped, never given to another.
        plan, planner_thread = record.plan.value, record.plan.thread_id
        if plan is None or planner_thread is None:
            return record
        names = {number: role.name for number, role in enumerate(plan.roles, start=1)}
        texts = {number: outcome.text for number, outcome in enumerate(record.proposals, start=1) if outcome.ok}
        offered = list(texts)
        fork = StepRoles.unanchored(selector)
        selection_schema = (await ComposeTexts.load(ComposePrompt.SELECTION_SCHEMA)).format_map({})

        # A Grok selector runs in place, in its own read-only mode; an
        # opencode or Muse selector runs every turn in one worktree
        # filled from the snapshot taken before the planner. An
        # unanchored fork's first turn branches the planner's thread.
        place: contextlib.AbstractAsyncContextManager[Path | None] = DisposableWorktree.from_tree(git, tree) if StepRoles.needs_worktree(selector) else contextlib.nullcontext()
        rounds: list[JsonAnswer[EnsembleRound]] = []
        selection: JsonAnswer[EnsembleSelection] | None = None
        try:
            async with place as folder:
                step = selector if folder is None else ThreadBinder.relocate(selector, folder)
                step = ThreadBinder.anchor(step, planner_thread, NativeThreadVerb.FORK) if fork else step

                # @intent each-round-keeps-at-most-one-proposal-in-five
                # While more than one proposal may survive, the selector
                # keeps at most target of the numbers offered, one in
                # five rounded up, and the numbers it kept, in proposer
                # order, are offered next on the same thread. A round
                # with no usable answer after its repairs ends the
                # stage.
                while (target := max(math.ceil(len(offered) / native_compose.ENSEMBLE_NARROWING_FACTOR), 1)) > 1:
                    schema = (await ComposeTexts.load(ComposePrompt.ROUND_SCHEMA)).format_map({ComposeField.TARGET: target})
                    values: dict[ComposeField, str | tuple[PromptSegment, ...]] = {ComposeField.TASK: task, ComposeField.ROUND: str(len(rounds) + 1), ComposeField.SURVIVING: str(len(offered)), ComposeField.TARGET: str(target), ComposeField.CANDIDATES: await EnsembleSelector._blocks(offered, names, texts)}
                    message = await EnsembleSelector._message(ComposePrompt.SELECTOR_ROUND_TURN, values, schema, first=not rounds, fork=fork)
                    answer = await JsonAnswers.ask(step, message, schema, functools.partial(AnswerDecoders.round, offered=tuple(offered), target=target), keys)
                    rounds.append(answer)
                    narrowing, thread = answer.value, answer.thread_id
                    if narrowing is None or thread is None:
                        return dataclasses.replace(record, rounds=tuple(rounds))
                    offered = [number for number in offered if number in narrowing.kept]
                    step = ThreadBinder.anchor(step, thread)

                # Then the selector names one offered number, the
                # proposal the implementer will build, still on the same
                # thread.
                values = {ComposeField.TASK: task, ComposeField.ROUND: str(len(rounds) + 1), ComposeField.SURVIVING: str(len(offered)), ComposeField.CANDIDATES: await EnsembleSelector._blocks(offered, names, texts)}
                message = await EnsembleSelector._message(ComposePrompt.SELECTOR_FINAL_TURN, values, selection_schema, first=not rounds, fork=fork)
                selection = await JsonAnswers.ask(step, message, selection_schema, functools.partial(AnswerDecoders.selection, offered=tuple(offered)), keys)
        except ThreadComposeError as error:
            # A worktree that cannot be removed after the last turn
            # fails the run, with the rounds and the selection so far
            # in the record (spec EC-16).
            if error.result is None:
                error.result = dataclasses.replace(record, rounds=tuple(rounds), selection=selection)
            raise
        return dataclasses.replace(record, rounds=tuple(rounds), selection=selection)

    @staticmethod
    async def check(selector: ThreadStep, task: str, count: int) -> None:
        """Refuse, naming prompt, a task that leaves a turn of the selector over count proposals no room in the selector's step (spec INV-18)."""
        # Every turn the selector can be sent, at its longest: a first
        # turn holding one block per proposer, each role name and
        # proposal as its longest truncation note, with the round number
        # and the survivors counted as count, which no real turn
        # exceeds. A round turn is sent only when its target is above 1.
        target = max(math.ceil(count / native_compose.ENSEMBLE_NARROWING_FACTOR), 1)
        values: dict[ComposeField, str | tuple[PromptSegment, ...]] = {ComposeField.TASK: task, ComposeField.ROUND: str(count), ComposeField.SURVIVING: str(count), ComposeField.TARGET: str(target), ComposeField.CANDIDATES: await EnsembleSelector._blocks(range(1, count + 1), {}, {})}
        turns = [(ComposePrompt.SELECTOR_FINAL_TURN, (await ComposeTexts.load(ComposePrompt.SELECTION_SCHEMA)).format_map({}))]
        if target > 1:
            turns.append((ComposePrompt.SELECTOR_ROUND_TURN, (await ComposeTexts.load(ComposePrompt.ROUND_SCHEMA)).format_map({ComposeField.TARGET: target})))
        receiver = StepRoles.member(native_compose.COMPOSE_ROSTER_ARGUMENT, native_compose.COMPOSE_SELECTOR_MEMBER)
        for turn, schema in turns:
            message = await EnsembleSelector._message(turn, values, schema, first=True, fork=StepRoles.unanchored(selector))
            await PromptFitter.check(message, selector, argument=native_compose.COMPOSE_PROMPT_PARAMETER, receiver=receiver)

    @staticmethod
    async def _blocks(numbers: Iterable[int], names: Mapping[int, str], texts: Mapping[int, str]) -> tuple[PromptSegment, ...]:
        # One proposal_block per number, with the role's name and the
        # proposal spliced, so keys are scrubbed and a long proposal is
        # cut to its share; a name or text not given is empty, the form
        # the up-front check measures.
        template = await ComposeTexts.load(ComposePrompt.PROPOSAL_BLOCK)
        return ComposeTexts.join([ComposeTexts.render(template, {ComposeField.NUMBER: str(number), ComposeField.ROLE_NAME: ComposeTexts.spliced(names.get(number, "")), ComposeField.TEXT: ComposeTexts.spliced(texts.get(number, ""))}) for number in numbers])

    @staticmethod
    async def _message(turn: ComposePrompt, values: Mapping[ComposeField, str | tuple[PromptSegment, ...]], schema: str, *, first: bool, fork: bool) -> tuple[PromptSegment, ...]:
        # One selector turn wrapped with its schema; the first turn
        # carries selector_system before it, or fork_turn around both
        # for an unanchored fork.
        message = ComposeTexts.render(await ComposeTexts.load(turn), values)
        if first:
            system = await ComposeTexts.load(ComposePrompt.SELECTOR_SYSTEM)
            message = await ComposeTexts.opening(ComposeTexts.fixed(system), message, fork=fork)
        return await JsonAnswers.wrapped(message, schema)


__all__ = ["EnsembleSelector"]
