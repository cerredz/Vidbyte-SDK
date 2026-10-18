"""FILE: vidbyte/harnesses/native/compose/ensemble.py

PURPOSE: The ensemble composite: ThreadEnsembles.run_ensemble has a planner write one role per proposer, runs the proposers at the same time, each writing a proposal for its own role, has the selector narrow the proposals to one through EnsembleSelector, checks that none of these readers changed the workspace, and then has the implementer build the chosen proposal in place.
ROLE IN CODEBASE: run_ensemble is bound as a public name in vidbyte/harnesses/native/compose/__init__.py. It builds on the plumbing modules: steps.py for the role rules, the anchors and the relocation, git.py for the repository checks and the snapshot, workspace.py for the reader worktrees and the backstop, texts.py for the prompt files and the fit, answers.py for the plan, and calls.py for the calls and the fan-out; selection.py runs the selector stage.
ARCHITECTURE NOTE: The CLI ensemble's plan, propose, select and implement shape on the nine thread functions (spec INV-23, D-3, D-13, D-20), any role on any harness within the reader rules. The planner, the proposers and the selector form one read-only phase: one snapshot before the planner is the tree every opencode or Muse reader's worktree is filled from and what the backstop compares the working tree with once the phase ends, early or not (INV-9, INV-11); a Grok reader runs in place in its own plan or default permission mode. The plan is a JSON answer repaired on the planner's thread, and proposals are free text (D-13). An unanchored Grok fork in a role other than the planner is anchored at the planner's thread and opens with fork_turn. The implementer, the one writer, runs once, in place, after the backstop passed, and no snapshot follows it (INV-12, NG-13). The module holds no literals (base spec INV-15).
FUNCTION INVENTORY: ThreadEnsembles.run_ensemble is the narrated main function; _roles checks the roster; _question builds the planner's question; _frame builds a proposer's or the implementer's first turn; _fit checks the planner's, the proposers' and the implementer's prompts; _plan asks the planner; _propose runs one proposer; _role_texts and _brief collect what a proposer's and the implementer's turns splice.
COMMON MODIFICATION PATTERNS: A new fact for proposers is one field in role_system.md or role_turn.md and COMPOSE_PROMPT_FIELDS, added to _role_texts; _frame splices every field but the task and the approach range. A change to the narrowing rounds or the selection belongs in selection.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not start the implementer before the selector has finished and the backstop has passed (INV-12). 2. Do not run an opencode or Muse reader in place, or change any step's permission mode; refuse it instead (D-21). 3. Do not show a proposer another role's identity or another proposal. 4. Do not skip the backstop after a failed plan, no successful proposal or a failed selection; it is skipped only on a cancellation or a defect (INV-11).
KNOWN EDGE CASES: No successful proposal stops before the selector, yet the backstop runs (EC-51). One proposer means no narrowing round (EC-70). A planner and a selector bound to the same run step work on two threads, because the selector's first turn starts its own. A repository with no commit allows Grok readers and refuses opencode and Muse readers with WORKTREE_FAILED before any step (EC-5). A worktree that cannot be removed after the planner or the selector answered raises WORKTREE_FAILED whose result holds that answer; after one of several proposers running at once, the result holds the plan only, because the first failure stops the other proposers (EC-16).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_ensemble.py, tests/features/harness_compose/test_harness_compose_keys.py, tests/features/harness_compose/test_harness_compose_git.py, tests/features/harness_compose/test_harness_compose_validation.py, tests/features/harness_compose/test_harness_compose_acceptance.py
"""

from __future__ import annotations

import dataclasses
import functools
from collections.abc import Mapping, Sequence
from pathlib import Path

from vidbyte.harnesses.native.compose.answers import AnswerDecoders, JsonAnswers
from vidbyte.harnesses.native.compose.calls import ComposeCalls
from vidbyte.harnesses.native.compose.git import ComposeGit
from vidbyte.harnesses.native.compose.selection import EnsembleSelector
from vidbyte.harnesses.native.compose.steps import StepRoles, ThreadBinder
from vidbyte.harnesses.native.compose.texts import ComposeTexts, PromptFitter
from vidbyte.harnesses.native.compose.workspace import DisposableWorktree
from vidbyte.lib.constants import native_compose, native_threads
from vidbyte.lib.dataclasses.native_compose import JsonAnswer, StepOutcome, ThreadStep
from vidbyte.lib.dataclasses.native_ensemble import (
    EnsemblePlan,
    EnsembleResult,
    EnsembleRole,
    EnsembleRoster,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_compose import ComposeField, ComposePrompt
from vidbyte.lib.enums.native_threads import NativeThreadVerb
from vidbyte.lib.errors import ThreadComposeError


class ThreadEnsembles:
    """Runs an ensemble: a planner's roles, proposals written at the same time, a selection among them and one implementation, every role the caller's own step."""

    @staticmethod
    async def run_ensemble(prompt: str, roster: EnsembleRoster) -> EnsembleResult:
        """Plan, propose, select and implement with the caller's step in every role; raise READER_CHANGED_WORKSPACE, before the implementer starts, when the planner, a proposer or the selector changed the workspace (spec INV-23, INV-11, INV-12)."""
        # Check every input before anything runs: the four roles, with
        # the reader and fork rules and one workspace, and the task.
        planner, proposers, selector, implementer = ThreadEnsembles._roles(roster)
        RecordFieldValidator.require_text(prompt, native_compose.COMPOSE_PROMPT_PARAMETER, max_chars=native_threads.NATIVE_PROMPT_MAX_CHARS, pattern=native_threads.NATIVE_PROMPT_PATTERN)

        # Make sure every first turn fits its step before anything runs.
        # The planner's question holds no model output, so it is checked
        # as it will be sent; every other turn is checked at its longest,
        # each spliced value as its longest truncation note, so only the
        # task can make a turn too long.
        schema = (await ComposeTexts.load(ComposePrompt.PLAN_SCHEMA)).format_map({ComposeField.ROLES: len(proposers)})
        question = await ThreadEnsembles._question(prompt, len(proposers), schema)
        longest_roles = [await ThreadEnsembles._frame(step, ComposePrompt.ROLE_SYSTEM, ComposePrompt.ROLE_TURN, prompt, None) for step in proposers]
        longest_brief = await ThreadEnsembles._frame(implementer, ComposePrompt.IMPLEMENTER_SYSTEM, ComposePrompt.IMPLEMENTER_TURN, prompt, None)
        await ThreadEnsembles._fit(planner, question, proposers, longest_roles, implementer, longest_brief)
        await EnsembleSelector.check(selector, prompt, len(proposers))

        # Find git and the repository before any step runs. A worktree
        # starts at HEAD, so an opencode or Muse reader needs a commit.
        keys = tuple(step.api_key for step in (planner, *proposers, selector, implementer))
        git = ComposeGit.locate(Path(planner.workspace), keys)
        await git.toplevel()
        await git.has_commit(required=any(StepRoles.needs_worktree(step) for step in (planner, *proposers, selector)))

        # @intent readers-plan-propose-and-select-before-the-one-writer
        # The planner, the proposers and the selector only read, so one
        # snapshot before the planner is the tree every reader worktree
        # is filled from and what the whole read-only phase must leave;
        # the implementer, the one writer, runs only after that check.
        tree = await git.snapshot()
        record: EnsembleResult | None = None
        try:
            # Plan: the planner answers one role per proposer, repaired
            # on its own thread when the answer does not parse.
            plan = await ThreadEnsembles._plan(git, tree, planner, question, schema, len(proposers), keys)
            record = EnsembleResult(plan=plan)

            # Propose: with a plan, every proposer writes a proposal for
            # its own role at the same time, and a proposer's failure
            # stops no other.
            if plan.value is not None and plan.thread_id is not None:
                frames = [await ThreadEnsembles._frame(step, ComposePrompt.ROLE_SYSTEM, ComposePrompt.ROLE_TURN, prompt, ThreadEnsembles._role_texts(role, plan.value)) for step, role in zip(proposers, plan.value.roles, strict=True)]
                proposals = await ComposeCalls.fan_out([ThreadEnsembles._propose(git, tree, step, frame, plan.thread_id, keys) for step, frame in zip(proposers, frames, strict=True)])
                record = EnsembleResult(plan=plan, proposals=proposals)

            # Select: with at least one proposal, the selector narrows
            # them to the one the implementer will build.
            if any(outcome.ok for outcome in record.proposals):
                record = await EnsembleSelector.select(git, tree, selector, record, prompt, keys)

            # With every reader done and every worktree gone, the working
            # tree must still match the snapshot, also when the phase
            # stopped early.
            await DisposableWorktree.backstop(git, tree, record)
        except ThreadComposeError as error:
            # A compose failure carries the record so far, unless it
            # already carries a fuller one.
            if error.result is None:
                error.result = record
            raise

        # Implement: only after a selection, the implementer builds the
        # chosen proposal in place, told its role, its text and the
        # selector's brief; no snapshot is taken after it.
        texts = ThreadEnsembles._brief(record)
        if texts is None or record.plan.thread_id is None:
            return record
        brief = await ThreadEnsembles._frame(implementer, ComposePrompt.IMPLEMENTER_SYSTEM, ComposePrompt.IMPLEMENTER_TURN, prompt, texts)
        writer = ThreadBinder.anchor(implementer, record.plan.thread_id, NativeThreadVerb.FORK) if StepRoles.unanchored(implementer) else implementer
        implementation = await ComposeCalls.call(writer, await PromptFitter.fit(brief, writer, keys))
        return dataclasses.replace(record, implementation=implementation)

    @staticmethod
    def _roles(roster: object) -> tuple[ThreadStep, tuple[ThreadStep, ...], ThreadStep, ThreadStep]:
        # The planner reads, and starts or continues a thread of its own.
        # Every other role works in the planner's workspace, a proposer
        # and the selector may only read, and an unanchored fork may hold
        # such a role only beside a Grok planner on the same workspace.
        checked: EnsembleRoster = RecordFieldConverter.require_instance(roster, native_compose.COMPOSE_ROSTER_ARGUMENT, EnsembleRoster)
        name = native_compose.COMPOSE_ROSTER_ARGUMENT
        planner_argument = StepRoles.member(name, native_compose.COMPOSE_PLANNER_MEMBER)
        planner = ThreadBinder.require_step(checked.planner, planner_argument)
        StepRoles.anchored(planner, planner_argument)
        StepRoles.reader(planner, planner_argument)
        proposers = StepRoles.member(name, native_compose.COMPOSE_PROPOSERS_MEMBER)
        roles = [(item, StepRoles.item(proposers, index), True) for index, item in enumerate(checked.proposers)]
        roles.append((checked.selector, StepRoles.member(name, native_compose.COMPOSE_SELECTOR_MEMBER), True))
        roles.append((checked.implementer, StepRoles.member(name, native_compose.COMPOSE_IMPLEMENTER_MEMBER), False))
        steps: list[ThreadStep] = []
        for value, argument, reads in roles:
            step = ThreadBinder.require_step(value, argument)
            StepRoles.fork_role(step, argument, planner)
            if reads:
                StepRoles.reader(step, argument)
            StepRoles.same_workspace(step, argument, planner, planner_argument)
            steps.append(step)
        *readers, selector, implementer = steps
        return planner, tuple(readers), selector, implementer

    @staticmethod
    async def _question(task: str, count: int, schema: str) -> tuple[tuple[str, bool], ...]:
        # The planner's first turn: its system text and the task, both
        # asking for exactly count roles, wrapped with the plan schema.
        values = {ComposeField.TASK: task, ComposeField.ROLES: str(count)}
        system = ComposeTexts.render(await ComposeTexts.load(ComposePrompt.PLANNER_SYSTEM), values)
        turn = ComposeTexts.render(await ComposeTexts.load(ComposePrompt.PLANNER_TURN), values)
        return await JsonAnswers.wrapped(ComposeTexts.join((system, turn)), schema)

    @staticmethod
    async def _frame(step: ThreadStep, system: ComposePrompt, turn: ComposePrompt, task: str, texts: Mapping[ComposeField, str] | None) -> tuple[tuple[str, bool], ...]:
        # A proposer's or the implementer's first turn: its system text,
        # then its turn. The task and the approach range are fixed text;
        # every other field is model output, spliced, and empty when
        # texts is None, the longest form the up-front check measures.
        # An unanchored fork opens on the planner's thread with fork_turn.
        fixed = {ComposeField.TASK: task, ComposeField.MINIMUM: str(native_compose.ENSEMBLE_MIN_APPROACHES), ComposeField.MAXIMUM: str(native_compose.ENSEMBLE_MAX_APPROACHES)}
        fields = native_compose.COMPOSE_PROMPT_FIELDS[system].union(native_compose.COMPOSE_PROMPT_FIELDS[turn]).difference(fixed)
        values: dict[ComposeField, str | tuple[tuple[str, bool], ...]] = {field: ComposeTexts.spliced("" if texts is None else texts[field]) for field in fields}
        values.update(fixed)
        opening = ComposeTexts.render(await ComposeTexts.load(system), values)
        body = ComposeTexts.render(await ComposeTexts.load(turn), values)
        return await ComposeTexts.opening(opening, body, fork=StepRoles.unanchored(step))

    @staticmethod
    async def _fit(planner: ThreadStep, question: Sequence[tuple[str, bool]], proposers: Sequence[ThreadStep], frames: Sequence[Sequence[tuple[str, bool]]], implementer: ThreadStep, brief: Sequence[tuple[str, bool]]) -> None:
        # The planner's question, each proposer's first turn and the
        # implementer's, each for its own step; the task is the only
        # caller text in them, so it is the argument a refusal names.
        name = native_compose.COMPOSE_ROSTER_ARGUMENT
        argument = native_compose.COMPOSE_PROMPT_PARAMETER
        await PromptFitter.check(question, planner, argument=argument, receiver=StepRoles.member(name, native_compose.COMPOSE_PLANNER_MEMBER))
        for index, (step, frame) in enumerate(zip(proposers, frames, strict=True)):
            await PromptFitter.check(frame, step, argument=argument, receiver=StepRoles.item(StepRoles.member(name, native_compose.COMPOSE_PROPOSERS_MEMBER), index))
        await PromptFitter.check(brief, implementer, argument=argument, receiver=StepRoles.member(name, native_compose.COMPOSE_IMPLEMENTER_MEMBER))

    @staticmethod
    async def _plan(git: ComposeGit, tree: str, planner: ThreadStep, question: Sequence[tuple[str, bool]], schema: str, count: int, keys: Sequence[str]) -> JsonAnswer[EnsemblePlan]:
        # A plan must hold exactly count roles, one per proposer.
        parse = functools.partial(AnswerDecoders.plan, roles=count)

        # A Grok planner plans in place, in its own read-only mode.
        if not StepRoles.needs_worktree(planner):
            return await JsonAnswers.ask(planner, question, schema, parse, keys)

        # An opencode or Muse planner answers, repairs included, in a
        # worktree of its own filled from the snapshot. A worktree that
        # cannot be removed after the planner answered fails the run
        # with the answer in the record so far (spec EC-16).
        answer: JsonAnswer[EnsemblePlan] | None = None
        try:
            async with DisposableWorktree.from_tree(git, tree) as folder:
                answer = await JsonAnswers.ask(ThreadBinder.relocate(planner, folder), question, schema, parse, keys)
                return answer
        except ThreadComposeError as error:
            if error.result is None and answer is not None:
                error.result = EnsembleResult(plan=answer)
            raise

    @staticmethod
    async def _propose(git: ComposeGit, tree: str, proposer: ThreadStep, frame: Sequence[tuple[str, bool]], planner_thread: str, keys: Sequence[str]) -> StepOutcome:
        # An unanchored fork branches the planner's thread.
        step = ThreadBinder.anchor(proposer, planner_thread, NativeThreadVerb.FORK) if StepRoles.unanchored(proposer) else proposer

        # A Grok proposer answers in place, in its own read-only mode.
        if not StepRoles.needs_worktree(step):
            return await ComposeCalls.call(step, await PromptFitter.fit(frame, step, keys))

        # An opencode or Muse proposer answers in a worktree of its own,
        # filled from the snapshot taken before the planner.
        async with DisposableWorktree.from_tree(git, tree) as folder:
            relocated = ThreadBinder.relocate(step, folder)
            return await ComposeCalls.call(relocated, await PromptFitter.fit(frame, relocated, keys))

    @staticmethod
    def _role_texts(role: EnsembleRole, plan: EnsemblePlan) -> dict[ComposeField, str]:
        # What a proposer's turns splice: its own role from the plan and
        # the planner's reading of the task.
        return {
            ComposeField.ROLE_NAME: role.name,
            ComposeField.IDENTITY: role.identity,
            ComposeField.PERSONALITY: role.personality,
            ComposeField.EXPERTISE: role.expertise,
            ComposeField.KNOWLEDGE: role.knowledge,
            ComposeField.SKILLS: role.skills,
            ComposeField.GOAL: role.goal,
            ComposeField.TASK_ANALYSIS: plan.task_analysis,
            ComposeField.ROSTER_STRATEGY: plan.roster_strategy,
            ComposeField.COVERAGE_SUMMARY: plan.coverage_summary,
        }

    @staticmethod
    def _brief(record: EnsembleResult) -> dict[ComposeField, str] | None:
        # What the implementer's turn splices: the chosen proposal's role
        # name and text, and the selection's approach, rationale and
        # guidance; None when the run stopped before a selection.
        plan = record.plan.value
        chosen = record.selection.value if record.selection is not None else None
        if plan is None or chosen is None:
            return None
        index = chosen.proposal - 1
        return {
            ComposeField.ROLE_NAME: plan.roles[index].name,
            ComposeField.PROPOSAL: record.proposals[index].text,
            ComposeField.APPROACH: chosen.approach,
            ComposeField.RATIONALE: chosen.rationale,
            ComposeField.GUIDANCE: chosen.guidance,
        }


__all__ = ["ThreadEnsembles"]
