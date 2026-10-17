"""FILE: vidbyte/harnesses/native/__init__.py

PURPOSE: The package of harness thread functions: twelve async functions that run, continue and fork Grok Build, opencode, Muse Code and Claude Code threads by driving each vendor's installed command-line tool headless once, with the caller's API key, and return the thread id and the final answer.
ROLE IN CODEBASE: The public entry point of vidbyte.harnesses.native. It re-exports the three functions of each harness subpackage (grok, opencode, muse, claude), the records a caller builds or receives (GrokThreadConfig, OpencodeThreadConfig, MuseThreadConfig, ClaudeThreadConfig, NativeThreadResult), the one error type (NativeThreadError) and the config enums. Nothing here is re-exported from vidbyte or vidbyte.harnesses, and `import vidbyte` never imports this package.
ARCHITECTURE NOTE: A package initializer that only imports and re-exports. The functions live in each harness's threads module, the records in vidbyte/lib/dataclasses/native_threads.py, the enums in vidbyte/lib/enums/native_threads.py and the error in vidbyte/lib/errors/base.py; the shared plumbing lives in the hostkit subpackage, which is internal.
FUNCTION INVENTORY: No functions of its own. run_grok_thread, continue_grok_thread, fork_grok_thread, run_opencode_thread, continue_opencode_thread, fork_opencode_thread, run_muse_thread, continue_muse_thread, fork_muse_thread, run_claude_thread, continue_claude_thread and fork_claude_thread come from the harness subpackages.
COMMON MODIFICATION PATTERNS: A new harness adds its own subpackage with three functions and one config record, and this module re-exports them in the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding an executable or reading a key. 2. Do not export the flow classes, codecs, launchers or hostkit helpers; they are internal plumbing.
KNOWN EDGE CASES: None; the module only re-exports names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

from vidbyte.harnesses.native.claude import (
    continue_claude_thread,
    fork_claude_thread,
    run_claude_thread,
)
from vidbyte.harnesses.native.grok import (
    continue_grok_thread,
    fork_grok_thread,
    run_grok_thread,
)
from vidbyte.harnesses.native.muse import (
    continue_muse_thread,
    fork_muse_thread,
    run_muse_thread,
)
from vidbyte.harnesses.native.opencode import (
    continue_opencode_thread,
    fork_opencode_thread,
    run_opencode_thread,
)
from vidbyte.lib.dataclasses.native_threads import (
    ClaudeThreadConfig,
    GrokThreadConfig,
    MuseThreadConfig,
    NativeThreadResult,
    OpencodeThreadConfig,
)
from vidbyte.lib.enums.native_threads import (
    ClaudePermissionMode,
    ClaudeReasoningEffort,
    GrokPermissionMode,
    GrokReasoningEffort,
    MuseReasoningEffort,
)
from vidbyte.lib.errors import NativeThreadError

__all__ = [
    "ClaudePermissionMode",
    "ClaudeReasoningEffort",
    "ClaudeThreadConfig",
    "GrokPermissionMode",
    "GrokReasoningEffort",
    "GrokThreadConfig",
    "MuseReasoningEffort",
    "MuseThreadConfig",
    "NativeThreadError",
    "NativeThreadResult",
    "OpencodeThreadConfig",
    "continue_claude_thread",
    "continue_grok_thread",
    "continue_muse_thread",
    "continue_opencode_thread",
    "fork_claude_thread",
    "fork_grok_thread",
    "fork_muse_thread",
    "fork_opencode_thread",
    "run_claude_thread",
    "run_grok_thread",
    "run_muse_thread",
    "run_opencode_thread",
]
