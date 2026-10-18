"""FILE: vidbyte/harnesses/native/compose/workspace.py

PURPOSE: Holds the two workspace context managers and the read-only backstop: DiffCapture snapshots the whole repository when its block starts and ends and keeps the change between them as .diff, and DisposableWorktree adds a detached worktree filled from a snapshot, yields the folder that matches the workspace inside it, and always removes it; DisposableWorktree.backstop fails a read-only phase that changed the workspace.
ROLE IN CODEBASE: capture_diff and in_worktree are bound as public names in vidbyte/harnesses/native/compose/__init__.py. It runs git through ComposeGit (git.py) and waits for its git steps with ComposeCalls.settle (calls.py). verify.py, ensemble.py and selection.py run their opencode and Muse readers inside a DisposableWorktree made from a tree they already snapshotted, and verify.py and ensemble.py end each read-only phase with DisposableWorktree.backstop.
ARCHITECTURE NOTE: Both managers check the workspace when they are built, the way the nine thread functions do (an absolute existing folder, stored resolved), and start no git process until their block is entered (spec §9.2). All git work goes through ComposeGit (git.py), so every failure is a ThreadComposeError. A reader's worktree is built from a tree id the composite took, with a verifier's index set to the before-writer tree so git inside the worktree shows the writer's change (D-20, INV-9). The add and every removal run as tasks of their own that ComposeCalls.settle waits for through any number of cancels, so git never stops half-way through registering or unregistering a worktree, and the cancel goes on once git is done; each git step stays bounded by COMPOSE_GIT_TIMEOUT_SECONDS (EC-17, INV-30).
FUNCTION INVENTORY: DiffCapture.capture_diff builds the manager; __aenter__ takes the before-snapshot and __aexit__ the after-snapshot and the diff. DisposableWorktree.in_worktree builds the manager for a caller and from_tree for a reader; backstop compares a read-only phase's snapshots; __aenter__ makes the folder, adds, fills and re-indexes the worktree and makes the matching folder, and removes the worktree again when any of that fails; __aexit__ removes it; _prepared, _settled and _matching are leaves.
COMMON MODIFICATION PATTERNS: A new kind of reader workspace is another DisposableWorktree constructor that hands __aenter__ what to fill the worktree from. A new use of a diff goes through DiffCapture or through ComposeGit.snapshot and ComposeGit.diff directly.
WHAT NOT TO DO IN THIS FILE: 1. Do not run git here; call ComposeGit. 2. Do not let a removal failure hide the block's own exception. 3. Do not take a diff after a block that raised; .diff stays None. 4. Do not leave a worktree behind when entering fails half-way.
KNOWN EDGE CASES: A workspace folder that no snapshot holds (empty, or holding only ignored files) is created inside the worktree after the fill (EC-74). A repository with no commit allows capture_diff but refuses in_worktree with WORKTREE_FAILED (EC-5). A cancel that lands during the add or a removal, once or many times, waits for that git step, then propagates; a git step past its time bound is stopped all the same. The backstop cannot tell who changed the files, so an edit by another process during a read-only phase is reported too (EC-11).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_workspace.py, tests/features/harness_compose/test_harness_compose_git.py, tests/features/harness_compose/test_harness_compose_verify.py
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable
from pathlib import Path
from types import TracebackType
from typing import Self

from vidbyte.harnesses.native.compose.calls import ComposeCalls
from vidbyte.harnesses.native.compose.git import ComposeFailures, ComposeGit
from vidbyte.lib.constants import native_compose
from vidbyte.lib.dataclasses.native_compose import WorkspaceDiff
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_compose import ThreadComposeProblem
from vidbyte.lib.errors import ThreadComposeError


class DiffCapture:
    """An async context manager whose .diff is the change its block made to the whole repository, new files included (spec INV-7, INV-8)."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.diff: WorkspaceDiff | None = None
        self._git: ComposeGit | None = None
        self._before: str | None = None

    @staticmethod
    def capture_diff(workspace: str | Path) -> DiffCapture:
        """A manager that diffs the repository holding workspace across its block; workspace must be an absolute existing folder."""
        path = RecordFieldConverter.to_path(workspace, native_compose.COMPOSE_WORKSPACE_ARGUMENT)
        RecordFieldValidator.require_directory(path, native_compose.COMPOSE_WORKSPACE_ARGUMENT)
        return DiffCapture(path.resolve())

    async def __aenter__(self) -> Self:
        """Find git and the repository, then snapshot the working tree before the block runs."""
        git = ComposeGit.locate(self.workspace, ())
        await git.toplevel()
        await git.has_commit()
        self._before = await git.snapshot()
        self._git = git
        return self

    async def __aexit__(self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None) -> None:
        """After a block that ended normally, snapshot again and keep the diff; after one that raised, keep none and let its exception go on."""
        if error is not None or self._git is None or self._before is None:
            return
        after = await self._git.snapshot()
        self.diff = await self._git.diff(self._before, after)


class DisposableWorktree:
    """An async context manager that yields the workspace's folder inside a detached worktree filled from a snapshot, and always removes the worktree (spec INV-9)."""

    def __init__(self, workspace: Path, *, git: ComposeGit | None = None, tree: str | None = None, index: str | None = None) -> None:
        # in_worktree leaves git and tree empty, so entering snapshots
        # the workspace as it is; a reader's worktree gets both.
        self.workspace = workspace
        self._git = git
        self._tree = tree
        self._index = index
        self._folder: Path | None = None

    @staticmethod
    def in_worktree(workspace: str | Path) -> DisposableWorktree:
        """A manager that yields a disposable copy of workspace's folder, holding its committed, edited and untracked files; workspace must be an absolute existing folder."""
        path = RecordFieldConverter.to_path(workspace, native_compose.COMPOSE_WORKSPACE_ARGUMENT)
        RecordFieldValidator.require_directory(path, native_compose.COMPOSE_WORKSPACE_ARGUMENT)
        return DisposableWorktree(path.resolve())

    @staticmethod
    def from_tree(git: ComposeGit, tree: str, index: str | None = None) -> DisposableWorktree:
        """A reader's worktree filled from tree, a snapshot the composite took; with index, its index is set to that tree (a verifier's view of the writer's change)."""
        return DisposableWorktree(git.workspace, git=git, tree=tree, index=index)

    @staticmethod
    async def backstop(git: ComposeGit, before: str, result: object) -> None:
        """Raise READER_CHANGED_WORKSPACE, carrying result and the change, when the working tree no longer matches before, the snapshot taken when a read-only phase began (spec INV-11)."""
        # @intent read-only-phases-leave-the-workspace-as-they-found-it
        # Readers are kept from writing by mechanism, Grok's permission
        # mode and these worktrees; this comparison, made once every
        # reader worktree is gone, catches whatever got past them.
        # Compose reports the change and never restores the workspace.
        after = await git.snapshot()
        if after == before:
            return
        changed = await git.diff(before, after)
        raise ComposeFailures.error(ThreadComposeProblem.READER_CHANGED_WORKSPACE, git.workspace, ComposeFailures.changed(changed.files), git.keys, diff=changed, result=result)

    async def __aenter__(self) -> Path:
        """Add the worktree, fill it, set its index when asked, and yield the workspace's folder inside it."""
        # A caller's worktree finds git, the repository and its commit
        # first, and fills the worktree from a snapshot taken now.
        git = await self._prepared()
        tree = self._tree if self._tree is not None else await git.snapshot()

        # Make the worktree's folder, add the detached worktree there
        # and fill it from the snapshot. An add that started runs to its
        # end through any cancel: git stopped while it holds the new
        # worktree's lock leaves a registration nothing can remove.
        folder = await git.worktree_folder()
        try:
            await DisposableWorktree._settled(git.add_worktree(folder))
            await git.fill_worktree(folder, tree)

            # A verifier's index is the before-writer snapshot, so git
            # status and git diff inside the worktree show the change.
            if self._index is not None:
                await git.set_index(folder, self._index)
            matching = await self._matching(git, folder)
        except BaseException:
            # Entering failed half-way, so the worktree goes now, waited
            # for through any cancel; the first error wins over a
            # removal error.
            with contextlib.suppress(ThreadComposeError):
                await DisposableWorktree._settled(git.remove_worktree(folder))
            raise
        self._folder = folder
        return matching

    async def __aexit__(self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None) -> None:
        """Remove the worktree however the block ended; a removal failure is the error only after a normal exit."""
        if self._git is None or self._folder is None:
            return
        try:
            # The removal is waited for through any cancel, so git never
            # stops half-way through unregistering the worktree; a
            # cancel that lands meanwhile goes on once it is done.
            await DisposableWorktree._settled(self._git.remove_worktree(self._folder))
        except ThreadComposeError:
            # After a block that raised, its own exception wins.
            if error is None:
                raise

    async def _prepared(self) -> ComposeGit:
        # The git a reader's worktree shares with its composite, or for
        # in_worktree a new one that has checked the repository and its
        # commit, which worktree add needs.
        if self._git is not None:
            return self._git
        git = ComposeGit.locate(self.workspace, ())
        await git.toplevel()
        await git.has_commit(required=True)
        self._git = git
        return git

    @staticmethod
    async def _settled(step: Awaitable[None]) -> None:
        # One git step as a task of its own, waited for through any
        # number of cancels; its own failure goes on, and so does a
        # cancel that arrived meanwhile, once the step has ended.
        task = asyncio.ensure_future(step)
        await ComposeCalls.settle((task,))
        task.result()

    async def _matching(self, git: ComposeGit, folder: Path) -> Path:
        # The workspace's own folder inside the worktree, made when no
        # snapshot holds it because it is empty or ignored (EC-74).
        matching = folder / self.workspace.relative_to(git.root)
        try:
            await asyncio.to_thread(matching.mkdir, parents=True, exist_ok=True)
        except OSError as error:
            observation = native_compose.THREAD_COMPOSE_FOLDER_OBSERVATION.format(folder=matching, error_type=type(error).__name__)
            raise ComposeFailures.error(ThreadComposeProblem.WORKTREE_FAILED, self.workspace, observation, git.keys) from error
        return matching


__all__ = ["DiffCapture", "DisposableWorktree"]
