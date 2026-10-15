"""FILE: vidbyte/harnesses/native/muse/__init__.py

PURPOSE: The Muse Code subpackage of the harness thread functions; exports run_muse_thread, continue_muse_thread and fork_muse_thread.
ROLE IN CODEBASE: Imported by vidbyte/harnesses/native/__init__.py, which re-exports the three functions. Nothing here is re-exported from vidbyte or vidbyte.harnesses.
ARCHITECTURE NOTE: A package initializer that only binds each public function to its MuseThreads attribute (muse/threads.py), so callers get plain module functions while the code stays in one class.
FUNCTION INVENTORY: No functions of its own. run_muse_thread, continue_muse_thread and fork_muse_thread are bound from MuseThreads.
COMMON MODIFICATION PATTERNS: Bind each public function to its class attribute and list it in the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding the muse executable or listing WSL distros. 2. Do not export MuseThreadRun, MuseLauncher, MuseWire or MuseExecOutput; they are internal.
KNOWN EDGE CASES: None; the module only binds names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

from vidbyte.harnesses.native.muse.threads import MuseThreads

run_muse_thread = MuseThreads.run_muse_thread
continue_muse_thread = MuseThreads.continue_muse_thread
fork_muse_thread = MuseThreads.fork_muse_thread

__all__ = ["continue_muse_thread", "fork_muse_thread", "run_muse_thread"]
