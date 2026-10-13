"""FILE: vidbyte/lib/enums/harness_backends.py

PURPOSE: Defines the closed value sets of the GLM and DeepSeek backend profiles: which backend a profile is, and which Anthropic API features a backend's compatible endpoint silently ignores.
ROLE IN CODEBASE: Imported by vidbyte/lib/dataclasses/harness_backends.py, vidbyte/lib/configs/harness_backends.py, vidbyte/lib/dataclasses/opencode.py (OpencodeHostSettings.backends), vidbyte/harnesses/native/backends/ and vidbyte/tools/builtins/harness_backends/. Exported from vidbyte/lib/enums/__init__.py.
ARCHITECTURE NOTE: Both enums are str Enums. The functions accept a member or its value string at the Python surface and convert once, so the records always hold members.
FUNCTION INVENTORY: No functions. HarnessBackendName and BackendFeature.
COMMON MODIFICATION PATTERNS: A new backend adds a HarnessBackendName member and its profile row in vidbyte/lib/configs/harness_backends.py together; a new ignored feature adds a BackendFeature member and the profiles that ignore it.
WHAT NOT TO DO IN THIS FILE: 1. Do not import anything from vidbyte. 2. Do not reorder HarnessBackendName; HARNESS_BACKENDS is declared in member order.
KNOWN EDGE CASES: BackendFeature names request features, not response features, because check_backend_compat runs before a request is sent.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §9.1
TESTS: tests/features/native_backends/test_native_backends_records.py, tests/features/native_backends/test_native_backends_profiles.py
"""

from __future__ import annotations

from enum import Enum


class HarnessBackendName(str, Enum):
    """The declared Anthropic-compatible backend profiles."""

    GLM = "glm"
    DEEPSEEK = "deepseek"


class BackendFeature(str, Enum):
    """An Anthropic request feature that a backend endpoint may silently ignore."""

    MCP_SERVERS = "mcp_servers"
    CACHE_CONTROL = "cache_control"
    CONTAINER = "container"
    TOP_K = "top_k"
    SERVICE_TIER = "service_tier"
    ANTHROPIC_BETA = "anthropic_beta"
    DISABLE_PARALLEL_TOOL_USE = "disable_parallel_tool_use"
    THINKING_BUDGET_TOKENS = "thinking_budget_tokens"
    TOOL_RESULT_IS_ERROR = "tool_result_is_error"
    DOCUMENT_BLOCKS = "document_blocks"
    SEARCH_RESULT_BLOCKS = "search_result_blocks"


__all__ = ["BackendFeature", "HarnessBackendName"]
