"""FILE: vidbyte/providers/decisions.py

PURPOSE: Shared plumbing for every decision adapter: `DecisionTransport`, which sends a `DecisionHttpCall` as the one bounded, timed, retrying HTTP call a decision adapter makes, and `DecisionFailures`, which rewrites transport and unexpected failures into messages that name the host and the setting to fix. The validated `DecisionHttpCall` record is defined in `vidbyte/lib/dataclasses/jev.py` and re-exported here.
ROLE IN CODEBASE: `vidbyte/providers/typesafe.py`, `vidbyte/providers/systemone.py`, and `vidbyte/providers/openai_decisions.py` build a `DecisionHttpCall` (defined in `vidbyte/lib/dataclasses/jev.py`) per request, send it with `DecisionTransport.send`, and route their failures through `DecisionFailures`; `vidbyte/lib/runners/decision.py` sees only the typed errors these produce.
ARCHITECTURE NOTE: Imports only `vidbyte.lib` (A006): constants, records, registries, errors, and `vidbyte.lib.http`, which owns the transport. The managed TypeSafe gateway's credential-safe wording stays in `typesafe.py`; this module holds the direct-mode wording every host shares.
COMMON MODIFICATION PATTERNS: A newly documented status adds one branch to `DecisionFailures.transport_error` worded with `label`; a new transport limit is a constant in `vidbyte/lib/constants/jev.py` passed through `DecisionTransport.send`.
KNOWN EDGE CASES: A `ProviderRequestError` without a status code means no response arrived (network failure or timeout). The config may be None when the failure happened before a config resolved, so the message falls back to "configured" and zero retries. `DecisionHttpCall.headers` (the record in `vidbyte/lib/dataclasses/jev.py`) stay out of `repr` because they carry the API key.
RELATED DOCS: vidbyte/providers/README.md ("Endpoint And Auth Matrix", "Decision providers"), docs/spec/decision-model-providers/spec.md, https://docs.typesafe.ai/api.md.
TESTS: tests/features/decision_model_providers/test_decision_failures.py, tests/features/decision_model_providers/test_decision_regression_typesafe.py, tests/test_jev_agent.py, and tests/test_jev_managed_gateway.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.constants.jev import (
    JEV_MAX_RESPONSE_BYTES,
    JEV_NO_RETRIES,
    JEV_RETRY_BACKOFF_SECONDS,
    JEV_RETRY_STATUS_CODES,
    JEV_STATUS_OVERLOADED,
    JEV_STATUS_RATE_LIMITED,
    JEV_STATUS_REQUEST_TIMEOUT,
    JEV_STATUS_SERVER_ERROR_FLOOR,
    JEV_STATUS_UNAUTHORIZED,
    JEV_STATUS_UNPROCESSABLE,
)
from vidbyte.lib.dataclasses.jev import DecisionHttpCall
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderRequestError, ProviderResponseError
from vidbyte.lib.http import HttpResponse, HttpTransport
from vidbyte.lib.registries.models import ProviderModelRegistry


class DecisionTransport:
    """Sends a validated DecisionHttpCall with the transport policy every decision host shares."""

    @staticmethod
    async def send(call: DecisionHttpCall, transport: HttpTransport) -> HttpResponse:
        # Sends the call with the bounded body size, retry statuses, and backoff every decision host shares.
        # @intent decision-calls-share-one-transport-policy
        # Every decision host is called with the same timeout, retry, backoff, and response-size bounds, so a
        # runaway or flaky vendor fails the same documented way whichever adapter sent the call.
        return await transport.request(method=call.method, url=call.url, headers=call.headers, json_body=call.json_body, timeout_seconds=call.timeout_seconds, retry_count=call.retry_count, backoff_seconds=JEV_RETRY_BACKOFF_SECONDS, retry_status_codes=JEV_RETRY_STATUS_CODES, max_response_bytes=JEV_MAX_RESPONSE_BYTES, idempotency_key=call.idempotency_key)


class DecisionFailures:
    """Rewrites transport and unexpected failures into errors that say which host failed, why, and what to change."""

    @staticmethod
    def transport_error(exc: ProviderRequestError, *, operation: str, provider: ModelProvider, label: str, config: DecisionModelConfig | None) -> ProviderRequestError:
        # Maps each documented HTTP status (and a missing response) to a specific, actionable message.
        # @intent http-failures-name-cause-and-fix
        # The generic transport error only says a request failed; the decision hosts document what 401,
        # 422, 429, and 529 mean, so the rewritten message names the host and the knob to turn.
        status = exc.status_code
        timeout = f"{config.timeout_seconds}s" if config is not None else "configured"
        retries = config.retry_count if config is not None else JEV_NO_RETRIES
        # Name the environment variable this provider's key comes from, so the fix points at the right setting.
        env_var = ProviderModelRegistry.get_api_key_env_var(provider)
        if status is None:
            reason = f"no response arrived (network failure or the {timeout} timeout elapsed); raise DecisionModelConfig.timeout_seconds or retry_count if this recurs"
        elif status == JEV_STATUS_UNAUTHORIZED:
            reason = f"{label} rejected the API key (401); check {env_var} or DecisionModelConfig.api_key"
        elif status == JEV_STATUS_UNPROCESSABLE:
            reason = f"{label} rejected the request body as invalid (422); the response excerpt names the offending field"
        elif status == JEV_STATUS_RATE_LIMITED:
            reason = f"{label}'s rate limit was exceeded (429) after {retries} retries; back off or raise DecisionModelConfig.retry_count"
        elif status == JEV_STATUS_OVERLOADED or status >= JEV_STATUS_SERVER_ERROR_FLOOR:
            reason = f"{label} is overloaded or failing ({status}) after {retries} retries; retry after a short delay"
        elif status == JEV_STATUS_REQUEST_TIMEOUT:
            reason = f"{label} timed out the request (408) after {retries} retries"
        else:
            reason = f"{label} returned HTTP {status}"
        # Keep the status code and the bounded response excerpt so callers can branch on them.
        return ProviderRequestError(f"{label} {operation} request failed: {reason}. Underlying error: {exc.message}", provider=provider.value, status_code=status, response_excerpt=exc.response_excerpt)

    @staticmethod
    def unexpected(exc: Exception, *, operation: str, provider: ModelProvider, usage: Mapping[str, Any] | None, message: str | None = None) -> ProviderResponseError:
        # Wraps an error no specific branch anticipated, keeping any billed usage for the caller.
        # @intent no-bare-exception-escapes-the-provider
        # Callers catch SDK errors to fail open; a stray TypeError from a drifted payload must arrive as a
        # ProviderResponseError, not as an exception type they never expected. `message` replaces the
        # exception text for a caller that must clean it first.
        text = message if message is not None else str(exc)
        error = ProviderResponseError(f"{provider.value} {operation} failed with an unexpected {type(exc).__name__}: {text}", provider=provider.value)
        if usage is not None:
            error.details["usage"] = dict(usage)
        return error


__all__ = ["DecisionFailures", "DecisionHttpCall", "DecisionTransport"]
