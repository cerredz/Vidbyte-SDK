"""FILE: vidbyte/harnesses/native/compose/handoff.py

PURPOSE: The handoff composite: ThreadHandoffs.handoff_thread asks a step that continues or forks an existing thread for a summary of its state, decisions and open items, then starts the target step with a seed prompt that carries the summary, so the work moves to a new thread, model or vendor.
ROLE IN CODEBASE: handoff_thread is bound as a public name in vidbyte/harnesses/native/compose/__init__.py. It builds on the plumbing modules: steps.py for the step checks, texts.py for the two prompt files and the prompt fit, and calls.py for each call.
ARCHITECTURE NOTE: A two-step sequential pipeline (spec D-27) with no git, worktree or backstop (INV-6): the summary turn runs on from_thread, and only when it succeeded does to_step run, on the handoff_seed prompt with the summary spliced in, so the summary is scrubbed of both bound keys and cut only when the seed would not fit (INV-4, INV-18). Both prompts are fixed files with no caller text, so no up-front fit check can blame a caller argument; the fit at send time still applies. The module holds no literals (base spec INV-15).
FUNCTION INVENTORY: ThreadHandoffs.handoff_thread is the narrated main function; _steps checks the source and the target.
COMMON MODIFICATION PATTERNS: A change to what the summary asks for or how the seed frames it is a change to handoff_summary.md or handoff_seed.md, not to this file. A new value for the seed is one field in handoff_seed.md and COMPOSE_PROMPT_FIELDS, filled in handoff_thread.
WHAT NOT TO DO IN THIS FILE: 1. Do not accept a run step as from_thread; a new thread has nothing to summarize (EC-76). 2. Do not start to_step after a failed summary turn. 3. Do not run git; a handoff moves a conversation, not files.
KNOWN EDGE CASES: A source whose key is still rejected fails the summary turn and the target never runs; to move away from a key problem, bind from_thread with another key for the same vendor (EC-64). The summary turn continues the source thread, so it becomes the last turn of that thread.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_handoff.py, tests/features/harness_compose/test_harness_compose_validation.py
"""

from __future__ import annotations

from vidbyte.harnesses.native.compose.calls import ComposeCalls
from vidbyte.harnesses.native.compose.steps import StepRoles, ThreadBinder
from vidbyte.harnesses.native.compose.texts import ComposeTexts, PromptFitter
from vidbyte.lib.constants import native_compose
from vidbyte.lib.dataclasses.native_compose import HandoffResult, ThreadStep
from vidbyte.lib.enums.native_compose import ComposeField, ComposePrompt


class ThreadHandoffs:
    """Moves work from an existing thread to a new step: a summary turn on the old thread, then a seeded turn on the new step."""

    @staticmethod
    async def handoff_thread(from_thread: ThreadStep, to_step: ThreadStep) -> HandoffResult:
        """Ask from_thread for the handoff summary, then send to_step the handoff seed holding that summary; to_step never runs after a failed summary turn (spec INV-16, INV-17)."""
        # Check both steps before anything runs: the source must
        # continue or fork an existing thread, and the target needs a
        # thread to run on.
        source, target = ThreadHandoffs._steps(from_thread, to_step)
        keys = (source.api_key, target.api_key)

        # Ask the source thread for its summary: state, decisions and
        # open items, written for an agent that cannot see the thread.
        summary_template = await ComposeTexts.load(ComposePrompt.HANDOFF_SUMMARY)
        summary = await ComposeCalls.call(source, await PromptFitter.fit(ComposeTexts.render(summary_template, {}), source, keys))
        if not summary.ok:
            return HandoffResult(summary=summary)

        # Start the target with the seed prompt around that summary,
        # spliced so no bound key reaches the target and a summary too
        # long for it is cut.
        seed = await ComposeTexts.load(ComposePrompt.HANDOFF_SEED)
        frame = ComposeTexts.render(seed, {ComposeField.SUMMARY: ComposeTexts.spliced(summary.text)})
        return HandoffResult(summary=summary, target=await ComposeCalls.call(target, await PromptFitter.fit(frame, target, keys)))

    @staticmethod
    def _steps(from_thread: object, to_step: object) -> tuple[ThreadStep, ThreadStep]:
        # The source continues an existing thread or forks one it names,
        # because a run step starts a new thread with nothing to
        # summarize; the target is any step with a thread to run on.
        source = ThreadBinder.require_step(from_thread, native_compose.COMPOSE_FROM_THREAD_ARGUMENT)
        StepRoles.from_thread(source, native_compose.COMPOSE_FROM_THREAD_ARGUMENT)
        StepRoles.anchored(source, native_compose.COMPOSE_FROM_THREAD_ARGUMENT)
        target = ThreadBinder.require_step(to_step, native_compose.COMPOSE_TO_STEP_ARGUMENT)
        StepRoles.anchored(target, native_compose.COMPOSE_TO_STEP_ARGUMENT)
        return source, target


__all__ = ["ThreadHandoffs"]
