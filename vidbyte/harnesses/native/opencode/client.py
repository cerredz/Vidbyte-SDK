"""FILE: vidbyte/harnesses/native/opencode/client.py

PURPOSE: Defines OpencodeClient, the one place an OpencodeHost makes HTTP calls: it builds each URL with urlencode and quoted path segments (always with directory=<workspace>), adds the basic-auth header, sends through HttpTransport with the host's request deadline and OPENCODE_MAX_RESPONSE_BYTES, and maps transport failures and status codes to the EC-55 to EC-59 rows.
ROLE IN CODEBASE: Built by OpencodeHost and shared with its OpencodeTurnWatcher instances; reads the owned server's exit code from OpencodeServer to tell EC-56 from EC-55. Bodies it returns are decoded JSON, which OpencodeWire turns into records.
ARCHITECTURE NOTE: An HTTP adapter over the canonical HttpTransport (AGENTS.md principle 5, D-5): no retry, no redirect, a bounded body. JSON floats decode as Decimal so costs stay exact. A route's own 404 or 409 meaning is passed in by the caller; any other 404 is protocol_mismatch.
FUNCTION INVENTORY: connect records the server address and credentials; call is the narrated main function for one request; probe tells whether a GET finds its object; _url builds the address; _send runs the request and maps transport failures; _status_error maps a non-2xx answer; _decode reads the JSON body.
COMMON MODIFICATION PATTERNS: A new route is a new call site with its path segments; a new status rule is one branch in _status_error.
WHAT NOT TO DO IN THIS FILE: 1. Do not put the password or any credential in a URL, a query or an error; it travels only in the Authorization header. 2. Do not surface ProviderRequestError text or response_excerpt; both may echo the request. 3. Do not retry; opencode routes are not idempotent and the watcher has its own failure count.
KNOWN EDGE CASES: A 204 or empty body decodes to None. A ProviderRequestError with a status code means the body passed the size cap (EC-58); one without a status means no answer arrived, which is EC-56 once the owned server's exit has been collected and EC-55 before that (EC-153).
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (OpencodeClient, HTTP routes), D-5, EC-55 to EC-59, EC-153, T-2
TESTS: tests/features/opencode_host/test_opencode_host_errors.py, tests/features/opencode_host/test_opencode_host_acceptance.py, tests/features/opencode_host/test_opencode_host_security.py
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.harnesses.native.opencode.server import OpencodeServer
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import NativeHostError, ProviderRequestError
from vidbyte.lib.http.transport import HttpResponse, HttpTransport

_UNAUTHORIZED_STATUS = 401
_NOT_FOUND_STATUS = 404
_CONFLICT_STATUS = 409
_UNAVAILABLE_STATUS = 503
_GET = "GET"
_DIRECTORY_QUERY = "directory"
_SIGNED_OUT_STEP = "The opencode server rejected the host's credentials; check server_username and server_password."


class OpencodeClient:
    """Every HTTP call one OpencodeHost makes to its opencode server."""

    def __init__(self, *, server: OpencodeServer, workspace: Path, request_timeout_seconds: float, errors: NativeErrorFactory) -> None:
        # @intent opencode-client-one-bounded-transport
        # Every call goes through one HttpTransport with the host's
        # request_timeout_seconds and a body cap, scoped to the
        # workspace by the directory query; no call is retried
        # here, because the watcher owns the only retry budget and
        # a write must not repeat.
        self._server = server
        self._directory = str(workspace)
        self._timeout_seconds = request_timeout_seconds
        self._errors = errors
        self._transport = HttpTransport()
        self._base_url = ""
        self._headers: dict[str, str] = {"accept": "application/json"}

    def connect(self, base_url: str, credentials: tuple[str, str] | None) -> None:
        # The server's address, and the basic-auth header when the
        # server needs credentials.
        self._base_url = base_url.rstrip("/")
        if credentials is not None:
            pair = f"{credentials[0]}:{credentials[1]}".encode()
            self._headers["authorization"] = f"Basic {base64.b64encode(pair).decode('ascii')}"

    async def call(
        self,
        method: str,
        segments: tuple[str, ...],
        *,
        operation: str,
        query: Mapping[str, str] | None = None,
        body: Mapping[str, object] | None = None,
        not_found: FailureCode | None = None,
        conflict: FailureCode | None = None,
        context: Mapping[str, str] | None = None,
    ) -> Any:
        # @intent opencode-client-one-bounded-request
        # One request to one listed route, bounded by the host's request
        # deadline and the response size cap, with every failure mapped
        # to its opencode.* failure before the caller sees it.
        # Build the address with the workspace in the query and send it.
        response = await self._send(method, self._url(segments, query), body, operation=operation)

        # A non-2xx answer becomes its failure; the route's own 404 and
        # 409 meanings come from the caller.
        if not native_host_constants.NATIVE_HTTP_SUCCESS_FIRST_STATUS <= response.status_code < native_host_constants.NATIVE_HTTP_SUCCESS_END_STATUS:
            raise self._status_error(response, operation=operation, not_found=not_found, conflict=conflict, context=context)

        # A 2xx body must be JSON (or empty, as for 204).
        return self._decode(response, operation=operation)

    async def probe(self, segments: tuple[str, ...], *, operation: str) -> bool:
        # @intent opencode-client-existence-probe
        # A GET whose 404 answers "not there" instead of raising, for
        # the checks a route cannot do itself (abort answers 200 for a
        # missing session); every other failure still raises.
        response = await self._send(_GET, self._url(segments, None), None, operation=operation)
        if response.status_code == _NOT_FOUND_STATUS:
            return False
        if not native_host_constants.NATIVE_HTTP_SUCCESS_FIRST_STATUS <= response.status_code < native_host_constants.NATIVE_HTTP_SUCCESS_END_STATUS:
            raise self._status_error(response, operation=operation, not_found=None, conflict=None, context=None)
        return True

    def _url(self, segments: tuple[str, ...], query: Mapping[str, str] | None) -> str:
        # Each path segment is quoted whole, so an id can never add a
        # path step; directory is always sent.
        path = "/".join(quote(segment, safe="") for segment in segments)
        parameters = {**(query or {}), _DIRECTORY_QUERY: self._directory}
        return f"{self._base_url}/{path}?{urlencode(parameters)}"

    async def _send(self, method: str, url: str, body: Mapping[str, object] | None, *, operation: str) -> HttpResponse:
        # @intent opencode-client-transport-failures
        # No answer at all is process_exited once the owned server's
        # exit is known and server_unreachable before that; an answer
        # over the size cap is protocol_mismatch. The transport's text
        # is never copied, because it can echo the request.
        try:
            return await self._transport.request(method=method, url=url, headers=self._headers, json_body=body, timeout_seconds=self._timeout_seconds, max_response_bytes=native_host_constants.OPENCODE_MAX_RESPONSE_BYTES)
        except ProviderRequestError as exc:
            if exc.status_code is not None:
                raise self._errors.build(FailureCode.OPENCODE_PROTOCOL_MISMATCH, "The opencode server sent an answer larger than this SDK reads.", operation=operation, context={"reason": "response_too_large"}) from exc
            exit_code = self._server.exit_code
            if exit_code is not None:
                raise self._errors.build(FailureCode.OPENCODE_PROCESS_EXITED, f"The opencode server this host started exited with code {exit_code}.", operation=operation, context={"exit_code": str(exit_code)}) from exc
            raise self._errors.build(FailureCode.OPENCODE_SERVER_UNREACHABLE, "The opencode server did not answer within the request deadline.", operation=operation) from exc

    def _status_error(self, response: HttpResponse, *, operation: str, not_found: FailureCode | None, conflict: FailureCode | None, context: Mapping[str, str] | None) -> NativeHostError:
        # @intent opencode-client-status-failures
        # 401 is a credential mismatch, 503 a server that cannot serve
        # yet, 404 and 409 mean what the route says or else a protocol
        # mismatch, and any other status is an API error carrying the
        # vendor's name and scrubbed message.
        status = response.status_code
        if status == _UNAUTHORIZED_STATUS:
            return self._errors.build(FailureCode.OPENCODE_NOT_SIGNED_IN, "The opencode server answered 401 Unauthorized.", operation=operation, next_step=_SIGNED_OUT_STEP, context={"status_code": str(status)})
        if status == _UNAVAILABLE_STATUS:
            return self._errors.build(FailureCode.OPENCODE_SERVER_UNREACHABLE, "The opencode server answered 503 and cannot serve requests yet.", operation=operation, context={"status_code": str(status)})
        if status == _NOT_FOUND_STATUS and not_found is not None:
            return self._errors.build(not_found, "The opencode server does not know the requested session or message.", operation=operation, context=dict(context or {}))
        if status == _CONFLICT_STATUS and conflict is not None:
            return self._errors.build(conflict, "The opencode server reports the session as busy.", operation=operation, context=dict(context or {}))
        if status == _NOT_FOUND_STATUS:
            return self._errors.build(FailureCode.OPENCODE_PROTOCOL_MISMATCH, "The opencode server does not offer a route this SDK relies on.", operation=operation, context={"status_code": str(status)})
        details: dict[str, str] = {**(context or {}), "status_code": str(status)}
        try:
            payload = json.loads(response.body)
        except ValueError:
            payload = None
        if isinstance(payload, Mapping):
            data = payload.get("data")
            name = payload.get("name") or payload.get("_tag") or ""
            message = data.get("message") if isinstance(data, Mapping) else payload.get("message")
            details["vendor_error"] = ": ".join(str(part) for part in (name, message) if part)
        elif response.body.strip():
            details["vendor_error"] = response.body
        return self._errors.build(FailureCode.OPENCODE_API_ERROR, f"The opencode server answered HTTP {status}.", operation=operation, context=details)

    def _decode(self, response: HttpResponse, *, operation: str) -> Any:
        # The JSON body with floats as Decimal; an empty body is None.
        if not response.body.strip():
            return None
        try:
            return json.loads(response.body, parse_float=Decimal)
        except ValueError as exc:
            raise self._errors.build(FailureCode.OPENCODE_PROTOCOL_MISMATCH, "The opencode server sent an answer that is not JSON.", operation=operation, context={"reason": "not_json"}) from exc


__all__ = ["OpencodeClient"]
