"""FILE: vidbyte/harnesses/native/claude/__init__.py

PURPOSE: The Claude Code subpackage of the harness thread functions; exports run_claude_thread, continue_claude_thread and fork_claude_thread.
ROLE IN CODEBASE: Imported by vidbyte/harnesses/native/__init__.py, which re-exports the three functions. Nothing here is re-exported from vidbyte or vidbyte.harnesses.
ARCHITECTURE NOTE: A package initializer that only binds each public function to its ClaudeThreads attribute (claude/threads.py), so callers get plain module functions while the code stays in one class.
FUNCTION INVENTORY: No functions of its own. run_claude_thread, continue_claude_thread and fork_claude_thread are bound from ClaudeThreads.
COMMON MODIFICATION PATTERNS: Bind each public function to its class attribute and list it in the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding the claude executable. 2. Do not export ClaudeThreadRun or ClaudeWire; they are internal.
KNOWN EDGE CASES: None; the module only binds names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

from vidbyte.harnesses.native.claude.threads import ClaudeThreads

run_claude_thread = ClaudeThreads.run_claude_thread
continue_claude_thread = ClaudeThreads.continue_claude_thread
fork_claude_thread = ClaudeThreads.fork_claude_thread

__all__ = ["continue_claude_thread", "fork_claude_thread", "run_claude_thread"]
