"""FILE: vidbyte/harnesses/native/compose/git.py

PURPOSE: Runs the closed set of git commands compose needs for one workspace and turns every failure into a ThreadComposeError: ComposeGit finds git and the repository, snapshots the whole working tree into a temporary index, diffs two snapshots, and adds, fills, re-indexes and removes disposable worktrees; ComposeFailures builds each ThreadComposeError with its message, git's text and the texts for its problem.
ROLE IN CODEBASE: Used by DiffCapture and DisposableWorktree (workspace.py) and by the composites that need git (chain.py for a template with {diff}, verify.py, ensemble.py and selection.py); ComposeFailures also builds the read-only backstop error the composites raise.
ARCHITECTURE NOTE: Every git child goes through CliRunner with the program found by CliRunner.find_program, the no-optional-locks flag and the two -c settings first, the 15 repository-location variables removed, no standard input, and the COMPOSE_GIT_TIMEOUT_SECONDS and COMPOSE_GIT_MAX_OUTPUT_BYTES bounds (spec INV-26, §9.2, §9.3). No argument holds a caret, a caller value or model text: the only operands are HEAD, tree ids and temporary folder paths. A snapshot writes only to a fresh temporary index named by GIT_INDEX_FILE and to the object store, so the working tree, the real index, HEAD and every ref stay as they are (INV-7). ComposeFailures replaces every bound key in git's text as exact text, through SecretText.replace_all, before HarnessRedactor and the tail cap, so a cap never cuts a key in half, and writes the message in the INV-6 order: the problem and its summary, the workspace, what compose observed, git's text, the likely cause and the next step.
FUNCTION INVENTORY: ComposeGit.locate finds git; toplevel and has_commit find the repository root and whether HEAD names a commit, which has_commit(required=True) demands for a worktree; snapshot is the narrated main function of a snapshot; diff compares two trees; worktree_folder, add_worktree, fill_worktree, set_index and remove_worktree manage a reader's worktree; _run starts one git child; _failure, _folder and _delete are leaves. ComposeFailures.error builds one ThreadComposeError; changed names the files a read-only phase changed.
COMMON MODIFICATION PATTERNS: A new git command is a §9.2 row first: its subcommand word in vidbyte/lib/constants/native_compose.py, its flags as GitFlag members, and one method here that goes through _run. A new failure kind is a ThreadComposeProblem member with its own summary, likely cause and next step.
WHAT NOT TO DO IN THIS FILE: 1. Do not run a git command that changes the working tree, the real index, HEAD or a ref; snapshots use a temporary index and worktrees are detached. 2. Do not pass --ignore-errors to add; a file git cannot read must fail the snapshot (EC-73). 3. Do not put a caret in an argument; cmd.exe strips it when git is a batch launcher (D-24). 4. Do not let an OSError escape; folder failures are ThreadComposeError too. 5. Do not clean up a half-made worktree here; DisposableWorktree.__aenter__ removes it, waiting for a started add to end first (EC-17).
KNOWN EDGE CASES: rev-parse --verify --quiet HEAD exits 1 in a repository with no commit, so snapshots skip read-tree HEAD there, while a worktree needs HEAD and is refused as WORKTREE_FAILED (EC-5). An add that exits non-zero gets the two add texts, and one that passes its time bound keeps the generic texts (EC-73, EC-9). A worktree whose removal fails is deleted from disk anyway, and the error names its folder; the registration git keeps is cleared by git worktree prune (EC-16). git prints the repository root with forward slashes on win32, so it is resolved before use.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_git.py, tests/features/harness_compose/test_harness_compose_workspace.py, tests/features/harness_compose/test_harness_compose_keys.py
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path

from vidbyte.harnesses.serialization import HarnessRedactor
from vidbyte.lib.constants import native_compose, native_threads
from vidbyte.lib.dataclasses.native_compose import WorkspaceDiff
from vidbyte.lib.dataclasses.process import CliInvocation, CliOption, CliOutcome
from vidbyte.lib.enums.native_compose import GitFlag, ThreadComposeProblem
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.errors import ThreadComposeError
from vidbyte.lib.process.argv import CliArgv
from vidbyte.lib.process.runner import CliRunner
from vidbyte.lib.util.secret_text import SecretText


class ComposeFailures:
    """Builds every ThreadComposeError compose raises, with the message in the INV-6 order and no bound key anywhere in it."""

    @staticmethod
    def error(problem: ThreadComposeProblem, workspace: Path, observation: str, keys: Sequence[str], *, git_text: str = "", add: bool = False, diff: WorkspaceDiff | None = None, result: object | None = None) -> ThreadComposeError:
        """The ThreadComposeError for problem in workspace, with what compose observed and git's own text; add selects the texts for an add that exited non-zero."""
        # @intent compose-errors-never-show-a-key
        # A folder name or git's text can hold a key a writer saved, so
        # every bound key is replaced as exact text on the whole text
        # first; then the shared redactor scrubs credential assignments
        # and the tail is kept, because git prints its final error last.
        place = SecretText.replace_all(str(workspace), keys, native_compose.COMPOSE_REDACTED_KEY)
        printed = SecretText.replace_all(git_text.strip(), keys, native_compose.COMPOSE_REDACTED_KEY)
        git_message = str(HarnessRedactor().redact(printed))[-native_compose.COMPOSE_GIT_MESSAGE_MAX_CHARS :] or None
        cause = native_compose.THREAD_COMPOSE_ADD_LIKELY_CAUSE if add else native_compose.THREAD_COMPOSE_LIKELY_CAUSES[problem]
        step = native_compose.THREAD_COMPOSE_ADD_NEXT_STEP if add else native_compose.THREAD_COMPOSE_NEXT_STEPS[problem]
        sentences = (
            native_compose.THREAD_COMPOSE_MESSAGE_HEAD.format(problem=problem.value),
            native_compose.THREAD_COMPOSE_SUMMARIES[problem],
            native_compose.THREAD_COMPOSE_WORKSPACE_SENTENCE.format(workspace=place),
            SecretText.replace_all(observation, keys, native_compose.COMPOSE_REDACTED_KEY),
            native_compose.THREAD_COMPOSE_GIT_TEXT_SENTENCE.format(git_message=git_message) if git_message else "",
            native_compose.THREAD_COMPOSE_LIKELY_CAUSE_SENTENCE.format(likely_cause=cause),
            native_compose.THREAD_COMPOSE_NEXT_STEP_SENTENCE.format(next_step=step),
        )
        message = native_threads.NATIVE_SENTENCE_SEPARATOR.join(sentence for sentence in sentences if sentence)
        return ThreadComposeError(message, problem=problem, workspace=place, likely_cause=cause, next_step=step, git_message=git_message, diff=diff, result=result)

    @staticmethod
    def changed(files: Sequence[str]) -> str:
        """The observation for a read-only phase that changed files: the first COMPOSE_MESSAGE_MAX_FILES names and how many more."""
        shown = native_threads.NATIVE_LISTING_SEPARATOR.join(files[: native_compose.COMPOSE_MESSAGE_MAX_FILES])
        more = len(files) - native_compose.COMPOSE_MESSAGE_MAX_FILES
        listing = native_compose.THREAD_COMPOSE_MORE_FILES.format(names=shown, count=more) if more > 0 else shown
        return native_compose.THREAD_COMPOSE_CHANGED_FILES_OBSERVATION.format(files=listing)


class ComposeGit:
    """The git commands of spec §9.2 for one workspace: each a bounded child with a clean environment, and each failure a ThreadComposeError (INV-6, INV-26)."""

    def __init__(self, program: str, workspace: Path, keys: Sequence[str]) -> None:
        # toplevel fills root and has_commit fills commit; snapshots and
        # worktrees run from root and need to know whether HEAD exists.
        self.program = program
        self.workspace = workspace
        self.keys = tuple(keys)
        self.root = workspace
        self.commit = False

    @staticmethod
    def locate(workspace: Path, keys: Sequence[str]) -> ComposeGit:
        """A ComposeGit for workspace with the git program found in the PATH folders; GIT_UNAVAILABLE when there is none (EC-2)."""
        program = CliRunner.find_program(native_compose.COMPOSE_GIT_PROGRAM)
        if program is None:
            raise ComposeFailures.error(ThreadComposeProblem.GIT_UNAVAILABLE, workspace, native_compose.THREAD_COMPOSE_MISSING_OBSERVATION.format(program=native_compose.COMPOSE_GIT_PROGRAM), keys)
        return ComposeGit(program, workspace, keys)

    async def toplevel(self) -> Path:
        """The root of the repository that holds the workspace, kept as root; NOT_A_GIT_REPOSITORY when git finds none (EC-1, EC-60)."""
        outcome = await self._run((native_compose.COMPOSE_GIT_REV_PARSE,), (CliOption(GitFlag.SHOW_TOPLEVEL),), cwd=self.workspace, problem=ThreadComposeProblem.GIT_FAILED)
        if outcome.exit_code != 0:
            raise self._failure(ThreadComposeProblem.NOT_A_GIT_REPOSITORY, (native_compose.COMPOSE_GIT_REV_PARSE,), outcome)
        self.root = Path(outcome.stdout.strip()).resolve()
        return self.root

    async def has_commit(self, *, required: bool = False) -> bool:
        """Whether HEAD names a commit, kept as commit. A repository with no commit yet answers False, or with required is WORKTREE_FAILED, because worktree add needs HEAD (EC-5)."""
        outcome = await self._run((native_compose.COMPOSE_GIT_REV_PARSE,), (CliOption(GitFlag.VERIFY), CliOption(GitFlag.QUIET)), (native_compose.COMPOSE_GIT_HEAD,), cwd=self.workspace, problem=ThreadComposeProblem.GIT_FAILED)
        if outcome.exit_code not in (0, native_compose.COMPOSE_GIT_UNBORN_EXIT_CODE):
            raise self._failure(ThreadComposeProblem.GIT_FAILED, (native_compose.COMPOSE_GIT_REV_PARSE,), outcome)
        self.commit = outcome.exit_code == 0
        if required and not self.commit:
            raise self._failure(ThreadComposeProblem.WORKTREE_FAILED, (native_compose.COMPOSE_GIT_REV_PARSE,), outcome)
        return self.commit

    async def snapshot(self) -> str:
        """The tree id of the whole working tree, tracked and untracked files alike, built in a temporary index (INV-7)."""
        # A fresh index in a temporary folder takes every change, so the
        # real index is never read or written.
        folder = await self._folder(native_compose.COMPOSE_INDEX_PREFIX, ThreadComposeProblem.GIT_FAILED)
        index = folder / native_compose.COMPOSE_GIT_INDEX_FILE_NAME
        try:
            # Start from the commit's tree when there is one, so a
            # tracked file that is also ignored stays in the snapshot.
            if self.commit:
                outcome = await self._run((native_compose.COMPOSE_GIT_READ_TREE,), operands=(native_compose.COMPOSE_GIT_HEAD,), cwd=self.root, problem=ThreadComposeProblem.GIT_FAILED, index=index)
                if outcome.exit_code != 0:
                    raise self._failure(ThreadComposeProblem.GIT_FAILED, (native_compose.COMPOSE_GIT_READ_TREE,), outcome)

            # Add every file git does not ignore. An add that exits
            # non-zero names an untracked repository with no commit or
            # an unreadable file, so it gets the texts for both causes.
            outcome = await self._run((native_compose.COMPOSE_GIT_ADD,), (CliOption(GitFlag.ALL),), cwd=self.root, problem=ThreadComposeProblem.GIT_FAILED, index=index)
            if outcome.exit_code != 0:
                raise self._failure(ThreadComposeProblem.GIT_FAILED, (native_compose.COMPOSE_GIT_ADD,), outcome, add=True)

            # Write the index as a tree object and return its id.
            outcome = await self._run((native_compose.COMPOSE_GIT_WRITE_TREE,), cwd=self.root, problem=ThreadComposeProblem.GIT_FAILED, index=index)
            if outcome.exit_code != 0:
                raise self._failure(ThreadComposeProblem.GIT_FAILED, (native_compose.COMPOSE_GIT_WRITE_TREE,), outcome)
            return outcome.stdout.strip()
        finally:
            # The temporary index goes however the snapshot ends.
            await asyncio.to_thread(shutil.rmtree, folder, ignore_errors=True)

    async def diff(self, before: str, after: str) -> WorkspaceDiff:
        """What changed from tree before to tree after: the paths from the repository root and the patch text, each cut to its cap."""
        names = await self._run((native_compose.COMPOSE_GIT_DIFF,), (CliOption(GitFlag.NAME_ONLY), CliOption(GitFlag.NUL_TERMINATED), CliOption(GitFlag.NO_RENAMES)), (before, after), cwd=self.root, problem=ThreadComposeProblem.GIT_FAILED)
        if names.exit_code != 0:
            raise self._failure(ThreadComposeProblem.GIT_FAILED, (native_compose.COMPOSE_GIT_DIFF,), names)
        patch = await self._run((native_compose.COMPOSE_GIT_DIFF,), (CliOption(GitFlag.NO_COLOR), CliOption(GitFlag.NO_EXT_DIFF), CliOption(GitFlag.NO_TEXTCONV), CliOption(GitFlag.NO_RENAMES)), (before, after), cwd=self.root, problem=ThreadComposeProblem.GIT_FAILED)
        if patch.exit_code != 0:
            raise self._failure(ThreadComposeProblem.GIT_FAILED, (native_compose.COMPOSE_GIT_DIFF,), patch)
        files = tuple(name for name in names.stdout.split(native_compose.COMPOSE_NUL) if name)
        max_files, max_chars = native_compose.COMPOSE_DIFF_MAX_FILES, native_compose.COMPOSE_DIFF_MAX_CHARS
        truncated = len(files) > max_files or len(patch.stdout) > max_chars or names.stdout_truncated or patch.stdout_truncated
        return WorkspaceDiff(files=files[:max_files], text=patch.stdout[:max_chars], truncated=truncated)

    async def worktree_folder(self) -> Path:
        """A fresh temporary folder for a reader's worktree; WORKTREE_FAILED, naming the temporary folder, when none can be made."""
        return await self._folder(native_compose.COMPOSE_WORKTREE_PREFIX, ThreadComposeProblem.WORKTREE_FAILED)

    async def add_worktree(self, folder: Path) -> None:
        """Register a new detached worktree at HEAD in folder, its files not yet written; WORKTREE_FAILED when git refuses (INV-9)."""
        outcome = await self._run((native_compose.COMPOSE_GIT_WORKTREE, native_compose.COMPOSE_GIT_WORKTREE_ADD), (CliOption(GitFlag.DETACH), CliOption(GitFlag.NO_CHECKOUT)), (str(folder), native_compose.COMPOSE_GIT_HEAD), cwd=self.root, problem=ThreadComposeProblem.WORKTREE_FAILED)
        if outcome.exit_code != 0:
            raise self._failure(ThreadComposeProblem.WORKTREE_FAILED, (native_compose.COMPOSE_GIT_WORKTREE, native_compose.COMPOSE_GIT_WORKTREE_ADD), outcome)

    async def fill_worktree(self, folder: Path, tree: str) -> None:
        """Write tree's files and index into the worktree in folder; WORKTREE_FAILED when git refuses."""
        outcome = await self._run((native_compose.COMPOSE_GIT_READ_TREE,), (CliOption(GitFlag.UPDATE), CliOption(GitFlag.RESET)), (tree,), cwd=folder, problem=ThreadComposeProblem.WORKTREE_FAILED)
        if outcome.exit_code != 0:
            raise self._failure(ThreadComposeProblem.WORKTREE_FAILED, (native_compose.COMPOSE_GIT_READ_TREE,), outcome)

    async def set_index(self, folder: Path, tree: str) -> None:
        """Set the worktree's index to tree and leave its files as they are, so git there shows the change from tree."""
        outcome = await self._run((native_compose.COMPOSE_GIT_READ_TREE,), operands=(tree,), cwd=folder, problem=ThreadComposeProblem.WORKTREE_FAILED)
        if outcome.exit_code != 0:
            raise self._failure(ThreadComposeProblem.WORKTREE_FAILED, (native_compose.COMPOSE_GIT_READ_TREE,), outcome)

    async def remove_worktree(self, folder: Path) -> None:
        """Unregister the worktree and delete its folder; WORKTREE_FAILED when git refuses or the folder cannot be deleted (EC-16)."""
        try:
            outcome = await self._run((native_compose.COMPOSE_GIT_WORKTREE, native_compose.COMPOSE_GIT_WORKTREE_REMOVE), (CliOption(GitFlag.FORCE),), (str(folder),), cwd=self.root, problem=ThreadComposeProblem.WORKTREE_FAILED)
        finally:
            # Whatever git left on disk goes too, however git ended.
            await self._delete(folder)
        if outcome.exit_code != 0:
            raise self._failure(ThreadComposeProblem.WORKTREE_FAILED, (native_compose.COMPOSE_GIT_WORKTREE, native_compose.COMPOSE_GIT_WORKTREE_REMOVE), outcome)

    async def _run(self, command: tuple[str, ...], options: tuple[CliOption, ...] = (), operands: tuple[str, ...] = (), *, cwd: Path, problem: ThreadComposeProblem, index: Path | None = None) -> CliOutcome:
        # One git child: the program, the no-optional-locks flag and the
        # two settings, then the subcommand; the caller's repository
        # location variables removed, and GIT_INDEX_FILE only for a
        # snapshot. A launch failure is GIT_UNAVAILABLE (EC-3) and a run
        # past the time bound is problem; the caller reads the status.
        settings = tuple(CliOption(GitFlag.CONFIG, setting) for setting in native_compose.COMPOSE_GIT_SETTINGS)
        prefix = CliArgv.build((self.program,), options=(CliOption(GitFlag.NO_OPTIONAL_LOCKS), *settings), style=CliOptionStyle.SEPARATE)
        argv = CliArgv.build(prefix, command=command, options=options, style=CliOptionStyle.SEPARATE, operands=operands)
        overlay = {} if index is None else {native_compose.COMPOSE_GIT_INDEX_VARIABLE: str(index)}
        invocation = CliInvocation(argv, overlay, native_compose.COMPOSE_GIT_TIMEOUT_SECONDS, native_compose.COMPOSE_GIT_MAX_OUTPUT_BYTES, cwd=cwd, env_remove=native_compose.COMPOSE_GIT_CLEARED_VARIABLES)
        outcome = await CliRunner().run(invocation)
        if outcome.launch_failure is not None:
            raise ComposeFailures.error(ThreadComposeProblem.GIT_UNAVAILABLE, self.workspace, native_compose.THREAD_COMPOSE_LAUNCH_OBSERVATION.format(program=self.program, failure=outcome.launch_failure.value), self.keys)
        if outcome.timed_out:
            subcommand = native_threads.NATIVE_SENTENCE_SEPARATOR.join(command)
            raise ComposeFailures.error(problem, self.workspace, native_compose.THREAD_COMPOSE_TIMEOUT_OBSERVATION.format(subcommand=subcommand, seconds=native_compose.COMPOSE_GIT_TIMEOUT_SECONDS), self.keys, git_text=outcome.stderr)
        return outcome

    def _failure(self, problem: ThreadComposeProblem, command: tuple[str, ...], outcome: CliOutcome, *, add: bool = False) -> ThreadComposeError:
        # The error for a git command that exited non-zero, quoting
        # git's own text.
        subcommand = native_threads.NATIVE_SENTENCE_SEPARATOR.join(command)
        observation = native_compose.THREAD_COMPOSE_EXIT_OBSERVATION.format(subcommand=subcommand, exit_code=outcome.exit_code)
        return ComposeFailures.error(problem, self.workspace, observation, self.keys, git_text=outcome.stderr, add=add)

    async def _folder(self, prefix: str, problem: ThreadComposeProblem) -> Path:
        # A fresh folder in the system temporary folder; failing to make
        # one is problem, naming the temporary folder.
        try:
            return Path(await asyncio.to_thread(tempfile.mkdtemp, prefix=prefix))
        except OSError as error:
            observation = native_compose.THREAD_COMPOSE_FOLDER_OBSERVATION.format(folder=tempfile.gettempdir(), error_type=type(error).__name__)
            raise ComposeFailures.error(problem, self.workspace, observation, self.keys) from error

    async def _delete(self, folder: Path) -> None:
        # Delete what is left of a worktree folder; a folder that cannot
        # be deleted is WORKTREE_FAILED, naming it.
        try:
            await asyncio.to_thread(shutil.rmtree, folder)
        except FileNotFoundError:
            return
        except OSError as error:
            observation = native_compose.THREAD_COMPOSE_FOLDER_OBSERVATION.format(folder=folder, error_type=type(error).__name__)
            raise ComposeFailures.error(ThreadComposeProblem.WORKTREE_FAILED, self.workspace, observation, self.keys) from error


__all__ = ["ComposeFailures", "ComposeGit"]
