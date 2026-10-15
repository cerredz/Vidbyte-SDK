"""FILE: vidbyte/harnesses/native/grok/__init__.py

PURPOSE: The Grok Build subpackage of the harness thread functions; exports run_grok_thread, continue_grok_thread and fork_grok_thread.
ROLE IN CODEBASE: Imported by vidbyte/harnesses/native/__init__.py, which re-exports the three functions. Nothing here is re-exported from vidbyte or vidbyte.harnesses.
ARCHITECTURE NOTE: A package initializer that only binds each public function to its GrokThreads attribute (grok/threads.py), so callers get plain module functions while the code stays in one class.
FUNCTION INVENTORY: No functions of its own. run_grok_thread, continue_grok_thread and fork_grok_thread are bound from GrokThreads.
COMMON MODIFICATION PATTERNS: Bind each public function to its class attribute and list it in the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding the grok executable. 2. Do not export GrokThreadRun or GrokWire; they are internal.
KNOWN EDGE CASES: None; the module only binds names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

from vidbyte.harnesses.native.grok.threads import GrokThreads

run_grok_thread = GrokThreads.run_grok_thread
continue_grok_thread = GrokThreads.continue_grok_thread
fork_grok_thread = GrokThreads.fork_grok_thread

__all__ = ["continue_grok_thread", "fork_grok_thread", "run_grok_thread"]
