"""FILE: vidbyte/tools/builtins/opencode/__init__.py

PURPOSE: Exports the 18 opencode tool classes: the ten READ tools of read_tools.py and the eight session tools of session_tools.py.
ROLE IN CODEBASE: Imported by OpencodeTools in vidbyte/tools/toolsets/opencode.py. Not re-exported from vidbyte/tools/builtins/__init__.py or the root package.
ARCHITECTURE NOTE: A package initializer that only re-exports; the classes live in read_tools.py and session_tools.py and their text in descriptions.py.
FUNCTION INVENTORY: No functions. Re-exports the 18 tool classes.
COMMON MODIFICATION PATTERNS: A new opencode tool class is added to the import and the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects. 2. Do not export OpencodeHostTool or the shared parameters from here; they are the base, importable from read_tools.py.
KNOWN EDGE CASES: None; the module only re-exports.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Tools), §9.2 rows 11-28
TESTS: tests/features/opencode_host/test_opencode_host_tools.py
"""

from __future__ import annotations

from vidbyte.tools.builtins.opencode.read_tools import (
    CheckOpencodeReadyTool,
    GetOpencodeMessageTool,
    GetOpencodeProviderAuthTool,
    GetOpencodeSessionDiffTool,
    GetOpencodeSessionMessagesTool,
    GetOpencodeSessionTool,
    ListOpencodeModelsTool,
    ListOpencodeProvidersTool,
    ListOpencodeSessionsTool,
    TrackOpencodeSessionUsageTool,
)
from vidbyte.tools.builtins.opencode.session_tools import (
    AddOpencodeMcpServerTool,
    ContinueOpencodeSessionTool,
    ForkOpencodeSessionTool,
    InterruptOpencodeTurnTool,
    RevertOpencodeSessionTool,
    SpawnOpencodeSessionTool,
    UnrevertOpencodeSessionTool,
    WaitOpencodeTurnTool,
)

__all__ = [
    "AddOpencodeMcpServerTool",
    "CheckOpencodeReadyTool",
    "ContinueOpencodeSessionTool",
    "ForkOpencodeSessionTool",
    "GetOpencodeMessageTool",
    "GetOpencodeProviderAuthTool",
    "GetOpencodeSessionDiffTool",
    "GetOpencodeSessionMessagesTool",
    "GetOpencodeSessionTool",
    "InterruptOpencodeTurnTool",
    "ListOpencodeModelsTool",
    "ListOpencodeProvidersTool",
    "ListOpencodeSessionsTool",
    "RevertOpencodeSessionTool",
    "SpawnOpencodeSessionTool",
    "TrackOpencodeSessionUsageTool",
    "UnrevertOpencodeSessionTool",
    "WaitOpencodeTurnTool",
]
