"""FILE: vidbyte/harnesses/native/compose/steps.py

PURPOSE: Binds the nine thread functions into checked steps and holds the step rules every composite applies: ThreadBinder (bind_thread, bind_continue, the table of the nine functions, require_step, and invoke, the only path by which compose calls a step) and StepRoles (the reader, unanchored-fork, fork-role, from_thread and one-workspace rules, the count rule, argument path names and needs_worktree).
ROLE IN CODEBASE: bind_thread and bind_continue are bound as public names in vidbyte/harnesses/native/compose/__init__.py. ComposeCalls (calls.py), JsonAnswers (answers.py) and every composite call ThreadBinder.invoke, require_step, anchor, relocate and rung, and check their inputs with StepRoles before any I/O (spec INV-5).
ARCHITECTURE NOTE: ThreadStep (vidbyte/lib/dataclasses/native_compose.py) validates its own arguments but holds no calling convention (spec D-2): the binders store ThreadBinder.invoke as its invoker, and invoke calls the step's function in its verb's argument order. Composites call ThreadBinder.invoke directly, never a step's stored invoker, and re-check every step against FUNCTIONS, which is keyed by the imported function objects themselves, so a step whose function or invoker was swapped still runs only one of the nine functions with its checked arguments (INV-3, EC-78). The module holds no literals (base spec INV-15): every text and argument name comes from vidbyte/lib/constants/native_compose.py.
FUNCTION INVENTORY: ThreadBinder.bind_thread and bind_continue build a step from one of the nine functions; invoke makes the one call a step stands for; require_step re-checks a step a composite received; anchor, relocate and rung give the same step on another thread, workspace or config; _identify finds a function's harness and verb. StepRoles.counted applies a count rule; item and member name an argument path; anchored refuses an unanchored fork; reader applies the reader rules; fork_role applies the ensemble fork rule; from_thread applies the handoff source rule; same_workspace applies the one-workspace rule; needs_worktree says whether a reader is relocated.
COMMON MODIFICATION PATTERNS: A tenth thread function is one more FUNCTIONS entry. A new role rule is one StepRoles method that raises ConfigurationError naming the argument path, with its message template in the constants module, called by each composite before any I/O.
WHAT NOT TO DO IN THIS FILE: 1. Do not call a step's stored invoker; call ThreadBinder.invoke. 2. Do not change a step's config or permission mode to make it fit a role; refuse it instead (spec D-21). 3. Do not quote a key, a workspace path or any other caller value in a refusal; name the argument path only. 4. Do not import a composite module; this is plumbing.
KNOWN EDGE CASES: A fork step bound with bind_thread has no thread id; it can only become an ensemble role, where compose anchors it at a Grok planner's thread on the same workspace (spec D-3). Workspaces are compared after os.path.normcase of the resolved path, so two spellings of one folder on Windows are one workspace. A functools.partial or a lambda wrapping one of the nine functions is not one of them and is refused.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_binding.py, tests/features/harness_compose/test_harness_compose_validation.py
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

from vidbyte.harnesses.native.grok import (
    continue_grok_thread,
    fork_grok_thread,
    run_grok_thread,
)
from vidbyte.harnesses.native.muse import (
    continue_muse_thread,
    fork_muse_thread,
    run_muse_thread,
)
from vidbyte.harnesses.native.opencode import (
    continue_opencode_thread,
    fork_opencode_thread,
    run_opencode_thread,
)
from vidbyte.lib.constants import native_compose, native_threads
from vidbyte.lib.dataclasses.native_compose import ThreadStep
from vidbyte.lib.dataclasses.native_threads import (
    GrokThreadConfig,
    MuseThreadConfig,
    NativeThreadResult,
    OpencodeThreadConfig,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_threads import NativeHarness, NativeThreadVerb
from vidbyte.lib.errors import ConfigurationError


class ThreadBinder:
    """Binds the nine thread functions into checked steps, and makes the one call each step stands for."""

    FUNCTIONS: ClassVar[MappingProxyType[tuple[NativeHarness, NativeThreadVerb], Callable[..., Awaitable[NativeThreadResult]]]] = MappingProxyType(
        {
            (NativeHarness.GROK, NativeThreadVerb.RUN): run_grok_thread,
            (NativeHarness.GROK, NativeThreadVerb.CONTINUE): continue_grok_thread,
            (NativeHarness.GROK, NativeThreadVerb.FORK): fork_grok_thread,
            (NativeHarness.OPENCODE, NativeThreadVerb.RUN): run_opencode_thread,
            (NativeHarness.OPENCODE, NativeThreadVerb.CONTINUE): continue_opencode_thread,
            (NativeHarness.OPENCODE, NativeThreadVerb.FORK): fork_opencode_thread,
            (NativeHarness.MUSE, NativeThreadVerb.RUN): run_muse_thread,
            (NativeHarness.MUSE, NativeThreadVerb.CONTINUE): continue_muse_thread,
            (NativeHarness.MUSE, NativeThreadVerb.FORK): fork_muse_thread,
        }
    )

    @staticmethod
    def bind_thread(function: Callable[..., Awaitable[NativeThreadResult]], *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | OpencodeThreadConfig | MuseThreadConfig | None = None) -> ThreadStep:
        """Bind a run_ function, or a fork_ function whose thread run_ensemble supplies later, with its arguments checked now."""
        harness, verb = ThreadBinder._identify(function, (NativeThreadVerb.RUN, NativeThreadVerb.FORK), native_compose.COMPOSE_BIND_THREAD_RULE)
        return ThreadStep(function=function, harness=harness, verb=verb, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config, invoker=ThreadBinder.invoke)

    @staticmethod
    def bind_continue(function: Callable[..., Awaitable[NativeThreadResult]], thread_id: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | OpencodeThreadConfig | MuseThreadConfig | None = None) -> ThreadStep:
        """Bind a continue_ or fork_ function to the thread thread_id, with its arguments checked now."""
        harness, verb = ThreadBinder._identify(function, (NativeThreadVerb.CONTINUE, NativeThreadVerb.FORK), native_compose.COMPOSE_BIND_CONTINUE_RULE)
        # A fork bound here is anchored, so its thread id must be given.
        RecordFieldValidator.require_text(thread_id, native_compose.COMPOSE_THREAD_ID_ARGUMENT, max_chars=native_threads.NATIVE_THREAD_ID_MAX_CHARS, pattern=native_threads.NATIVE_THREAD_ID_PATTERN)
        return ThreadStep(function=function, harness=harness, verb=verb, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config, thread_id=thread_id, invoker=ThreadBinder.invoke)

    @staticmethod
    async def invoke(step: ThreadStep, prompt: str) -> NativeThreadResult:
        """Call the step's function once with its bound arguments, the thread id first for continue and fork (spec INV-2, D-2)."""
        # @intent compose-calls-a-step-only-through-invoke
        # This is the one place compose calls a thread function, so the
        # unanchored-fork guard and each verb's argument order live
        # here and nowhere else. A step's own error propagates as the
        # very object the function raised.
        if step.verb is NativeThreadVerb.FORK and step.thread_id is None:
            raise ConfigurationError(native_compose.COMPOSE_UNANCHORED_FORK_CALL, details={native_threads.NATIVE_FIELD_DETAIL_KEY: native_compose.COMPOSE_THREAD_ID_ARGUMENT})
        if step.thread_id is None:
            return await step.function(prompt, api_key=step.api_key, workspace=step.workspace, model=step.model, skills=step.skills, config=step.config)
        return await step.function(step.thread_id, prompt, api_key=step.api_key, workspace=step.workspace, model=step.model, skills=step.skills, config=step.config)

    @staticmethod
    def require_step(value: object, argument: str) -> ThreadStep:
        """Return value when it is a ThreadStep whose function is one of the nine and matches its harness and verb; refuse it naming argument otherwise (spec INV-3)."""
        step: ThreadStep = RecordFieldConverter.require_instance(value, argument, ThreadStep)
        known = next((key for key, function in ThreadBinder.FUNCTIONS.items() if function is step.function), None)
        if known is None:
            raise ConfigurationError(native_compose.COMPOSE_UNKNOWN_STEP_FUNCTION.format(argument=argument), details={native_threads.NATIVE_FIELD_DETAIL_KEY: argument})
        harness, verb = known
        if (harness, verb) != (step.harness, step.verb):
            raise ConfigurationError(native_compose.COMPOSE_STEP_MISMATCH.format(argument=argument, harness=step.harness.value, verb=step.verb.value, function_harness=harness.value, function_verb=verb.value), details={native_threads.NATIVE_FIELD_DETAIL_KEY: argument})
        return step

    @staticmethod
    def anchor(step: ThreadStep, thread_id: str, verb: NativeThreadVerb = NativeThreadVerb.CONTINUE) -> ThreadStep:
        """The same bound step on thread_id through verb's function: a repair turn continues its thread, and an unanchored fork forks the planner's."""
        return replace(step, function=ThreadBinder.FUNCTIONS[(step.harness, verb)], verb=verb, thread_id=thread_id)

    @staticmethod
    def relocate(step: ThreadStep, workspace: Path) -> ThreadStep:
        """The same bound step with its workspace moved to workspace, the folder a worktree reader runs in."""
        return replace(step, workspace=workspace)

    @staticmethod
    def rung(step: ThreadStep, config: GrokThreadConfig | OpencodeThreadConfig | MuseThreadConfig) -> ThreadStep:
        """The same bound step with config, one rung of a stage's ladder."""
        return replace(step, config=config)

    @staticmethod
    def _identify(function: object, verbs: tuple[NativeThreadVerb, ...], rule: str) -> tuple[NativeHarness, NativeThreadVerb]:
        # One of the nine functions is found by identity, so a wrapper
        # such as a partial or a lambda is refused; the refusal names
        # the type only, never the value.
        found = next((key for key, known in ThreadBinder.FUNCTIONS.items() if known is function and key[1] in verbs), None)
        if found is None:
            raise ConfigurationError(rule.format(type_name=type(function).__name__), details={native_threads.NATIVE_FIELD_DETAIL_KEY: native_compose.COMPOSE_FUNCTION_ARGUMENT})
        return found


class StepRoles:
    """The rules a composite applies to its steps before any I/O: counts, readers, forks, handoff sources and one workspace."""

    @staticmethod
    def counted(values: object, argument: str, *, minimum: int, maximum: int) -> tuple[object, ...]:
        """values as a tuple when it is a list or tuple of minimum to maximum items; refuse it naming argument otherwise."""
        items = RecordFieldConverter.to_tuple(values, argument, item_type=object)
        if not minimum <= len(items) <= maximum:
            raise ConfigurationError(native_compose.COMPOSE_COUNT_RULE.format(argument=argument, minimum=minimum, maximum=maximum, count=len(items)), details={native_threads.NATIVE_FIELD_DETAIL_KEY: argument})
        return items

    @staticmethod
    def item(name: str, index: int) -> str:
        """The argument path of item index of name, such as steps[1]."""
        return native_compose.COMPOSE_ITEM_ARGUMENT.format(name=name, index=index)

    @staticmethod
    def member(name: str, member: str) -> str:
        """The argument path of member of name, such as roster.planner."""
        return native_compose.COMPOSE_MEMBER_ARGUMENT.format(name=name, member=member)

    @staticmethod
    def anchored(step: ThreadStep, argument: str) -> None:
        """Refuse a fork step with no thread id where there is no thread to fork (spec EC-44)."""
        if step.verb is NativeThreadVerb.FORK and step.thread_id is None:
            raise ConfigurationError(native_compose.COMPOSE_UNANCHORED_FORK_RULE.format(argument=argument), details={native_threads.NATIVE_FIELD_DETAIL_KEY: argument})

    @staticmethod
    def reader(step: ThreadStep, argument: str) -> None:
        """Refuse a step that may not read: a Grok step whose permission mode lets it edit, or an opencode or Muse step that is not a run step (spec INV-9, INV-10)."""
        # @intent readers-are-refused-never-reconfigured
        # A Grok reader runs in place, so only the plan and default
        # permission modes may read; compose never switches the mode
        # (D-21). An opencode or Muse reader runs in a disposable
        # worktree, where the thread a continue or fork names is not
        # reachable, so it must start a new thread there.
        config = step.config
        if isinstance(config, GrokThreadConfig) and config.permission_mode not in native_compose.COMPOSE_READER_GROK_MODES:
            raise ConfigurationError(native_compose.COMPOSE_GROK_READER_RULE.format(argument=argument, mode=config.permission_mode.value), details={native_threads.NATIVE_FIELD_DETAIL_KEY: argument})
        if StepRoles.needs_worktree(step) and step.verb is not NativeThreadVerb.RUN:
            raise ConfigurationError(native_compose.COMPOSE_WORKTREE_READER_RULE.format(argument=argument), details={native_threads.NATIVE_FIELD_DETAIL_KEY: argument})

    @staticmethod
    def fork_role(step: ThreadStep, argument: str, planner: ThreadStep) -> None:
        """Refuse an unanchored fork role unless it and the planner are Grok steps on one workspace (spec D-3)."""
        # @intent ensemble-forks-branch-only-a-reachable-grok-thread
        # A Grok thread is reachable only from its own workspace, and
        # no fork crosses harnesses, so an unanchored fork can branch
        # the planner's thread only when both are Grok on one folder.
        if step.verb is not NativeThreadVerb.FORK or step.thread_id is not None:
            return
        reachable = step.harness is NativeHarness.GROK and planner.harness is NativeHarness.GROK and os.path.normcase(str(step.workspace)) == os.path.normcase(str(planner.workspace))
        if not reachable:
            raise ConfigurationError(native_compose.COMPOSE_FORK_ROLE_RULE.format(argument=argument), details={native_threads.NATIVE_FIELD_DETAIL_KEY: argument})

    @staticmethod
    def from_thread(step: ThreadStep, argument: str) -> None:
        """Refuse a handoff source that starts a new thread: it must continue or fork an existing one (spec INV-5, EC-76)."""
        if step.verb is NativeThreadVerb.RUN:
            raise ConfigurationError(native_compose.COMPOSE_FROM_THREAD_RULE.format(argument=argument), details={native_threads.NATIVE_FIELD_DETAIL_KEY: argument})

    @staticmethod
    def same_workspace(step: ThreadStep, argument: str, reference: ThreadStep, reference_argument: str) -> None:
        """Refuse a step whose resolved workspace differs from the reference step's, compared after os.path.normcase (spec INV-5)."""
        if os.path.normcase(str(step.workspace)) != os.path.normcase(str(reference.workspace)):
            raise ConfigurationError(native_compose.COMPOSE_WORKSPACE_RULE.format(argument=argument, reference=reference_argument), details={native_threads.NATIVE_FIELD_DETAIL_KEY: argument})

    @staticmethod
    def needs_worktree(step: ThreadStep) -> bool:
        """Whether a reader on this step runs in a disposable worktree: every opencode and Muse reader does, a Grok reader runs in place."""
        return step.harness is not NativeHarness.GROK


__all__ = ["StepRoles", "ThreadBinder"]
