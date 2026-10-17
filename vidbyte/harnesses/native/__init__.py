"""FILE: vidbyte/harnesses/native/__init__.py

PURPOSE: The package of native coding-harness code, in two shapes. The codex subpackage is the Codex host: one host class that wraps the official openai-codex SDK in small, atomic functions. The grok, opencode and muse subpackages hold the harness thread functions: nine async functions that run, continue and fork Grok Build, opencode and Muse Code threads by driving each vendor's installed command-line tool headless once, with the caller's API key, and return the thread id and the final answer; and nine browser functions (run_<harness>_with_browser, continue_<harness>_with_browser, fork_<harness>_with_browser) that do the same with the caller's browser tools mounted for that one call and also return the calls made on those tools and the files they saved.
ROLE IN CODEBASE: The public entry point of the harness thread functions. It re-exports the six functions of each thread subpackage (grok, opencode, muse), the records a caller builds or receives (GrokThreadConfig, OpencodeThreadConfig, MuseThreadConfig, NativeThreadResult, BrowserThreadResult, BrowserToolCall), the one error type (NativeThreadError) and the config enums. It does not re-export the Codex host: callers import CodexHost and the Codex module functions from vidbyte.harnesses.native.codex. Nothing here is re-exported from vidbyte or vidbyte.harnesses, and `import vidbyte` never imports this package.
ARCHITECTURE NOTE: A package initializer that only imports and re-exports. The thread functions live in each harness's threads module and the browser functions in its browser module, the records in vidbyte/lib/dataclasses/native_threads.py and browser_tools.py, the enums in vidbyte/lib/enums/native_threads.py and the error in vidbyte/lib/errors/base.py; the shared plumbing lives in the hostkit subpackage, which is internal. Nothing here imports a vendor SDK, so importing this package never requires an optional extra; the codex subpackage loads openai-codex only when a host opens.
FUNCTION INVENTORY: No functions of its own. run_grok_thread, continue_grok_thread, fork_grok_thread, run_opencode_thread, continue_opencode_thread, fork_opencode_thread, run_muse_thread, continue_muse_thread and fork_muse_thread, and the browser functions run_grok_with_browser, continue_grok_with_browser, fork_grok_with_browser, run_opencode_with_browser, continue_opencode_with_browser, fork_opencode_with_browser, run_muse_with_browser, continue_muse_with_browser and fork_muse_with_browser, come from the harness subpackages.
COMMON MODIFICATION PATTERNS: A new thread harness adds its own subpackage with three thread functions, three browser functions and one config record, and this module re-exports them in the literal __all__. A new host harness adds its own subpackage beside codex, and this module leaves it unexported.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding an executable or reading a key. 2. Do not export the flow classes, codecs, launchers, mount compilers, browser harnesses or hostkit helpers; they are internal plumbing. 3. Do not import the codex subpackage or any vendor SDK here.
KNOWN EDGE CASES: None; the module only re-exports names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/ for the re-exports; tests/features/codex_host/ for the codex subpackage.
"""

from __future__ import annotations

from vidbyte.harnesses.native.grok import (
    continue_grok_thread,
    continue_grok_with_browser,
    fork_grok_thread,
    fork_grok_with_browser,
    run_grok_thread,
    run_grok_with_browser,
)
from vidbyte.harnesses.native.muse import (
    continue_muse_thread,
    continue_muse_with_browser,
    fork_muse_thread,
    fork_muse_with_browser,
    run_muse_thread,
    run_muse_with_browser,
)
from vidbyte.harnesses.native.opencode import (
    continue_opencode_thread,
    continue_opencode_with_browser,
    fork_opencode_thread,
    fork_opencode_with_browser,
    run_opencode_thread,
    run_opencode_with_browser,
)
from vidbyte.lib.dataclasses.browser_tools import BrowserThreadResult, BrowserToolCall
from vidbyte.lib.dataclasses.native_threads import (
    GrokThreadConfig,
    MuseThreadConfig,
    NativeThreadResult,
    OpencodeThreadConfig,
)
from vidbyte.lib.enums.native_threads import (
    GrokPermissionMode,
    GrokReasoningEffort,
    MuseReasoningEffort,
)
from vidbyte.lib.errors import NativeThreadError

__all__ = [
    "BrowserThreadResult",
    "BrowserToolCall",
    "GrokPermissionMode",
    "GrokReasoningEffort",
    "GrokThreadConfig",
    "MuseReasoningEffort",
    "MuseThreadConfig",
    "NativeThreadError",
    "NativeThreadResult",
    "OpencodeThreadConfig",
    "continue_grok_thread",
    "continue_grok_with_browser",
    "continue_muse_thread",
    "continue_muse_with_browser",
    "continue_opencode_thread",
    "continue_opencode_with_browser",
    "fork_grok_thread",
    "fork_grok_with_browser",
    "fork_muse_thread",
    "fork_muse_with_browser",
    "fork_opencode_thread",
    "fork_opencode_with_browser",
    "run_grok_thread",
    "run_grok_with_browser",
    "run_muse_thread",
    "run_muse_with_browser",
    "run_opencode_thread",
    "run_opencode_with_browser",
]
