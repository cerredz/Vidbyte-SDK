"""FILE: vidbyte/providers/typesafe.py

PURPOSE: Provider adapter for TypeSafe's System One API: sends a JevDecisionRequest directly to TypeSafe or through Vidbyte's managed gateway, returns Jev's answers as JevAnswer records, lists the models an account can use, and closes managed runs.
ROLE IN CODEBASE: `ModelProviders.decision()` builds this adapter and `vidbyte/lib/runners/decision.py` calls `run_decision` and `list_models` for programmatic Jev decisions.
ARCHITECTURE NOTE: The System One wire lives in `vidbyte/providers/systemone.py` (`SystemOneRequest` builds and encodes the body, `SystemOneAnswers` normalizes answers, `SystemOneProvider.HOSTS` holds TypeSafe's host row), and the HTTP call record and direct-mode failure wording live in `vidbyte/providers/decisions.py`; this module owns only what is TypeSafe-specific (managed gateway headers and run context, `/models`, run close). HTTP goes through vidbyte.lib.http only.
COMMON MODIFICATION PATTERNS: When the System One API changes, update the wire records, `SystemOneRequest`, and `SystemOneAnswers` together and extend the scripted-transport tests; change managed-gateway behaviour here.
KNOWN EDGE CASES: Score answers key probabilities by level index strings and carry a weighted `score` between levels; both normalize onto level labels. Noul answers carry no confidence. A malformed answer raises ProviderResponseError carrying the billed usage in details["usage"].
RELATED DOCS: docs/design/jev-agent-scaffold.md, https://docs.typesafe.ai/api.md, and https://docs.typesafe.ai/models.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_managed_gateway.py, tests/features/decision_model_providers/test_decision_regression_typesafe.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from contextvars import ContextVar, Token
from typing import Any

from vidbyte.lib.constants.jev import (
    JEV_IDEMPOTENCY_KEY_HEADER,
    JEV_MANAGED_RUN_ID_HEADER,
    JEV_MODELS_PATH,
    JEV_NO_RETRIES,
    JEV_STATUS_REQUEST_TIMEOUT,
    JEV_STATUS_SERVER_ERROR_FLOOR,
    JEV_SYSTEMONE_PATH,
    VIDBYTE_STATUS_FORBIDDEN,
    VIDBYTE_STATUS_PAYMENT_REQUIRED,
    VIDBYTE_STATUS_RATE_LIMITED,
    VIDBYTE_STATUS_UNAUTHORIZED,
)
from vidbyte.lib.dataclasses.jev import (
    JevDecisionRequest,
    JevManagedRunScope,
    JevModelCard,
    JevValidation,
)
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums import DecisionModelMode, ModelProvider
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
)
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.providers.decisions import DecisionFailures, DecisionHttpCall
from vidbyte.providers.systemone import (
    SystemOneAnswers,
    SystemOneProvider,
    SystemOneRequest,
)

_PROVIDER = ModelProvider.TYPESAFE.value
# TypeSafe's System One row: its display name labels every direct-mode message, and its documented model echo stays required.
_TYPESAFE_HOST = SystemOneProvider.HOSTS[ModelProvider.TYPESAFE]

# @intent the-run-follows-the-task
# A managed run spans the gate, done checks, continuation, and tool selector, which each build their own
# runner. A context variable reaches all of them, including asyncio.gather fan-out, without a parameter.
_MANAGED_RUN: ContextVar[JevManagedRunScope | None] = ContextVar("vidbyte_jev_managed_run", default=None)


class TypeSafeManagedRunContext:
    """The managed run, if any, that decision calls in the current task belong to."""

    @staticmethod
    def current() -> JevManagedRunScope | None:
        # Returns the innermost open managed run in this task's context.
        return _MANAGED_RUN.get()

    @staticmethod
    def enter(scope: JevManagedRunScope) -> Token[JevManagedRunScope | None]:
        # Makes scope the active run; the returned token restores the previous one.
        return _MANAGED_RUN.set(scope)

    @staticmethod
    def exit(token: Token[JevManagedRunScope | None]) -> None:
        # Restores whatever run was active before the matching enter.
        _MANAGED_RUN.reset(token)


class _TypeSafeCallBuilder:
    """Builds the typed HTTP calls for each TypeSafe endpoint from a resolved config."""

    def __init__(self, parser: HttpResponseParser) -> None:
        # Keeps the parser that formats the bearer-auth headers.
        self._parser = parser

    def decision(self, config: DecisionModelConfig, request: JevDecisionRequest, *, run_id: str | None = None) -> DecisionHttpCall:
        # Returns the POST /systemone call with the configured timeout and optional retries.
        # @intent decisions-retry-with-an-idempotency-key
        # Direct to TypeSafe a decision has no side effects, so the key only satisfies the transport's
        # POST retry guard. Through Vidbyte's gateway each answer is billed, so the key is also sent:
        # the gateway replays the answer it already billed instead of paying for a second one.
        retrying = config.retry_count > JEV_NO_RETRIES
        idempotency_key = uuid.uuid4().hex if retrying else None
        body = SystemOneRequest.encode(SystemOneRequest.build(config, request, host=_TYPESAFE_HOST))
        headers = self._parser.bearer_headers(config.resolved_api_key())
        if config.mode is DecisionModelMode.VIDBYTE_MANAGED:
            if run_id is not None:
                headers[JEV_MANAGED_RUN_ID_HEADER] = run_id
            if idempotency_key is not None:
                headers[JEV_IDEMPOTENCY_KEY_HEADER] = idempotency_key
        return DecisionHttpCall(method="POST", url=f"{config.resolved_endpoint()}{JEV_SYSTEMONE_PATH}", headers=headers, timeout_seconds=config.timeout_seconds, json_body=body, retry_count=config.retry_count, idempotency_key=idempotency_key)

    def close_run(self, config: DecisionModelConfig, run_id: str) -> DecisionHttpCall:
        # Returns the gateway's POST /runs/{run_id}/close call; it is sent once, because the reaper is the retry.
        return DecisionHttpCall(method="POST", url=config.resolved_run_close_url(run_id), headers=self._parser.bearer_headers(config.resolved_api_key()), timeout_seconds=config.timeout_seconds)

    def models(self, config: DecisionModelConfig) -> DecisionHttpCall:
        # Returns the GET /models call; GET is idempotent, so retries need no key.
        # @intent model-list-retries-without-a-key
        # The transport only demands an idempotency key for non-idempotent methods, so the
        # configured retry count applies to this read as-is.
        return DecisionHttpCall(method="GET", url=f"{config.resolved_endpoint()}{JEV_MODELS_PATH}", headers=self._parser.bearer_headers(config.resolved_api_key()), timeout_seconds=config.timeout_seconds, retry_count=config.retry_count)


class _TypeSafeFailures:
    """Rewrites transport and unexpected failures into errors that say what TypeSafe reported and how to fix it."""

    @staticmethod
    def transport_error(exc: ProviderRequestError, *, operation: str, config: DecisionModelConfig | None) -> ProviderRequestError:
        # Maps each documented HTTP status (and a missing response) to a specific, actionable message.
        # @intent http-failures-name-cause-and-fix
        # The generic transport error only says a request failed; TypeSafe documents what 401,
        # 422, 429, and 529 mean, so the rewritten message tells the caller which knob to turn.
        # Managed calls keep the credential-safe Vidbyte wording; direct calls share every decision host's wording.
        if config is not None and config.mode is DecisionModelMode.VIDBYTE_MANAGED:
            return _TypeSafeFailures.managed_transport_error(exc, operation=operation, timeout=f"{config.timeout_seconds}s", retries=config.retry_count)
        return DecisionFailures.transport_error(exc, operation=operation, provider=ModelProvider.TYPESAFE, label=_TYPESAFE_HOST.display_name, config=config)

    @staticmethod
    def managed_transport_error(exc: ProviderRequestError, *, operation: str, timeout: str, retries: int) -> ProviderRequestError:
        # Maps Vidbyte access and service statuses without copying untrusted response text.
        # @intent managed-error-output-never-echoes-gateway-body
        # Gateway bodies could reflect the bearer key, so managed exceptions keep only status and SDK-authored guidance.
        reason = _TypeSafeFailures.managed_failure_reason(exc.status_code, timeout=timeout, retries=retries)
        return ProviderRequestError(f"Vidbyte managed Jev {operation} request failed: {reason}.", provider="vidbyte", status_code=exc.status_code)

    @staticmethod
    def managed_failure_reason(status: int | None, *, timeout: str, retries: int) -> str:
        # Returns safe, actionable wording for one Vidbyte gateway status.
        # @intent managed-status-messages-are-credential-safe
        # Status-only guidance preserves useful repair information without copying an untrusted response message.
        if status == VIDBYTE_STATUS_UNAUTHORIZED:
            return "Vidbyte rejected the API key (401); check VIDBYTE_API_KEY and the key lifecycle status"
        if status == VIDBYTE_STATUS_PAYMENT_REQUIRED:
            return "Vidbyte requires available API balance (402); add balance to the API key's account"
        if status == VIDBYTE_STATUS_FORBIDDEN:
            return "Vidbyte denied models:invoke access (403); update the API key's scopes"
        if status == VIDBYTE_STATUS_RATE_LIMITED:
            return f"Vidbyte rate or quota limit was reached (429) after {retries} retries; retry after the limit resets"
        if status is None:
            return f"no response arrived (network failure or the {timeout} timeout elapsed); retry when connectivity returns"
        if status == JEV_STATUS_REQUEST_TIMEOUT:
            return f"Vidbyte or its upstream timed out the request (408) after {retries} retries"
        if status >= JEV_STATUS_SERVER_ERROR_FLOOR:
            return f"Vidbyte or its upstream is temporarily failing ({status}) after {retries} retries"
        return f"Vidbyte returned HTTP {status}"

    @staticmethod
    def managed_response_error(exc: ProviderResponseError) -> ProviderResponseError:
        # Keeps useful response context while removing bodies and any echoed Vidbyte key.
        # @intent malformed-managed-output-redacts-live-keys
        # Normalization details can include provider values, so redact live key forms and omit response excerpts.
        message = re.sub(r"vb_live_[A-Za-z0-9_-]{32,}", "[redacted]", exc.message)
        error = ProviderResponseError(message, provider="vidbyte", status_code=exc.status_code)
        usage = exc.details.get("usage")
        if isinstance(usage, Mapping):
            error.details["usage"] = dict(usage)
        return error

    @staticmethod
    def unexpected(exc: Exception, *, operation: str, usage: Mapping[str, Any] | None, config: DecisionModelConfig | None) -> ProviderResponseError:
        # Wraps an error no specific branch anticipated, keeping any billed usage for the caller.
        # @intent no-bare-exception-escapes-the-provider
        # Callers catch SDK errors to fail open; a stray TypeError from a drifted payload must
        # arrive as a ProviderResponseError, not as an exception type they never expected.
        # Direct calls share every decision host's wording; managed calls redact live keys and name Vidbyte.
        if config is None or config.mode is not DecisionModelMode.VIDBYTE_MANAGED:
            return DecisionFailures.unexpected(exc, operation=operation, provider=ModelProvider.TYPESAFE, usage=usage)
        message = re.sub(r"vb_live_[A-Za-z0-9_-]{32,}", "[redacted]", str(exc))
        error = ProviderResponseError(f"vidbyte {operation} failed with an unexpected {type(exc).__name__}: {message}", provider="vidbyte")
        if usage is not None:
            error.details["usage"] = dict(usage)
        return error


class _TypeSafeModelListNormalizer:
    """Turns a GET /models body into JevModelCard records."""

    @staticmethod
    def normalize(parsed: Mapping[str, Any]) -> tuple[JevModelCard, ...]:
        # Returns one card per listed model, raising ProviderResponseError on any malformed entry.
        # @intent model-list-drift-is-an-error
        # A partially parsed list would silently hide models, so any malformed entry fails the call.
        models = parsed.get("models")
        if not isinstance(models, list):
            raise ProviderResponseError(f"TypeSafe model list has no `models` array; received {JevValidation.describe(models)}.", provider=_PROVIDER)
        cards: list[JevModelCard] = []
        for index, entry in enumerate(models):
            if not isinstance(entry, Mapping):
                raise ProviderResponseError(f"TypeSafe model list entry {index} is not an object; received {JevValidation.describe(entry)}.", provider=_PROVIDER)
            name, description, release_date = (entry.get(key) for key in ("name", "description", "release_date"))
            if not isinstance(name, str) or not isinstance(description, str) or not isinstance(release_date, str):
                raise ProviderResponseError(f"TypeSafe model list entry {index} needs string name, description, and release_date; received {JevValidation.describe(dict(entry))}.", provider=_PROVIDER)
            try:
                cards.append(JevModelCard(name=name, description=description, release_date=release_date))
            except ConfigurationError as exc:
                raise ProviderResponseError(f"TypeSafe model list entry {index} was malformed: {exc.message}", provider=_PROVIDER) from exc
        return tuple(cards)


class TypeSafeProvider:
    """Decision-only provider adapter for TypeSafe's Jev models."""

    provider = ModelProvider.TYPESAFE

    def __init__(self, *, decision_config: DecisionModelConfig | None = None, response_parser: HttpResponseParser | None = None, **_: Any) -> None:
        # Stores the decision config; other factory kwargs are accepted and ignored.
        self._decision_config = decision_config
        self._parser = response_parser or HttpResponseParser()
        self._calls = _TypeSafeCallBuilder(self._parser)

    async def run_decision(self, *, request: JevDecisionRequest, transport: HttpTransport, config: DecisionModelConfig | None = None) -> DecisionModelResponse:
        # POSTs one System One request and returns its normalized answers, versioned model, and raw usage.
        # @intent one-guarded-decision-call
        # Every failure funnels through one try: missing config or key stays a configuration error,
        # a normalization failure keeps its billed usage, transport and HTTP failures are rewritten
        # per documented status, and anything unanticipated becomes a ProviderResponseError instead
        # of a bare exception. Cancellation is a BaseException and propagates untouched.
        usage: Mapping[str, Any] | None = None
        resolved: DecisionModelConfig | None = None
        try:
            resolved = self._config_for(config)
            scope = TypeSafeManagedRunContext.current() if resolved.mode is DecisionModelMode.VIDBYTE_MANAGED else None
            call = self._calls.decision(resolved, request, run_id=None if scope is None else scope.run_id)
            if scope is not None:
                scope.used = True
            response = await call.send(transport)
            parsed = self._parser.parse_json_response(response, provider=_PROVIDER)
            raw_usage = parsed.get("usage")
            usage = raw_usage if isinstance(raw_usage, Mapping) else None
            normalizer = SystemOneAnswers(usage, provider=ModelProvider.TYPESAFE, label=_TYPESAFE_HOST.display_name)
            answers = normalizer.normalize(request, parsed)
            # TypeSafe documents the versioned model that answered, so its echo is required and priced.
            model = normalizer.model(parsed, host=_TYPESAFE_HOST, fallback=resolved.resolved_model())
            return DecisionModelResponse(provider=self.provider, model=model, answers=answers, raw=parsed, usage=usage)
        except ProviderResponseError as exc:
            if resolved is not None and resolved.mode is DecisionModelMode.VIDBYTE_MANAGED:
                raise _TypeSafeFailures.managed_response_error(exc) from None
            raise
        except (ProviderConfigurationError, ConfigurationError):
            raise
        except ProviderRequestError as exc:
            error = _TypeSafeFailures.transport_error(exc, operation="decision", config=resolved)
            if resolved is not None and resolved.mode is DecisionModelMode.VIDBYTE_MANAGED:
                raise error from None
            raise error from exc
        except Exception as exc:
            failure = _TypeSafeFailures.unexpected(exc, operation="decision", usage=usage, config=resolved)
            if resolved is not None and resolved.mode is DecisionModelMode.VIDBYTE_MANAGED:
                raise failure from None
            raise failure from exc

    async def list_models(self, *, transport: HttpTransport, config: DecisionModelConfig | None = None) -> tuple[JevModelCard, ...]:
        # GETs the model IDs and aliases the account can send in the request `model` field.
        # @intent one-guarded-model-list-call
        # Same single-try failure mapping as run_decision, so both endpoints fail the same way.
        resolved: DecisionModelConfig | None = None
        try:
            resolved = self._config_for(config)
            response = await self._calls.models(resolved).send(transport)
            return _TypeSafeModelListNormalizer.normalize(self._parser.parse_json_response(response, provider=_PROVIDER))
        except ProviderResponseError as exc:
            if resolved is not None and resolved.mode is DecisionModelMode.VIDBYTE_MANAGED:
                raise _TypeSafeFailures.managed_response_error(exc) from None
            raise
        except (ProviderConfigurationError, ConfigurationError):
            raise
        except ProviderRequestError as exc:
            error = _TypeSafeFailures.transport_error(exc, operation="model list", config=resolved)
            if resolved is not None and resolved.mode is DecisionModelMode.VIDBYTE_MANAGED:
                raise error from None
            raise error from exc
        except Exception as exc:
            failure = _TypeSafeFailures.unexpected(exc, operation="model list", usage=None, config=resolved)
            if resolved is not None and resolved.mode is DecisionModelMode.VIDBYTE_MANAGED:
                raise failure from None
            raise failure from exc

    async def close_run(self, *, run_id: str, transport: HttpTransport, config: DecisionModelConfig | None = None) -> None:
        # Closes one managed run so the gateway settles its final part-cent now, not at the idle reaper.
        # @intent one-guarded-close-call
        # Same failure mapping as run_decision; the caller decides that a failed close never fails a run.
        resolved: DecisionModelConfig | None = None
        try:
            resolved = self._config_for(config)
            response = await self._calls.close_run(resolved, run_id).send(transport)
            self._parser.parse_json_response(response, provider=_PROVIDER)
        except ProviderResponseError as exc:
            if resolved is not None and resolved.mode is DecisionModelMode.VIDBYTE_MANAGED:
                raise _TypeSafeFailures.managed_response_error(exc) from None
            raise
        except (ProviderConfigurationError, ConfigurationError):
            raise
        except ProviderRequestError as exc:
            error = _TypeSafeFailures.transport_error(exc, operation="run close", config=resolved)
            if resolved is not None and resolved.mode is DecisionModelMode.VIDBYTE_MANAGED:
                raise error from None
            raise error from exc
        except Exception as exc:
            failure = _TypeSafeFailures.unexpected(exc, operation="run close", usage=None, config=resolved)
            if resolved is not None and resolved.mode is DecisionModelMode.VIDBYTE_MANAGED:
                raise failure from None
            raise failure from exc

    def _config_for(self, config: DecisionModelConfig | None) -> DecisionModelConfig:
        # Resolves the active config, raising when neither the call nor the adapter supplied one.
        # @intent per-call-config-wins
        # A per-call config overrides the adapter's, so one adapter can serve several model pins.
        resolved = config or self._decision_config
        if resolved is None:
            raise ProviderConfigurationError("TypeSafeProvider requires a DecisionModelConfig: pass config= to the call or decision_config= to the adapter.", provider=_PROVIDER)
        return resolved


__all__ = ["TypeSafeManagedRunContext", "TypeSafeProvider"]
