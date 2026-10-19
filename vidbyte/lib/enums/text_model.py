"""FILE: vidbyte/lib/enums/text_model.py

PURPOSE: Defines the three connection modes for text-model configurations: AUTO (through the Vidbyte gateway, relaying the caller's own provider key when one is held, Vidbyte-paid otherwise), VIDBYTE_MANAGED (through the gateway, always Vidbyte-paid), and DIRECT (straight to the provider with the caller's own key, no Vidbyte key and no fee); and the error codes the gateway's own refusals carry.
ROLE IN CODEBASE: TextModelConfig.mode and the agents' model_mode use these values; TextModelConfig.credentials() resolves the keys for the mode, and TextModelRunner and StreamingTextModelRunner read the resolved credentials to route, relay, or refuse a call. VidbyteGatewayTransport (vidbyte/lib/http/vidbyte_gateway.py) reads VidbyteGatewayErrorCode from a gateway error body to word the failure and to say whether a fresh call can succeed.
ARCHITECTURE NOTE: This lower-layer module declares values only and imports no provider, runner, or agent behavior. The error-code values are the backend's (backend/lib/errors/model_gateway.py), vendored in lint/contracts/vidbyte-platform-contract.json, so lint C019 rejects a value the platform never sends.
COMMON MODIFICATION PATTERNS: Add a mode only when its key source, endpoint policy, and runner routing are implemented together. Add an error code only after the platform contract exports it, together with its wording in the gateway transport and its row in VIDBYTE_GATEWAY_TRANSIENT_ERROR_CODES when a fresh call can succeed.
KNOWN EDGE CASES: AUTO always uses the gateway and needs a Vidbyte key, even when a provider key is held (the call then relays). DIRECT is the only unbilled path, and the only mode that streams or accepts an unserved provider or a custom endpoint. The gateway's API-key gatekeeper refuses a wrong key, a missing scope, or a spent request quota with an error body that has no code, so those failures never map to a member here.
RELATED DOCS: docs/spec/byok-api-keys/spec.md (sections 6.1 and 9.2 table R), docs/spec/managed-generative-models/spec.md, and field-guide/vidbyte-sdk/strict-config-dataclasses.md.
TESTS: tests/features/sdk_provider_keys/test_provider_keys_modes.py, tests/features/sdk_managed_text/test_managed_text_selection.py, and tests/features/sdk_managed_text/test_managed_text_error_surfacing.py.
"""

from __future__ import annotations

from enum import Enum


class TextModelMode(str, Enum):
    """Select the gateway (relayed or Vidbyte-paid), the gateway always Vidbyte-paid, or the provider directly."""

    AUTO = "auto"
    VIDBYTE_MANAGED = "vidbyte_managed"
    DIRECT = "direct"


class VidbyteGatewayErrorCode(str, Enum):
    """The code in a generative-gateway refusal body ({"error": true, "code": ...}), one per backend failure class."""

    AUTHENTICATION_REQUIRED = "model_gateway_authentication_required"
    PAYMENT_REQUIRED = "model_gateway_payment_required"
    UNSUPPORTED_MODEL = "model_gateway_unsupported_model"
    UNBILLABLE_REQUEST = "model_gateway_unbillable_request"
    REQUEST_TOO_LARGE = "model_gateway_request_too_large"
    DAILY_SPEND_CAP_REACHED = "model_gateway_daily_spend_cap_reached"
    UPSTREAM_FAILED = "model_gateway_upstream_failed"
    UNAVAILABLE = "model_gateway_unavailable"
    IDEMPOTENCY_IN_PROGRESS = "model_gateway_idempotency_in_progress"
    IDEMPOTENCY_KEY_REUSED = "model_gateway_idempotency_key_reused"


__all__ = ["TextModelMode", "VidbyteGatewayErrorCode"]
