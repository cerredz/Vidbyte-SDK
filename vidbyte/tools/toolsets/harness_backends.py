"""FILE: vidbyte/tools/toolsets/harness_backends.py

PURPOSE: Defines HarnessBackendTools, the catalog of the three READ tools over the GLM and DeepSeek backend profiles: list_harness_backends, check_backend_ready and get_deepseek_balance.
ROLE IN CODEBASE: Exported by vidbyte/tools/toolsets/__init__.py; composes the tool classes in vidbyte/tools/builtins/harness_backends/. Hand it to an agent or to ToolExecutor like any other Tools catalog.
ARCHITECTURE NOTE: A Tools subclass that holds only the three tools. It needs no host, because the backend functions are module functions, and no read_only variant, because all three tools are READ and pass the default PermissionPolicy.
FUNCTION INVENTORY: HarnessBackendTools.__init__ is the narrated main function and builds the three tools in spec order.
COMMON MODIFICATION PATTERNS: A new backend tool is one more entry in the tuple, in §9.2 order.
WHAT NOT TO DO IN THIS FILE: 1. Do not read keys or environment variables here; the backend functions read them on each call. 2. Do not add tools for the internal backend functions.
KNOWN EDGE CASES: Building the catalog reads no key and makes no request; a missing key is reported when a tool runs.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Toolsets), §9.2 rows 41-43; vidbyte/tools/README.md
TESTS: tests/features/native_backends/test_native_backends_tools.py
"""

from __future__ import annotations

from vidbyte.tools.builtins.harness_backends import (
    CheckBackendReadyTool,
    GetDeepseekBalanceTool,
    ListHarnessBackendsTool,
)
from vidbyte.tools.catalog import Tools


class HarnessBackendTools(Tools):
    """Catalog of the three READ tools over the backend profiles."""

    def __init__(self) -> None:
        # List the profiles first, then the readiness check, then the DeepSeek balance read.
        super().__init__((ListHarnessBackendsTool(), CheckBackendReadyTool(), GetDeepseekBalanceTool()))


__all__ = ["HarnessBackendTools"]
