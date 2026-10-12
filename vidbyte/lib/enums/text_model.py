"""FILE: vidbyte/lib/enums/text_model.py

PURPOSE: Defines the closed connection modes for text-model configurations: the caller's own provider key, or Vidbyte's managed generative gateway.
ROLE IN CODEBASE: TextModelConfig.mode uses these values; TextModelRunner and StreamingTextModelRunner read the resolved mode to route or refuse a call.
ARCHITECTURE NOTE: This lower-layer enum declares values only and imports no provider, runner, or agent behavior.
COMMON MODIFICATION PATTERNS: Add a mode only when its key source, endpoint policy, and runner routing are implemented together.
KNOWN EDGE CASES: AUTO still becomes managed when the key the fall-through selects is a Vidbyte key, so AUTO does not mean "never billed by Vidbyte".
RELATED DOCS: docs/spec/managed-generative-models/spec.md and field-guide/vidbyte-sdk/strict-config-dataclasses.md.
TESTS: tests/features/sdk_managed_text/test_managed_text_selection.py.
"""

from __future__ import annotations

from enum import Enum


class TextModelMode(str, Enum):
    """Select BYOK-unless-a-Vidbyte-key-is-selected, or always the Vidbyte-managed gateway."""

    AUTO = "auto"
    VIDBYTE_MANAGED = "vidbyte_managed"


__all__ = ["TextModelMode"]
