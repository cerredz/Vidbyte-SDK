"""FILE: tests/features/codex_host/test_codex_host_worktree.py

PURPOSE: Proves create_codex_worktree and the canonical GitWorktrees helper with the real git on temporary repositories: one git worktree add under Path.home()/.vidbyte/codex-worktrees on a new branch from HEAD or a base ref, a folder name built from the repository name and the branch, an existing folder refused before git runs, a worktree root that cannot be prepared refused by the exception's type alone, git missing, a nonzero exit with git's first stderr line cut to the cap, a hang stopped at the bound, the branch rule refused before git, logs that carry no path, branch or git output, and never a Codex request.
ROLE IN CODEBASE: Worktree layer of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md AC-24, INV-8, INV-9, INV-2, INV-29, FR-13, FR-35, D-19, EC-34 to EC-36, EC-63, T-5, NFR-7). The host class needs the optional openai-codex extra, so CI skips it; the GitWorktrees class needs only git and runs everywhere.
ARCHITECTURE NOTE: Spec section 13 makes git a real seam: CliRunner and CliArgv stay real and only Path.home is patched. The repositories are built with subprocess git under a private global config (GIT_CONFIG_GLOBAL to an empty file, GIT_CONFIG_NOSYSTEM, GIT_CEILING_DIRECTORIES at the temporary root), so a developer's own git settings, hooks or a parent repository cannot change an answer. Expected git messages come from an oracle: the test runs the same git worktree add argv the spec gives and reads its exit code and first stderr line, so no git wording is hard-coded. A post-checkout hook is the child that observes git's environment or hangs; git worktree add runs it after the checkout.
COMMON MODIFICATION PATTERNS: Add a git failure as one row of the EC-34 table with the setup that causes it; the oracle supplies the expected text. Keep repository and branch names to safe characters unless the test is about the folder name.
KNOWN EDGE CASES: A hook's script is written with LF line endings, because Git for Windows runs it with sh. The timeout test patches vidbyte.harnesses.native.codex.thread_methods.CODEX_HOST_WORKTREE_TIMEOUT_SECONDS to 1.5 seconds and its hook sleeps a bounded 20 seconds, so the test waits for the bound by design. For a branch that already exists, git 2.49 prints "Preparing worktree (new branch ...)" before the fatal line, so the spec's first stderr line is that progress line (reported in test-plan.md). git worktree add creates the branch before it finds the target folder taken, so a missing branch proves git never ran.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 6.1 (INV-29), 6.3, 9.1 (GitWorktreeSpec), 9.2 and 13; tests/features/harness_threads/test_harness_threads_runner.py.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_worktree.py
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from tests.features.codex_host.codex_host_feature_support import (
    BRANCH_CANARY,
    GIT_STDERR_CANARY,
    PATH_CANARY,
    WORKTREE_EXISTS_CAUSE,
    WORKTREE_EXISTS_MESSAGE,
    WORKTREE_EXISTS_NEXT_STEP,
    WORKTREE_FAILED_CAUSE,
    WORKTREE_FAILED_MESSAGE,
    WORKTREE_FAILED_NEXT_STEP,
    WORKTREE_GIT_MISSING_CAUSE,
    WORKTREE_GIT_MISSING_MESSAGE,
    WORKTREE_GIT_MISSING_NEXT_STEP,
    WORKTREE_REF_MESSAGE,
    WORKTREE_REPOSITORY_MESSAGE,
    WORKTREE_ROOT_CAUSE,
    WORKTREE_ROOT_MESSAGE,
    WORKTREE_ROOT_NEXT_STEP,
    WORKTREE_TIMED_OUT_CAUSE,
    WORKTREE_TIMED_OUT_MESSAGE,
    WORKTREE_TIMED_OUT_NEXT_STEP,
    assert_packet,
)
from tests.features.codex_host.codex_host_support import HOST_LOGGER, WAIT_SECONDS, FeatureHostCase, assert_no_canary, log_events, log_fields, requires_sdk

OPERATION = "create_codex_worktree"
INVALID = "configuration.invalid_argument"
ROOT_PARTS = (".vidbyte", "codex-worktrees")
DETAIL_MAX_CHARS = 500
REF_MAX_CHARS = 200
GIT_SECONDS = 60.0
TIMEOUT_SECONDS = 1.5
HOOK_HANG_SECONDS = 20
THREAD_METHODS_MODULE = "vidbyte.harnesses.native.codex.thread_methods"
FAILED_FIELDS = {"operation", "exit_code", "timed_out", "launch_failure", "duration_ms"}


class _GitSandbox:
    """A temporary root with a private git configuration, plus the git steps the worktree tests read back."""

    def start_git_sandbox(self) -> None:
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        config = self.root / "empty.gitconfig"
        config.write_text("", encoding="utf-8")
        isolated = {
            "GIT_CONFIG_GLOBAL": str(config),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CEILING_DIRECTORIES": str(self.root),
            "GIT_AUTHOR_NAME": "Vidbyte Tests",
            "GIT_AUTHOR_EMAIL": "tests@example.invalid",
            "GIT_COMMITTER_NAME": "Vidbyte Tests",
            "GIT_COMMITTER_EMAIL": "tests@example.invalid",
        }
        environment = mock.patch.dict(os.environ, isolated)
        environment.start()
        self.addCleanup(environment.stop)

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=GIT_SECONDS, check=False)

    def git_ok(self, *args: str) -> str:
        result = self.git(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def make_repo(self, name: str) -> Path:
        """A repository with two commits; the tag release-1 marks the first, so it differs from HEAD."""
        repo = self.root / name
        repo.mkdir()
        self.git_ok("-C", str(repo), "init", "-q")
        for index, text in enumerate(("one\n", "two\n")):
            (repo / "README.md").write_text(text, encoding="utf-8")
            self.git_ok("-C", str(repo), "add", "README.md")
            self.git_ok("-C", str(repo), "commit", "-q", "-m", f"commit {text.strip()}")
            if index == 0:
                self.git_ok("-C", str(repo), "tag", "release-1")
        return repo

    def head(self, folder: Path, ref: str = "HEAD") -> str:
        return self.git_ok("-C", str(folder), "rev-parse", ref)

    def branch_of(self, folder: Path) -> str:
        return self.git_ok("-C", str(folder), "rev-parse", "--abbrev-ref", "HEAD")

    def branches(self, repo: Path) -> list[str]:
        return self.git_ok("-C", str(repo), "branch", "--list", "--format=%(refname:short)").splitlines()

    def worktree_paths(self, repo: Path) -> list[Path]:
        lines = self.git_ok("-C", str(repo), "worktree", "list", "--porcelain").splitlines()
        return [Path(line[len("worktree ") :]) for line in lines if line.startswith("worktree ")]

    def hook(self, repo: Path, body: str) -> None:
        """A post-checkout hook, which git worktree add runs after its checkout."""
        hook = repo / ".git" / "hooks" / "post-checkout"
        hook.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
        hook.chmod(0o755)

    def target(self, repo: Path, folder_branch: str) -> Path:
        return self.home.joinpath(*ROOT_PARTS, f"{repo.name}-{folder_branch}")

    def oracle(self, repo: Path, branch: str, path: Path, base_ref: str = "") -> tuple[int, str]:
        """Run the spec's own argv and return git's exit code and first stderr line (the EC-34 detail)."""
        result = self.git("-C", str(repo), "worktree", "add", "-b", branch, "--", str(path), base_ref or "HEAD")
        self.assertNotEqual(result.returncode, 0, "the oracle expected a failing git run")
        return result.returncode, result.stderr.splitlines()[0]

    def without_git(self) -> Any:
        """Patch PATH to an empty folder for the block, so no git program can be found."""
        empty = self.root / "empty-path"
        empty.mkdir(exist_ok=True)
        return mock.patch.dict(os.environ, {"PATH": str(empty)})


@requires_sdk
class CodexWorktreeHostTests(_GitSandbox, FeatureHostCase):
    """AC-24, INV-29, EC-34, EC-35 and T-5: create_codex_worktree on a real repository, with no Codex request."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.start_git_sandbox()
        home = mock.patch("pathlib.Path.home", return_value=self.home)
        home.start()
        self.addCleanup(home.stop)

    async def worktree_error(self, awaitable: Any) -> Any:
        error = await self.codex_error(awaitable, INVALID)
        self.assertEqual(error.thread_id, "")
        return error

    async def test_a_worktree_is_made_under_the_vidbyte_root_on_a_new_branch_from_head_and_codex_hears_nothing(self) -> None:
        # AC-24 first call, INV-29: <home>/.vidbyte/codex-worktrees/<repo name>-feat-x, the root made when missing.
        repo = self.make_repo("notes")
        host = await self.opened(linux=False)
        self.assertFalse((self.home / ".vidbyte").exists())
        worktree = await self.call(host.create_codex_worktree(repo, "feat/x"))
        expected = self.target(repo, "feat-x")
        self.assertIsInstance(worktree.path, str)
        self.assertEqual(Path(worktree.path), expected)
        self.assertEqual((worktree.branch, worktree.base_ref), ("feat/x", "HEAD"))
        self.assertEqual(Path(worktree.repository), repo)
        self.assertEqual(self.branch_of(expected), "feat/x")
        self.assertEqual(self.head(expected), self.head(repo))
        self.assertIn(expected, self.worktree_paths(repo))
        self.assertEqual(self.sent_methods(), [])

    async def test_a_base_ref_is_given_to_git_and_unsafe_branch_characters_become_dashes_in_the_folder_name(self) -> None:
        # INV-29: <base_ref or HEAD>; every character outside [A-Za-z0-9._-] in the branch becomes "-"; a str repository is taken.
        repo = self.make_repo("notes")
        host = await self.opened(linux=False)
        worktree = await self.call(host.create_codex_worktree(str(repo), "team/fix.v2_b", base_ref="release-1"))
        expected = self.target(repo, "team-fix.v2_b")
        self.assertEqual(Path(worktree.path), expected)
        self.assertEqual((worktree.branch, worktree.base_ref), ("team/fix.v2_b", "release-1"))
        self.assertEqual(self.head(expected), self.head(repo, "release-1"))
        self.assertNotEqual(self.head(expected), self.head(repo))
        self.assertEqual(self.sent_methods(), [])

    async def test_an_existing_target_folder_is_refused_before_git_runs(self) -> None:
        # AC-24 second call: the same repository and branch, a branch that maps to the same folder, and a folder made by hand.
        repo = self.make_repo("notes")
        host = await self.opened(linux=False)
        await self.call(host.create_codex_worktree(repo, "feat/x"))
        self.target(repo, "feat-y").mkdir(parents=True)
        worktrees = self.worktree_paths(repo)
        for branch in ("feat/x", "feat-x", "feat/y"):
            with self.subTest(branch=branch):
                error = await self.worktree_error(host.create_codex_worktree(repo, branch))
                assert_packet(self, error, operation=OPERATION, code=INVALID, message=WORKTREE_EXISTS_MESSAGE, cause=WORKTREE_EXISTS_CAUSE, next_step=WORKTREE_EXISTS_NEXT_STEP)
        # git worktree add makes its branch before it finds the folder taken, so these branches prove git never ran.
        self.assertNotIn("feat-x", self.branches(repo))
        self.assertNotIn("feat/y", self.branches(repo))
        self.assertEqual(self.worktree_paths(repo), worktrees)
        self.assertEqual(self.sent_methods(), [])

    async def test_without_git_on_path_the_call_reports_that_git_could_not_start(self) -> None:
        # AC-24 third call: CliRunner finds no git, so the outcome is a launch failure, not an exception.
        repo = self.make_repo("notes")
        host = await self.opened(linux=False)
        with self.without_git():
            error = await self.worktree_error(host.create_codex_worktree(repo, "feat/z"))
        assert_packet(self, error, operation=OPERATION, code=INVALID, message=WORKTREE_GIT_MISSING_MESSAGE, cause=WORKTREE_GIT_MISSING_CAUSE, next_step=WORKTREE_GIT_MISSING_NEXT_STEP)
        self.assertFalse(self.target(repo, "feat-z").exists())
        self.assertNotIn("feat/z", self.branches(repo))
        self.assertEqual(self.sent_methods(), [])

    async def test_a_folder_outside_git_a_branch_that_exists_or_an_unknown_base_ref_reports_gits_exit_code_and_first_stderr_line(self) -> None:
        # EC-34: the oracle runs the same argv after the host's run and supplies the exit code and first stderr line.
        repo = self.make_repo("notes")
        plain = self.root / "plain"
        plain.mkdir()
        self.git_ok("-C", str(repo), "branch", "feat/old")
        host = await self.opened(linux=False)
        rows = (("not a work tree", plain, "feat/x", ""), ("branch exists", repo, "feat/old", ""), ("unknown base ref", repo, "feat/new", "nosuchref"))
        for label, repository, branch, base_ref in rows:
            with self.subTest(case=label):
                error = await self.worktree_error(host.create_codex_worktree(repository, branch, base_ref=base_ref))
                code, line = self.oracle(repository, branch, self.target(repository, branch.replace("/", "-")), base_ref)
                message = WORKTREE_FAILED_MESSAGE.format(exit_code=code, detail=line)
                assert_packet(self, error, operation=OPERATION, code=INVALID, message=message, cause=WORKTREE_FAILED_CAUSE, next_step=WORKTREE_FAILED_NEXT_STEP)
        self.assertEqual(self.sent_methods(), [])

    async def test_a_first_stderr_line_longer_than_the_cap_is_cut_to_500_characters_and_never_logged(self) -> None:
        # EC-34 cap and NFR-7: a bad boolean in the repository's config makes git's first stderr line about 750 characters.
        records = self.capture_logs(HOST_LOGGER)
        repo = self.make_repo("notes")
        self.git_ok("-C", str(repo), "config", "core.filemode", GIT_STDERR_CANARY + "x" * 700)
        host = await self.opened(linux=False)
        error = await self.worktree_error(host.create_codex_worktree(repo, "feat/x"))
        code, line = self.oracle(repo, "feat/x", self.target(repo, "feat-x"))
        self.assertGreater(len(line), DETAIL_MAX_CHARS)
        head = f"{OPERATION} failed with {INVALID}. " + WORKTREE_FAILED_MESSAGE.format(exit_code=code, detail="")
        tail = f" Likely cause: {WORKTREE_FAILED_CAUSE} Next step: {WORKTREE_FAILED_NEXT_STEP}"
        self.assertTrue(error.message.startswith(head), error.message[:200])
        self.assertTrue(error.message.endswith(tail), error.message[-200:])
        detail = error.message[len(head) : len(error.message) - len(tail)]
        self.assertLessEqual(len(detail), DETAIL_MAX_CHARS)
        self.assertEqual(detail[:400], line[:400])
        self.assertEqual(len(log_events(records, "codex_host_worktree_failed")), 1)
        assert_no_canary(self, [record.getMessage() for record in records], (GIT_STDERR_CANARY,))

    async def test_a_git_run_that_outlives_the_bound_is_stopped_and_reported_as_timed_out(self) -> None:
        # EC-36: the bound is read at call time from thread_methods (section 13); a half-made folder may remain.
        records = self.capture_logs(HOST_LOGGER)
        bound = mock.patch(f"{THREAD_METHODS_MODULE}.CODEX_HOST_WORKTREE_TIMEOUT_SECONDS", TIMEOUT_SECONDS)
        bound.start()
        self.addCleanup(bound.stop)
        repo = self.make_repo("notes")
        self.hook(repo, f"sleep {HOOK_HANG_SECONDS}\n")
        host = await self.opened(linux=False)
        error = await self.worktree_error(host.create_codex_worktree(repo, "feat/slow"))
        message = WORKTREE_TIMED_OUT_MESSAGE.format(seconds=TIMEOUT_SECONDS)
        assert_packet(self, error, operation=OPERATION, code=INVALID, message=message, cause=WORKTREE_TIMED_OUT_CAUSE, next_step=WORKTREE_TIMED_OUT_NEXT_STEP)
        failed = [log_fields(record) for record in log_events(records, "codex_host_worktree_failed")]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["timed_out"].casefold(), "true")

    async def test_a_bad_branch_base_ref_or_repository_is_refused_before_git_runs_or_the_root_is_made(self) -> None:
        # EC-35, T-5: the record refuses option injection, "..", spaces and an overlong name; a relative repository too.
        repo = self.make_repo("notes")
        host = await self.opened(linux=False)
        branches = ("-x", "--upload-pack=touch", "a..b", "a b", "x" * (REF_MAX_CHARS + 1))
        for branch in branches:
            with self.subTest(branch=branch[:20]):
                error = await self.refused_locally(host.create_codex_worktree(repo, branch), "branch")
                self.assertEqual(str(error), WORKTREE_REF_MESSAGE.format(field="branch", maximum=REF_MAX_CHARS))
        error = await self.refused_locally(host.create_codex_worktree(repo, "feat/x", base_ref="-b"), "base_ref")
        self.assertEqual(str(error), WORKTREE_REF_MESSAGE.format(field="base_ref", maximum=REF_MAX_CHARS))
        error = await self.refused_locally(host.create_codex_worktree("notes", "feat/x"), "repository")
        self.assertEqual(str(error), WORKTREE_REPOSITORY_MESSAGE)
        self.assertFalse((self.home / ".vidbyte").exists())
        self.assertEqual(self.branches(repo), [self.branch_of(repo)])

    def root_error_type(self, home: Path) -> str:
        """The type the root's own mkdir raises under this home: FileExistsError on Windows, NotADirectoryError on Linux."""
        try:
            home.joinpath(*ROOT_PARTS).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return type(exc).__name__
        self.fail("the worktree root could be made, so this case does not reach EC-63")

    async def test_a_worktree_root_that_cannot_be_prepared_is_refused_by_type_without_the_home_path_and_git_never_runs(self) -> None:
        # EC-63, INV-2, INV-29 (spec r6, review R-1): the home lookup or the root's mkdir raises, and the packet names only
        # the exception's type, raised from None: no home path or exception text, no log record, no branch, no request.
        repo = self.make_repo("notes")
        home = self.root / f"home-{PATH_CANARY}"
        home.mkdir()
        host = await self.opened(linux=False)
        records = self.capture_logs(HOST_LOGGER)
        real_mkdir = Path.mkdir

        def denied(path: Path, *args: Any, **kwargs: Any) -> None:
            # A home this process may not write to. A read-only folder does not stop mkdir on Windows, so the
            # refusal is simulated; like the real one, it quotes the absolute path.
            if path == home or home in path.parents:
                raise PermissionError(13, "Permission denied", str(path))
            real_mkdir(path, *args, **kwargs)

        def at_home() -> Any:
            return mock.patch("pathlib.Path.home", return_value=home)

        rows = (
            ("no home folder", (mock.patch("pathlib.Path.home", side_effect=RuntimeError(f"Could not determine home directory {PATH_CANARY}.")),), lambda: None, lambda: "RuntimeError"),
            ("home not writable", (at_home(), mock.patch("pathlib.Path.mkdir", denied)), lambda: None, lambda: "PermissionError"),
            ("~/.vidbyte is a file", (at_home(),), lambda: (home / ROOT_PARTS[0]).write_text("not a folder", encoding="utf-8"), lambda: self.root_error_type(home)),
        )
        for label, patches, prepare, error_type in rows:
            with self.subTest(case=label):
                prepare()
                with contextlib.ExitStack() as stack:
                    for patch in patches:
                        stack.enter_context(patch)
                    error = await self.worktree_error(host.create_codex_worktree(repo, "feat/x"))
                message = WORKTREE_ROOT_MESSAGE.format(error_type=error_type())
                assert_packet(self, error, operation=OPERATION, code=INVALID, message=message, cause=WORKTREE_ROOT_CAUSE, next_step=WORKTREE_ROOT_NEXT_STEP)
                # Raised from None: the original exception, whose text holds the home path, is not chained.
                self.assertIsNone(error.__cause__)
                self.assertTrue(error.__suppress_context__)
                assert_no_canary(self, [error.message, str(error), error.next_step], (PATH_CANARY, str(home)))
        # git worktree add makes its branch first, so an unchanged branch list proves git never ran.
        self.assertEqual(self.branches(repo), [self.branch_of(repo)])
        self.assertEqual([record.getMessage() for record in records], [])
        self.assertEqual(self.sent_methods(), [])


@requires_sdk
class CodexWorktreeLogTests(_GitSandbox, FeatureHostCase):
    """INV-9 and NFR-7: the two worktree log events, their fields, and no path, branch or git output in any record."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.start_git_sandbox()
        home = mock.patch("pathlib.Path.home", return_value=self.home)
        home.start()
        self.addCleanup(home.stop)

    async def test_the_worktree_logs_carry_the_operation_and_outcome_and_never_the_path_or_branch(self) -> None:
        records = self.capture_logs(HOST_LOGGER)
        repo = self.make_repo(f"repo-{PATH_CANARY}")
        plain = self.root / f"plain-{PATH_CANARY}"
        plain.mkdir()
        host = await self.opened(linux=False)
        await self.call(host.create_codex_worktree(repo, f"feat/{BRANCH_CANARY}"))
        await self.codex_error(host.create_codex_worktree(plain, f"feat/{BRANCH_CANARY}"), INVALID)
        with self.without_git():
            await self.codex_error(host.create_codex_worktree(repo, f"fix/{BRANCH_CANARY}"), INVALID)

        created = log_events(records, "codex_host_worktree_created")
        self.assertEqual([record.levelno for record in created], [logging.DEBUG])
        fields = log_fields(created[0])
        self.assertEqual(set(fields), {"operation", "duration_ms"})
        self.assertEqual(fields["operation"], OPERATION)
        self.assertTrue(fields["duration_ms"].isdigit(), fields)

        failed = log_events(records, "codex_host_worktree_failed")
        self.assertEqual([record.levelno for record in failed], [logging.WARNING, logging.WARNING])
        exited, missing = (log_fields(record) for record in failed)
        for row in (exited, missing):
            self.assertEqual(set(row), FAILED_FIELDS)
            self.assertEqual(row["operation"], OPERATION)
            self.assertEqual(row["timed_out"].casefold(), "false")
            self.assertTrue(row["duration_ms"].isdigit(), row)
        self.assertEqual(exited["exit_code"], "128")
        self.assertIn("not_found", missing["launch_failure"].casefold())
        self.assertTrue(all(record.exc_info is None for record in records))
        assert_no_canary(self, [record.getMessage() for record in records], (PATH_CANARY, BRANCH_CANARY))
        self.assertEqual(self.sent_methods(), [])


class GitWorktreesHelperTests(_GitSandbox, unittest.IsolatedAsyncioTestCase):
    """FR-35, D-19 and INV-29: GitWorktrees.add runs one bounded git worktree add and reports every failure in its CliOutcome."""

    def setUp(self) -> None:
        self.start_git_sandbox()

    def spec(self, repo: Path, branch: str, path: Path, **fields: Any) -> Any:
        from vidbyte.lib.dataclasses.process import GitWorktreeSpec

        return GitWorktreeSpec(repository=repo, branch=branch, path=path, timeout_seconds=GIT_SECONDS, max_output_bytes=65536, **fields)

    async def add(self, spec: Any) -> Any:
        from vidbyte.lib.process.git_worktree import GitWorktrees

        return await asyncio.wait_for(GitWorktrees.add(spec), GIT_SECONDS + WAIT_SECONDS)

    async def test_add_makes_the_worktree_on_a_new_branch_and_git_runs_with_terminal_prompts_off(self) -> None:
        # GIT_NO_PROMPT_ENV is the env_overlay, so it wins over the caller's own GIT_TERMINAL_PROMPT.
        repo = self.make_repo("lib")
        marker = self.root / "prompt.txt"
        self.hook(repo, f'printf "%s" "$GIT_TERMINAL_PROMPT" > "{marker.as_posix()}"\n')
        target = self.root / "worktrees" / "lib-feat-lib"
        with mock.patch.dict(os.environ, {"GIT_TERMINAL_PROMPT": "1"}):
            outcome = await self.add(self.spec(repo, "feat/lib", target))
        self.assertEqual((outcome.exit_code, outcome.timed_out, outcome.launch_failure), (0, False, None), outcome.stderr)
        self.assertEqual(self.branch_of(target), "feat/lib")
        self.assertEqual(self.head(target), self.head(repo))
        self.assertEqual(marker.read_text(encoding="utf-8"), "0")

    async def test_add_starts_the_branch_at_the_base_ref_when_one_is_given(self) -> None:
        repo = self.make_repo("lib")
        target = self.root / "worktrees" / "lib-feat-old"
        outcome = await self.add(self.spec(repo, "feat/old", target, base_ref="release-1"))
        self.assertEqual(outcome.exit_code, 0, outcome.stderr)
        self.assertEqual(self.head(target), self.head(repo, "release-1"))

    async def test_a_nonzero_git_exit_comes_back_in_the_outcome_instead_of_raising(self) -> None:
        repo = self.make_repo("lib")
        self.git_ok("-C", str(repo), "branch", "feat/taken")
        target = self.root / "worktrees" / "lib-feat-taken"
        outcome = await self.add(self.spec(repo, "feat/taken", target))
        code, _ = self.oracle(repo, "feat/taken", target)
        self.assertEqual((outcome.exit_code, outcome.timed_out, outcome.launch_failure), (code, False, None))
        self.assertIn("feat/taken", outcome.stderr)
        self.assertFalse(target.exists())

    async def test_a_missing_git_comes_back_as_a_not_found_launch_failure(self) -> None:
        from vidbyte.lib.enums.process import ProcessLaunchFailure

        repo = self.make_repo("lib")
        with self.without_git():
            outcome = await self.add(self.spec(repo, "feat/none", self.root / "worktrees" / "lib-feat-none"))
        self.assertEqual((outcome.exit_code, outcome.launch_failure), (None, ProcessLaunchFailure.NOT_FOUND))


if __name__ == "__main__":
    unittest.main()
