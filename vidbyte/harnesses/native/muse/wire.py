"""FILE: vidbyte/harnesses/native/muse/wire.py

PURPOSE: Defines MuseWire, the MSP 1.0.1 codec of MuseHost: it builds the params of every call the host makes (each with every member the schema marks required), mints UUIDv7 commandIds, parses results and inbound frames into the §9.1 records, and maps JSON-RPC error answers and `muse --version` output to failure rows.
ROLE IN CODEBASE: Used by MuseHost (vidbyte/harnesses/native/muse/host.py) for every call and result, and by MuseTurnDriver (vidbyte/harnesses/native/muse/turn.py) for the frames of a running turn. Nothing outside the muse package imports it.
ARCHITECTURE NOTE: A static class (field guide class-bound-helpers.md). Every parser goes through RecordFieldConverter and a §9.1 record, and any ConfigurationError on the way becomes muse.protocol_mismatch, so a missing or wrongly typed member never falls back to a default (D-13). A JSON-RPC error answer arrives as McpProtocolError with details["error"]; vendor_failure maps its code to EC-98, EC-100, EC-101, EC-102, EC-111, EC-112 or EC-113; exchange_loaded resumes an unloaded session once (EC-114); and the is_* predicates let callers handle the codes that are not errors for them (EC-156, the stale cursor, the already-stopping interrupt and a rejected steer).
FUNCTION INVENTORY: new_command_id mints a commandId; initialize_params and the *_params builders build call params; exchange makes one call and maps a vendor error; exchange_loaded adds the one resume and retry of EC-114; vendor_failure maps an error answer; vendor_code and the is_* predicates read its code; method_not_found_error is the answer to an unknown server request; read_cli_version, read_server_version, read_model_catalog, read_session_result, read_session_page, read_view_page and read_latest_usage read results; the six parse_* methods read inbound records; _mismatch and _session are their single-step helpers.
COMMON MODIFICATION PATTERNS: A new MSP call gets a *_params builder listing every required member, and a result reader that builds a §9.1 record; a newly mapped error code goes in _CODE_PROBLEMS or gets an is_* predicate.
WHAT NOT TO DO IN THIS FILE: 1. Do not send an approve-everything value, a top-level lastTurnId or a commandId that is not from new_command_id (INV-9, spec §8.5). 2. Do not copy vidbyte.__version__ at import time; initialize_params reads it on every call. 3. Do not fall back to a default when a relied-on member is missing; raise protocol_mismatch.
KNOWN EDGE CASES: The parsers are static and are called without an operation by tests, so their errors name _PARSE_OPERATION unless the caller passes one. `wsl.exe -l -q` output is decoded in launcher.py, not here. An event's JSON is cut at NATIVE_EVENT_MAX_CHARS characters, so a cut event_json is no longer valid JSON and is marked truncated.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.5, §8.5 (MuseHost, MSP calls), §9.1 (Muse records), §9.3, D-13, D-14
TESTS: tests/features/muse_host/test_muse_host_wire.py, tests/features/muse_host/test_muse_host_errors.py, tests/features/muse_host/test_muse_host_reads.py
"""

from __future__ import annotations

import json
import re
import secrets
import time
import uuid
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

import vidbyte
from vidbyte.harnesses.native.hostkit import NativeErrorFactory, NativePeer
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.muse import (
    MuseApprovalChoice,
    MuseApprovalRequest,
    MuseItemCompleted,
    MuseModel,
    MuseModelCatalog,
    MusePage,
    MuseSession,
    MuseSessionPage,
    MuseTurnAck,
    MuseTurnCompleted,
    MuseUserInputRequest,
    MuseViewEvent,
)
from vidbyte.lib.dataclasses.native_hosts import NativeTokenUsage
from vidbyte.lib.dataclasses.process import CliOutcome
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.native_hosts import (
    MuseReasoningEffort,
    MuseViewDirection,
    NativeHarness,
)
from vidbyte.lib.errors import ConfigurationError, McpProtocolError, NativeHostError

_ERRORS = NativeErrorFactory(NativeHarness.MUSE)
_PARSE_OPERATION = "parse_msp_frame"
_NANOSECONDS_PER_MILLISECOND = 1_000_000
_SERVER_VERSION_PATTERN = r"(\d+)\.(\d+)\.(\d+)"
_LAST_INDEX = -1
_USAGE_EVENT_METHOD = "session/tokenUsage"
_COMPACT_SEPARATORS = (",", ":")
# The next step for a prompt that Muse rejects as too large.
_PROMPT_TOO_LARGE_NEXT_STEP = "Shorten the prompt; Muse rejected its size."
_PROMPT_TOO_LARGE_CODE = -32002
_FORK_BOUNDARY_CODE = -32023
_STALE_CURSOR_CODES = frozenset({-32602})
_NOT_LOADED_CODES = frozenset({-32024})
_ALREADY_STOPPING_CODES = frozenset({-32013, -32014})
_BENIGN_RACE_CODES = frozenset({-32051, -32053})
_COMMAND_REJECTED_CODES = frozenset({-32030})
# JSON-RPC codes that each map to one failure; every other
# code is muse.api_error.
_CODE_PROBLEMS: Mapping[int, str] = MappingProxyType(
    {
        -32700: "protocol_mismatch",
        -32600: "protocol_mismatch",
        -32601: "capability_missing",
        -32010: "capability_missing",
        -32020: "session_not_found",
        -32011: "session_not_found",
        -32021: "session_busy",
    }
)
_PROBLEM_MESSAGES: Mapping[str, str] = MappingProxyType(
    {
        "protocol_mismatch": "Muse Code refused a request this SDK sent as malformed or out of order.",
        "capability_missing": "This Muse Code release does not offer a method this SDK needs.",
        "session_not_found": "Muse Code has no session with that id in this workspace.",
        "session_busy": "The Muse session is in use by another turn or client.",
    }
)


class MuseWire:
    """Builds MSP params, parses MSP results and frames into records, and maps MSP errors to failure rows."""

    @staticmethod
    def new_command_id() -> str:
        # An RFC 9562 UUIDv7: 48-bit unix_ts_ms, version 7, 12
        # bits rand_a, variant 0b10, 62 bits rand_b, all 74 random
        # bits from one call.
        random_bits = secrets.randbits(native_host_constants.MUSE_UUID_RANDOM_BITS)
        unix_ts_ms = time.time_ns() // _NANOSECONDS_PER_MILLISECOND
        value = (
            ((unix_ts_ms & native_host_constants.MUSE_UUID_TIMESTAMP_MASK) << native_host_constants.MUSE_UUID_TIMESTAMP_SHIFT)
            | (native_host_constants.MUSE_UUID_VERSION << native_host_constants.MUSE_UUID_VERSION_SHIFT)
            | ((random_bits >> native_host_constants.MUSE_UUID_RAND_B_BITS) << native_host_constants.MUSE_UUID_RAND_A_SHIFT)
            | (native_host_constants.MUSE_UUID_VARIANT << native_host_constants.MUSE_UUID_VARIANT_SHIFT)
            | (random_bits & native_host_constants.MUSE_UUID_RAND_B_MASK)
        )
        return str(uuid.UUID(int=value))

    @staticmethod
    def initialize_params() -> dict[str, Any]:
        # clientInfo needs both members; the version is read now, never
        # copied at import time.
        return {"clientInfo": {"name": native_host_constants.MUSE_CLIENT_NAME, "version": vidbyte.__version__}}

    @staticmethod
    def session_start_params(workspace_root: str, model: str | None) -> dict[str, Any]:
        # @intent muse-session-start-denies-unmatched-approvals
        # approvalMode is always denyUnmatched: the user's own Muse
        # rules still apply and everything else is denied.
        params: dict[str, Any] = {"commandId": MuseWire.new_command_id(), "workspaceRoot": workspace_root, "approvalMode": native_host_constants.MUSE_APPROVAL_MODE}
        if model is not None:
            params["modelId"] = model
        return params

    @staticmethod
    def session_resume_params(session_id: str) -> dict[str, Any]:
        return {"commandId": MuseWire.new_command_id(), "sessionId": session_id}

    @staticmethod
    def session_fork_params(session_id: str, last_turn_id: str | None) -> dict[str, Any]:
        # The cut point travels only as cutPoint.lastTurnId; a top-level
        # lastTurnId is not a schema member.
        params: dict[str, Any] = {"commandId": MuseWire.new_command_id(), "sessionId": session_id}
        if last_turn_id is not None:
            params["cutPoint"] = {"lastTurnId": last_turn_id}
        return params

    @staticmethod
    def session_list_params(workspace_root: str, cursor: str | None, limit: int) -> dict[str, Any]:
        return {"workspaceRoot": workspace_root, "cursor": cursor, "limit": limit}

    @staticmethod
    def session_read_params(session_id: str) -> dict[str, Any]:
        return {"sessionId": session_id, "excludeItems": True}

    @staticmethod
    def view_page_params(session_id: str, cursor: str | None, limit: int, direction: MuseViewDirection) -> dict[str, Any]:
        return {"sessionId": session_id, "limit": limit, "cursor": cursor, "direction": direction.value}

    @staticmethod
    def turn_start_params(session_id: str, prompt: str, reasoning_effort: MuseReasoningEffort | None) -> dict[str, Any]:
        # One text part; reasoningEffort only when the request sets it.
        params: dict[str, Any] = {"commandId": MuseWire.new_command_id(), "sessionId": session_id, "input": [{"type": "text", "text": prompt}]}
        if reasoning_effort is not None:
            params["reasoningEffort"] = reasoning_effort.value
        return params

    @staticmethod
    def turn_steer_params(session_id: str, turn_id: str, text: str) -> dict[str, Any]:
        return {"commandId": MuseWire.new_command_id(), "sessionId": session_id, "expectedTurnId": turn_id, "input": [{"type": "text", "text": text}]}

    @staticmethod
    def turn_interrupt_params(session_id: str, turn_id: str) -> dict[str, Any]:
        return {"commandId": MuseWire.new_command_id(), "sessionId": session_id, "turnId": turn_id}

    @staticmethod
    def approval_decide_params(request: MuseApprovalRequest, choice_id: str) -> dict[str, Any]:
        # requirementId echoes the approval's latest
        # currentRequirementId object.
        requirement = {"approvalId": request.requirement_approval_id, "sourceIndex": request.requirement_source_index}
        return {"commandId": MuseWire.new_command_id(), "sessionId": request.session_id, "approvalId": request.approval_id, "requirementId": requirement, "choiceId": choice_id}

    @staticmethod
    def user_input_cancel_params(request: MuseUserInputRequest) -> dict[str, Any]:
        return {"commandId": MuseWire.new_command_id(), "sessionId": request.session_id, "userInputId": request.user_input_id}

    @staticmethod
    def method_not_found_error() -> dict[str, Any]:
        # The answer to any server request the host does not handle.
        return {"code": native_host_constants.NATIVE_JSONRPC_METHOD_NOT_FOUND_CODE, "message": native_host_constants.NATIVE_JSONRPC_METHOD_NOT_FOUND_TEXT}

    @staticmethod
    async def exchange(peer: NativePeer, method: str, params: Mapping[str, Any], *, operation: str, timeout_seconds: float | None = None) -> Mapping[str, Any]:
        # @intent muse-wire-maps-every-error-answer
        # One MSP call on the peer; a transport failure is already a
        # NativeHostError, and a JSON-RPC error answer is mapped to
        # its muse.* failure.
        try:
            return await peer.call(method, params, operation=operation, timeout_seconds=timeout_seconds)
        except McpProtocolError as exc:
            raise MuseWire.vendor_failure(exc, operation=operation) from exc

    @staticmethod
    async def exchange_loaded(peer: NativePeer, method: str, build_params: Callable[[], Mapping[str, Any]], session_id: str, *, operation: str) -> Mapping[str, Any]:
        # @intent muse-wire-resumes-an-unloaded-session-once
        # A session-scoped call answered -32024 sessionNotLoaded gets
        # one session/resume and one retry with freshly built params (a
        # new commandId); a second -32024, or any other error answer, is
        # mapped to its failure like every other call.
        try:
            return await peer.call(method, build_params(), operation=operation)
        except McpProtocolError as exc:
            if MuseWire.vendor_code(exc) not in _NOT_LOADED_CODES:
                raise MuseWire.vendor_failure(exc, operation=operation) from exc
        try:
            await peer.call("session/resume", {"commandId": MuseWire.new_command_id(), "sessionId": session_id}, operation=operation)
            return await peer.call(method, build_params(), operation=operation)
        except McpProtocolError as exc:
            raise MuseWire.vendor_failure(exc, operation=operation) from exc

    @staticmethod
    def vendor_failure(exc: McpProtocolError, *, operation: str) -> NativeHostError:
        # @intent muse-wire-error-code-to-failure
        # Maps an MSP error answer: -32002 to an invalid prompt
        # argument, -32023 to an invalid last_turn_id (the fork
        # boundary), the codes in _CODE_PROBLEMS to their failures, and
        # every other code to api_error with the vendor's code, kind,
        # retryable flag and scrubbed message.
        try:
            error = RecordFieldConverter.require_instance(exc.details.get("error"), "error", Mapping)
        except ConfigurationError:
            return _ERRORS.build(_ERRORS.code("protocol_mismatch"), "Muse Code sent an error answer this SDK cannot read.", operation=operation, context={"reason": "invalid_error"})
        code = error.get("code")
        data = error.get("data") if isinstance(error.get("data"), Mapping) else {}
        context = {"vendor_code": str(code)}
        if isinstance(data.get("kind"), str):
            context["vendor_kind"] = data["kind"]
        if code == _PROMPT_TOO_LARGE_CODE:
            return _ERRORS.invalid_argument("prompt", "Muse rejected the prompt as too large; it accepted nothing.", operation=operation, next_step=_PROMPT_TOO_LARGE_NEXT_STEP)
        if code == _FORK_BOUNDARY_CODE:
            return _ERRORS.invalid_argument("last_turn_id", "last_turn_id is not a turn of the session.", operation=operation)
        problem = _CODE_PROBLEMS.get(code) if isinstance(code, int) else None
        if problem is not None:
            return _ERRORS.build(_ERRORS.code(problem), _PROBLEM_MESSAGES[problem], operation=operation, context=context)
        if isinstance(data.get("retryable"), bool):
            context["retryable"] = native_host_constants.NATIVE_TRUE_TEXT if data["retryable"] else native_host_constants.NATIVE_FALSE_TEXT
        context["vendor_error"] = str(error.get("message", ""))
        return _ERRORS.build(_ERRORS.code("api_error"), "Muse Code answered with an error.", operation=operation, context=context)

    @staticmethod
    def vendor_code(exc: McpProtocolError) -> int | None:
        # The JSON-RPC code of an error answer, or None when
        # the answer has none.
        error = exc.details.get("error")
        code = error.get("code") if isinstance(error, Mapping) else None
        return code if isinstance(code, int) else None

    @staticmethod
    def is_stale_cursor(exc: McpProtocolError) -> bool:
        # -32602 invalidParams, which means a stale cursor
        # when a cursor was sent.
        return MuseWire.vendor_code(exc) in _STALE_CURSOR_CODES

    @staticmethod
    def is_already_stopping(exc: McpProtocolError) -> bool:
        # -32013 interrupted or -32014 cancelled: an interrupt that
        # finds the turn stopping succeeded.
        return MuseWire.vendor_code(exc) in _ALREADY_STOPPING_CODES

    @staticmethod
    def is_benign_race(exc: McpProtocolError) -> bool:
        # -32051 approvalAlreadyResolved or -32053
        # approvalRequirementStale: a decision that lost a
        # race, which is harmless.
        return MuseWire.vendor_code(exc) in _BENIGN_RACE_CODES

    @staticmethod
    def is_command_rejected(exc: McpProtocolError) -> bool:
        # -32030 commandRejected, which for a steer means the turn
        # is no longer running.
        return MuseWire.vendor_code(exc) in _COMMAND_REJECTED_CODES

    @staticmethod
    def read_cli_version(outcome: CliOutcome, *, operation: str) -> str:
        # `<launcher> --version`: a launch failure, a timeout or a
        # non-zero exit is a process failure; output without
        # MUSE_VERSION_PATTERN is protocol_mismatch and a version below
        # MUSE_MIN_VERSION is version_unsupported.
        if outcome.launch_failure is not None:
            raise _ERRORS.from_launch_failure(outcome.launch_failure, operation=operation)
        if outcome.timed_out:
            raise _ERRORS.build(_ERRORS.code("server_unreachable"), "muse --version did not finish in time.", operation=operation, context={"reason": "timeout"})
        if outcome.exit_code != native_host_constants.NATIVE_SUCCESS_EXIT_CODE:
            raise _ERRORS.build(_ERRORS.code("process_exited"), f"muse --version exited with code {outcome.exit_code}.", operation=operation, context={"exit_code": str(outcome.exit_code)})
        match = re.search(native_host_constants.MUSE_VERSION_PATTERN, outcome.stdout)
        if match is None:
            raise _ERRORS.build(_ERRORS.code("protocol_mismatch"), "muse --version printed no Muse Code version this SDK can read.", operation=operation, context={"reason": "version_output"})
        version = ".".join(match.groups())
        if tuple(int(part) for part in match.groups()) < native_host_constants.MUSE_MIN_VERSION:
            raise _ERRORS.build(_ERRORS.code("version_unsupported"), f"Muse Code {version} is older than this SDK supports.", operation=operation, context={"version": version})
        return version

    @staticmethod
    def read_server_version(result: object, *, operation: str) -> str:
        # The initialize result must carry schema.version ==
        # MUSE_SCHEMA_VERSION and a string serverInfo.version of at
        # least MUSE_MIN_VERSION.
        try:
            fields = RecordFieldConverter.require_instance(result, "initialize", Mapping)
            schema = RecordFieldConverter.require_instance(fields.get("schema"), "schema", Mapping)
            server = RecordFieldConverter.require_instance(fields.get("serverInfo"), "serverInfo", Mapping)
            version = RecordFieldConverter.require_instance(server.get("version"), "serverInfo.version", str)
            schema_version = RecordFieldConverter.require_instance(schema.get("version"), "schema.version", int)
        except ConfigurationError as exc:
            raise MuseWire._mismatch("initialize", exc.details.get("field"), operation) from exc
        match = re.match(_SERVER_VERSION_PATTERN, version)
        if schema_version != native_host_constants.MUSE_SCHEMA_VERSION or match is None:
            raise MuseWire._mismatch("initialize", "schema.version", operation)
        if tuple(int(part) for part in match.groups()) < native_host_constants.MUSE_MIN_VERSION:
            raise _ERRORS.build(_ERRORS.code("version_unsupported"), f"Muse Code {version} is older than this SDK supports.", operation=operation, context={"version": version})
        return version

    @staticmethod
    def read_model_catalog(result: object, *, operation: str) -> MuseModelCatalog:
        # model/list: the models in order (an empty list is not an
        # error) and the provider, profile and source verbatim.
        try:
            fields = RecordFieldConverter.require_instance(result, "model/list", Mapping)
            entries = [RecordFieldConverter.require_instance(entry, "models", Mapping) for entry in RecordFieldConverter.require_instance(fields.get("models"), "models", list)]
            models = tuple(MuseModel(model_id=entry.get("modelId"), display_name=entry.get("displayLabel")) for entry in entries)
            return MuseModelCatalog(provider_id=fields.get("providerId"), profile_id=fields.get("profileId"), source=fields.get("source"), models=models)
        except ConfigurationError as exc:
            raise MuseWire._mismatch("model/list", exc.details.get("field"), operation) from exc

    @staticmethod
    def read_session_result(result: object, *, operation: str) -> MuseSession:
        # session/start, session/resume, session/read and session/fork
        # all carry the session under "session".
        try:
            fields = RecordFieldConverter.require_instance(result, "result", Mapping)
            return MuseWire._session(fields.get("session"), "session")
        except ConfigurationError as exc:
            raise MuseWire._mismatch("session result", exc.details.get("field"), operation) from exc

    @staticmethod
    def read_session_page(result: object, *, operation: str) -> MuseSessionPage:
        # session/list: the sessions in order and the vendor's
        # next cursor verbatim.
        try:
            fields = RecordFieldConverter.require_instance(result, "session/list", Mapping)
            entries = RecordFieldConverter.require_instance(fields.get("sessions"), "sessions", list)
            sessions = tuple(MuseWire._session(entry, "sessions") for entry in entries)
            return MuseSessionPage(sessions=sessions, next_cursor=fields.get("nextCursor"))
        except ConfigurationError as exc:
            raise MuseWire._mismatch("session/list", exc.details.get("field"), operation) from exc

    @staticmethod
    def read_view_page(session_id: str, result: object, *, operation: str) -> MusePage:
        # view/page: each event as compact sorted JSON, cut at
        # NATIVE_EVENT_MAX_CHARS and marked when cut.
        limit = native_host_constants.NATIVE_EVENT_MAX_CHARS
        try:
            fields = RecordFieldConverter.require_instance(result, "view/page", Mapping)
            entries = [RecordFieldConverter.require_instance(entry, "events", Mapping) for entry in RecordFieldConverter.require_instance(fields.get("events"), "events", list)]
            texts = [(entry.get("method"), json.dumps(entry, sort_keys=True, separators=_COMPACT_SEPARATORS)) for entry in entries]
            events = tuple(MuseViewEvent(kind=kind, event_json=text[:limit], truncated=len(text) > limit) for kind, text in texts)
            return MusePage(session_id=session_id, events=events, next_cursor=fields.get("nextCursor"))
        except ConfigurationError as exc:
            raise MuseWire._mismatch("view/page", exc.details.get("field"), operation) from exc

    @staticmethod
    def read_latest_usage(result: object, *, operation: str) -> NativeTokenUsage | None:
        # The last session/tokenUsage event of the page (events
        # ascend in both directions); promptTokens,
        # outputTokens and totalTokens map to input, output and
        # total. Cost is never reported.
        try:
            fields = RecordFieldConverter.require_instance(result, "view/page", Mapping)
            entries = [RecordFieldConverter.require_instance(entry, "events", Mapping) for entry in RecordFieldConverter.require_instance(fields.get("events"), "events", list)]
            usages = [entry for entry in entries if entry.get("method") == _USAGE_EVENT_METHOD]
            if not usages:
                return None
            params = RecordFieldConverter.require_instance(usages[_LAST_INDEX].get("params"), "params", Mapping)
            cumulative = RecordFieldConverter.require_instance(params.get("cumulative"), "cumulative", Mapping)
            return NativeTokenUsage(input_tokens=cumulative.get("promptTokens"), output_tokens=cumulative.get("outputTokens"), total_tokens=cumulative.get("totalTokens"))
        except ConfigurationError as exc:
            raise MuseWire._mismatch(_USAGE_EVENT_METHOD, exc.details.get("field"), operation) from exc

    @staticmethod
    def parse_turn_start_result(result: object, *, operation: str = _PARSE_OPERATION) -> MuseTurnAck:
        # The ack's turnId is the turn's MSP id from now on; turn/start
        # requires a disposition.
        try:
            fields = RecordFieldConverter.require_instance(result, "turn/start", Mapping)
            disposition = RecordFieldConverter.require_instance(fields.get("disposition"), "disposition", str)
            return MuseTurnAck(command_id=fields.get("commandId"), turn_id=fields.get("turnId"), status=fields.get("status"), disposition=disposition)
        except ConfigurationError as exc:
            raise MuseWire._mismatch("turn/start", exc.details.get("field"), operation) from exc

    @staticmethod
    def parse_turn_steer_result(result: object, *, operation: str = _PARSE_OPERATION) -> MuseTurnAck:
        # A steer ack has no disposition; its status
        # is returned verbatim.
        try:
            fields = RecordFieldConverter.require_instance(result, "turn/steer", Mapping)
            return MuseTurnAck(command_id=fields.get("commandId"), turn_id=fields.get("turnId"), status=fields.get("status"))
        except ConfigurationError as exc:
            raise MuseWire._mismatch("turn/steer", exc.details.get("field"), operation) from exc

    @staticmethod
    def parse_approval_request(params: object, *, operation: str = _PARSE_OPERATION) -> MuseApprovalRequest:
        # @intent muse-approval-frame-names-the-current-requirement
        # approval/requested and approval/updated: the requirement to
        # decide is currentRequirementId, and every offered choice is
        # kept so the driver can find the denied choice scoped once.
        try:
            fields = RecordFieldConverter.require_instance(params, "approval", Mapping)
            requirement = RecordFieldConverter.require_instance(fields.get("currentRequirementId"), "currentRequirementId", Mapping)
            offered = [RecordFieldConverter.require_instance(entry, "availableChoices", Mapping) for entry in RecordFieldConverter.require_instance(fields.get("availableChoices"), "availableChoices", list)]
            choices = tuple(MuseApprovalChoice(choice_id=entry.get("choiceId"), decision=entry.get("decision"), scope=entry.get("scope")) for entry in offered)
            return MuseApprovalRequest(
                session_id=fields.get("sessionId"),
                approval_id=fields.get("approvalId"),
                requirement_approval_id=requirement.get("approvalId"),
                requirement_source_index=requirement.get("sourceIndex"),
                choices=choices,
                turn_id=fields.get("turnId"),
                tool_name=fields.get("toolName"),
            )
        except ConfigurationError as exc:
            raise MuseWire._mismatch("approval", exc.details.get("field"), operation) from exc

    @staticmethod
    def parse_user_input_request(params: object, *, operation: str = _PARSE_OPERATION) -> MuseUserInputRequest:
        # @intent muse-user-input-frame-is-parsed-before-cancel
        # userInput/requested, which the host always cancels; the id and
        # session are required, because the cancel must name both.
        try:
            fields = RecordFieldConverter.require_instance(params, "userInput/requested", Mapping)
            return MuseUserInputRequest(session_id=fields.get("sessionId"), turn_id=fields.get("turnId"), user_input_id=fields.get("userInputId"), tool_name=fields.get("toolName"))
        except ConfigurationError as exc:
            raise MuseWire._mismatch("userInput/requested", exc.details.get("field"), operation) from exc

    @staticmethod
    def parse_item_completed(params: object, *, operation: str = _PARSE_OPERATION) -> MuseItemCompleted:
        # item/completed is read from its item; truncated defaults to
        # False only when Muse leaves it out.
        try:
            fields = RecordFieldConverter.require_instance(params, "item/completed", Mapping)
            item = RecordFieldConverter.require_instance(fields.get("item"), "item", Mapping)
            return MuseItemCompleted(
                session_id=fields.get("sessionId"),
                item_id=item.get("itemId"),
                kind=item.get("kind"),
                turn_id=item.get("turnId"),
                text=item.get("text"),
                truncated=item.get("truncated", False),
            )
        except ConfigurationError as exc:
            raise MuseWire._mismatch("item/completed", exc.details.get("field"), operation) from exc

    @staticmethod
    def parse_turn_completed(params: object, *, operation: str = _PARSE_OPERATION) -> MuseTurnCompleted:
        # turn/completed: the error is read only for a failed turn, and
        # the usage takes cache reads from cacheReadTokens, else
        # cachedTokens, with no total, because TokenUsage has none.
        try:
            fields = RecordFieldConverter.require_instance(params, "turn/completed", Mapping)
            terminal = RecordFieldConverter.require_instance(fields.get("terminal"), "terminal", str)
            error = RecordFieldConverter.require_instance(fields.get("error"), "error", Mapping) if terminal == native_host_constants.MUSE_FAILED_TERMINAL else {}
            raw_usage = RecordFieldConverter.require_instance(fields.get("usage"), "usage", Mapping, optional=True)
            usage = None
            if raw_usage is not None:
                cache_read = raw_usage.get("cacheReadTokens", raw_usage.get("cachedTokens"))
                usage = NativeTokenUsage(
                    input_tokens=raw_usage.get("inputTokens"),
                    output_tokens=raw_usage.get("outputTokens"),
                    reasoning_tokens=raw_usage.get("reasoningTokens"),
                    cache_read_tokens=cache_read,
                    cache_write_tokens=raw_usage.get("cacheWriteTokens"),
                )
            return MuseTurnCompleted(
                session_id=fields.get("sessionId"),
                turn_id=fields.get("turnId"),
                terminal=terminal,
                error_kind=error.get("kind"),
                error_message=error.get("message"),
                error_retryable=error.get("retryable"),
                usage=usage,
            )
        except ConfigurationError as exc:
            raise MuseWire._mismatch("turn/completed", exc.details.get("field"), operation) from exc

    @staticmethod
    def _session(value: object, field: str) -> MuseSession:
        # One MSP Session object, refused as field when it is not an
        # object; forkedFrom is a ForkProvenance object whose
        # sessionId names the source.
        fields = RecordFieldConverter.require_instance(value, field, Mapping)
        forked = fields.get("forkedFrom")
        forked_from = forked.get("sessionId") if isinstance(forked, Mapping) else forked
        return MuseSession(
            session_id=fields.get("sessionId"),
            workspace_root=fields.get("workspaceRoot"),
            status=fields.get("status"),
            active_turn_id=fields.get("activeTurnId"),
            model_id=fields.get("modelId"),
            provider_id=fields.get("providerId"),
            forked_from=forked_from,
            turn_count=fields.get("turnCount"),
            created_at=fields.get("createdAt"),
            updated_at=fields.get("updatedAt"),
        )

    @staticmethod
    def _mismatch(source: str, field: object, operation: str) -> NativeHostError:
        # A relied-on member is missing or has the wrong type.
        name = str(field or source).rsplit(".", 1)[-1]
        message = f"Muse Code sent a {source} frame whose {name} member is missing or has the wrong type."
        return _ERRORS.build(FailureCode.MUSE_PROTOCOL_MISMATCH, message, operation=operation, context={"method": source, "field": name})


__all__ = ["MuseWire"]
