"""FILE: vidbyte/harnesses/native/grok/__init__.py

PURPOSE: The Grok Build subpackage of the harness thread functions; exports run_grok_thread, continue_grok_thread and fork_grok_thread, and the browser functions run_grok_with_browser, continue_grok_with_browser and fork_grok_with_browser.
ROLE IN CODEBASE: Imported by vidbyte/harnesses/native/__init__.py, which re-exports the six functions. Nothing here is re-exported from vidbyte or vidbyte.harnesses.
ARCHITECTURE NOTE: A package initializer that only binds each public function to its GrokThreads attribute (grok/threads.py) or GrokBrowserThreads attribute (grok/browser.py), so callers get plain module functions while the code stays in one class per family.
FUNCTION INVENTORY: No functions of its own. run_grok_thread, continue_grok_thread and fork_grok_thread are bound from GrokThreads; run_grok_with_browser, continue_grok_with_browser and fork_grok_with_browser are bound from GrokBrowserThreads.
COMMON MODIFICATION PATTERNS: Bind each public function to its class attribute and list it in the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding the grok executable. 2. Do not export GrokThreadRun or GrokWire, nor GrokMounts or GrokBrowserHarness; they are internal.
KNOWN EDGE CASES: None; the module only binds names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

from vidbyte.harnesses.native.grok.browser import GrokBrowserThreads
from vidbyte.harnesses.native.grok.threads import GrokThreads

run_grok_thread = GrokThreads.run_grok_thread
continue_grok_thread = GrokThreads.continue_grok_thread
fork_grok_thread = GrokThreads.fork_grok_thread
run_grok_with_browser = GrokBrowserThreads.run_grok_with_browser
continue_grok_with_browser = GrokBrowserThreads.continue_grok_with_browser
fork_grok_with_browser = GrokBrowserThreads.fork_grok_with_browser

__all__ = ["continue_grok_thread", "continue_grok_with_browser", "fork_grok_thread", "fork_grok_with_browser", "run_grok_thread", "run_grok_with_browser"]
