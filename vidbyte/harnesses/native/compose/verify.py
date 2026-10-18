"""FILE: vidbyte/harnesses/native/compose/verify.py

PURPOSE: The verify composite and its three trio aliases: ThreadVerifiers.verify_with runs one writer alone, then has one to ten verifiers review the change it made at the same time, each answering a structured verdict, and fails the call when a verifier changed the workspace; ThreadVerifyTrio is one generated alias such as run_opencode_verify_with_grok_and_muse, and ThreadVerifyTrios holds the three.
ROLE IN CODEBASE: verify_with and the three run_<w>_verify_with_<x>_and_<y> aliases are bound as public names in vidbyte/harnesses/native/compose/__init__.py. It builds on the plumbing modules: steps.py for the step and reader rules, git.py for the snapshots and the diff, workspace.py for the reader worktrees and the backstop, answers.py for the verdicts and calls.py for the calls and the fan-out.
ARCHITECTURE NOTE: One writer, then readers (spec INV-9 to INV-12, D-20): the writer runs alone between two snapshots, and the second snapshot serves three uses, the end of the writer's diff, the tree each worktree verifier is filled from, and the start of the backstop. A Grok verifier reviews in place in its own plan or default permission mode; an opencode or Muse verifier reviews in a disposable worktree whose index is the before-writer snapshot, so git there shows the writer's change. The verifiers run concurrently through ComposeCalls.fan_out, so a step failure is recorded while any other exception stops them all. The aliases are generated as in chain.py (INV-24, D-18). The module holds no literals (base spec INV-15).
FUNCTION INVENTORY: ThreadVerifiers.verify_with is the narrated main function; _steps checks the writer and the verifiers; _question builds a verifier's first turn; _fit checks every prompt against its step; _review runs one verifier in place or in its worktree and keeps its answer as it arrives; _kept builds the record a compose failure carries. ThreadVerifyTrio.__init__ builds an alias's signature and __call__ runs the alias; ThreadVerifyTrios holds the three aliases.
COMMON MODIFICATION PATTERNS: A new fact for verifiers is one field in verify_turn.md and COMPOSE_PROMPT_FIELDS, filled in _question, spliced when it holds model output or workspace content. A new verdict member is a ThreadVerdict field, a line in verdict_schema.md and nothing here.
WHAT NOT TO DO IN THIS FILE: 1. Do not start a verifier before the writer's after-snapshot. 2. Do not run an opencode or Muse verifier in place, or change a Grok verifier's permission mode; refuse it instead (D-21). 3. Do not send verifiers the writer's answer; they review its change. 4. Do not skip the backstop after a verifier failed; skip it only on a cancellation or a defect.
KNOWN EDGE CASES: A failed writer gets no verifier, but its diff is taken (EC-52). A repository with no commit allows Grok verifiers and refuses worktree verifiers with WORKTREE_FAILED before any step (EC-5). A writer that leaves an untracked repository with no commit fails the after-snapshot's add, carrying the writer's outcome (EC-73). Two verifiers on one workspace that are both Grok take turns (INV-13). A worktree that cannot be removed after every verifier answered raises WORKTREE_FAILED whose result holds the writer and every verdict; when the failure stopped a verifier before it answered, the result holds the writer only, because the positional verdicts cannot show the gap (EC-16).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_verify.py, tests/features/harness_compose/test_harness_compose_git.py, tests/features/harness_compose/test_harness_compose_concurrency.py, tests/features/harness_compose/test_harness_compose_keys.py
"""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from vidbyte.harnesses.native.compose.answers import AnswerDecoders, JsonAnswers
from vidbyte.harnesses.native.compose.calls import ComposeCalls
from vidbyte.harnesses.native.compose.git import ComposeGit
from vidbyte.harnesses.native.compose.steps import StepRoles, ThreadBinder
from vidbyte.harnesses.native.compose.texts import ComposeTexts, PromptFitter
from vidbyte.harnesses.native.compose.workspace import DisposableWorktree
from vidbyte.lib.constants import native_compose, native_threads
from vidbyte.lib.dataclasses.native_compose import (
    JsonAnswer,
    ThreadStep,
    ThreadVerdict,
    VerifyResult,
)
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.enums.native_compose import ComposeField, ComposePrompt
from vidbyte.lib.enums.native_threads import NativeHarness
from vidbyte.lib.errors import ThreadComposeError


class ThreadVerifiers:
    """Runs one writer alone, then one to ten verifiers that review its change at the same time and cannot change the workspace."""

    @staticmethod
    async def verify_with(writer: ThreadStep, verifiers: Sequence[ThreadStep], *, prompt: str) -> VerifyResult:
        """Run writer on prompt alone, then have every verifier review the change it made and answer a structured verdict; raise READER_CHANGED_WORKSPACE when a verifier changed the workspace (spec INV-9 to INV-12, INV-25)."""
        # Check every input before anything runs: the writer, one to ten
        # verifiers that can only read and share its workspace, the
        # caller's prompt, and that every prompt fits its step.
        checked, readers = ThreadVerifiers._steps(writer, verifiers)
        RecordFieldValidator.require_text(prompt, native_compose.COMPOSE_PROMPT_PARAMETER, max_chars=native_threads.NATIVE_PROMPT_MAX_CHARS, pattern=native_threads.NATIVE_PROMPT_PATTERN)
        schema = (await ComposeTexts.load(ComposePrompt.VERDICT_SCHEMA)).format_map({})
        await ThreadVerifiers._fit(checked, readers, prompt, await ThreadVerifiers._question(prompt, (), "", schema))

        # Find git and the repository before any step runs. A worktree
        # starts at HEAD, so an opencode or Muse verifier needs a commit.
        keys = tuple(step.api_key for step in (checked, *readers))
        git = ComposeGit.locate(Path(checked.workspace), keys)
        await git.toplevel()
        await git.has_commit(required=any(StepRoles.needs_worktree(reader) for reader in readers))

        # @intent the-writer-runs-alone-and-readers-see-its-snapshot
        # The writer is the only step that may change the workspace, so
        # it runs alone, between two snapshots, before any verifier. The
        # second snapshot is the end of its diff, the tree every worktree
        # verifier is filled from, and what the verifiers must leave.
        before = await git.snapshot()
        record = VerifyResult(writer=await ComposeCalls.call(checked, await PromptFitter.fit(((prompt, False),), checked, keys)))
        kept: list[JsonAnswer[ThreadVerdict] | None] = [None] * len(readers)
        try:
            after = await git.snapshot()
            diff = await git.diff(before, after)
            record = VerifyResult(writer=dataclasses.replace(record.writer, diff=diff))

            # A failed writer gets no review, but keeps its diff, because
            # it may have edited files before it failed.
            if not record.writer.ok:
                return record

            # Every verifier reviews the change at the same time and
            # answers a verdict, repaired on its own thread when it does
            # not parse; one verifier's failure stops no other. Each
            # answer is kept as it arrives, before its worktree goes.
            question = await ThreadVerifiers._question(prompt, diff.files, diff.text, schema)
            verdicts = await ComposeCalls.fan_out([ThreadVerifiers._review(git, reader, (after, before), question, schema, keys, kept, index) for index, reader in enumerate(readers)])
            record = VerifyResult(writer=record.writer, verdicts=verdicts)

            # With every verifier done and every worktree gone, the
            # working tree must still be exactly what the writer left.
            await DisposableWorktree.backstop(git, after, record)
        except ThreadComposeError as error:
            # A compose failure after the writer ran carries the record
            # so far, with every verdict once every verifier answered,
            # unless it already carries a fuller one (EC-16).
            if error.result is None:
                error.result = ThreadVerifiers._kept(record, kept)
            raise
        return record

    @staticmethod
    def _steps(writer: object, verifiers: object) -> tuple[ThreadStep, tuple[ThreadStep, ...]]:
        # The writer is any step with a thread to run on; each of one to
        # ten verifiers must be a step that can only read and that works
        # in the writer's workspace, where the change it reviews is.
        checked = ThreadBinder.require_step(writer, native_compose.COMPOSE_WRITER_PARAMETER)
        StepRoles.anchored(checked, native_compose.COMPOSE_WRITER_PARAMETER)
        items = StepRoles.counted(verifiers, native_compose.COMPOSE_VERIFIERS_ARGUMENT, minimum=1, maximum=native_compose.COMPOSE_MAX_VERIFIERS)
        readers: list[ThreadStep] = []
        for index, item in enumerate(items):
            argument = StepRoles.item(native_compose.COMPOSE_VERIFIERS_ARGUMENT, index)
            reader = ThreadBinder.require_step(item, argument)
            StepRoles.anchored(reader, argument)
            StepRoles.reader(reader, argument)
            StepRoles.same_workspace(reader, argument, checked, native_compose.COMPOSE_WRITER_PARAMETER)
            readers.append(reader)
        return checked, tuple(readers)

    @staticmethod
    async def _question(prompt: str, files: Sequence[str], text: str, schema: str) -> tuple[tuple[str, bool], ...]:
        # A verifier's first turn: the caller's prompt, the changed files
        # one per line and the diff, wrapped with the verdict schema.
        turn = await ComposeTexts.load(ComposePrompt.VERIFY_TURN)
        listing = native_threads.NATIVE_LINE_SEPARATOR.join(files)
        return await JsonAnswers.wrapped(ComposeTexts.render(turn, {ComposeField.PROMPT: prompt, ComposeField.FILES: ComposeTexts.spliced(listing), ComposeField.DIFF: ComposeTexts.spliced(text)}), schema)

    @staticmethod
    async def _fit(writer: ThreadStep, readers: Sequence[ThreadStep], prompt: str, question: Sequence[tuple[str, bool]]) -> None:
        # The writer must take the caller's prompt as it is, and every
        # verifier its question with the file list and the diff at their
        # longest truncation notes; only the prompt can make either long.
        await PromptFitter.check(((prompt, False),), writer, argument=native_compose.COMPOSE_PROMPT_PARAMETER, receiver=native_compose.COMPOSE_WRITER_PARAMETER)
        for index, reader in enumerate(readers):
            await PromptFitter.check(question, reader, argument=native_compose.COMPOSE_PROMPT_PARAMETER, receiver=StepRoles.item(native_compose.COMPOSE_VERIFIERS_ARGUMENT, index))

    @staticmethod
    async def _review(git: ComposeGit, reader: ThreadStep, trees: tuple[str, str], question: Sequence[tuple[str, bool]], schema: str, keys: Sequence[str], kept: list[JsonAnswer[ThreadVerdict] | None], index: int) -> JsonAnswer[ThreadVerdict]:
        # A Grok verifier reviews in place, in its own read-only mode.
        if not StepRoles.needs_worktree(reader):
            answer = await JsonAnswers.ask(reader, question, schema, AnswerDecoders.verdict, keys)
            kept[index] = answer
            return answer

        # An opencode or Muse verifier reviews in a worktree of its own,
        # filled with the writer's result and indexed at the snapshot
        # before the writer, so git there shows the writer's change.
        # Its answer is kept before the worktree goes, so a removal
        # that fails cannot lose it (EC-16).
        after, before = trees
        async with DisposableWorktree.from_tree(git, after, before) as folder:
            answer = await JsonAnswers.ask(ThreadBinder.relocate(reader, folder), question, schema, AnswerDecoders.verdict, keys)
            kept[index] = answer
        return answer

    @staticmethod
    def _kept(record: VerifyResult, kept: Sequence[JsonAnswer[ThreadVerdict] | None]) -> VerifyResult:
        # The record so far, with the verdicts once every verifier has
        # answered; a verifier stopped before it answered leaves a gap
        # the positional verdicts cannot show, so then none are added.
        verdicts = tuple(answer for answer in kept if answer is not None)
        if len(verdicts) < len(kept):
            return record
        return VerifyResult(writer=record.writer, verdicts=verdicts)


class ThreadVerifyTrio:
    """One generated trio alias, run_<w>_verify_with_<x>_and_<y>(prompt, *, writer, <x>, <y>): verify_with(writer, [<x>, <y>], prompt=prompt) with the writer on <w> (spec INV-24)."""

    def __init__(self, writer: NativeHarness, first: NativeHarness, second: NativeHarness) -> None:
        # The alias shows the prompt, the writer, and then one
        # keyword-only verifier per harness, named after it, in the
        # order of the verdicts.
        self.writer = writer
        self.readers = (first, second)
        names = (native_compose.COMPOSE_WRITER_PARAMETER, *(harness.value for harness in self.readers))
        steps = (inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY) for name in names)
        self.__signature__ = inspect.Signature((inspect.Parameter(native_compose.COMPOSE_PROMPT_PARAMETER, inspect.Parameter.POSITIONAL_OR_KEYWORD), *steps))

    async def __call__(self, prompt: str, **steps: ThreadStep) -> VerifyResult:
        """Verify once the writer and each verifier are checked to be on their parameters' harnesses; a missing or unknown keyword is a TypeError before that (spec EC-77)."""
        # Bind the arguments to the signature before anything else, so a
        # keyword mistake is Python's TypeError. The partial bind goes
        # first because it names an unknown keyword, which a full bind
        # would report as the missing one it replaced.
        self.__signature__.bind_partial(prompt, **steps)
        self.__signature__.bind(prompt, **steps)

        # The writer must be on the alias's writer harness, and each
        # verifier on the harness its parameter names.
        writer = StepRoles.on_harness(steps[native_compose.COMPOSE_WRITER_PARAMETER], native_compose.COMPOSE_WRITER_PARAMETER, self.writer)
        readers = [StepRoles.on_harness(steps[harness.value], harness.value, harness) for harness in self.readers]
        return await ThreadVerifiers.verify_with(writer, readers, prompt=prompt)


class ThreadVerifyTrios:
    """The three trio aliases, one per writer harness with the other two as verifiers, bound in __init__.py as run_<w>_verify_with_<x>_and_<y>."""

    GROK_WRITES: ClassVar[ThreadVerifyTrio] = ThreadVerifyTrio(NativeHarness.GROK, NativeHarness.OPENCODE, NativeHarness.MUSE)
    OPENCODE_WRITES: ClassVar[ThreadVerifyTrio] = ThreadVerifyTrio(NativeHarness.OPENCODE, NativeHarness.GROK, NativeHarness.MUSE)
    MUSE_WRITES: ClassVar[ThreadVerifyTrio] = ThreadVerifyTrio(NativeHarness.MUSE, NativeHarness.GROK, NativeHarness.OPENCODE)


__all__ = ["ThreadVerifiers", "ThreadVerifyTrio", "ThreadVerifyTrios"]
