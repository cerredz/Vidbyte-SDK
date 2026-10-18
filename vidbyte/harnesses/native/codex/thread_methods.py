"""FILE: vidbyte/harnesses/native/codex/thread_methods.py

PURPOSE: CodexThreadMethods, the CodexHost mixin for side chats, worktrees and the thread lifecycle: it starts a side chat on an ephemeral fork of a thread, makes a git worktree for a new branch, archives, unarchives, reverts and renames stored threads, injects items into a thread's history, lists and cleans a thread's background terminals, searches thread content, and lists a thread's child threads.
ROLE IN CODEBASE: One of the four feature mixins of vidbyte/harnesses/native/codex/; CodexHost inherits its eleven public methods (first-class D-1). Each method is a thin narrated main function over the host's collaborators: CodexThreadHelpers for the fork, the existence read, the idle status and the load, CodexTurnStarts for the side chat's turn, and the canonical GitWorktrees helper of vidbyte/lib/process/git_worktree.py for the worktree.
ARCHITECTURE NOTE: Imports no openai-codex module and none of the host's SDK-loading collaborators at module level, so importing this mixin, or CodexHost, still loads no SDK (first-class INV-45). Every Codex request goes through CodexConnection.call, and the side chat's turn through CodexTurnStarts, so each writes one call record (INV-3). The worktree never talks to Codex: it builds its target under Path.home() at call time and reads its git bound from this module's namespace at call time, so a test patches both (section 13). The history-changing calls run CodexHostCore._change_idle (INV-34).
COMMON MODIFICATION PATTERNS: A new thread function is one public method here: guard, its record from vidbyte/lib/dataclasses/codex_host_inputs.py, the experimental gate when Codex marks the call experimental, the existence read when Codex would not refuse an unknown thread itself, then one call. A call that changes stored history goes through _change_idle. Its messages go in vidbyte/lib/constants/codex_host.py, never here.
KNOWN EDGE CASES: A side chat forks through the parent's latest completed turn and never touches the parent, which may be running; a fork whose approvals Codex routes to a person nothing here answers is refused before it shares the parent's tool handler, and a later failure releases that handler, so a failed side chat registers nothing (INV-27, INV-28, D-36). The ephemeral fork stays loaded until the host closes (EC-30). A worktree whose folder already exists is refused before git runs; so is a worktree root that cannot be prepared, named by the exception's type alone and raised from None, so the home path never reaches the caller (EC-63); and every git failure is configuration.invalid_argument with git's first stderr line cut to CODEX_HOST_WORKTREE_DETAIL_MAX_CHARS; its logs carry no path, branch or git output (INV-9, INV-29). Background terminals are not loaded first (EC-47).
RELATED DOCS: docs/spec/codex-host-first-class/spec.md (sections 8.5, 9.2 and 12.3 row 28, INV-1, INV-4, INV-9, INV-27 to INV-29, INV-34 to INV-40, D-18, D-19, D-22, D-24, D-25, D-35, D-36)
TESTS: tests/features/codex_host/test_codex_host_side_chat.py, tests/features/codex_host/test_codex_host_worktree.py, tests/features/codex_host/test_codex_host_thread_admin.py, tests/features/codex_host/test_codex_host_feature_contract.py, tests/features/codex_host/test_codex_host_feature_structure.py, tests/features/codex_host/test_codex_host_feature_docs.py
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import Any

from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.harnesses.native.codex.host_core import CodexHostCore
from vidbyte.lib.constants.codex import (
    CODEX_MILLISECONDS_PER_SECOND,
    CODEX_THREAD_LIST_METHOD,
    CODEX_THREAD_NAME_SET_METHOD,
)
from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_WORKTREE_DETAIL_MAX_CHARS,
    CODEX_HOST_WORKTREE_EXISTS_CAUSE,
    CODEX_HOST_WORKTREE_EXISTS_MESSAGE,
    CODEX_HOST_WORKTREE_EXISTS_NEXT_STEP,
    CODEX_HOST_WORKTREE_FAILED_CAUSE,
    CODEX_HOST_WORKTREE_FAILED_MESSAGE,
    CODEX_HOST_WORKTREE_FAILED_NEXT_STEP,
    CODEX_HOST_WORKTREE_GIT_MISSING_CAUSE,
    CODEX_HOST_WORKTREE_GIT_MISSING_MESSAGE,
    CODEX_HOST_WORKTREE_GIT_MISSING_NEXT_STEP,
    CODEX_HOST_WORKTREE_MAX_OUTPUT_BYTES,
    CODEX_HOST_WORKTREE_NAME_SEPARATOR,
    CODEX_HOST_WORKTREE_ROOT_CAUSE,
    CODEX_HOST_WORKTREE_ROOT_MESSAGE,
    CODEX_HOST_WORKTREE_ROOT_NEXT_STEP,
    CODEX_HOST_WORKTREE_ROOT_PARTS,
    CODEX_HOST_WORKTREE_TIMED_OUT_CAUSE,
    CODEX_HOST_WORKTREE_TIMED_OUT_MESSAGE,
    CODEX_HOST_WORKTREE_TIMED_OUT_NEXT_STEP,
    CODEX_HOST_WORKTREE_TIMEOUT_SECONDS,
    CODEX_HOST_WORKTREE_UNSAFE_NAME_PATTERN,
    CODEX_THREAD_ARCHIVE_METHOD,
    CODEX_THREAD_BACKGROUND_TERMINALS_CLEAN_METHOD,
    CODEX_THREAD_BACKGROUND_TERMINALS_LIST_METHOD,
    CODEX_THREAD_INJECT_ITEMS_METHOD,
    CODEX_THREAD_REVERT_METHOD,
    CODEX_THREAD_SEARCH_METHOD,
    CODEX_THREAD_UNARCHIVE_METHOD,
)
from vidbyte.lib.constants.native_threads import GIT_DEFAULT_BASE_REF
from vidbyte.lib.dataclasses.codex import CodexRunInput
from vidbyte.lib.dataclasses.codex_host import (
    CodexSpawnRequest,
    CodexThreadInfo,
    CodexThreadPage,
    CodexTurnHandle,
)
from vidbyte.lib.dataclasses.codex_host_features import (
    CodexBackgroundTerminalPage,
    CodexThreadSearchPage,
    CodexWorktree,
)
from vidbyte.lib.dataclasses.codex_host_inputs import (
    CodexChildThreadsRequest,
    CodexForkRequest,
    CodexItemsInjectRequest,
    CodexSideChatRequest,
    CodexTerminalListRequest,
    CodexThreadRef,
    CodexThreadRenameRequest,
    CodexThreadRevertRequest,
    CodexThreadSearchRequest,
    CodexWorktreeRequest,
)
from vidbyte.lib.dataclasses.process import CliOutcome, GitWorktreeSpec
from vidbyte.lib.enums.codex import (
    CodexHostOperation,
    CodexSortDirection,
    CodexThreadSortKey,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.process.git_worktree import GitWorktrees

logger = logging.getLogger(__name__)


class CodexThreadMethods(CodexHostCore):
    """The side-chat, worktree and thread-lifecycle functions CodexHost inherits."""

    async def start_codex_side_chat(self, thread_id: str, prompt: str | CodexRunInput, request: CodexSpawnRequest | None = None) -> CodexTurnHandle:
        """Ask a side question on an ephemeral fork of a thread, without touching the thread, and return the fork's turn.

        The fork goes through the thread's latest completed turn, is told
        it is a side conversation, and is never named; the parent may be
        running. The fork shares the parent's Vidbyte tools, which stay
        callable from the side chat and run in Vidbyte, outside Codex's
        sandbox, so a read-only request limits Codex's own commands only.
        A parent with an active goal may pass that goal to the fork, and
        Codex may continue it there as paid turns this host does not
        track. The fork stays loaded until the host closes.
        """
        # @intent a-side-chat-follows-codexs-own-side-flow
        # Fork the thread, mark where the side chat starts, then start
        # its turn on the fork, as Codex's own /side flow does
        # (first-class INV-27). Only a missing request means the
        # default, so any other value reaches the record.
        operation = CodexHostOperation.START_CODEX_SIDE_CHAT
        self._guard(operation, talks=True)
        side = CodexSideChatRequest(thread_id=thread_id, prompt=prompt, request=CodexSpawnRequest() if request is None else request)
        spawn = side.request
        # Build the input and check the answer schema, so a bad prompt
        # or schema sends nothing; then run the spending checks.
        items = self._params.input_items(side.prompt)
        self._params.reject_unusable_schema(spawn)
        await self._preflight.run(operation, spawn)
        # Fork through the latest completed turn as an ephemeral thread
        # told it is a side chat; the fork checks the reviewer Codex
        # resolved before it shares the parent's tools (D-36).
        fork_view, turn_view = self._feature_params.side_chat_views(spawn)
        forking = CodexForkRequest(thread_id=side.thread_id, exclude_turns=True, overrides=fork_view)
        fork = await self._threads.fork(operation, forking, starts_turn=True)
        # Mark the start of the side chat, then start its turn priced as
        # the fork's model. A failure releases the fork's tool handler,
        # so nothing stays registered (INV-28).
        try:
            connection = self._connection
            boundary = connection.raw(CODEX_THREAD_INJECT_ITEMS_METHOD, self._feature_params.side_chat_boundary(fork.thread_id), parse=self._feature_responses.empty)
            await connection.call(operation, CODEX_THREAD_INJECT_ITEMS_METHOD, boundary, thread_id=fork.thread_id)
            pricing = self._responses.pricing(fork.model, fork.model_provider, self._params.turn_model(turn_view))
            turn = await self._starts.start_turn(operation, fork.thread_id, turn_view, items, pricing)
        except BaseException:
            self._starts.release_tools(fork.thread_id)
            raise
        return self._starts.accept(operation, turn)

    async def create_codex_worktree(self, repository: str | Path, branch: str, base_ref: str = "") -> CodexWorktree:
        """Make a git worktree for a new branch under ~/.vidbyte/codex-worktrees, with one git worktree add and no Codex request.

        The folder is named after the repository folder and the branch,
        with every character outside letters, digits, '.', '_' and '-'
        made '-'. An existing folder is refused before git runs. git runs
        with no terminal prompt, within a time and output bound; a run
        stopped at the bound may leave a half-made folder. Remove a
        worktree with git worktree remove; its branch stays.
        """
        # @intent a-worktree-is-one-bounded-git-run
        # Make the folder name, refuse one that exists or a root that
        # cannot be prepared, then run git once and map any failure to
        # its own packet (first-class INV-29, D-19, EC-63).
        operation = CodexHostOperation.CREATE_CODEX_WORKTREE
        self._guard(operation, talks=False)
        worktree = CodexWorktreeRequest(repository=repository, branch=branch, base_ref=base_ref)
        repo = Path(worktree.repository)
        # The target is under the home folder read now, named
        # <repository folder>-<branch made safe>. The root is made
        # before git runs, because git makes the branch first.
        try:
            root = Path.home().joinpath(*CODEX_HOST_WORKTREE_ROOT_PARTS)
            target = root / f"{repo.name}{CODEX_HOST_WORKTREE_NAME_SEPARATOR}{re.sub(CODEX_HOST_WORKTREE_UNSAFE_NAME_PATTERN, CODEX_HOST_WORKTREE_NAME_SEPARATOR, worktree.branch)}"
            if target.exists():
                raise CodexErrorMapper.error(FailureCode.CONFIGURATION_INVALID_ARGUMENT, CODEX_HOST_WORKTREE_EXISTS_MESSAGE, operation, likely_cause=CODEX_HOST_WORKTREE_EXISTS_CAUSE, next_step=CODEX_HOST_WORKTREE_EXISTS_NEXT_STEP)
            root.mkdir(parents=True, exist_ok=True)
        except (OSError, RuntimeError) as exc:
            # A home that cannot be found or a root that cannot be made
            # is named by its type alone, because the exception's text
            # holds the home path; nothing is logged (EC-63).
            failed = CODEX_HOST_WORKTREE_ROOT_MESSAGE.format(error_type=type(exc).__name__)
            raise CodexErrorMapper.error(FailureCode.CONFIGURATION_INVALID_ARGUMENT, failed, operation, likely_cause=CODEX_HOST_WORKTREE_ROOT_CAUSE, next_step=CODEX_HOST_WORKTREE_ROOT_NEXT_STEP) from None
        # Run git once, within the bound read now, and time it for the
        # log.
        bound = CODEX_HOST_WORKTREE_TIMEOUT_SECONDS
        spec = GitWorktreeSpec(repository=repo, branch=worktree.branch, path=target, timeout_seconds=bound, max_output_bytes=CODEX_HOST_WORKTREE_MAX_OUTPUT_BYTES, base_ref=worktree.base_ref)
        started = time.monotonic()
        outcome = await GitWorktrees.add(spec)
        duration_ms = int((time.monotonic() - started) * CODEX_MILLISECONDS_PER_SECOND)
        # A failed run is logged without its path, branch or output,
        # then raised with its own cause and next step (INV-9).
        failure = self._worktree_failure(outcome, bound)
        if failure is not None:
            launch = outcome.launch_failure.value if outcome.launch_failure is not None else None
            logger.warning("codex_host_worktree_failed operation=%s exit_code=%s timed_out=%s launch_failure=%s duration_ms=%d", operation.value, outcome.exit_code, outcome.timed_out, launch, duration_ms)
            message, cause, next_step = failure
            raise CodexErrorMapper.error(FailureCode.CONFIGURATION_INVALID_ARGUMENT, message, operation, likely_cause=cause, next_step=next_step)
        logger.debug("codex_host_worktree_created operation=%s duration_ms=%d", operation.value, duration_ms)
        return CodexWorktree(path=str(target), branch=worktree.branch, base_ref=worktree.base_ref or GIT_DEFAULT_BASE_REF, repository=str(repo))

    async def archive_codex_thread(self, thread_id: str) -> None:
        """Archive a stored thread, which hides it from the default thread listings; unarchive_codex_thread brings it back.

        A thread any client is running is refused with codex.session_busy.
        """
        # Check the host and the thread id before anything is sent.
        operation = CodexHostOperation.ARCHIVE_CODEX_THREAD
        self._guard(operation, talks=True)
        ref = CodexThreadRef(operation=operation, thread_id=thread_id)
        # Archive the thread only while no client runs it: it is
        # reserved here, Codex's status is checked, and the reservation
        # is always released. An archive needs no load (INV-34).
        archive = partial(self._connection.client.thread_archive, ref.thread_id)
        await self._change_idle(operation, ref.thread_id, CODEX_THREAD_ARCHIVE_METHOD, archive, loads=False)

    async def unarchive_codex_thread(self, thread_id: str) -> CodexThreadInfo:
        """Bring an archived thread back and return it; a thread that is not archived, or does not exist, is Codex's own refusal."""
        # Check the host and the thread id before anything is sent.
        operation = CodexHostOperation.UNARCHIVE_CODEX_THREAD
        self._guard(operation, talks=True)
        ref = CodexThreadRef(operation=operation, thread_id=thread_id)
        # Send the unarchive with no read first: Codex itself refuses a
        # thread that is unknown or not archived (first-class INV-35).
        connection = self._connection
        restored = await connection.call(operation, CODEX_THREAD_UNARCHIVE_METHOD, connection.client.thread_unarchive, ref.thread_id, thread_id=ref.thread_id)
        # Return the restored thread in the host's own thread shape.
        return self._responses.thread_info(restored.thread)

    async def revert_codex_thread(self, thread_id: str, before_turn_id: str) -> CodexThreadInfo:
        """Remove the turns from before_turn_id on from a thread's stored history, and return the thread; it cannot be undone.

        Only the history changes: files the reverted turns changed on
        disk stay as they are. Snapshots of turns this host tracked keep
        what they reported. A thread any client is running is refused,
        and a thread not loaded here is loaded first unless its stored
        goal is active.
        """
        # Check the host, the thread id and the turn id first.
        operation = CodexHostOperation.REVERT_CODEX_THREAD
        self._guard(operation, talks=True)
        reverting = CodexThreadRevertRequest(thread_id=thread_id, before_turn_id=before_turn_id)
        # Build the one thread/revert call, whose answer is the thread
        # as Codex now stores it (first-class INV-36).
        params = self._feature_params.revert(reverting.thread_id, reverting.before_turn_id)
        revert = self._connection.raw(CODEX_THREAD_REVERT_METHOD, params, parse=self._feature_responses.reverted)
        # Run it only while no client runs the thread, loading the
        # thread first when it is not loaded here (INV-34).
        return await self._change_idle(operation, reverting.thread_id, CODEX_THREAD_REVERT_METHOD, revert, loads=True)

    async def rename_codex_thread(self, thread_id: str, name: str) -> None:
        """Give a stored thread a new name."""
        # Check the host, the thread id and the new name first.
        operation = CodexHostOperation.RENAME_CODEX_THREAD
        self._guard(operation, talks=True)
        renaming = CodexThreadRenameRequest(thread_id=thread_id, name=name)
        # Read the thread first, so an unknown one is refused as
        # codex.session_not_found, then send the rename (INV-35).
        await self._preflight.require_thread(operation, renaming.thread_id)
        connection = self._connection
        await connection.call(operation, CODEX_THREAD_NAME_SET_METHOD, connection.client.thread_set_name, renaming.thread_id, renaming.name, thread_id=renaming.thread_id)

    async def inject_codex_items(self, thread_id: str, items: Sequence[Mapping[str, Any]]) -> None:
        """Add items to a thread's stored history exactly as given, in order; they cannot be removed except by a revert.

        A thread any client is running is refused, and a thread not
        loaded here is loaded first unless its stored goal is active.
        """
        # Check the host and the thread id, and take a JSON copy of the
        # items, so a later change by the caller changes nothing sent.
        operation = CodexHostOperation.INJECT_CODEX_ITEMS
        self._guard(operation, talks=True)
        injecting = CodexItemsInjectRequest(thread_id=thread_id, items=items)
        # Build the one thread/inject_items call with the items in the
        # order given (first-class INV-37).
        params = self._feature_params.inject(injecting.thread_id, injecting.items)
        inject = self._connection.raw(CODEX_THREAD_INJECT_ITEMS_METHOD, params, parse=self._feature_responses.empty)
        # Run it only while no client runs the thread, loading the
        # thread first when it is not loaded here (INV-34).
        await self._change_idle(operation, injecting.thread_id, CODEX_THREAD_INJECT_ITEMS_METHOD, inject, loads=True)

    async def list_codex_background_terminals(self, thread_id: str, cursor: str = "", limit: int | None = None) -> CodexBackgroundTerminalPage:
        """One page of the background terminals a thread's commands left running; it needs Codex's experimental API.

        A thread that is not loaded here is not loaded first.
        """
        # Check the host and the page arguments, then refuse at once on
        # a host without Codex's experimental API (first-class INV-4).
        operation = CodexHostOperation.LIST_CODEX_BACKGROUND_TERMINALS
        self._guard(operation, talks=True)
        listing = CodexTerminalListRequest(thread_id=thread_id, cursor=cursor, limit=limit)
        self._preflight.require_experimental_api(operation, CODEX_THREAD_BACKGROUND_TERMINALS_LIST_METHOD)
        # Read the thread first, so an unknown one is refused; a thread
        # that is not loaded is not loaded for this (INV-38, EC-47).
        await self._preflight.require_thread(operation, listing.thread_id)
        # Ask Codex for one page of the thread's background terminals.
        connection = self._connection
        page = connection.raw(CODEX_THREAD_BACKGROUND_TERMINALS_LIST_METHOD, self._feature_params.terminals(listing), parse=self._feature_responses.terminals)
        return await connection.call(operation, CODEX_THREAD_BACKGROUND_TERMINALS_LIST_METHOD, page, thread_id=listing.thread_id)

    async def clean_codex_background_terminals(self, thread_id: str) -> None:
        """Stop every background terminal process a thread's commands left running; it cannot be undone, and it needs Codex's experimental API.

        It is a plain function and never a tool, so no model can reach it.
        """
        # Check the host and the thread id, then refuse at once on a
        # host without Codex's experimental API (first-class INV-4).
        operation = CodexHostOperation.CLEAN_CODEX_BACKGROUND_TERMINALS
        self._guard(operation, talks=True)
        ref = CodexThreadRef(operation=operation, thread_id=thread_id)
        self._preflight.require_experimental_api(operation, CODEX_THREAD_BACKGROUND_TERMINALS_CLEAN_METHOD)
        # Read the thread first, so an unknown one is refused before
        # any terminal is stopped (INV-38).
        await self._preflight.require_thread(operation, ref.thread_id)
        # Ask Codex to stop every background terminal of the thread.
        connection = self._connection
        clean = connection.raw(CODEX_THREAD_BACKGROUND_TERMINALS_CLEAN_METHOD, self._params.thread_params(ref.thread_id), parse=self._feature_responses.empty)
        await connection.call(operation, CODEX_THREAD_BACKGROUND_TERMINALS_CLEAN_METHOD, clean, thread_id=ref.thread_id)

    async def search_codex_thread_content(self, query: str, archived: bool = False, cursor: str = "", limit: int | None = None) -> CodexThreadSearchPage:
        """One page of the account's threads whose content matches query, with a snippet each; it needs Codex's experimental API.

        Every top-level thread source is searched, so threads this host
        created are found. Sub-agent threads are not; list them with
        list_codex_child_threads.
        """
        # Check the host and the search arguments, then refuse at once
        # on a host without Codex's experimental API (INV-4).
        operation = CodexHostOperation.SEARCH_CODEX_THREAD_CONTENT
        self._guard(operation, talks=True)
        search = CodexThreadSearchRequest(query=query, archived=archived, cursor=cursor, limit=limit)
        self._preflight.require_experimental_api(operation, CODEX_THREAD_SEARCH_METHOD)
        # Search every top-level thread source, so threads this host
        # created are found, and return one page of hits (INV-39).
        connection = self._connection
        page = connection.raw(CODEX_THREAD_SEARCH_METHOD, self._feature_params.search(search), parse=self._feature_responses.search)
        return await connection.call(operation, CODEX_THREAD_SEARCH_METHOD, page)

    async def list_codex_child_threads(self, thread_id: str, descendants: bool = False, cursor: str = "", limit: int | None = None) -> CodexThreadPage:
        """One page of a thread's child threads, or of every descendant with descendants=True; it needs Codex's experimental API.

        Sub-agent children are listed too. A child whose source kind is
        newer than CodexThreadSourceKind is not listed.
        """
        operation = CodexHostOperation.LIST_CODEX_CHILD_THREADS
        self._guard(operation, talks=True)
        listing = CodexChildThreadsRequest(thread_id=thread_id, descendants=descendants, cursor=cursor, limit=limit)
        # thread/list itself is stable; only the parent or ancestor
        # filter it carries here is experimental, so a host without
        # that API is refused naming the filter (first-class D-24).
        self._preflight.require_experimental_api(operation, self._feature_params.child_filter_key(listing))
        # The parent must exist; then list its children of every source
        # kind (first-class INV-40).
        await self._preflight.require_thread(operation, listing.thread_id)
        page_params = self._params.thread_list("", "", False, (), CodexThreadSortKey.PROVIDER_DEFAULT, CodexSortDirection.PROVIDER_DEFAULT, listing.cursor, listing.limit)
        connection = self._connection
        page = await connection.call(operation, CODEX_THREAD_LIST_METHOD, connection.client.thread_list, self._feature_params.child_threads(page_params, listing), thread_id=listing.thread_id)
        return self._responses.page(page)

    @staticmethod
    def _worktree_failure(outcome: CliOutcome, bound: float) -> tuple[str, str, str] | None:
        # The message, likely cause and next step of a git run that
        # failed, or None for a clean exit: git missing, the bound
        # reached, or a nonzero exit with git's first stderr line, cut
        # to the cap (first-class INV-29, EC-34 to EC-36).
        if outcome.launch_failure is not None:
            return CODEX_HOST_WORKTREE_GIT_MISSING_MESSAGE, CODEX_HOST_WORKTREE_GIT_MISSING_CAUSE, CODEX_HOST_WORKTREE_GIT_MISSING_NEXT_STEP
        if outcome.timed_out:
            return CODEX_HOST_WORKTREE_TIMED_OUT_MESSAGE.format(seconds=bound), CODEX_HOST_WORKTREE_TIMED_OUT_CAUSE, CODEX_HOST_WORKTREE_TIMED_OUT_NEXT_STEP
        if outcome.exit_code != 0:
            detail = next(iter(outcome.stderr.splitlines()), "")[:CODEX_HOST_WORKTREE_DETAIL_MAX_CHARS]
            return CODEX_HOST_WORKTREE_FAILED_MESSAGE.format(exit_code=outcome.exit_code, detail=detail), CODEX_HOST_WORKTREE_FAILED_CAUSE, CODEX_HOST_WORKTREE_FAILED_NEXT_STEP
        return None


__all__ = ["CodexThreadMethods"]
