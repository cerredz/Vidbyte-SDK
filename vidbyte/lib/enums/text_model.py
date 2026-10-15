"""FILE: vidbyte/lib/enums/text_model.py

PURPOSE: Defines the three connection modes for text-model configurations: AUTO (through the Vidbyte gateway, relaying the caller's own provider key when one is held, Vidbyte-paid otherwise), VIDBYTE_MANAGED (through the gateway, always Vidbyte-paid), and DIRECT (straight to the provider with the caller's own key, no Vidbyte key and no fee).
ROLE IN CODEBASE: TextModelConfig.mode and the agents' model_mode use these values; TextModelConfig.credentials() resolves the keys for the mode, and TextModelRunner and StreamingTextModelRunner read the resolved credentials to route, relay, or refuse a call.
ARCHITECTURE NOTE: This lower-layer enum declares values only and imports no provider, runner, or agent behavior.
COMMON MODIFICATION PATTERNS: Add a mode only when its key source, endpoint policy, and runner routing are implemented together.
KNOWN EDGE CASES: AUTO always uses the gateway and needs a Vidbyte key, even when a provider key is held (the call then relays). DIRECT is the only unbilled path, and the only mode that streams or accepts an unserved provider or a custom endpoint.
RELATED DOCS: docs/spec/byok-api-keys/spec.md (sections 6.1 and 9.2 table R), docs/spec/managed-generative-models/spec.md, and field-guide/vidbyte-sdk/strict-config-dataclasses.md.
TESTS: tests/features/sdk_provider_keys/test_provider_keys_modes.py and tests/features/sdk_managed_text/test_managed_text_selection.py.
"""

from __future__ import annotations

from enum import Enum


class TextModelMode(str, Enum):
    """Select the gateway (relayed or Vidbyte-paid), the gateway always Vidbyte-paid, or the provider directly."""

    AUTO = "auto"
    VIDBYTE_MANAGED = "vidbyte_managed"
    DIRECT = "direct"


__all__ = ["TextModelMode"]
