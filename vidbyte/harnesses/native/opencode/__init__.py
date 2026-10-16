"""FILE: vidbyte/harnesses/native/opencode/__init__.py

PURPOSE: The opencode subpackage of the harness thread functions; exports run_opencode_thread, continue_opencode_thread and fork_opencode_thread, and the eight keyless opencode thread helpers (list, list recent, list since, get, read, lineage, search and delete).
ROLE IN CODEBASE: Imported by vidbyte/harnesses/native/__init__.py, which re-exports every function bound here. Nothing here is re-exported from vidbyte or vidbyte.harnesses.
ARCHITECTURE NOTE: A package initializer that only binds each public function to its class attribute, OpencodeThreads (opencode/threads.py) or OpencodeThreadHelpers (opencode/helpers.py), so callers get plain module functions while the code stays in its class.
FUNCTION INVENTORY: No functions of its own. run_opencode_thread, continue_opencode_thread and fork_opencode_thread are bound from OpencodeThreads; list_opencode_threads, list_recent_opencode_threads, list_opencode_threads_since, get_opencode_thread, read_opencode_thread, get_opencode_thread_lineage, search_opencode_threads and delete_opencode_thread from OpencodeThreadHelpers.
COMMON MODIFICATION PATTERNS: Bind each public function to its class attribute and list it in the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding the opencode executable. 2. Do not export OpencodeThreadRun, OpencodeHelperRun or the wire readers; they are internal.
KNOWN EDGE CASES: None; the module only binds names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

from vidbyte.harnesses.native.opencode.helpers import OpencodeThreadHelpers
from vidbyte.harnesses.native.opencode.threads import OpencodeThreads

run_opencode_thread = OpencodeThreads.run_opencode_thread
continue_opencode_thread = OpencodeThreads.continue_opencode_thread
fork_opencode_thread = OpencodeThreads.fork_opencode_thread
list_opencode_threads = OpencodeThreadHelpers.list_opencode_threads
list_recent_opencode_threads = OpencodeThreadHelpers.list_recent_opencode_threads
list_opencode_threads_since = OpencodeThreadHelpers.list_opencode_threads_since
get_opencode_thread = OpencodeThreadHelpers.get_opencode_thread
read_opencode_thread = OpencodeThreadHelpers.read_opencode_thread
get_opencode_thread_lineage = OpencodeThreadHelpers.get_opencode_thread_lineage
search_opencode_threads = OpencodeThreadHelpers.search_opencode_threads
delete_opencode_thread = OpencodeThreadHelpers.delete_opencode_thread

__all__ = [
    "continue_opencode_thread",
    "delete_opencode_thread",
    "fork_opencode_thread",
    "get_opencode_thread",
    "get_opencode_thread_lineage",
    "list_opencode_threads",
    "list_opencode_threads_since",
    "list_recent_opencode_threads",
    "read_opencode_thread",
    "run_opencode_thread",
    "search_opencode_threads",
]
