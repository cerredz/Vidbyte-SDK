"""FILE: vidbyte/harnesses/native/grok/wire.py

PURPOSE: Defines GrokWire, the Grok codec: it builds the ACP request params GrokHost sends, turns every ACP answer, server frame and Grok CLI outcome into a §9.1 record, and maps JSON-RPC error codes and CLI failures to the grok.* rows of spec §6.3.
ROLE IN CODEBASE: Owned by GrokHost (vidbyte/harnesses/native/grok/host.py) and shared with each GrokTurnDriver (turn.py). Neither of them reads a raw vendor field; they call one parse or check method here and get a record or a NativeHostError.
ARCHITECTURE NOTE: Pure functions over plain mappings and CliOutcome records, plus the host's NativeErrorFactory for building errors. A wrong shape is never smoothed over: missing optional fields become None or empty, but a field of the wrong type raises grok.protocol_mismatch. Open vocabularies (stop reasons, update kinds, tool kinds) are kept verbatim or mapped by the spec's own rule.
FUNCTION INVENTORY: Params: initialize_params, new_session_params, resume_session_params, list_sessions_params, prompt_params, cancel_params, permission_answer, method_not_found. ACP answers: check_initialize, require_session_capability, parse_model_catalog, require_model, parse_readiness, parse_session_id, parse_session_page, vendor_error, is_cancel_answer. Turn frames: parse_permission_request, parse_session_update, parse_prompt_result. CLI: check_cli, parse_version, parse_one_shot, check_fork_result. Private single-step helpers: _mismatch, _meta, _model, _tool_kind, _chunk_text, _cost, _usage, _signed_out.
COMMON MODIFICATION PATTERNS: A new JSON-RPC code row is one branch in vendor_error; a new ACP field is read in the parse method of its record; a new CLI failure text is a marker in GROK_NOT_SIGNED_IN_MARKERS.
WHAT NOT TO DO IN THIS FILE: 1. Do not copy exception text into an error; vendor text goes only into context values, which the factory scrubs and caps. 2. Do not start processes or await anything here. 3. Do not answer a permission with an allow_always or reject_always option.
KNOWN EDGE CASES: Grok answers an unknown --model by silently using its default, so the model check compares currentModelId with the requested id (EC-25). A JSON number cost is read through its text form so no binary float reaches the Decimal. A -32602 answer means a stale cursor only when a cursor was sent (EC-41).
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Grok host), §6.3.3, §9.1, D-11, D-12, D-14, EC-6, EC-7
TESTS: tests/features/grok_host/test_grok_host_errors.py, tests/features/grok_host/test_grok_host_reads.py, tests/features/grok_host/test_grok_host_turns.py
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

import vidbyte
from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.grok import (
    GrokModel,
    GrokModelCatalog,
    GrokOneShotResult,
    GrokPermissionOption,
    GrokPermissionRequest,
    GrokPromptResult,
    GrokReadiness,
    GrokSession,
    GrokSessionPage,
    GrokSessionUpdate,
)
from vidbyte.lib.dataclasses.native_hosts import NativeTokenUsage
from vidbyte.lib.dataclasses.process import CliOutcome
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_hosts import AcpToolKind
from vidbyte.lib.errors import ConfigurationError, McpProtocolError, NativeHostError

_AUTH_REQUIRED = -32000
_RESOURCE_NOT_FOUND = -32002
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_REQUEST_CANCELLED = -32800
_MALFORMED_CODES = frozenset({-32700, -32600})
_FS_NOT_FOUND = "FS_NOT_FOUND"
_AGENT_VERSION_PATTERN = r"^(\d+)\.(\d+)\.(\d+)"
_SESSION_ID_PATTERN = r"^\S+$"
_TEXT_CONTENT = "text"
_SELECTED = "selected"
_CANCELLED = "cancelled"
_EFFORT_NEXT_STEP = "Pick a reasoning effort list_grok_models shows for this model."
_ONE_SHOT_TIMEOUT_NEXT_STEP = "The one-shot run was stopped at max_turn_seconds; raise it or use spawn_grok_session for long work."


class GrokWire:
    """Builds Grok ACP params and turns Grok answers, frames and CLI outcomes into records or grok.* errors."""

    INITIALIZE: ClassVar[str] = "initialize"
    NEW_SESSION: ClassVar[str] = "session/new"
    RESUME_SESSION: ClassVar[str] = "session/resume"
    LIST_SESSIONS: ClassVar[str] = "session/list"
    PROMPT: ClassVar[str] = "session/prompt"
    CANCEL: ClassVar[str] = "session/cancel"
    REQUEST_PERMISSION: ClassVar[str] = "session/request_permission"
    SESSION_UPDATE: ClassVar[str] = "session/update"
    AGENT_MESSAGE_CHUNK: ClassVar[str] = "agent_message_chunk"
    USAGE_UPDATE: ClassVar[str] = "usage_update"
    CANCELLED_STOP_REASON: ClassVar[str] = "cancelled"
    LIST_CAPABILITY: ClassVar[str] = "list"
    RESUME_CAPABILITY: ClassVar[str] = "resume"

    def __init__(self, errors: NativeErrorFactory) -> None:
        self._errors = errors

    # ---- ACP request params -------------------------------------------------

    @staticmethod
    def initialize_params() -> dict[str, Any]:
        # §8.5: protocol 1, no file system or terminal for the agent, and who
        # the client is; the version is read on each call, as for Muse.
        capabilities = {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False}
        client = {"name": native_host_constants.GROK_CLIENT_NAME, "title": native_host_constants.GROK_CLIENT_TITLE, "version": vidbyte.__version__}
        return {"protocolVersion": native_host_constants.GROK_ACP_PROTOCOL_VERSION, "clientCapabilities": capabilities, "clientInfo": client}

    @staticmethod
    def new_session_params(cwd: Path) -> dict[str, Any]:
        # A session in the workspace with no MCP servers and never a _meta block (INV-9).
        return {"cwd": str(cwd), "mcpServers": []}

    @staticmethod
    def resume_session_params(session_id: str, cwd: Path) -> dict[str, Any]:
        # Resumes one session in the workspace with no MCP servers.
        return {"sessionId": session_id, "cwd": str(cwd), "mcpServers": []}

    @staticmethod
    def list_sessions_params(cwd: Path, cursor: str | None) -> dict[str, Any]:
        # One page of the workspace's sessions; the cursor is passed back verbatim.
        params: dict[str, Any] = {"cwd": str(cwd)}
        if cursor is not None:
            params["cursor"] = cursor
        return params

    @staticmethod
    def prompt_params(session_id: str, prompt: str) -> dict[str, Any]:
        # The prompt travels as one text content block.
        return {"sessionId": session_id, "prompt": [{"type": _TEXT_CONTENT, "text": prompt}]}

    @staticmethod
    def cancel_params(session_id: str) -> dict[str, Any]:
        # session/cancel names only the session.
        return {"sessionId": session_id}

    @staticmethod
    def permission_answer(option_id: str | None) -> dict[str, Any]:
        # @intent grok-permission-answer-shape
        # D-11: the host answers with the one option it chose, or with the
        # cancelled outcome when no option fits, never an option it was not
        # offered.
        if option_id is None:
            return {"outcome": {"outcome": _CANCELLED}}
        return {"outcome": {"outcome": _SELECTED, "optionId": option_id}}

    @staticmethod
    def method_not_found() -> dict[str, Any]:
        # INV-10: the JSON-RPC answer to any server request the host does not serve.
        return {"code": _METHOD_NOT_FOUND, "message": "Method not found"}

    # ---- ACP answers ----------------------------------------------------------

    def check_initialize(self, result: Mapping[str, Any], *, operation: str) -> None:
        # The peer must speak this SDK's ACP version, and its agent version must be supported (EC-17).
        try:
            version = RecordFieldConverter.require_instance(result.get("protocolVersion"), "protocolVersion", int)
            agent = RecordFieldConverter.require_instance(self._meta(result).get("agentVersion"), "agentVersion", str, optional=True)
        except ConfigurationError as exc:
            raise self._mismatch(operation, "initialize") from exc
        if version != native_host_constants.GROK_ACP_PROTOCOL_VERSION:
            raise self._mismatch(operation, "protocol_version")
        found = re.match(_AGENT_VERSION_PATTERN, agent or "")
        if agent is not None and found is None:
            raise self._mismatch(operation, "agent_version")
        if found is not None and tuple(int(part) for part in found.groups()) < native_host_constants.GROK_MIN_VERSION:
            raise self._errors.build(self._errors.code("version_unsupported"), "This Grok Build agent is older than this SDK supports.", operation=operation, context={"version": agent or ""})

    def require_session_capability(self, result: Mapping[str, Any], capability: str, *, operation: str, next_step: str) -> None:
        # The ACP session capability this call needs must be offered (EC-20, EC-30, EC-40).
        capabilities = result.get("agentCapabilities")
        session = capabilities.get("sessionCapabilities") if isinstance(capabilities, Mapping) else None
        if isinstance(session, Mapping) and session.get(capability) is not None:
            return
        method = "session/" + capability
        raise self._errors.build(self._errors.code("capability_missing"), f"This Grok Build release does not offer ACP {method}.", operation=operation, next_step=next_step, context={"method": method})

    def parse_model_catalog(self, result: Mapping[str, Any], *, operation: str) -> GrokModelCatalog:
        # D-12: the models and their reasoning efforts come from initialize's _meta.modelState (EC-22).
        try:
            state = RecordFieldConverter.require_instance(self._meta(result).get("modelState"), "modelState", Mapping)
            entries = RecordFieldConverter.to_tuple(state.get("availableModels"), "availableModels", item_type=Mapping)
            return GrokModelCatalog(current_model_id=state.get("currentModelId"), models=tuple(self._model(entry) for entry in entries))
        except ConfigurationError as exc:
            raise self._mismatch(operation, "model_state") from exc

    def require_model(self, catalog: GrokModelCatalog, model: str | None, reasoning_effort: str | None, *, operation: str) -> None:
        # @intent grok-live-model-check
        # D-12: the peer was started with --model, and Grok silently falls
        # back to its default for an id it does not know, so the requested
        # model must be the current one; an effort must be one the current
        # model lists. Both are checked before anything spends money.
        if model is not None and catalog.current_model_id != model:
            offered = self._errors.listing(entry.model_id for entry in catalog.models)
            raise self._errors.build(self._errors.code("model_unknown"), f"Grok Build does not offer the model {model}.", operation=operation, context={"available_models": offered})
        if reasoning_effort is None:
            return
        current = next((entry for entry in catalog.models if entry.model_id == catalog.current_model_id), None)
        if current is None or reasoning_effort not in current.reasoning_efforts:
            message = f"The model {catalog.current_model_id} does not accept the reasoning effort {reasoning_effort}."
            raise self._errors.build(self._errors.code("capability_missing"), message, operation=operation, next_step=_EFFORT_NEXT_STEP)

    def parse_readiness(self, version: str, result: Mapping[str, Any], *, operation: str) -> GrokReadiness:
        # FR-1: the CLI version plus what initialize reported.
        try:
            meta = self._meta(result)
            state = RecordFieldConverter.require_instance(meta.get("modelState"), "modelState", Mapping)
            methods = RecordFieldConverter.to_tuple(result.get("authMethods", []), "authMethods", item_type=Mapping)
            return GrokReadiness(
                version=version,
                protocol_version=RecordFieldConverter.require_instance(result.get("protocolVersion"), "protocolVersion", int),
                agent_version=meta.get("agentVersion"),
                auth_method_ids=tuple(method.get("id") for method in methods),
                current_model_id=state.get("currentModelId"),
            )
        except ConfigurationError as exc:
            raise self._mismatch(operation, "initialize") from exc

    def parse_session_id(self, result: Mapping[str, Any], *, operation: str) -> str:
        # session/new answers with the new session's id (EC-14).
        try:
            return RecordFieldValidator.require_text(result.get("sessionId"), "sessionId", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=_SESSION_ID_PATTERN)
        except ConfigurationError as exc:
            raise self._mismatch(operation, "session_id") from exc

    def parse_session_page(self, result: Mapping[str, Any], *, operation: str) -> GrokSessionPage:
        # One session/list page; every entry needs an id and a cwd (EC-42).
        try:
            entries = RecordFieldConverter.to_tuple(result.get("sessions"), "sessions", item_type=Mapping)
            sessions = tuple(GrokSession(session_id=entry.get("sessionId"), cwd=entry.get("cwd"), title=entry.get("title"), updated_at=entry.get("updatedAt")) for entry in entries)
            return GrokSessionPage(sessions=sessions, next_cursor=result.get("nextCursor"))
        except ConfigurationError as exc:
            raise self._mismatch(operation, "session_list") from exc

    def vendor_error(self, exc: McpProtocolError, *, operation: str, method: str, session_id: str | None = None, cursor: str | None = None) -> NativeHostError:
        # @intent grok-json-rpc-codes-to-rows
        # §6.3.3: ACP -32000 is authentication, -32002 or an FS_NOT_FOUND
        # payload is a missing session, -32601 a missing method, -32602 on a
        # cursor a stale cursor (EC-41), -32700 and -32600 a protocol
        # mismatch, and every other code, -32602 without a cursor included,
        # an api_error carrying the vendor code and message (EC-16). A
        # failure without a JSON-RPC error is a transport one.
        vendor = exc.details.get("error")
        if not isinstance(vendor, Mapping):
            return self._errors.from_protocol_error(exc, operation=operation)
        code = vendor.get("code")
        data = vendor.get("data")
        session = {"session_id": session_id} if session_id is not None else {}
        if code == _AUTH_REQUIRED:
            return self._errors.build(self._errors.code("not_signed_in"), "Grok Build is not signed in.", operation=operation, context=session)
        if code == _RESOURCE_NOT_FOUND or (isinstance(data, Mapping) and data.get("code") == _FS_NOT_FOUND):
            return self._errors.build(self._errors.code("session_not_found"), "Grok Build has no such session in this workspace.", operation=operation, context=session)
        if code == _METHOD_NOT_FOUND:
            return self._errors.build(self._errors.code("capability_missing"), f"This Grok Build release does not serve ACP {method}.", operation=operation, context={"method": method})
        if code == _INVALID_PARAMS and cursor is not None:
            return self._errors.invalid_argument("cursor", "Grok Build refused the cursor; it is stale or was not issued by list_grok_sessions.", operation=operation, next_step=native_host_constants.NATIVE_STALE_CURSOR_NEXT_STEP.format(tool="list_grok_sessions"))
        if isinstance(code, int) and code in _MALFORMED_CODES:
            return self._errors.build(self._errors.code("protocol_mismatch"), f"Grok Build could not read this SDK's {method} request.", operation=operation, context={"vendor_code": str(code), "method": method})
        context = {"vendor_code": str(code), "vendor_error": str(vendor.get("message", "")), **session}
        return self._errors.build(self._errors.code("api_error"), f"Grok Build answered {method} with an error.", operation=operation, context=context)

    @staticmethod
    def is_cancel_answer(exc: McpProtocolError) -> bool:
        # True when a session/prompt was answered with JSON-RPC -32800, the request-cancelled code.
        vendor = exc.details.get("error")
        return isinstance(vendor, Mapping) and vendor.get("code") == _REQUEST_CANCELLED

    # ---- Turn frames ----------------------------------------------------------

    def parse_permission_request(self, frame: Mapping[str, Any]) -> GrokPermissionRequest:
        # @intent grok-permission-request-is-a-record
        # A session/request_permission server request becomes a record
        # before the driver decides on it; a missing or unknown tool kind is
        # OTHER (§9.1), and any other wrong shape fails the turn rather than
        # being answered on a guess.
        try:
            params = RecordFieldConverter.require_instance(frame.get("params"), "params", Mapping)
            call = RecordFieldConverter.require_instance(params.get("toolCall"), "toolCall", Mapping)
            entries = RecordFieldConverter.to_tuple(params.get("options"), "options", item_type=Mapping)
            options = tuple(GrokPermissionOption(option_id=entry.get("optionId"), kind=entry.get("kind")) for entry in entries)
            title = call.get("title")
            return GrokPermissionRequest(request_id=RecordFieldConverter.require_instance(frame.get("id"), "id", (int, str)), session_id=params.get("sessionId"), tool_kind=self._tool_kind(call.get("kind")), title="" if title is None else title, options=options)
        except ConfigurationError as exc:
            raise self._mismatch(native_host_constants.GROK_TURN_OPERATION, "permission_request") from exc

    def parse_session_update(self, params: Any) -> GrokSessionUpdate:
        # A session/update notification's params: message text for a chunk, the cost for a usage update, the kind verbatim otherwise (EC-7).
        try:
            params = RecordFieldConverter.require_instance(params, "params", Mapping)
            update = RecordFieldConverter.require_instance(params.get("update"), "update", Mapping)
            kind = RecordFieldConverter.require_instance(update.get("sessionUpdate"), "sessionUpdate", str)
            text = self._chunk_text(update) if kind == self.AGENT_MESSAGE_CHUNK else ""
            amount, currency = self._cost(update) if kind == self.USAGE_UPDATE else (None, None)
            return GrokSessionUpdate(session_id=params.get("sessionId"), kind=kind, text=text, cost_amount=amount, cost_currency=currency)
        except ConfigurationError as exc:
            raise self._mismatch(native_host_constants.GROK_TURN_OPERATION, "session_update") from exc

    def parse_prompt_result(self, result: Mapping[str, Any]) -> GrokPromptResult:
        # The session/prompt answer: a verbatim stopReason (EC-49) and the usage when Grok sent one (D-14).
        try:
            stop_reason = RecordFieldValidator.require_text(result.get("stopReason"), "stopReason", max_chars=native_host_constants.NATIVE_ID_MAX_CHARS)
            usage = result.get("usage")
            return GrokPromptResult(stop_reason=stop_reason, usage=None if usage is None else self._usage(usage))
        except ConfigurationError as exc:
            raise self._mismatch(native_host_constants.GROK_TURN_OPERATION, "prompt_result") from exc

    # ---- CLI outcomes ---------------------------------------------------------

    def check_cli(self, outcome: CliOutcome, *, operation: str, one_shot: bool) -> None:
        # @intent grok-cli-outcome-to-rows
        # A missing program is not_installed and any other launch failure
        # process_exited; a run past its bound is turn_timed_out for a
        # one-shot or fork run (EC-38) and server_unreachable otherwise; the
        # signed-out line or a sign-in marker on a failed run is
        # not_signed_in; any other non-zero exit is api_error with the exit
        # code as vendor_code.
        if outcome.launch_failure is not None:
            raise self._errors.from_launch_failure(outcome.launch_failure, operation=operation)
        if outcome.timed_out and one_shot:
            raise self._errors.build(self._errors.code("turn_timed_out"), "The Grok run did not finish within max_turn_seconds, so it was stopped.", operation=operation, next_step=_ONE_SHOT_TIMEOUT_NEXT_STEP)
        if outcome.timed_out:
            raise self._errors.build(self._errors.code("server_unreachable"), "Grok Build did not finish within control_timeout_seconds.", operation=operation, context={"reason": "timeout"})
        if self._signed_out(outcome):
            raise self._errors.build(self._errors.code("not_signed_in"), "Grok Build is not signed in.", operation=operation)
        if outcome.exit_code != native_host_constants.NATIVE_SUCCESS_EXIT_CODE:
            context = {"vendor_code": str(outcome.exit_code), "vendor_error": outcome.stderr.strip() or outcome.stdout.strip(), "exit_code": str(outcome.exit_code)}
            raise self._errors.build(self._errors.code("api_error"), "Grok Build exited with an error.", operation=operation, context=context)

    def parse_version(self, outcome: CliOutcome, *, operation: str) -> str:
        # grok --version must name a release of at least GROK_MIN_VERSION (EC-18, EC-19).
        found = re.search(native_host_constants.GROK_VERSION_PATTERN, outcome.stdout)
        if found is None:
            raise self._mismatch(operation, "version_output")
        version = ".".join(found.groups())
        if tuple(int(part) for part in found.groups()) < native_host_constants.GROK_MIN_VERSION:
            raise self._errors.build(self._errors.code("version_unsupported"), "This Grok Build release is older than this SDK supports.", operation=operation, context={"version": version})
        return version

    def parse_one_shot(self, outcome: CliOutcome, *, operation: str) -> GrokOneShotResult:
        # The --output-format json object; text past NATIVE_RESULT_TEXT_MAX_CHARS is cut and flagged (INV-16).
        cap = native_host_constants.NATIVE_RESULT_TEXT_MAX_CHARS
        try:
            body = RecordFieldConverter.require_instance(json.loads(outcome.stdout), "output", Mapping)
            text = RecordFieldConverter.require_instance(body.get("text"), "text", str)
            session_id = RecordFieldValidator.require_text(body.get("sessionId"), "sessionId", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=_SESSION_ID_PATTERN)
            return GrokOneShotResult(text=text[:cap], text_truncated=len(text) > cap, stop_reason=body.get("stopReason"), session_id=session_id, request_id=body.get("requestId"))
        except (ConfigurationError, ValueError) as exc:
            raise self._mismatch(operation, "one_shot_output") from exc

    def check_fork_result(self, result: GrokOneShotResult, *, source: str, target: str | None, operation: str) -> None:
        # A fork must report a session other than its source, and the requested one when it was named (EC-39); UUIDs compare ignoring letter case (INV-14).
        returned = result.session_id.lower()
        if returned == source.lower() or (target is not None and returned != target.lower()):
            raise self._mismatch(operation, "fork_session_id")

    # ---- Single-step helpers --------------------------------------------------

    def _mismatch(self, operation: str, reason: str) -> NativeHostError:
        # grok.protocol_mismatch naming which part of Grok's answer could not be read.
        return self._errors.build(self._errors.code("protocol_mismatch"), "Grok Build sent an answer this SDK cannot read.", operation=operation, context={"reason": reason})

    @staticmethod
    def _meta(result: Mapping[str, Any]) -> Mapping[str, Any]:
        # The answer's _meta object; absent means empty, any other type is refused.
        meta = result.get("_meta")
        return {} if meta is None else RecordFieldConverter.require_instance(meta, "_meta", Mapping)

    @staticmethod
    def _model(entry: Mapping[str, Any]) -> GrokModel:
        # One availableModels entry with the efforts listed in its own _meta.reasoningEfforts.
        meta = entry.get("_meta")
        meta = {} if meta is None else RecordFieldConverter.require_instance(meta, "_meta", Mapping)
        efforts = RecordFieldConverter.to_tuple(meta.get("reasoningEfforts", []), "reasoningEfforts", item_type=str)
        return GrokModel(model_id=RecordFieldConverter.require_instance(entry.get("modelId"), "modelId", str), name=entry.get("name"), description=entry.get("description"), reasoning_efforts=efforts)

    @staticmethod
    def _tool_kind(value: Any) -> AcpToolKind:
        # §9.1: a missing or unknown ACP tool kind counts as OTHER.
        members = {member.value: member for member in AcpToolKind}
        return members.get(value, AcpToolKind.OTHER) if isinstance(value, str) else AcpToolKind.OTHER

    @staticmethod
    def _chunk_text(update: Mapping[str, Any]) -> str:
        # The text of an agent_message_chunk; a non-text content block adds no text.
        content = RecordFieldConverter.require_instance(update.get("content"), "content", Mapping)
        if content.get("type") != _TEXT_CONTENT:
            return ""
        return str(RecordFieldConverter.require_instance(content.get("text"), "text", str))

    @staticmethod
    def _cost(update: Mapping[str, Any]) -> tuple[Decimal | None, str | None]:
        # The cost of a usage_update as a Decimal read from its text form, with its currency.
        cost = update.get("cost")
        if cost is None:
            return None, None
        cost = RecordFieldConverter.require_instance(cost, "cost", Mapping)
        amount = RecordFieldConverter.require_instance(cost.get("amount"), "amount", (str, int, float))
        currency = RecordFieldConverter.require_instance(cost.get("currency"), "currency", str)
        return RecordFieldConverter.to_decimal(str(amount), "amount"), currency

    @staticmethod
    def _usage(value: Any) -> NativeTokenUsage:
        # ACP PromptResponse.usage; a count Grok left out stays None, never zero (INV-15).
        usage = RecordFieldConverter.require_instance(value, "usage", Mapping)
        return NativeTokenUsage(
            input_tokens=usage.get("inputTokens"),
            output_tokens=usage.get("outputTokens"),
            reasoning_tokens=usage.get("thoughtTokens"),
            cache_read_tokens=usage.get("cachedReadTokens"),
            cache_write_tokens=usage.get("cachedWriteTokens"),
            total_tokens=usage.get("totalTokens"),
        )

    @staticmethod
    def _signed_out(outcome: CliOutcome) -> bool:
        # The exact signed-out line on stdout, or a sign-in marker in the output of a failed run.
        if native_host_constants.GROK_SIGNED_OUT_LINE in {line.strip() for line in outcome.stdout.splitlines()}:
            return True
        text = (outcome.stdout + "\n" + outcome.stderr).casefold()
        return outcome.exit_code != native_host_constants.NATIVE_SUCCESS_EXIT_CODE and any(marker in text for marker in native_host_constants.GROK_NOT_SIGNED_IN_MARKERS)


__all__ = ["GrokWire"]
