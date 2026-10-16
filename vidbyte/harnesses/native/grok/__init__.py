"""FILE: vidbyte/harnesses/native/grok/__init__.py

PURPOSE: The Grok Build subpackage of the harness thread functions; exports run_grok_thread, continue_grok_thread and fork_grok_thread, and the eight keyless Grok thread helpers (list, list recent, list since, get, read, lineage, search and delete).
ROLE IN CODEBASE: Imported by vidbyte/harnesses/native/__init__.py, which re-exports every function bound here. Nothing here is re-exported from vidbyte or vidbyte.harnesses.
ARCHITECTURE NOTE: A package initializer that only binds each public function to its class attribute, GrokThreads (grok/threads.py) or GrokThreadHelpers (grok/helpers.py), so callers get plain module functions while the code stays in its class.
FUNCTION INVENTORY: No functions of its own. run_grok_thread, continue_grok_thread and fork_grok_thread are bound from GrokThreads; list_grok_threads, list_recent_grok_threads, list_grok_threads_since, get_grok_thread, read_grok_thread, get_grok_thread_lineage, search_grok_threads and delete_grok_thread from GrokThreadHelpers.
COMMON MODIFICATION PATTERNS: Bind each public function to its class attribute and list it in the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding the grok executable. 2. Do not export GrokThreadRun, GrokHelperRun, GrokHome, GrokStore or the wire readers; they are internal.
KNOWN EDGE CASES: None; the module only binds names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

from vidbyte.harnesses.native.grok.helpers import GrokThreadHelpers
from vidbyte.harnesses.native.grok.threads import GrokThreads

run_grok_thread = GrokThreads.run_grok_thread
continue_grok_thread = GrokThreads.continue_grok_thread
fork_grok_thread = GrokThreads.fork_grok_thread
list_grok_threads = GrokThreadHelpers.list_grok_threads
list_recent_grok_threads = GrokThreadHelpers.list_recent_grok_threads
list_grok_threads_since = GrokThreadHelpers.list_grok_threads_since
get_grok_thread = GrokThreadHelpers.get_grok_thread
read_grok_thread = GrokThreadHelpers.read_grok_thread
get_grok_thread_lineage = GrokThreadHelpers.get_grok_thread_lineage
search_grok_threads = GrokThreadHelpers.search_grok_threads
delete_grok_thread = GrokThreadHelpers.delete_grok_thread

__all__ = [
    "continue_grok_thread",
    "delete_grok_thread",
    "fork_grok_thread",
    "get_grok_thread",
    "get_grok_thread_lineage",
    "list_grok_threads",
    "list_grok_threads_since",
    "list_recent_grok_threads",
    "read_grok_thread",
    "run_grok_thread",
    "search_grok_threads",
]
