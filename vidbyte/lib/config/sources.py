"""Context Protocol Header

Description:
    Shared configuration constants for artifact sources.
Purpose:
    Keeps source size limits and untrusted-content boundary strings in the SDK lib config
    namespace instead of feature-local modules.
Architecture:
    - DEFAULT_SOURCE_MAX_BYTES: Default fetched artifact size cap.
    - UNTRUSTED_CONTENT_BEGIN/END: Visible boundary markers for external content.
    - TEXTUAL_SOURCE_CONTENT_TYPES: Exact content types treated as textual.
Relations:
    Imported by vidbyte.sources.base and source loaders.
"""

from __future__ import annotations

from typing import Final

DEFAULT_SOURCE_MAX_BYTES: Final[int] = 5 * 1024 * 1024
UNTRUSTED_CONTENT_BEGIN: Final[str] = "----- BEGIN UNTRUSTED EXTERNAL CONTENT"
UNTRUSTED_CONTENT_END: Final[str] = "----- END UNTRUSTED EXTERNAL CONTENT -----"
TEXTUAL_SOURCE_CONTENT_TYPES: Final[frozenset[str]] = frozenset({"application/json", "application/xml"})

__all__ = [
    "DEFAULT_SOURCE_MAX_BYTES",
    "TEXTUAL_SOURCE_CONTENT_TYPES",
    "UNTRUSTED_CONTENT_BEGIN",
    "UNTRUSTED_CONTENT_END",
]
