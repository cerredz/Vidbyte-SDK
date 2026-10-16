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
    vidbyte/lib/util/prompt_placement.py, and SupportedKwargs from
    vidbyte/lib/util/call_options.py. Imported by
    vidbyte/agents/speed/tracker.py, by vidbyte/agents/infinite/ for
    TokenEstimate and AppendOnlyJsonl, and by any future SDK code that needs the same
    general-purpose helpers.

ARCHITECTURE NOTE:
    A thin package export, mirroring how vidbyte/lib/enums/__init__.py and
    vidbyte/lib/dataclasses/__init__.py re-export their sibling modules.

FUNCTION INVENTORY:
    No functions of its own; re-exports MathHelper, CredentialKeyPolicy,
    SubstringCounter, TokenEstimate, AppendOnlyJsonl, PromptPlacement, and
    SupportedKwargs. See
    vidbyte/lib/util/math.py for MathHelper's own inventory.

COMMON MODIFICATION PATTERNS:
    Add a new general-purpose helper class as its own module in this folder,
    then re-export it here. Code belongs here only when it would be equally
    at home in an unrelated project with no SDK dependencies.

WHAT NOT TO DO IN THIS FILE:
    1. Do not add feature-specific logic (agent, session, or harness
       behavior); that belongs in the owning feature package.
    2. Do not add import-time side effects.

KNOWN EDGE CASES:
    None.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-speed-tracking.md

TESTS:
    tests/test_agent_speed.py (MathHelperTests) covers MathHelper, and
    tests/features/infinite_memory_agent/test_infinite_memory_contract.py
    imports TokenEstimate from here.
"""

from __future__ import annotations

from vidbyte.lib.util.call_options import SupportedKwargs
from vidbyte.lib.util.credential_keys import CredentialKeyPolicy
from vidbyte.lib.util.jsonl import AppendOnlyJsonl
from vidbyte.lib.util.math import MathHelper
from vidbyte.lib.util.prompt_placement import PromptPlacement
from vidbyte.lib.util.text import SubstringCounter, TokenEstimate

__all__ = ["AppendOnlyJsonl", "CredentialKeyPolicy", "MathHelper", "PromptPlacement", "SubstringCounter", "SupportedKwargs", "TokenEstimate"]
