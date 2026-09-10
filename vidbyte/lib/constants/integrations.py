"""FILE: vidbyte/lib/constants/integrations.py

PURPOSE: Declares every numeric bound the Sources access layer validates against.
ROLE IN CODEBASE: Budget defaults, ceilings, and truncation thresholds live here so limits are discoverable and widenable.
ARCHITECTURE NOTE: Bounds are referenced by dataclass __post_init__ validation rather than inlined as literals at call sites.
COMMON MODIFICATION PATTERNS: Widen a ceiling here and rerun the budget tests; never inline a replacement literal in a validator.
KNOWN EDGE CASES: The character-per-token ratio is a deliberate estimate, not a tokenizer, so budgets stay conservative.
RELATED DOCS: docs/design/sources-access-layer.md
TESTS: tests/test_sources_access_layer.py and scripts/test-sources-access-layer.py.
"""

from __future__ import annotations

INTEGRATIONS_DEFAULT_MAX_TOKENS = 20_000
INTEGRATIONS_MAX_TOKENS_CEILING = 1_000_000
INTEGRATIONS_DEFAULT_MAX_TOOL_CALLS = 40
INTEGRATIONS_MAX_TOOL_CALLS_CEILING = 10_000
INTEGRATIONS_DEFAULT_MAX_TOOL_BYTES = 2_000_000
INTEGRATIONS_MAX_TOOL_BYTES_CEILING = 1_000_000_000
INTEGRATIONS_MAX_SELECTIONS = 200
INTEGRATIONS_MIN_SELECTION_LIMIT = 1
INTEGRATIONS_MIN_CHARGED_BYTES = 0
INTEGRATIONS_CHARS_PER_TOKEN = 4
INTEGRATIONS_MIN_TRUNCATION_CHARS = 200
INTEGRATIONS_MAX_TOOL_NAME_RESOURCE_CHARS = 24
INTEGRATIONS_RESOURCE_HASH_CHARS = 6
INTEGRATIONS_TRUNCATION_MARKER = "\n[vidbyte: content truncated to fit the context budget]"
INTEGRATIONS_RESERVED_TOOL_PARAMETERS = ("resource_id", "repo", "repository", "channel", "connection", "workspace")

__all__ = [
    "INTEGRATIONS_CHARS_PER_TOKEN",
    "INTEGRATIONS_DEFAULT_MAX_TOKENS",
    "INTEGRATIONS_DEFAULT_MAX_TOOL_BYTES",
    "INTEGRATIONS_DEFAULT_MAX_TOOL_CALLS",
    "INTEGRATIONS_MAX_SELECTIONS",
    "INTEGRATIONS_MAX_TOKENS_CEILING",
    "INTEGRATIONS_MAX_TOOL_BYTES_CEILING",
    "INTEGRATIONS_MAX_TOOL_CALLS_CEILING",
    "INTEGRATIONS_MAX_TOOL_NAME_RESOURCE_CHARS",
    "INTEGRATIONS_MIN_CHARGED_BYTES",
    "INTEGRATIONS_MIN_SELECTION_LIMIT",
    "INTEGRATIONS_MIN_TRUNCATION_CHARS",
    "INTEGRATIONS_RESERVED_TOOL_PARAMETERS",
    "INTEGRATIONS_RESOURCE_HASH_CHARS",
    "INTEGRATIONS_TRUNCATION_MARKER",
]
