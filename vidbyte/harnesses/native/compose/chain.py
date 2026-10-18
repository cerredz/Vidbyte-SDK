"""FILE: vidbyte/harnesses/native/compose/chain.py

PURPOSE: The chain composite and its six pair aliases: ThreadChains.chain_threads runs two to twenty-five steps one after another, sending step 1 the caller's prompt and each later step a template filled with that prompt, the previous step's answer and, when the template asks for it, the previous step's diff; ThreadChainPair is one generated alias such as run_opencode_then_grok, and ThreadChainPairs holds the six.
ROLE IN CODEBASE: chain_threads and the six run_<a>_then_<b> aliases are bound as public names in vidbyte/harnesses/native/compose/__init__.py. The chain builds on the plumbing modules: steps.py for the step checks, texts.py for the template and the prompt fit, calls.py for each call and git.py for the diffs.
ARCHITECTURE NOTE: A sequential pipeline (spec D-27): one step runs at a time and each step may write, so a chain has no readers, worktrees or backstop. Git runs only when the template uses {diff}, and then only for the steps whose diff a later step reads, which is every step but the last (INV-6); each such step runs between two snapshots of its own repository, and its diff is taken also when it failed. The aliases are generated, never hand-written (INV-24, D-18): each is a callable instance whose __signature__ shows (prompt, *, <a>, <b>) and whose __call__ binds its arguments to that signature before anything else, so a keyword mistake is Python's TypeError (EC-77). The module holds no literals (base spec INV-15).
FUNCTION INVENTORY: ThreadChains.chain_threads is the narrated main function; _steps checks the steps; _template picks and checks the template; _fit checks every prompt against the step that receives it; _gits finds git for the steps whose diff is read; _values fills the next step's template. ThreadChainPair.__init__ builds an alias's signature and __call__ runs the alias; ThreadChainPairs holds the six aliases.
COMMON MODIFICATION PATTERNS: A new value for chain templates is one ComposeField member in CHAIN_TEMPLATE_FIELDS and one entry in _values and in _fit, spliced there when it holds model output or workspace content. A fourth harness adds its ordered pairs as ThreadChainPairs members and binds them in __init__.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not run git for a template without {diff}, or for the last step. 2. Do not hand-write an alias; build it as a ThreadChainPair. 3. Do not splice or shorten the caller's prompt or template; only answers and diffs are scrubbed and cut. 4. Do not start a step after a failed one.
KNOWN EDGE CASES: Steps on one workspace share one git check. A step's diff includes any edit made outside the chain while it ran (EC-12). A git failure after a step ran carries the chain so far in ThreadComposeError.result. A template made only of placeholders is refused before any I/O, because it would send a blank prompt when the previous answer is blank (INV-18, EC-37).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_chain.py, tests/features/harness_compose/test_harness_compose_keys.py, tests/features/harness_compose/test_harness_compose_validation.py
"""

from __future__ import annotations

import dataclasses
import inspect
import os
import string
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from vidbyte.harnesses.native.compose.calls import ComposeCalls
from vidbyte.harnesses.native.compose.git import ComposeGit
from vidbyte.harnesses.native.compose.steps import StepRoles, ThreadBinder
from vidbyte.harnesses.native.compose.texts import ComposeTexts, PromptFitter
from vidbyte.lib.constants import native_compose, native_threads
from vidbyte.lib.dataclasses.native_compose import (
    ChainResult,
    PromptSegment,
    StepOutcome,
    ThreadStep,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_compose import ComposeField, ComposePrompt
from vidbyte.lib.enums.native_threads import NativeHarness
from vidbyte.lib.errors import ThreadComposeError


class ThreadChains:
    """Runs two to twenty-five steps one after another, sending each later step the previous answer and, when the template asks for it, the previous step's diff."""

    @staticmethod
    async def chain_threads(steps: Sequence[ThreadStep], template: str | None = None, *, prompt: str) -> ChainResult:
        """Run steps in order: step 1 gets prompt as it is, and each later step the template filled with prompt, the previous answer and its diff; stop after the first failed step (spec INV-16, INV-17)."""
        # Check every input before anything runs: the steps, the
        # caller's prompt and template, and that the longest prompt each
        # step can receive still fits that step.
        checked = ThreadChains._steps(steps)
        RecordFieldValidator.require_text(prompt, native_compose.COMPOSE_PROMPT_PARAMETER, max_chars=native_threads.NATIVE_PROMPT_MAX_CHARS, pattern=native_threads.NATIVE_PROMPT_PATTERN, quote=False)
        text = await ThreadChains._template(template)
        await ThreadChains._fit(checked, text, prompt)

        # When the template splices a diff, find git and the repository
        # of every step whose diff a later step reads before any step
        # runs, so a missing git or repository costs no work.
        keys = tuple(step.api_key for step in checked)
        gits = await ThreadChains._gits(checked, text, keys)

        outcomes: list[StepOutcome] = []
        frame: tuple[PromptSegment, ...] = ComposeTexts.fixed(prompt)
        try:
            for step, git in zip(checked, gits, strict=True):
                # Snapshot the step's repository just before it runs
                # when a later step reads its diff.
                before = None if git is None else await git.snapshot()

                # Send the step its prompt. An answer or a diff too long
                # for the step is cut, and no bound key reaches it.
                outcomes.append(await ComposeCalls.call(step, await PromptFitter.fit(frame, step, keys)))

                # Its diff is what changed while it ran, taken also when
                # it failed, because a failed step may have edited
                # files.
                if git is not None and before is not None:
                    outcomes[-1] = dataclasses.replace(outcomes[-1], diff=await git.diff(before, await git.snapshot()))

                # A failed step ends the chain; otherwise the next step
                # gets the template filled with this step's answer.
                if not outcomes[-1].ok:
                    break
                frame = ComposeTexts.render(text, ThreadChains._values(prompt, outcomes[-1]))
        except ThreadComposeError as error:
            # A git failure after a step ran carries the chain so far.
            if outcomes:
                error.result = ChainResult(outcomes=tuple(outcomes))
            raise
        return ChainResult(outcomes=tuple(outcomes))

    @staticmethod
    def _steps(steps: object) -> tuple[ThreadStep, ...]:
        # Two to twenty-five steps, each one of the nine functions with
        # its own arguments; a fork must name the thread it forks,
        # because a chain has no thread to give it.
        items = RecordFieldConverter.to_tuple(steps, native_compose.COMPOSE_STEPS_ARGUMENT, item_type=object, min_items=native_compose.COMPOSE_MIN_CHAIN_STEPS, max_items=native_compose.COMPOSE_MAX_STEPS)
        checked: list[ThreadStep] = []
        for index, item in enumerate(items):
            argument = StepRoles.item(native_compose.COMPOSE_STEPS_ARGUMENT, index)
            step = ThreadBinder.require_step(item, argument)
            StepRoles.anchored(step, argument)
            checked.append(step)
        return tuple(checked)

    @staticmethod
    async def _template(template: str | None) -> str:
        # The caller's template, which must splice {previous} and may
        # use only {prompt}, {previous} and {diff}, or chain_turn
        # without one.
        if template is None:
            return await ComposeTexts.load(ComposePrompt.CHAIN_TURN)
        RecordFieldValidator.require_template(template, native_compose.COMPOSE_TEMPLATE_ARGUMENT, fields=native_compose.CHAIN_TEMPLATE_FIELDS, required=native_compose.CHAIN_REQUIRED_FIELDS)
        return RecordFieldValidator.require_text(template, native_compose.COMPOSE_TEMPLATE_ARGUMENT, max_chars=native_threads.NATIVE_PROMPT_MAX_CHARS, pattern=native_threads.NATIVE_PROMPT_PATTERN, quote=False)

    @staticmethod
    async def _fit(steps: Sequence[ThreadStep], template: str, prompt: str) -> None:
        # Step 1 must take the caller's prompt as it is. Every later
        # step must take the template with the answer and the diff at
        # their longest truncation notes: measured first without the
        # prompt, so a template too long by itself is blamed on the
        # template.
        for index, step in enumerate(steps):
            receiver = StepRoles.item(native_compose.COMPOSE_STEPS_ARGUMENT, index)
            if not index:
                await PromptFitter.check(ComposeTexts.fixed(prompt), step, argument=native_compose.COMPOSE_PROMPT_PARAMETER, receiver=receiver)
                continue
            for argument, text in ((native_compose.COMPOSE_TEMPLATE_ARGUMENT, ""), (native_compose.COMPOSE_PROMPT_PARAMETER, prompt)):
                frame = ComposeTexts.render(template, {ComposeField.PROMPT: text, ComposeField.PREVIOUS: ComposeTexts.spliced(""), ComposeField.DIFF: ComposeTexts.spliced("")})
                await PromptFitter.check(frame, step, argument=argument, receiver=receiver)

    @staticmethod
    async def _gits(steps: Sequence[ThreadStep], template: str, keys: Sequence[str]) -> tuple[ComposeGit | None, ...]:
        # Git for each step whose diff a later step reads: none when the
        # template has no {diff}, and never for the last step. Steps on
        # one workspace share one check of git and the repository.
        names = {name for _literal, name, _spec, _conversion in string.Formatter().parse(template)}
        if ComposeField.DIFF not in names:
            return tuple(None for _step in steps)
        found: dict[str, ComposeGit] = {}
        for step in steps[:-1]:
            place = os.path.normcase(str(step.workspace))
            if place not in found:
                found[place] = ComposeGit.locate(Path(step.workspace), keys)
                await found[place].toplevel()
                await found[place].has_commit()
        return (*(found[os.path.normcase(str(step.workspace))] for step in steps[:-1]), None)

    @staticmethod
    def _values(prompt: str, outcome: StepOutcome) -> dict[ComposeField, str | tuple[PromptSegment, ...]]:
        # The next step's template values: the caller's prompt as fixed
        # text, and the answer and the diff spliced, the diff empty when
        # none was taken.
        diff = "" if outcome.diff is None else outcome.diff.text
        return {ComposeField.PROMPT: prompt, ComposeField.PREVIOUS: ComposeTexts.spliced(outcome.text), ComposeField.DIFF: ComposeTexts.spliced(diff)}


class ThreadChainPair:
    """One generated pair alias, run_<a>_then_<b>(prompt, *, <a>, <b>): chain_threads([<a>, <b>], prompt=prompt) with the default template (spec INV-24)."""

    def __init__(self, first: NativeHarness, second: NativeHarness) -> None:
        # The alias shows the prompt and then one keyword-only step per
        # harness, named after it, in the order the chain runs them.
        self.harnesses = (first, second)
        steps = (inspect.Parameter(harness.value, inspect.Parameter.KEYWORD_ONLY) for harness in self.harnesses)
        self.__signature__ = inspect.Signature((inspect.Parameter(native_compose.COMPOSE_PROMPT_PARAMETER, inspect.Parameter.POSITIONAL_OR_KEYWORD), *steps))

    async def __call__(self, prompt: str, **steps: ThreadStep) -> ChainResult:
        """Chain the two steps once each is checked to be on its parameter's harness; a missing or unknown keyword is a TypeError before that (spec EC-77)."""
        # Bind the arguments to the signature before anything else, so a
        # keyword mistake is Python's TypeError. The partial bind goes
        # first because it names an unknown keyword, which a full bind
        # would report as the missing one it replaced.
        self.__signature__.bind_partial(prompt, **steps)
        self.__signature__.bind(prompt, **steps)

        # Each step must be on the harness its parameter names.
        checked = [StepRoles.on_harness(steps[harness.value], harness.value, harness) for harness in self.harnesses]
        return await ThreadChains.chain_threads(checked, prompt=prompt)


class ThreadChainPairs:
    """The six pair aliases, one per ordered pair of distinct harnesses, bound in __init__.py as run_<a>_then_<b>."""

    GROK_THEN_OPENCODE: ClassVar[ThreadChainPair] = ThreadChainPair(NativeHarness.GROK, NativeHarness.OPENCODE)
    GROK_THEN_MUSE: ClassVar[ThreadChainPair] = ThreadChainPair(NativeHarness.GROK, NativeHarness.MUSE)
    OPENCODE_THEN_GROK: ClassVar[ThreadChainPair] = ThreadChainPair(NativeHarness.OPENCODE, NativeHarness.GROK)
    OPENCODE_THEN_MUSE: ClassVar[ThreadChainPair] = ThreadChainPair(NativeHarness.OPENCODE, NativeHarness.MUSE)
    MUSE_THEN_GROK: ClassVar[ThreadChainPair] = ThreadChainPair(NativeHarness.MUSE, NativeHarness.GROK)
    MUSE_THEN_OPENCODE: ClassVar[ThreadChainPair] = ThreadChainPair(NativeHarness.MUSE, NativeHarness.OPENCODE)


__all__ = ["ThreadChainPair", "ThreadChainPairs", "ThreadChains"]
