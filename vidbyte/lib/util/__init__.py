"""FILE: vidbyte/lib/util/__init__.py

PURPOSE:
    Public surface for vidbyte/lib/util, the home for general-purpose,
    domain-agnostic helper classes that have no dependency on any specific
    SDK feature (agents, sessions, harnesses, or otherwise).

ROLE IN CODEBASE:
    Re-exports MathHelper from vidbyte/lib/util/math.py,
    CredentialKeyPolicy from vidbyte/lib/util/credential_keys.py,
    SubstringCounter and TokenEstimate from vidbyte/lib/util/text.py,
    AppendOnlyJsonl from vidbyte/lib/util/jsonl.py,
    PromptPlacement from
    vidbyte/lib/util/prompt_placement.py, SupportedKwargs from
    vidbyte/lib/util/call_options.py, and, on first access,
    FullTextIndex from vidbyte/lib/util/fulltext.py. Imported by
    vidbyte/agents/speed/tracker.py, by vidbyte/agents/infinite/ for
    TokenEstimate, AppendOnlyJsonl and FullTextIndex, and by any future
    SDK code that needs the same general-purpose helpers.

ARCHITECTURE NOTE:
    A thin package export, mirroring how vidbyte/lib/enums/__init__.py and
    vidbyte/lib/dataclasses/__init__.py re-export their sibling modules.
    FullTextIndex is the one lazy export: its module needs the records in
    vidbyte/lib/dataclasses/code_search.py, which need
    vidbyte/lib/dataclasses/validation.py, and validation imports
    vidbyte/lib/util/credential_keys.py, which runs this file first.

FUNCTION INVENTORY:
    Re-exports MathHelper, CredentialKeyPolicy, SubstringCounter,
    TokenEstimate, AppendOnlyJsonl, PromptPlacement, and SupportedKwargs;
    __getattr__ loads each name in _LAZY_EXPORTS from its module on first
    access. See vidbyte/lib/util/math.py for MathHelper's own inventory.

COMMON MODIFICATION PATTERNS:
    Add a new general-purpose helper class as its own module in this folder,
    then re-export it here. Code belongs here only when it would be equally
    at home in an unrelated project with no SDK dependencies.

WHAT NOT TO DO IN THIS FILE:
    1. Do not add feature-specific logic (agent, session, or harness
       behavior); that belongs in the owning feature package.
    2. Do not add import-time side effects.
    3. Do not import vidbyte/lib/util/fulltext.py at the top of this file;
       importing vidbyte.lib.dataclasses.validation first would then fail
       with a circular ImportError.

KNOWN EDGE CASES:
    None.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-speed-tracking.md

TESTS:
    tests/test_agent_speed.py (MathHelperTests) covers MathHelper,
    tests/features/infinite_memory_agent/test_infinite_memory_contract.py
    imports TokenEstimate from here, and tests/test_fulltext_index.py
    checks the FullTextIndex export.
"""

from __future__ import annotations

import importlib

from vidbyte.lib.util.call_options import SupportedKwargs
from vidbyte.lib.util.credential_keys import CredentialKeyPolicy
from vidbyte.lib.util.jsonl import AppendOnlyJsonl
from vidbyte.lib.util.math import MathHelper
from vidbyte.lib.util.prompt_placement import PromptPlacement
from vidbyte.lib.util.text import SubstringCounter, TokenEstimate

# Each name loaded from its module on first access, never at import.
_LAZY_EXPORTS = {"FullTextIndex": "vidbyte.lib.util.fulltext"}

__all__ = ["AppendOnlyJsonl", "CredentialKeyPolicy", "FullTextIndex", "MathHelper", "PromptPlacement", "SubstringCounter", "SupportedKwargs", "TokenEstimate"]


def __getattr__(name: str) -> object:
    """Return a lazily exported helper, importing its module on first access."""
    # @intent fulltext-export-loads-on-first-access
    # validation.py imports credential_keys, which runs this file while
    # validation is still loading; fulltext needs validation's checks for
    # its records, so importing it here then would fail. Loading it on
    # first access keeps every import order working.
    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module), name)
