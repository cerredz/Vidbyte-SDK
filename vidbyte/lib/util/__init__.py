"""FILE: vidbyte/lib/util/__init__.py

PURPOSE:
    Public surface for vidbyte/lib/util, the home for general-purpose,
    domain-agnostic helper classes that have no dependency on any specific
    SDK feature (agents, sessions, harnesses, or otherwise).

ROLE IN CODEBASE:
    Re-exports MathHelper from vidbyte/lib/util/math.py,
    CredentialKeyPolicy from vidbyte/lib/util/credential_keys.py,
    SubstringCounter from vidbyte/lib/util/text.py, PromptPlacement from
    vidbyte/lib/util/prompt_placement.py, SupportedKwargs from
    vidbyte/lib/util/call_options.py, JsonText from
    vidbyte/lib/util/json_text.py, and SecretText from
    vidbyte/lib/util/secret_text.py. Imported by
    vidbyte/agents/speed/tracker.py and any future SDK code that needs the
    same general-purpose statistics.

ARCHITECTURE NOTE:
    A thin package export, mirroring how vidbyte/lib/enums/__init__.py and
    vidbyte/lib/dataclasses/__init__.py re-export their sibling modules.

FUNCTION INVENTORY:
    No functions of its own; re-exports MathHelper, CredentialKeyPolicy,
    SubstringCounter, PromptPlacement, SupportedKwargs, JsonText (the
    strict decoder of the one JSON object in a model answer), and
    SecretText (the exact-text scrub of known secret values). See
    vidbyte/lib/util/math.py for MathHelper's own inventory and
    vidbyte/lib/util/json_text.py for JsonText's.

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
    tests/test_agent_speed.py (MathHelperTests) covers MathHelper;
    tests/features/harness_compose/test_harness_compose_answers.py covers
    JsonText; tests/features/harness_compose/test_harness_compose_keys.py
    covers SecretText.
"""

from __future__ import annotations

from vidbyte.lib.util.call_options import SupportedKwargs
from vidbyte.lib.util.credential_keys import CredentialKeyPolicy
from vidbyte.lib.util.json_text import JsonText
from vidbyte.lib.util.math import MathHelper
from vidbyte.lib.util.prompt_placement import PromptPlacement
from vidbyte.lib.util.secret_text import SecretText
from vidbyte.lib.util.text import SubstringCounter

__all__ = ["CredentialKeyPolicy", "JsonText", "MathHelper", "PromptPlacement", "SecretText", "SubstringCounter", "SupportedKwargs"]
