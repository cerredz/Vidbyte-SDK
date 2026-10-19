"""FILE: vidbyte/lib/process/__init__.py

PURPOSE: Exposes the canonical process helpers: CliArgv (build an argv of plain strings from flags, values and operands), CliRunner (run a command-line program to completion within a timeout and an output cap) and ProcessStopper (stop and reap a child's whole process tree). The package also holds GitWorktrees (create one git worktree with a bounded git worktree add) in git_worktree.py, which is not re-exported here.
ROLE IN CODEBASE: Imported by the harness thread functions under vidbyte/harnesses/native/, and git_worktree by CodexHost's create_codex_worktree. The records they take and return live in vidbyte/lib/dataclasses/process.py.
ARCHITECTURE NOTE: Bottom-layer package (AGENTS.md principles 3 and 5): it imports only vidbyte.lib modules and the standard library, so any layer may use it. No child it starts inherits the caller's stdin.
FUNCTION INVENTORY: No functions. Re-exports CliArgv, CliRunner and ProcessStopper.
COMMON MODIFICATION PATTERNS: Add a new helper in its own module here and export it from this literal __all__. GitWorktrees is the exception: callers import it from vidbyte.lib.process.git_worktree, because this __all__ is pinned by the harness-threads tests (first-class INV-53).
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.harnesses, vidbyte.tools or any higher layer (lint A006). 2. Do not add import-time side effects.
KNOWN EDGE CASES: Process-group stops are POSIX-only; on Windows the helpers use taskkill /T, which cannot reach a grandchild of a leader that already exited.
RELATED DOCS: vidbyte/lib/README.md
TESTS: tests/features/harness_threads/test_harness_threads_runner.py, tests/features/harness_threads/test_harness_threads_argv.py, tests/features/codex_host/test_codex_host_worktree.py
"""

from __future__ import annotations

from vidbyte.lib.process.argv import CliArgv
from vidbyte.lib.process.runner import CliRunner, ProcessStopper

__all__ = ["CliArgv", "CliRunner", "ProcessStopper"]
