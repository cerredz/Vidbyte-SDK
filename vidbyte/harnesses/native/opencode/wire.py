"""FILE: vidbyte/harnesses/native/opencode/wire.py

PURPOSE: Defines OpencodeWire, the opencode HTTP codec: it builds the request bodies the host sends, turns every JSON body opencode answers into a §9.1 record, and maps an assistant message's error object to its failure row (EC-82 to EC-85).
ROLE IN CODEBASE: Used by OpencodeHost and OpencodeTurnWatcher in vidbyte/harnesses/native/opencode/; the bodies come from OpencodeClient already decoded from JSON. The records live in vidbyte/lib/dataclasses/opencode.py and native_hosts.py.
ARCHITECTURE NOTE: Three small classes in one direction: _Members reads one typed member, _WireRecords builds one record from one decoded value, and OpencodeWire is the public codec that wraps each builder so a missing or wrongly typed relied-on member raises opencode.protocol_mismatch naming the member (D-13), never a raw parsing error. Vendor vocabularies (states, statuses, method types) are kept verbatim.
FUNCTION INVENTORY: OpencodeWire.session_body, prompt_body and mcp_body build request bodies; parse_health, parse_readiness, parse_providers, parse_config_providers, parse_provider_auth, parse_session, parse_sessions, parse_message, parse_messages, parse_diffs, parse_mcp_status, parse_permission_requests, parse_question_requests, parse_session_statuses and parse_assistant_error read bodies; reply_failure maps a reply's error to its row; _mismatch builds the protocol error. _WireRecords has one builder per record; _Members has member, mapping and items.
COMMON MODIFICATION PATTERNS: A newly relied-on member is one more _Members.member call in its builder; a new body is one more builder in _WireRecords plus one parse_* wrapper here.
WHAT NOT TO DO IN THIS FILE: 1. Do not fall back to a default when a relied-on member is missing or mistyped; raise protocol_mismatch. 2. Do not read a provider's key or options; they hold credentials. 3. Do not put raw exception text into an error; only the member name.
KNOWN EDGE CASES: Costs arrive as Decimal because OpencodeClient decodes JSON floats as Decimal, so sums stay exact; an integer cost is converted. A session status absent from GET /session/status means idle. An MCP answer that lacks the server's name returns no status, which the host reports as EC-92.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (OpencodeWire), §9.1 (vidbyte.lib.dataclasses.opencode), D-13, EC-58, EC-82 to EC-85
TESTS: tests/features/opencode_host/test_opencode_host_watcher.py, tests/features/opencode_host/test_opencode_host_errors.py, tests/features/opencode_host/test_opencode_host_acceptance.py
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.native_hosts import NativeTokenUsage
from vidbyte.lib.dataclasses.opencode import (
    OpencodeAssistantError,
    OpencodeAuthMethod,
    OpencodeFileDiff,
    OpencodeMcpServerConfig,
    OpencodeMessage,
    OpencodeModel,
    OpencodePermissionRequest,
    OpencodePromptRequest,
    OpencodeProvider,
    OpencodeProviderAuth,
    OpencodeQuestionRequest,
    OpencodeReadiness,
    OpencodeSession,
    OpencodeSessionStatus,
    OpencodeSpawnRequest,
)
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.native_hosts import OpencodeMcpKind
from vidbyte.lib.errors import ConfigurationError, NativeHostError

_VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
_TEXT_PART = "text"
_TEXT_SEPARATOR = "\n"
_BODY_MEMBER = "body"
_PROVIDER_AUTH_ERROR = "ProviderAuthError"
_API_ERROR = "APIError"


class _Members:
    """Reads one typed member of a decoded JSON value; a wrong shape raises ConfigurationError naming the member."""

    @staticmethod
    def member(container: Mapping[str, Any], key: str, expected: type[Any] | tuple[type[Any], ...], *, optional: bool = False) -> Any:
        # The member's value when it has the expected type, or None for
        # an absent optional member.
        return RecordFieldConverter.require_instance(container.get(key), key, expected, optional=optional)

    @staticmethod
    def mapping(value: Any, name: str) -> Mapping[str, Any]:
        # A JSON object.
        mapped: Mapping[str, Any] = RecordFieldConverter.require_instance(value, name, Mapping)
        return mapped

    @staticmethod
    def items(value: Any, name: str) -> tuple[Mapping[str, Any], ...]:
        # A JSON array whose entries are all objects.
        return RecordFieldConverter.to_tuple(value, name, item_type=Mapping)


class _WireRecords:
    """Builds one §9.1 record from one decoded opencode value."""

    @staticmethod
    def usage(info: Mapping[str, Any]) -> NativeTokenUsage | None:
        # The cost and tokens of a Session or an AssistantMessage; None
        # when neither was reported.
        tokens = _Members.member(info, "tokens", Mapping, optional=True)
        cost = _Members.member(info, "cost", (int, Decimal), optional=True)
        if tokens is None and cost is None:
            return None
        counts: Mapping[str, Any] = tokens or {}
        cache: Mapping[str, Any] = _Members.member(counts, "cache", Mapping, optional=True) or {}
        return NativeTokenUsage(
            input_tokens=_Members.member(counts, "input", int, optional=True),
            output_tokens=_Members.member(counts, "output", int, optional=True),
            reasoning_tokens=_Members.member(counts, "reasoning", int, optional=True),
            cache_read_tokens=_Members.member(cache, "read", int, optional=True),
            cache_write_tokens=_Members.member(cache, "write", int, optional=True),
            total_tokens=_Members.member(counts, "total", int, optional=True),
            cost_usd=None if cost is None else Decimal(cost),
        )

    @staticmethod
    def session(value: Any) -> OpencodeSession:
        # A Session object: ids, title, folder, times, usage and the
        # revert point when one is set.
        entry = _Members.mapping(value, "session")
        times = _Members.mapping(entry.get("time"), "time")
        revert: Mapping[str, Any] = _Members.member(entry, "revert", Mapping, optional=True) or {}
        return OpencodeSession(
            session_id=_Members.member(entry, "id", str),
            title=_Members.member(entry, "title", str),
            directory=_Members.member(entry, "directory", str),
            parent_id=_Members.member(entry, "parentID", str, optional=True),
            created_ms=_Members.member(times, "created", int),
            updated_ms=_Members.member(times, "updated", int),
            usage=_WireRecords.usage(entry),
            revert_message_id=_Members.member(revert, "messageID", str, optional=True),
            revert_part_id=_Members.member(revert, "partID", str, optional=True),
        )

    @staticmethod
    def assistant_error(value: Any) -> OpencodeAssistantError:
        # An AssistantMessage error: the name verbatim, and
        # data.message, data.statusCode and
        # data.isRetryable when present.
        entry = _Members.mapping(value, "error")
        data: Mapping[str, Any] = _Members.member(entry, "data", Mapping, optional=True) or {}
        return OpencodeAssistantError(
            name=_Members.member(entry, "name", str),
            message=_Members.member(data, "message", str, optional=True),
            status_code=_Members.member(data, "statusCode", int, optional=True),
            retryable=_Members.member(data, "isRetryable", bool, optional=True),
        )

    @staticmethod
    def message(value: Any) -> OpencodeMessage:
        # A {info, parts} message: the text parts joined and capped, the
        # times, the parent and the usage.
        entry = _Members.mapping(value, "message")
        info = _Members.mapping(entry.get("info"), "info")
        times = _Members.mapping(info.get("time"), "time")
        parts = _Members.items(entry.get("parts"), "parts")
        text = _TEXT_SEPARATOR.join(_Members.member(part, "text", str) for part in parts if part.get("type") == _TEXT_PART)
        limit = native_host_constants.NATIVE_RESULT_TEXT_MAX_CHARS
        error = info.get("error")
        return OpencodeMessage(
            message_id=_Members.member(info, "id", str),
            session_id=_Members.member(info, "sessionID", str),
            role=_Members.member(info, "role", str),
            created_ms=_Members.member(times, "created", int),
            completed_ms=_Members.member(times, "completed", int, optional=True),
            text=text[:limit],
            text_truncated=len(text) > limit,
            parent_id=_Members.member(info, "parentID", str, optional=True),
            provider_id=_Members.member(info, "providerID", str, optional=True),
            model_id=_Members.member(info, "modelID", str, optional=True),
            finish=_Members.member(info, "finish", str, optional=True),
            error=None if error is None else _WireRecords.assistant_error(error),
            usage=_WireRecords.usage(info),
        )

    @staticmethod
    def models(value: Any) -> tuple[OpencodeModel, ...]:
        # @intent opencode-wire-model-ids-verbatim
        # Model ids are the keys the provider lists them under, copied
        # verbatim, because the prompt body sends them back unchanged; a
        # malformed entry fails the whole parse as protocol_mismatch.
        # Every model of one Provider object, keyed by the model id the
        # provider lists it under.
        entry = _Members.mapping(value, "provider")
        provider_id = _Members.member(entry, "id", str)
        catalog = _Members.mapping(entry.get("models"), "models")
        found: list[OpencodeModel] = []
        for model_id, raw in catalog.items():
            model = _Members.mapping(raw, "model")
            limits: Mapping[str, Any] = _Members.member(model, "limit", Mapping, optional=True) or {}
            found.append(
                OpencodeModel(
                    provider_id=provider_id,
                    model_id=str(model_id),
                    name=_Members.member(model, "name", str, optional=True),
                    status=_Members.member(model, "status", str, optional=True),
                    context_limit=_Members.member(limits, "context", int, optional=True),
                    output_limit=_Members.member(limits, "output", int, optional=True),
                )
            )
        return tuple(found)

    @staticmethod
    def provider(value: Any, connected: frozenset[str], defaults: Mapping[str, Any]) -> OpencodeProvider:
        # @intent opencode-wire-provider-drops-keys
        # A Provider object carries the provider's key and options; only
        # the id, name, source, variable names, model ids and default
        # are read, so no key can reach a record or a tool result.
        # One Provider object without its key or options.
        entry = _Members.mapping(value, "provider")
        provider_id = _Members.member(entry, "id", str)
        catalog = _Members.mapping(entry.get("models"), "models")
        return OpencodeProvider(
            provider_id=provider_id,
            name=_Members.member(entry, "name", str),
            source=_Members.member(entry, "source", str),
            env_vars=RecordFieldConverter.to_tuple(entry.get("env"), "env", item_type=str),
            connected=provider_id in connected,
            model_ids=tuple(str(model_id) for model_id in catalog),
            default_model_id=_Members.member(defaults, provider_id, str, optional=True),
        )

    @staticmethod
    def provider_auth(provider_id: str, value: Any) -> OpencodeProviderAuth:
        # @intent opencode-wire-auth-methods-verbatim
        # The method types form an open set, so type and label
        # are copied verbatim instead of mapped to an enum that
        # would refuse a new one.
        # One provider's auth methods, type and label verbatim.
        methods = _Members.items(value, "methods")
        return OpencodeProviderAuth(provider_id=provider_id, methods=tuple(OpencodeAuthMethod(method_type=_Members.member(method, "type", str), label=_Members.member(method, "label", str)) for method in methods))

    @staticmethod
    def diff(value: Any) -> OpencodeFileDiff:
        # One FileDiff, with its patch cut at OPENCODE_PATCH_MAX_CHARS.
        entry = _Members.mapping(value, "diff")
        patch = _Members.member(entry, "patch", str)
        limit = native_host_constants.OPENCODE_PATCH_MAX_CHARS
        return OpencodeFileDiff(
            path=_Members.member(entry, "file", str),
            status=_Members.member(entry, "status", str),
            additions=_Members.member(entry, "additions", int),
            deletions=_Members.member(entry, "deletions", int),
            patch=patch[:limit],
            patch_truncated=len(patch) > limit,
        )

    @staticmethod
    def permission_request(value: Any) -> OpencodePermissionRequest:
        # @intent opencode-wire-permission-request-shape
        # A pending permission request keeps its id, session and
        # patterns so the watcher rejects exactly that request; a
        # malformed one fails the poll as protocol_mismatch instead of
        # being skipped unanswered.
        # One GET /permission entry.
        entry = _Members.mapping(value, "permission")
        return OpencodePermissionRequest(
            request_id=_Members.member(entry, "id", str),
            session_id=_Members.member(entry, "sessionID", str),
            permission=_Members.member(entry, "permission", str),
            patterns=RecordFieldConverter.to_tuple(entry.get("patterns"), "patterns", item_type=str),
        )

    @staticmethod
    def question_request(value: Any) -> OpencodeQuestionRequest:
        # @intent opencode-wire-question-request-shape
        # A pending question keeps its id and session so the watcher
        # rejects exactly that question; a malformed one fails the
        # poll, never skipped.
        # One GET /question entry.
        entry = _Members.mapping(value, "question")
        return OpencodeQuestionRequest(request_id=_Members.member(entry, "id", str), session_id=_Members.member(entry, "sessionID", str))

    @staticmethod
    def session_status(session_id: str, value: Any) -> OpencodeSessionStatus:
        # @intent opencode-wire-retry-status
        # A retry status carries the vendor's attempt number, message
        # and reason, which the watcher compares with its attempt limit;
        # any other status carries only its state.
        # One GET /session/status entry; a retry entry also carries its
        # attempt, message and action reason.
        entry = _Members.mapping(value, "status")
        state = _Members.member(entry, "type", str)
        if state != native_host_constants.OPENCODE_RETRY_STATE:
            return OpencodeSessionStatus(session_id=session_id, state=state)
        action: Mapping[str, Any] = _Members.member(entry, "action", Mapping, optional=True) or {}
        return OpencodeSessionStatus(
            session_id=session_id,
            state=state,
            retry_attempt=_Members.member(entry, "attempt", int),
            retry_message=_Members.member(entry, "message", str, optional=True),
            retry_reason=_Members.member(action, "reason", str, optional=True),
        )


class OpencodeWire:
    """The opencode codec: request bodies out, records in, and the failure row of an assistant error."""

    def __init__(self, errors: NativeErrorFactory) -> None:
        self._errors = errors

    @staticmethod
    def session_body(request: OpencodeSpawnRequest) -> dict[str, object]:
        # @intent opencode-wire-session-rules-from-caller
        # The session body carries only the title and the caller's
        # validated rules; no allow-everything rule is ever added, and
        # with no rules the permission member is absent.
        # POST /session: the title when given and the request's
        # permission rules, never more.
        body: dict[str, object] = {}
        if request.title is not None:
            body["title"] = request.title
        if request.permission_rules:
            body["permission"] = [{"permission": rule.permission, "pattern": rule.pattern, "action": rule.action.value} for rule in request.permission_rules]
        return body

    @staticmethod
    def prompt_body(request: OpencodePromptRequest) -> dict[str, object]:
        # @intent opencode-wire-prompt-body
        # The prompt goes as one text part; the model, already
        # checked by the record, is split at its first slash into
        # provider and model ids.
        # POST …/prompt_async: one text part, plus the model split at
        # its first slash, the agent and the system text.
        body: dict[str, object] = {"parts": [{"type": _TEXT_PART, "text": request.prompt}]}
        if request.model is not None:
            provider_id, model_id = request.model.split("/", native_host_constants.OPENCODE_MODEL_ID_SPLITS)
            body["model"] = {"providerID": provider_id, "modelID": model_id}
        if request.agent is not None:
            body["agent"] = request.agent
        if request.system is not None:
            body["system"] = request.system
        return body

    @staticmethod
    def mcp_body(config: OpencodeMcpServerConfig) -> dict[str, object]:
        # @intent opencode-wire-mcp-body-from-registration
        # The body is built only from a registered config, copied into
        # plain dicts the transport can encode; its environment and
        # header values are secrets the host registered before sending.
        # POST /mcp: a local command with its environment, or a remote
        # URL with its headers, and the timeout when set.
        server: dict[str, object] = {"type": config.kind.value}
        if config.kind is OpencodeMcpKind.LOCAL:
            server["command"] = list(config.command)
            if config.environment:
                server["environment"] = dict(config.environment)
        else:
            server["url"] = config.url
            if config.headers:
                server["headers"] = dict(config.headers)
        if config.timeout_ms is not None:
            server["timeout"] = config.timeout_ms
        return {"name": config.name, "config": server}

    def parse_health(self, body: Any, *, operation: str) -> tuple[bool, str, tuple[int, ...]]:
        # GET /global/health: healthy, the version verbatim, and its
        # numeric parts for the minimum version check.
        try:
            entry = _Members.mapping(body, _BODY_MEMBER)
            healthy = _Members.member(entry, "healthy", bool)
            version = _Members.member(entry, "version", str)
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc
        found = _VERSION_PATTERN.match(version)
        if found is None:
            raise self._errors.build(FailureCode.OPENCODE_PROTOCOL_MISMATCH, "The opencode server reported a version this SDK cannot read.", operation=operation, context={"field": "version"})
        return healthy, version, tuple(int(part) for part in found.groups())

    def parse_readiness(self, body: Any, *, version: str, server_url: str, operation: str) -> OpencodeReadiness:
        # GET /provider: the connected provider ids and the default
        # model of each provider.
        try:
            entry = _Members.mapping(body, _BODY_MEMBER)
            _Members.items(entry.get("all"), "all")
            connected = RecordFieldConverter.to_tuple(entry.get("connected"), "connected", item_type=str)
            defaults = RecordFieldConverter.to_mapping(entry.get("default"), "default")
            return OpencodeReadiness(version=version, server_url=server_url, connected_providers=connected, default_models=defaults)
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def parse_providers(self, body: Any, *, operation: str) -> tuple[OpencodeProvider, ...]:
        # @intent opencode-wire-providers-without-keys
        # Every known provider, marked connected from the server's
        # list; keys and options are never read, and a malformed body
        # is protocol_mismatch.
        # GET /provider: every provider in `all`, marked
        # connected from `connected`.
        try:
            entry = _Members.mapping(body, _BODY_MEMBER)
            providers = _Members.items(entry.get("all"), "all")
            connected = frozenset(RecordFieldConverter.to_tuple(entry.get("connected"), "connected", item_type=str))
            defaults = _Members.mapping(entry.get("default"), "default")
            return tuple(_WireRecords.provider(provider, connected, defaults) for provider in providers)
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def parse_config_providers(self, body: Any, *, operation: str) -> dict[str, tuple[OpencodeModel, ...]]:
        # @intent opencode-wire-connected-catalog
        # GET /config/providers lists only connected providers, so this
        # map is the one source for model checks and the model list.
        # GET /config/providers: each connected provider id with its
        # models, in server order.
        try:
            entry = _Members.mapping(body, _BODY_MEMBER)
            providers = _Members.items(entry.get("providers"), "providers")
            return {_Members.member(provider, "id", str): _WireRecords.models(provider) for provider in providers}
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def parse_provider_auth(self, body: Any, *, operation: str) -> tuple[OpencodeProviderAuth, ...]:
        # @intent opencode-wire-provider-auth-map
        # A map of provider id to methods, kept in server order; a
        # malformed body is protocol_mismatch rather than an
        # empty, misleading list.
        # GET /provider/auth: a map of provider id to its auth methods.
        try:
            entry = _Members.mapping(body, _BODY_MEMBER)
            return tuple(_WireRecords.provider_auth(str(provider_id), methods) for provider_id, methods in entry.items())
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def parse_session(self, body: Any, *, operation: str) -> OpencodeSession:
        # One Session object.
        try:
            return _WireRecords.session(body)
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def parse_sessions(self, body: Any, *, operation: str) -> tuple[OpencodeSession, ...]:
        # A list of Session objects, in server order.
        try:
            return tuple(_WireRecords.session(item) for item in _Members.items(body, _BODY_MEMBER))
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def parse_message(self, body: Any, *, operation: str) -> OpencodeMessage:
        # One {info, parts} message.
        try:
            return _WireRecords.message(body)
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def parse_messages(self, body: Any, *, operation: str) -> tuple[OpencodeMessage, ...]:
        # A list of {info, parts} messages, oldest first as
        # the server sends them.
        try:
            return tuple(_WireRecords.message(item) for item in _Members.items(body, _BODY_MEMBER))
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def parse_diffs(self, body: Any, *, operation: str) -> tuple[OpencodeFileDiff, ...]:
        # A list of FileDiff objects.
        try:
            return tuple(_WireRecords.diff(item) for item in _Members.items(body, _BODY_MEMBER))
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def parse_mcp_status(self, body: Any, name: str, *, operation: str) -> tuple[str | None, str | None]:
        # @intent opencode-wire-mcp-status-by-name
        # Only the entry for the added name counts; a missing name
        # returns (None, None) so the host reports mcp_server_failed.
        # POST /mcp answers a map of server name to {status, error?}; a
        # missing name gives (None, None).
        try:
            entry = _Members.mapping(body, _BODY_MEMBER)
            if name not in entry:
                return None, None
            server = _Members.mapping(entry[name], name)
            return _Members.member(server, "status", str), _Members.member(server, "error", str, optional=True)
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def parse_permission_requests(self, body: Any, *, operation: str) -> tuple[OpencodePermissionRequest, ...]:
        # @intent opencode-wire-permission-requests-all
        # Every pending permission request on the server, not only the
        # turn's; the watcher decides which belong to its session tree.
        # GET /permission: every pending permission
        # request on the server.
        try:
            return tuple(_WireRecords.permission_request(item) for item in _Members.items(body, _BODY_MEMBER))
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def parse_question_requests(self, body: Any, *, operation: str) -> tuple[OpencodeQuestionRequest, ...]:
        # @intent opencode-wire-question-requests-all
        # Every pending question on the server, not only the turn's; the
        # watcher decides which belong to its session tree.
        # GET /question: every pending question request on the server.
        try:
            return tuple(_WireRecords.question_request(item) for item in _Members.items(body, _BODY_MEMBER))
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def parse_session_statuses(self, body: Any, *, operation: str) -> tuple[OpencodeSessionStatus, ...]:
        # GET /session/status: a map of session id to its status; a
        # session absent from it is idle.
        try:
            entry = _Members.mapping(body, _BODY_MEMBER)
            return tuple(_WireRecords.session_status(str(session_id), value) for session_id, value in entry.items())
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def parse_assistant_error(self, error: Any, *, operation: str) -> OpencodeAssistantError:
        # An AssistantMessage error object.
        try:
            return _WireRecords.assistant_error(error)
        except ConfigurationError as exc:
            raise self._mismatch(exc, operation=operation) from exc

    def reply_failure(self, error: OpencodeAssistantError, *, operation: str) -> NativeHostError:
        # @intent opencode-reply-error-to-failure
        # The newest reply's error decides a failed turn: a provider
        # auth error or an API 401/403 means not signed in, 429 a usage
        # limit, 402 billing, anything else an API error. The vendor's
        # own name and message travel scrubbed in vendor_error.
        context = {"vendor_error": f"{error.name}: {error.message}" if error.message else error.name}
        if error.status_code is not None:
            context["status_code"] = str(error.status_code)
        if error.retryable is not None:
            context["retryable"] = native_host_constants.NATIVE_TRUE_TEXT if error.retryable else native_host_constants.NATIVE_FALSE_TEXT
        api_status = error.status_code if error.name == _API_ERROR else None
        if error.name == _PROVIDER_AUTH_ERROR or api_status in native_host_constants.NATIVE_HTTP_SIGNED_OUT_STATUSES:
            return self._errors.build(FailureCode.OPENCODE_NOT_SIGNED_IN, "The model provider rejected opencode's credentials during the turn.", operation=operation, context=context)
        if api_status == native_host_constants.NATIVE_HTTP_RATE_LIMIT_STATUS:
            return self._errors.build(FailureCode.OPENCODE_USAGE_LIMITED, "The model provider rate-limited the turn.", operation=operation, context=context)
        if api_status == native_host_constants.NATIVE_HTTP_BILLING_STATUS:
            return self._errors.build(FailureCode.OPENCODE_BILLING_ERROR, "The model provider refused the turn for billing.", operation=operation, context=context)
        return self._errors.build(FailureCode.OPENCODE_API_ERROR, "The turn's last reply ended with a model provider error.", operation=operation, context=context)

    def _mismatch(self, exc: ConfigurationError, *, operation: str) -> NativeHostError:
        # protocol_mismatch naming only the member that was
        # missing or mistyped.
        member = str(exc.details.get("field", _BODY_MEMBER)).rsplit(".", 1)[-1]
        return self._errors.build(FailureCode.OPENCODE_PROTOCOL_MISMATCH, f"The opencode server sent an answer whose {member} member this SDK cannot read.", operation=operation, context={"field": member})


__all__ = ["OpencodeWire"]
