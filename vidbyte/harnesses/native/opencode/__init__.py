"""FILE: vidbyte/harnesses/native/opencode/__init__.py

PURPOSE: The opencode subpackage of the harness thread functions; exports run_opencode_thread, continue_opencode_thread and fork_opencode_thread, and the browser functions run_opencode_with_browser, continue_opencode_with_browser and fork_opencode_with_browser.
ROLE IN CODEBASE: Imported by vidbyte/harnesses/native/__init__.py, which re-exports the six functions. Nothing here is re-exported from vidbyte or vidbyte.harnesses.
ARCHITECTURE NOTE: A package initializer that only binds each public function to its OpencodeThreads attribute (opencode/threads.py) or OpencodeBrowserThreads attribute (opencode/browser.py), so callers get plain module functions while the code stays in one class per family.
FUNCTION INVENTORY: No functions of its own. run_opencode_thread, continue_opencode_thread and fork_opencode_thread are bound from OpencodeThreads; run_opencode_with_browser, continue_opencode_with_browser and fork_opencode_with_browser are bound from OpencodeBrowserThreads.
COMMON MODIFICATION PATTERNS: Bind each public function to its class attribute and list it in the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding the opencode executable. 2. Do not export OpencodeThreadRun or OpencodeWire, nor OpencodeMounts or OpencodeBrowserHarness; they are internal.
KNOWN EDGE CASES: None; the module only binds names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

from vidbyte.harnesses.native.opencode.browser import OpencodeBrowserThreads
from vidbyte.harnesses.native.opencode.threads import OpencodeThreads

run_opencode_thread = OpencodeThreads.run_opencode_thread
continue_opencode_thread = OpencodeThreads.continue_opencode_thread
fork_opencode_thread = OpencodeThreads.fork_opencode_thread
run_opencode_with_browser = OpencodeBrowserThreads.run_opencode_with_browser
continue_opencode_with_browser = OpencodeBrowserThreads.continue_opencode_with_browser
fork_opencode_with_browser = OpencodeBrowserThreads.fork_opencode_with_browser

__all__ = ["continue_opencode_thread", "continue_opencode_with_browser", "fork_opencode_thread", "fork_opencode_with_browser", "run_opencode_thread", "run_opencode_with_browser"]
