"""FILE: vidbyte/harnesses/native/backends/profiles.py

PURPOSE: Defines HarnessBackends, the six functions over the two declared Anthropic-compatible backend profiles (GLM through Z.ai, and DeepSeek): list the profiles, build the Claude Code environment for one, check a key is usable, check a request's harness and features, read the DeepSeek balance, and describe the opencode provider wiring.
ROLE IN CODEBASE: Re-exported as module functions by vidbyte/harnesses/native/backends/__init__.py; called by the backend tools in vidbyte/tools/builtins/harness_backends/ and by OpencodeServer when an opencode host adds backends. Reads HARNESS_BACKENDS from vidbyte/lib/configs/harness_backends.py.
ARCHITECTURE NOTE: A class of static methods with no state. Keys are read from os.environ on every call and live only in ClaudeBackendEnv.auth_token or the Bearer header of the one balance request. Every NativeHostError is built by a per-call NativeErrorFactory that has the key registered, so vendor text echoing it is redacted. The balance call goes through HttpTransport with BACKEND_HTTP_TIMEOUT_SECONDS and BACKEND_MAX_RESPONSE_BYTES, no retry and no redirect.
FUNCTION INVENTORY: list_harness_backends, build_claude_backend_env, check_backend_ready, check_backend_compat, get_deepseek_balance and build_opencode_backend_provider are the public functions; _profile, _claude_model, _require_harness, _key, _read_balance, _send_balance_request, _check_balance_status, _vendor_text and _parse_balance are their steps.
COMMON MODIFICATION PATTERNS: A new backend adds its profile in vidbyte/lib/configs/harness_backends.py and its model slots in _CLAUDE_MODEL_SLOTS; a new balance status mapping is one branch in _check_balance_status.
WHAT NOT TO DO IN THIS FILE: 1. Do not cache a key between calls or put one in a message, context value or repr. 2. Do not add a call that spends tokens to verify a key (D-17); GLM is checked by its variable only. 3. Do not follow redirects or retry the balance call; a redirect is reported as api_error.
KNOWN EDGE CASES: A blank key variable counts as unset. A balance body over the size cap raises protocol_mismatch, while a transport failure with no status raises server_unreachable. check_backend_compat checks the harness before the features, although no declared profile shows the order.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.6, §8.5 (Backends), §9.1 (The two declared profiles), D-16, D-17
TESTS: tests/features/native_backends/test_native_backends_profiles.py, tests/features/native_backends/test_native_backends_balance.py, tests/features/native_backends/test_native_backends_errors.py, tests/features/native_backends/test_native_backends_security.py
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.lib.configs.harness_backends import HARNESS_BACKENDS
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.harness_backends import (
    BackendCompatRequest,
    BackendReadiness,
    ClaudeBackendEnv,
    DeepseekBalance,
    DeepseekBalanceEntry,
    HarnessBackend,
    OpencodeBackendProvider,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.harness_backends import HarnessBackendName
from vidbyte.lib.enums.native_hosts import NativeHarness
from vidbyte.lib.errors import ConfigurationError, NativeHostError, ProviderRequestError
from vidbyte.lib.http.transport import HttpResponse, HttpTransport

# The Claude Code variables build_claude_backend_env fills with the chosen model (spec §9.1 profile table).
_CLAUDE_MODEL_SLOTS: Mapping[HarnessBackendName, tuple[str, ...]] = MappingProxyType(
    {
        HarnessBackendName.GLM: ("ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL"),
        HarnessBackendName.DEEPSEEK: ("ANTHROPIC_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL"),
    }
)
_BASE_URL_VARIABLE = "ANTHROPIC_BASE_URL"
_KEY_REJECTED_STEP = "DeepSeek rejected {variable}; set a valid key."
_BODY_FIELD = "body"
# Backend errors use explicit backend.* codes; the factory's harness only labels
# process and transport failures, which the backend functions never raise.
_ERROR_HARNESS = NativeHarness.CLAUDE_CODE


class HarnessBackends:
    """The six backend functions over HARNESS_BACKENDS; every failure is a NativeHostError with a backend or argument code."""

    @staticmethod
    def list_harness_backends() -> tuple[HarnessBackend, ...]:
        # The declared profiles in HarnessBackendName order; no key and no I/O.
        return HARNESS_BACKENDS

    @staticmethod
    def build_claude_backend_env(backend: HarnessBackendName | str, model: str | None = None) -> ClaudeBackendEnv:
        operation = "build_claude_backend_env"
        errors = NativeErrorFactory(_ERROR_HARNESS)
        try:
            # Resolve the backend and the model before anything else, so a bad argument fails first.
            profile = HarnessBackends._profile(backend)
            chosen = HarnessBackends._claude_model(profile, model, errors, operation=operation)

            # Refuse a backend whose terms do not cover Claude Code.
            HarnessBackends._require_harness(profile, NativeHarness.CLAUDE_CODE, errors, operation=operation)

            # Read the key now, on every call, so a changed variable takes effect at once.
            key = HarnessBackends._key(profile, errors, operation=operation)

            # The public pairs are the endpoint, the profile's fixed pairs and the model slots; the key stays apart.
            public_env = {_BASE_URL_VARIABLE: profile.anthropic_base_url, **profile.claude_env, **dict.fromkeys(_CLAUDE_MODEL_SLOTS[profile.name], chosen)}
            return ClaudeBackendEnv(backend=profile.name, model=chosen, public_env=public_env, auth_token=key)
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, operation=operation) from exc

    @staticmethod
    async def check_backend_ready(backend: HarnessBackendName | str) -> BackendReadiness:
        # @intent backend-ready-without-spending
        # Readiness never spends tokens or money (D-17): GLM is checked by its
        # key variable alone, DeepSeek by its free balance read, and an account
        # that reports is_available=false is a billing error, not readiness.
        operation = "check_backend_ready"
        errors = NativeErrorFactory(_ERROR_HARNESS)
        try:
            # Resolve the backend and make sure its key variable is set.
            profile = HarnessBackends._profile(backend)
            key = HarnessBackends._key(profile, errors, operation=operation)

            # GLM has no free endpoint to verify a key, so the variable is the whole check (D-17).
            if profile.balance_url is None:
                return BackendReadiness(backend=profile.name, remote_verified=False)

            # DeepSeek's balance read verifies the key without spending anything.
            balance = await HarnessBackends._read_balance(profile.balance_url, key, errors, operation=operation)

            # An account that cannot serve calls is not ready, whatever its listed balances.
            if not balance.is_available:
                currencies = errors.listing(entry.currency for entry in balance.balances)
                raise errors.build(FailureCode.BACKEND_BILLING_ERROR, "DeepSeek reports that the account cannot serve calls.", operation=operation, context={"vendor_error": f"is_available=false; currencies={currencies}"})
            return BackendReadiness(backend=profile.name, remote_verified=True, balance=balance)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, operation=operation) from exc

    @staticmethod
    def check_backend_compat(backend: HarnessBackendName | str, request: BackendCompatRequest) -> None:
        # @intent backend-compat-harness-before-features
        # The harness is checked before the features: a harness the backend's
        # terms forbid is the first thing to fix, whatever features the
        # request lists (spec §6.3.6). No key and no I/O.
        operation = "check_backend_compat"
        errors = NativeErrorFactory(_ERROR_HARNESS)
        try:
            # Resolve the backend and make sure the request is the record this check reads.
            profile = HarnessBackends._profile(backend)
            compat = RecordFieldConverter.require_instance(request, "request", BackendCompatRequest)

            # Refuse a harness the backend's terms do not allow.
            HarnessBackends._require_harness(profile, compat.harness, errors, operation=operation)

            # Refuse features the endpoint would silently ignore, naming every one of them.
            ignored = sorted(feature.value for feature in compat.features & profile.unsupported_features)
            if ignored:
                raise errors.build(FailureCode.BACKEND_FEATURE_UNSUPPORTED, f"The {profile.name.value} endpoint silently ignores these request features.", operation=operation, context={"features": errors.listing(ignored)})
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, operation=operation) from exc

    @staticmethod
    async def get_deepseek_balance() -> DeepseekBalance:
        operation = "get_deepseek_balance"
        errors = NativeErrorFactory(_ERROR_HARNESS)
        try:
            # Only DeepSeek has a balance endpoint; its key is the only one this call reads.
            profile = HarnessBackends._profile(HarnessBackendName.DEEPSEEK)
            key = HarnessBackends._key(profile, errors, operation=operation)

            # Read the balance; is_available=false is data here, not an error.
            return await HarnessBackends._read_balance(str(profile.balance_url), key, errors, operation=operation)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, operation=operation) from exc

    @staticmethod
    def build_opencode_backend_provider(backend: HarnessBackendName | str) -> OpencodeBackendProvider:
        # @intent backend-opencode-provider-holds-names-only
        # The provider wiring names the variable to copy and the variable the
        # server reads; it never holds or checks a key value, because the
        # opencode host reads and checks the key itself when it starts.
        operation = "build_opencode_backend_provider"
        errors = NativeErrorFactory(_ERROR_HARNESS)
        try:
            # Resolve the backend and refuse one whose terms do not cover opencode.
            profile = HarnessBackends._profile(backend)
            HarnessBackends._require_harness(profile, NativeHarness.OPENCODE, errors, operation=operation)

            # Name opencode's built-in provider, the key variable to copy from and into, and the models.
            return OpencodeBackendProvider(backend=profile.name, provider_id=profile.opencode_provider_id, source_env_var=profile.auth_env_var, child_env_var=profile.opencode_key_env_var, model_ids=profile.opencode_models)
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, operation=operation) from exc

    @staticmethod
    def _profile(backend: object) -> HarnessBackend:
        # The declared profile for a HarnessBackendName member or its exact value string (EC-122).
        name = RecordFieldConverter.to_enum(backend, HarnessBackendName, "backend")
        return next(profile for profile in HARNESS_BACKENDS if profile.name is name)

    @staticmethod
    def _claude_model(profile: HarnessBackend, model: object, errors: NativeErrorFactory, *, operation: str) -> str:
        # The profile's first model when none is given; otherwise a declared model of this profile (EC-124, EC-125).
        if model is None:
            return profile.claude_models[0]
        chosen = RecordFieldValidator.require_text(model, "model", max_chars=native_host_constants.NATIVE_ID_MAX_CHARS)
        if chosen not in profile.claude_models:
            raise errors.build(FailureCode.BACKEND_MODEL_UNKNOWN, f"The model is not declared for the {profile.name.value} backend.", operation=operation, context={"available_models": errors.listing(profile.claude_models)})
        return chosen

    @staticmethod
    def _require_harness(profile: HarnessBackend, harness: NativeHarness, errors: NativeErrorFactory, *, operation: str) -> None:
        # Refuses a harness outside the profile's allowed_harnesses (EC-126, EC-135, EC-137).
        if harness not in profile.allowed_harnesses:
            raise errors.build(FailureCode.BACKEND_HARNESS_NOT_ALLOWED, f"The {profile.name.value} backend's terms do not allow the {harness.value} harness.", operation=operation)

    @staticmethod
    def _key(profile: HarnessBackend, errors: NativeErrorFactory, *, operation: str) -> str:
        # @intent backend-key-read-per-call-and-registered-secret
        # The key comes from os.environ on every call and is registered with
        # the error factory, so any vendor text that echoes it is redacted.
        # A blank value counts as unset, and the error names the variable,
        # never its value (EC-123).
        key = os.environ.get(profile.auth_env_var, "")
        if not key.strip():
            raise errors.build(FailureCode.BACKEND_NOT_SIGNED_IN, f"{profile.auth_env_var} is not set in the environment.", operation=operation, next_step=native_host_constants.BACKEND_KEY_MISSING_NEXT_STEP.format(variable=profile.auth_env_var))
        errors.register_secret(key)
        return key

    @staticmethod
    async def _read_balance(url: str, key: str, errors: NativeErrorFactory, *, operation: str) -> DeepseekBalance:
        # One GET, then the status rows, then the body's relied-on members.
        response = await HarnessBackends._send_balance_request(url, key, errors, operation=operation)
        HarnessBackends._check_balance_status(response, errors, operation=operation)
        return HarnessBackends._parse_balance(response.body, errors, operation=operation)

    @staticmethod
    async def _send_balance_request(url: str, key: str, errors: NativeErrorFactory, *, operation: str) -> HttpResponse:
        # @intent backend-balance-request-bounded-no-retry
        # One GET through HttpTransport with the backend deadline and body cap,
        # the key only in the Bearer header, no retry and no redirect. A failure
        # with no status means the endpoint was not reached (EC-131); one with
        # a status is a body over the cap (EC-132). The transport's own text is
        # never surfaced, because it can echo the request.
        headers = {"authorization": f"Bearer {key}", "accept": "application/json"}
        try:
            return await HttpTransport().request(method="GET", url=url, headers=headers, timeout_seconds=native_host_constants.BACKEND_HTTP_TIMEOUT_SECONDS, max_response_bytes=native_host_constants.BACKEND_MAX_RESPONSE_BYTES)
        except ProviderRequestError as exc:
            if exc.status_code is None:
                raise errors.build(FailureCode.BACKEND_SERVER_UNREACHABLE, "The DeepSeek balance endpoint could not be reached in time.", operation=operation) from exc
            raise errors.build(FailureCode.BACKEND_PROTOCOL_MISMATCH, "The DeepSeek balance answer is larger than this SDK reads.", operation=operation, context={"reason": "response_too_large"}) from exc

    @staticmethod
    def _check_balance_status(response: HttpResponse, errors: NativeErrorFactory, *, operation: str) -> None:
        # @intent backend-balance-status-rows
        # 401 and 403 mean the key was rejected, 402 an empty balance and 429
        # a rate limit; any other non-2xx status, a redirect included, is an
        # unclassified vendor error with its scrubbed text (EC-127 to EC-130).
        status = response.status_code
        if status in native_host_constants.NATIVE_HTTP_SIGNED_OUT_STATUSES:
            raise errors.build(FailureCode.BACKEND_NOT_SIGNED_IN, "DeepSeek rejected the key in DEEPSEEK_API_KEY.", operation=operation, next_step=_KEY_REJECTED_STEP.format(variable="DEEPSEEK_API_KEY"), context={"status_code": str(status)})
        if status == native_host_constants.NATIVE_HTTP_BILLING_STATUS:
            raise errors.build(FailureCode.BACKEND_BILLING_ERROR, "DeepSeek refused the call for billing.", operation=operation, context={"status_code": str(status)})
        if status == native_host_constants.NATIVE_HTTP_RATE_LIMIT_STATUS:
            raise errors.build(FailureCode.BACKEND_USAGE_LIMITED, "DeepSeek rate-limited the call.", operation=operation, context={"status_code": str(status)})
        if not native_host_constants.NATIVE_HTTP_SUCCESS_FIRST_STATUS <= status < native_host_constants.NATIVE_HTTP_SUCCESS_END_STATUS:
            context = {"status_code": str(status)}
            vendor_text = HarnessBackends._vendor_text(response.body)
            if vendor_text.strip():
                context["vendor_error"] = vendor_text
            raise errors.build(FailureCode.BACKEND_API_ERROR, f"DeepSeek answered the balance call with HTTP {status}.", operation=operation, context=context)

    @staticmethod
    def _vendor_text(body: str) -> str:
        # The error envelope's message when the body has one, else the body text; the factory scrubs and caps it.
        try:
            payload = json.loads(body)
        except ValueError:
            return body
        envelope = payload.get("error") if isinstance(payload, Mapping) else None
        message = envelope.get("message") if isinstance(envelope, Mapping) else None
        return message if isinstance(message, str) and message.strip() else body

    @staticmethod
    def _parse_balance(body: str, errors: NativeErrorFactory, *, operation: str) -> DeepseekBalance:
        # @intent backend-balance-relied-on-members
        # Only the members this SDK relies on are read: a bool is_available, a
        # list balance_infos, and per entry a currency string and three decimal
        # strings. Anything else missing or mistyped is protocol_mismatch
        # naming the member, never a raw parsing error (EC-132, D-13).
        try:
            payload: Any = RecordFieldConverter.require_instance(json.loads(body), _BODY_FIELD, Mapping)
            is_available = RecordFieldValidator.require_bool(payload.get("is_available"), "is_available")
            infos = RecordFieldConverter.to_tuple(payload.get("balance_infos"), "balance_infos", item_type=Mapping)
            entries = tuple(
                DeepseekBalanceEntry(
                    currency=RecordFieldConverter.require_instance(info.get("currency"), "currency", str),
                    total_balance=RecordFieldConverter.to_decimal(info.get("total_balance"), "total_balance"),
                    granted_balance=RecordFieldConverter.to_decimal(info.get("granted_balance"), "granted_balance"),
                    topped_up_balance=RecordFieldConverter.to_decimal(info.get("topped_up_balance"), "topped_up_balance"),
                )
                for info in infos
            )
            return DeepseekBalance(is_available=is_available, balances=entries)
        except ValueError as exc:
            raise errors.build(FailureCode.BACKEND_PROTOCOL_MISMATCH, "The DeepSeek balance answer is not JSON.", operation=operation, context={"field": _BODY_FIELD}) from exc
        except ConfigurationError as exc:
            field = str(exc.details.get("field", _BODY_FIELD)).rsplit(".", 1)[-1]
            raise errors.build(FailureCode.BACKEND_PROTOCOL_MISMATCH, "The DeepSeek balance answer lacks a member this SDK relies on.", operation=operation, context={"field": field}) from exc


__all__ = ["HarnessBackends"]
