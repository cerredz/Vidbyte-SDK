"""FILE: vidbyte/harnesses/native/compose/calls.py

PURPOSE: Runs step calls for the composites: ComposeCalls.call makes one step call and records its result or its own error, ComposeCalls.fan_out runs concurrent children and stops them all on the first unexpected failure, and GrokWorkspaceLocks serializes Grok step calls per event loop and workspace.
ROLE IN CODEBASE: Used by JsonAnswers (answers.py) and by every composite (chain.py, verify.py, handoff.py, stages.py, ensemble.py, selection.py) for each step call, and by verify.py and ensemble.py for their fan-outs.
ARCHITECTURE NOTE: call awaits ThreadBinder.invoke, never a step's stored invoker (spec D-2). It follows the one-guarded-try shape of the thread functions: cancellation passes first, a step's own NativeThreadError becomes the outcome (the very object raised), and anything else propagates as a defect. Every Grok call in every composite holds a one-slot asyncio.Semaphore for its running loop and normcased resolved workspace, for that one call only (spec D-5, INV-13); a Semaphore and not an asyncio.Lock, which lint bans (TID251). fan_out uses tasks with asyncio.gather and explicit sibling cancellation, never a TaskGroup, so exactly one exception propagates and never an ExceptionGroup (spec D-17, INV-14).
FUNCTION INVENTORY: ComposeCalls.call is the narrated main function of one step call; _invoke takes the Grok slot around ThreadBinder.invoke; fan_out runs children concurrently and returns their values in order. GrokWorkspaceLocks.slot returns the semaphore for a workspace in the running loop.
COMMON MODIFICATION PATTERNS: A harness whose concurrent calls in one workspace collide gets the same slot treatment in _invoke. A new fan-out reuses fan_out with a child coroutine that records its own step failures.
WHAT NOT TO DO IN THIS FILE: 1. Do not use asyncio.Lock or asyncio.TaskGroup. 2. Do not catch broad exceptions around a step call; only NativeThreadError is a step's own failure. 3. Do not hold a Grok slot across more than one step call; each repair turn takes it again. 4. Do not import a composite module; this is plumbing.
KNOWN EDGE CASES: The semaphores live in a WeakValueDictionary, so an entry disappears once no call holds or awaits it, and a new event loop gets its own semaphore. Direct calls to the nine functions, other event loops and other processes are not serialized (spec NG-10). A caller who cancels during fan_out gets CancelledError only after every child has stopped and cleaned up.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_concurrency.py, tests/features/harness_compose/test_harness_compose_verify.py
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Sequence
from pathlib import Path
from typing import ClassVar
from weakref import WeakValueDictionary

from vidbyte.harnesses.native.compose.steps import ThreadBinder
from vidbyte.lib.constants import native_compose
from vidbyte.lib.dataclasses.native_compose import AnswerT, StepOutcome, ThreadStep
from vidbyte.lib.dataclasses.native_threads import NativeThreadResult
from vidbyte.lib.enums.native_threads import NativeHarness
from vidbyte.lib.errors import NativeThreadError


class GrokWorkspaceLocks:
    """One single-slot semaphore per running event loop and resolved workspace, so Grok calls on one workspace take turns (spec D-5)."""

    _slots: ClassVar[WeakValueDictionary[tuple[asyncio.AbstractEventLoop, str], asyncio.Semaphore]] = WeakValueDictionary()

    @staticmethod
    def slot(workspace: Path | str) -> asyncio.Semaphore:
        """The semaphore that Grok calls on workspace share in the running event loop."""
        # @intent grok-calls-take-turns-per-loop-and-workspace
        # Concurrent Grok calls in one workspace share one private home
        # whose skills folder each call rebuilds, so they run one at a
        # time; calls in other workspaces or loops do not wait.
        key = (asyncio.get_running_loop(), os.path.normcase(str(workspace)))
        semaphore = GrokWorkspaceLocks._slots.get(key)
        if semaphore is None:
            semaphore = asyncio.Semaphore(native_compose.COMPOSE_GROK_MAX_CONCURRENT_CALLS)
            GrokWorkspaceLocks._slots[key] = semaphore
        return semaphore


class ComposeCalls:
    """One step call with its failure recorded, and concurrent children that stop together."""

    @staticmethod
    async def call(step: ThreadStep, prompt: str) -> StepOutcome:
        """Run prompt on step once and return its result, or the very NativeThreadError it raised, as a StepOutcome."""
        # @intent step-failures-are-outcomes-and-cancellation-passes
        # A step's own failure is data the composite records, so it
        # never stops a sibling; cancellation and any other exception
        # are not step failures and propagate unchanged.
        try:
            result = await ComposeCalls._invoke(step, prompt)
        except asyncio.CancelledError:
            raise
        except NativeThreadError as error:
            return StepOutcome(error=error)
        return StepOutcome(result=result)

    @staticmethod
    async def fan_out(children: Sequence[Awaitable[AnswerT]]) -> tuple[AnswerT, ...]:
        """Run children concurrently and return their values in order; the first exception cancels and awaits every sibling, then propagates alone (spec INV-14)."""
        # Start every child, then wait until all finish or one fails.
        tasks = [asyncio.ensure_future(child) for child in children]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        finally:
            # Stop whatever still runs, also when the caller cancelled,
            # and wait until every child has cleaned up its worktree.
            for task in tasks:
                task.cancel()
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Let one failure through: a real exception before a child's
        # cancellation, and never a group of them.
        failures = [result for result in results if isinstance(result, BaseException)]
        for failure in failures:
            if not isinstance(failure, asyncio.CancelledError):
                raise failure
        if failures:
            raise failures[0]
        return tuple(result for result in results if not isinstance(result, BaseException))

    @staticmethod
    async def _invoke(step: ThreadStep, prompt: str) -> NativeThreadResult:
        # A Grok call holds its workspace's slot for this one call.
        if step.harness is not NativeHarness.GROK:
            return await ThreadBinder.invoke(step, prompt)
        async with GrokWorkspaceLocks.slot(step.workspace):
            return await ThreadBinder.invoke(step, prompt)


__all__ = ["ComposeCalls", "GrokWorkspaceLocks"]
