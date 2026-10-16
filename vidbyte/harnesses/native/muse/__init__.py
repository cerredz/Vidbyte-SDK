"""FILE: vidbyte/harnesses/native/muse/__init__.py

PURPOSE: The Muse Code subpackage of the harness thread functions; exports run_muse_thread, continue_muse_thread and fork_muse_thread, the six keyless Muse thread helpers (list, list recent, list since, get, read and lineage) and init_muse_workspace.
ROLE IN CODEBASE: Imported by vidbyte/harnesses/native/__init__.py, which re-exports every function bound here. Nothing here is re-exported from vidbyte or vidbyte.harnesses.
ARCHITECTURE NOTE: A package initializer that only binds each public function to its class attribute, MuseThreads (muse/threads.py) or MuseThreadHelpers (muse/helpers.py), so callers get plain module functions while the code stays in its class.
FUNCTION INVENTORY: No functions of its own. run_muse_thread, continue_muse_thread and fork_muse_thread are bound from MuseThreads; list_muse_threads, list_recent_muse_threads, list_muse_threads_since, get_muse_thread, read_muse_thread, get_muse_thread_lineage and init_muse_workspace from MuseThreadHelpers.
COMMON MODIFICATION PATTERNS: Bind each public function to its class attribute and list it in the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding the muse executable or listing WSL distros. 2. Do not export MuseThreadRun, MuseHelperRun, MuseLauncher, MuseWire, MuseSessionWire or MuseExecOutput; they are internal.
KNOWN EDGE CASES: None; the module only binds names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

from vidbyte.harnesses.native.muse.helpers import MuseThreadHelpers
from vidbyte.harnesses.native.muse.threads import MuseThreads

run_muse_thread = MuseThreads.run_muse_thread
continue_muse_thread = MuseThreads.continue_muse_thread
fork_muse_thread = MuseThreads.fork_muse_thread
list_muse_threads = MuseThreadHelpers.list_muse_threads
list_recent_muse_threads = MuseThreadHelpers.list_recent_muse_threads
list_muse_threads_since = MuseThreadHelpers.list_muse_threads_since
get_muse_thread = MuseThreadHelpers.get_muse_thread
read_muse_thread = MuseThreadHelpers.read_muse_thread
get_muse_thread_lineage = MuseThreadHelpers.get_muse_thread_lineage
init_muse_workspace = MuseThreadHelpers.init_muse_workspace

__all__ = [
    "continue_muse_thread",
    "fork_muse_thread",
    "get_muse_thread",
    "get_muse_thread_lineage",
    "init_muse_workspace",
    "list_muse_threads",
    "list_muse_threads_since",
    "list_recent_muse_threads",
    "read_muse_thread",
    "run_muse_thread",
]
