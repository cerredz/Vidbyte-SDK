"""FILE: vidbyte/lib/process/git_worktree.py

PURPOSE: Defines GitWorktrees, the canonical way to create one git worktree: a single bounded git worktree add on a new branch, from a base ref or HEAD, run through CliArgv and CliRunner with terminal prompts off.
ROLE IN CODEBASE: Called by CodexHost's create_codex_worktree (CodexThreadMethods under vidbyte/harnesses/native/codex/), which builds the GitWorktreeSpec from vidbyte/lib/dataclasses/process.py after it has refused an existing target folder. It is the one place a git worktree is created (first-class FR-35, D-19).
ARCHITECTURE NOTE: Canonical lib helper (AGENTS.md principle 5): it takes everything it needs as the spec, imports only vidbyte.lib modules, and returns CliRunner's CliOutcome as is, so a missing git, a nonzero exit and a timeout are fields of the outcome, not exceptions. The argv is built from fixed subcommand words by CliArgv and started without a shell; standard input is the null device, and GIT_NO_PROMPT_ENV is the environment overlay, so git can never stop to ask for credentials.
FUNCTION INVENTORY: GitWorktrees.add is the narrated main function and has no helpers.
COMMON MODIFICATION PATTERNS: A new git operation gets its own static method here with its own spec record in vidbyte/lib/dataclasses/process.py and its own GIT_* constants in vidbyte/lib/constants/native_threads.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not build a command string or pass shell=True; argv goes to CliRunner. 2. Do not put the target path before the end-of-options operand; a path that starts with a dash would become an option. 3. Do not export GitWorktrees from vidbyte.lib.process; callers import this module. 4. Do not import from a layer above vidbyte.lib.
KNOWN EDGE CASES: git creates the new branch before it finds the target folder taken, so a caller refuses an existing folder before it calls add (first-class INV-29). An empty base_ref starts the branch at HEAD. A folder that appears between the caller's check and git's run makes git exit nonzero, which comes back in the outcome (EC-34).
RELATED DOCS: vidbyte/lib/README.md; docs/spec/codex-host-first-class/spec.md (FR-35, D-19, T-5)
TESTS: tests/features/codex_host/test_codex_host_worktree.py
"""

from __future__ import annotations

from vidbyte.lib.constants.native_threads import (
    GIT_DEFAULT_BASE_REF,
    GIT_END_OF_OPTIONS,
    GIT_NO_PROMPT_ENV,
    GIT_PROGRAM,
    GIT_WORKTREE_ADD_COMMAND,
)
from vidbyte.lib.dataclasses.process import (
    CliInvocation,
    CliOption,
    CliOutcome,
    GitWorktreeSpec,
)
from vidbyte.lib.enums.process import CliOptionStyle, GitFlag
from vidbyte.lib.process.argv import CliArgv
from vidbyte.lib.process.runner import CliRunner


class GitWorktrees:
    """Creates git worktrees with one bounded git worktree add each."""

    @staticmethod
    async def add(spec: GitWorktreeSpec) -> CliOutcome:
        # @intent a-worktree-add-is-one-bounded-git-run-without-prompts
        # git can hang on a credential prompt or a hook, so the run is
        # bounded by the spec, never reads standard input, and runs with
        # terminal prompts off; every failure comes back in the outcome
        # (first-class FR-35, T-5).
        # Point git at the repository, ask for a new branch, and put the
        # end-of-options marker before the target path and base ref, so
        # neither can ever be read as an option.
        argv = CliArgv.build(
            (GIT_PROGRAM, GitFlag.REPOSITORY, str(spec.repository)),
            command=GIT_WORKTREE_ADD_COMMAND,
            options=(CliOption(GitFlag.NEW_BRANCH, spec.branch),),
            style=CliOptionStyle.SEPARATE,
            operands=(GIT_END_OF_OPTIONS, str(spec.path), spec.base_ref or GIT_DEFAULT_BASE_REF),
        )

        # Run git once within the spec's time and output bounds, with
        # terminal prompts turned off over the caller's own setting.
        invocation = CliInvocation(argv, env_overlay=GIT_NO_PROMPT_ENV, timeout_seconds=spec.timeout_seconds, max_output_bytes=spec.max_output_bytes)
        return await CliRunner().run(invocation)


__all__ = ["GitWorktrees"]
