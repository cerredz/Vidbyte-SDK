"""FILE: vidbyte/lib/http/vidbyte_gateway.py

PURPOSE: Sends every gateway text call (AUTO and VIDBYTE_MANAGED) to Vidbyte's one generative gateway route, wrapping the provider adapter's native body in the gateway envelope, relaying the caller's own provider key in its own header when the call has one, re-sending only the answers the gateway marks safe to retry with the same Idempotency-Key, and turning every failure into a credential-safe error worded for a relayed or a Vidbyte-paid call.
ROLE IN CODEBASE: TextModelRunner.arun wraps its transport in VidbyteGatewayTransport when its resolved TextCredentials use the gateway, passing the Vidbyte key and, for a relay call, the provider key; the unchanged provider adapters (OpenAI, Anthropic, Gemini, OpenAI-compatible) then reach the gateway instead of a vendor, and a 2xx JSON object goes back to the adapter unchanged, so DIRECT and gateway calls share one parser.
ARCHITECTURE NOTE: A decorator over HttpTransport: it discards the adapter's URL and headers, builds the gateway headers itself (bearer key, Idempotency-Key, and the optional X-Vidbyte-Provider-Key, each a subscript store with an imported constant, the shape lint C017 traces), and makes each attempt one inner request with no inner retries. Each except block only records which kind of exception the send raised; the error is raised after the block, so it carries no __cause__ or __context__ that could hold a response body.
COMMON MODIFICATION PATTERNS: A new gateway status gets its reason in _GatewayAnswer.gateway_reason; a change to which answers are re-sent changes _GatewayAnswer.retryable and the README together; the route, key format, and timeout floor live in vidbyte/lib/constants/jev.py.
KNOWN EDGE CASES: An answer that is not a JSON object (an HTML edge page, an empty body, a JSON array, truncated JSON) is an edge failure at any status, including 200, and is re-sent; a missing answer (network failure or timeout) is never re-sent, because a retry after a 630 s timeout would only meet the gateway's pending claim. Re-sends stop at one deadline per call (the call's own timeout from the first POST), but each attempt keeps its full timeout, so the worst case is about twice the timeout and a slow 502 gets at most one re-send; messages state how many re-sends the call made. A relayed vendor body nests an object under "error", which is not the gateway's top-level "error": true. Cancellation is never caught.
RELATED DOCS: docs/spec/managed-generative-models/spec.md (sections 8.5 and 9.2); docs/spec/byok-api-keys/spec.md (section 9.2 table G, D-15, D-16); field-guide/vidbyte-sdk/provider-api-contracts.md.
TESTS: tests/features/sdk_managed_text/test_managed_text_failures.py, tests/features/sdk_managed_text/test_managed_text_wire_contract.py, tests/features/sdk_managed_text/test_managed_text_acceptance.py, tests/features/sdk_provider_keys/test_provider_keys_failures.py, tests/features/sdk_provider_keys/test_provider_keys_wire_contract.py.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Mapping
from http import HTTPStatus

from vidbyte.lib.constants.jev import (
    JEV_DEFAULT_RETRY_COUNT,
    JEV_IDEMPOTENCY_KEY_HEADER,
    JEV_NO_RETRIES,
    JEV_RETRY_BACKOFF_SECONDS,
    JEV_STATUS_SERVER_ERROR_FLOOR,
    JEV_STATUS_UNPROCESSABLE,
    VIDBYTE_API_KEY_ENV_VAR,
    VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS,
    VIDBYTE_GENERATIVE_GATEWAY_ENDPOINT,
    VIDBYTE_PROVIDER_KEY_HEADER,
    VIDBYTE_STATUS_FORBIDDEN,
    VIDBYTE_STATUS_PAYMENT_REQUIRED,
    VIDBYTE_STATUS_RATE_LIMITED,
    VIDBYTE_STATUS_UNAUTHORIZED,
)
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http.parser import HttpResponseParser
from vidbyte.lib.http.transport import HttpResponse, HttpTransport


class _GatewayAnswer:
    """One gateway attempt's outcome: its answer and decoded body, or the kind of exception its send raised."""

    __slots__ = ("body", "raised", "response")

    def __init__(self, response: HttpResponse | None, raised: type[Exception] | None) -> None:
        # Decodes the body once, so the retry decision and the failure
        # wording read the same parse.
        self.response = response
        self.raised = raised
        self.body = self._json_object(response)

    def status(self) -> int | None:
        # The answer's HTTP status, or None when no answer arrived.
        return self.response.status_code if self.response is not None else None

    def succeeded(self) -> bool:
        # True for a 2xx answer whose body is a JSON object.
        status = self.status()
        return status is not None and self.body is not None and HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES

    def retryable(self) -> bool:
        """Return True for a 409, a 502, or an answer that is not a JSON object."""
        # @intent only-answers-the-gateway-replays-are-retried
        # A same-key retry is answered from the gateway's replay, so it
        # never pays twice; a missing answer is not one of them, because
        # a retry after the timeout would only meet the pending claim.
        status = self.status()
        if status is None:
            return False
        return self.body is None or status in (HTTPStatus.CONFLICT, HTTPStatus.BAD_GATEWAY)

    def failure_reason(self, provider: ModelProvider, timeout_seconds: float, resends: int, relays: bool) -> str:
        """Explain why this attempt failed, from its status, its shape, and whether the call relayed a provider key."""
        # @intent managed-failures-never-echo-a-response-body
        # Gateway and vendor bodies can reflect the bearer key or the
        # relayed provider key, so every reason is written by the SDK
        # and no body text is ever copied.
        status = self.status()
        retried = f"the SDK re-sent it with the same Idempotency-Key (re-sends in this call: {resends})"
        if resends == JEV_NO_RETRIES:
            retried = f"the SDK did not re-send it, because the call's {timeout_seconds:g} s timeout left no time for another attempt"
        if status is None and self.raised is ProviderRequestError:
            return f"no response arrived (network failure, or the {timeout_seconds:g} s timeout elapsed), and Vidbyte may already have billed the call"
        if status is None:
            return "the request failed before an answer arrived, and if it reached Vidbyte it may have been billed"
        if self.body is None:
            return f"Vidbyte's hosting edge answered HTTP {status} instead of the gateway (usually during a deploy or restart); {retried}, the failure is usually transient, and Vidbyte may already have billed the call"
        if self.body.get("error") is True:
            return self.gateway_reason(status, retried, provider, relays)
        # @intent relayed-refusal-blames-the-callers-own-key
        # On a relay call a provider 401, 402, or 403 answers the
        # caller's own key or account, so the remedy is theirs to fix,
        # never a Vidbyte wallet, quota, or cap.
        if relays and status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.PAYMENT_REQUIRED, HTTPStatus.FORBIDDEN):
            return f"{provider.value} refused the call made with your own {provider.value} key (HTTP {status}): the key is wrong or revoked, lacks access to this model, or its {provider.value} account cannot pay; the provider's message is withheld, and Vidbyte did not bill the call"
        relayed = f"{provider.value} returned HTTP {status} through the Vidbyte gateway; the provider's message is withheld, and the call was not billed"
        return f"{relayed}; {retried}" if status in (HTTPStatus.CONFLICT, HTTPStatus.BAD_GATEWAY) else relayed

    def gateway_reason(self, status: int, retried: str, provider: ModelProvider, relays: bool) -> str:
        """Look up the remedy for one gateway error status, worded for a relay call or a Vidbyte-paid call."""
        # @intent gateway-status-names-its-remedy
        # The gateway's own error code is body text, so the remedy comes
        # from the status alone, which is all the caller needs to act.
        # Under relay the wallet pays only Vidbyte's fee, no daily cap
        # applies, and no Vidbyte account is behind the call, so those
        # remedies are worded differently there.
        reasons = {
            VIDBYTE_STATUS_UNAUTHORIZED: f"Vidbyte rejected the Vidbyte API key (HTTP {status}); check {VIDBYTE_API_KEY_ENV_VAR} or vidbyte_api_key",
            VIDBYTE_STATUS_PAYMENT_REQUIRED: f"your own Vidbyte wallet balance is too low for this call (HTTP {status}, which never means a provider's billing); top up the wallet, or add your own provider key for {provider.value} to api_keys so the wallet pays only Vidbyte's fee",
            VIDBYTE_STATUS_FORBIDDEN: f"the Vidbyte API key lacks the models:invoke scope (HTTP {status}); grant that scope to the key",
            HTTPStatus.CONFLICT: f"an earlier attempt of this call is still running at Vidbyte (HTTP {status}) and may still complete and be billed; {retried}, so wait before sending the request again, because a new request may pay twice",
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE: f"the request exceeds the gateway's 2,000,000-byte limit, measured as JSON with non-ASCII characters escaped (HTTP {status}); shorten the context, or use TextModelMode.DIRECT to send it straight to the provider",
            JEV_STATUS_UNPROCESSABLE: f"the gateway cannot manage this request (HTTP {status}); the causes are an unmanaged or unpriced provider or model, a malformed model name, streaming, a missing or invalid output-token limit, a body model that differs from the model (or any body model for Gemini), a hosted (non-function) tool, a service tier, a previous-response or conversation reference, or a body field outside the gateway's allowed list, including Gemini snake_case keys; to send a request the gateway cannot bill, use TextModelMode.DIRECT, which sends it straight to the provider with your own key",
            VIDBYTE_STATUS_RATE_LIMITED: f"the Vidbyte API key reached its request quota or its daily managed spend cap (HTTP {status}); wait for the limit to reset, or raise the cap",
        }
        if relays:
            reasons[VIDBYTE_STATUS_PAYMENT_REQUIRED] = f"your Vidbyte wallet balance is too low for Vidbyte's fee on this call (HTTP {status}, which never means a provider's billing); top up the wallet"
            reasons[VIDBYTE_STATUS_RATE_LIMITED] = f"the Vidbyte API key reached its request quota (HTTP {status}); wait for the quota to reset"
        if status in reasons:
            return reasons[status]
        if status < JEV_STATUS_SERVER_ERROR_FLOOR:
            return f"Vidbyte returned HTTP {status}"
        cause = "is unavailable" if relays else "is unavailable or refused Vidbyte's own account"
        unavailable = f"the Vidbyte gateway, or the provider behind it, {cause} (HTTP {status}), and the cause is not known"
        return f"{unavailable}; {retried}" if status == HTTPStatus.BAD_GATEWAY else unavailable

    @staticmethod
    def _json_object(response: HttpResponse | None) -> Mapping[str, object] | None:
        # The body as a JSON object, or None when it is not one.
        if response is None:
            return None
        try:
            decoded = json.loads(response.body)
        except ValueError:
            return None
        return decoded if isinstance(decoded, dict) else None


class VidbyteGatewayTransport(HttpTransport):
    """Sends a provider adapter's native request to Vidbyte's generative gateway, with same-key retries and credential-safe errors."""

    def __init__(self, inner: HttpTransport, *, provider: ModelProvider, model: str, api_key: str, provider_api_key: str | None = None) -> None:
        """Keep the transport that sends each attempt and what this call's envelope and headers carry."""
        # @intent one-gateway-transport-per-call-holds-the-bearer
        # The runner builds one transport for each gateway call, so the
        # Vidbyte key, the relayed provider key, and this call's
        # envelope fields live only as long as the call and are never
        # shared with a concurrent one. Neither key is ever logged.
        self._inner = inner
        self._provider = provider
        self._model = model
        self._api_key = api_key
        self._provider_api_key = provider_api_key
        self._parser = HttpResponseParser()

    async def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, object] | None = None,
        timeout_seconds: float = VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS,
        **transport_options: object,
    ) -> HttpResponse:
        """Send the adapter's body through the gateway and return the provider's answer, or raise a credential-safe error."""
        # Mint one key for this call; every retry of it reuses the key,
        # so the gateway answers a retry from its replay instead of
        # paying the provider again.
        idempotency_key = uuid.uuid4().hex
        # @intent managed-request-reaches-only-the-gateway
        # Build the gateway headers from the Vidbyte bearer key, JSON,
        # the idempotency key, and, on a relay call, the provider key.
        # The adapter's vendor URL and headers are dropped, so the
        # Vidbyte key goes only to the gateway and never sits in a
        # vendor header, and the provider key travels only in its own
        # header.
        gateway_headers = self._parser.bearer_headers(self._api_key)
        gateway_headers[JEV_IDEMPOTENCY_KEY_HEADER] = idempotency_key
        if self._provider_api_key is not None:
            gateway_headers[VIDBYTE_PROVIDER_KEY_HEADER] = self._provider_api_key
        # Wrap the adapter's body, unchanged, in the envelope the
        # gateway bills from.
        envelope: dict[str, object] = {"provider": self._provider.value, "model": self._model, "body": dict(json_body or {})}
        # Give the whole call one deadline, its own timeout from now, so
        # re-sends cannot stretch it without bound; each attempt still
        # gets the full timeout, because a cut-short attempt could give
        # up on a call the gateway is still finishing and billing.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        # Send it once, then re-send while the answer is one the gateway
        # marks safe to retry and the deadline leaves time for the wait,
        # waiting longer before each retry; resends counts the re-sends
        # already made, so the error can say how many there were.
        answer = await self._send(envelope=envelope, headers=gateway_headers, idempotency_key=idempotency_key, timeout_seconds=timeout_seconds)
        retry_wait = JEV_RETRY_BACKOFF_SECONDS
        for resends in range(JEV_DEFAULT_RETRY_COUNT):
            if not answer.retryable() or loop.time() + retry_wait >= deadline:
                break
            await asyncio.sleep(retry_wait)
            retry_wait += JEV_RETRY_BACKOFF_SECONDS
            answer = await self._send(envelope=envelope, headers=gateway_headers, idempotency_key=idempotency_key, timeout_seconds=timeout_seconds)
        else:
            # Every allowed re-send was made.
            resends = JEV_DEFAULT_RETRY_COUNT
        # Hand a 2xx JSON object to the adapter exactly as it came back.
        if answer.succeeded() and answer.response is not None:
            return answer.response
        # Otherwise raise the last attempt's failure, worded by the SDK
        # for a relay call or a Vidbyte-paid call.
        reason = answer.failure_reason(self._provider, timeout_seconds, resends, self._provider_api_key is not None)
        raise ProviderRequestError(f"Vidbyte gateway {self._provider.value} request failed: {reason}.", provider="vidbyte", status_code=answer.status())

    async def _send(self, *, envelope: Mapping[str, object], headers: Mapping[str, str], idempotency_key: str, timeout_seconds: float) -> _GatewayAnswer:
        """Make one POST to the gateway and record what came back."""
        # @intent one-gateway-attempt-records-no-exception
        # Only the kind of exception is kept, never the instance, so no
        # response excerpt or exception text can reach the raised error;
        # cancellation is not an Exception and still propagates.
        response: HttpResponse | None = None
        raised: type[Exception] | None = None
        try:
            response = await self._inner.request(method="POST", url=VIDBYTE_GENERATIVE_GATEWAY_ENDPOINT, headers=headers, json_body=envelope, timeout_seconds=timeout_seconds, idempotency_key=idempotency_key)
        except ProviderRequestError:
            raised = ProviderRequestError
        except Exception:
            raised = Exception
        return _GatewayAnswer(response, raised)


__all__ = ["VidbyteGatewayTransport"]
