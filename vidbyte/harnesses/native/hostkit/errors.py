"""FILE: vidbyte/harnesses/native/hostkit/errors.py

PURPOSE: Defines NativeErrorFactory, which builds every NativeHostError a native host raises: it scrubs vendor text (the shared HarnessRedactor plus every value the host injected), caps it, and maps launch failures, transport failures and unexpected exceptions to the spec's failure codes.
ROLE IN CODEBASE: One factory per host (GrokHost, OpencodeHost, MuseHost), shared with that host's NativeTurnTable and NativePeer. Hosts and their wire codecs call build for every row of spec §6.3.
ARCHITECTURE NOTE: Lives in hostkit, not vidbyte.lib, because scrubbing reuses HarnessRedactor from vidbyte.harnesses.serialization and lib may not import upward (D-22). Codes are looked up as "<harness>.<problem>" so one factory serves all three hosts.
FUNCTION INVENTORY: register_secret remembers an injected value; scrub redacts and caps text; listing joins ids for a context value; build makes a NativeHostError with scrubbed message and context; invalid_argument makes configuration.invalid_argument naming the argument; from_configuration_error maps a validator or record refusal to the same code; from_unexpected maps a defect to runtime.error; from_launch_failure maps a process launch failure; from_protocol_error maps a McpProtocolError reason.
COMMON MODIFICATION PATTERNS: A new transport reason gets one entry in _EXITED_REASONS or its own branch in from_protocol_error; a new harness needs its codes in FailureCode and a label in _LABELS.
WHAT NOT TO DO IN THIS FILE: 1. Do not put raw exception text into a message or context; only class names and scrubbed vendor text. 2. Do not add context keys outside the spec §13 list. 3. Do not raise from build; a builder that fails would hide the original error.
KNOWN EDGE CASES: A registered value is replaced before the redactor runs and before the cap, so a cap cannot cut a secret in half and leave its prefix. Empty text stays empty instead of becoming the redactor's "raised without a message" fallback.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Shared host plumbing), §6.3.1, EC-5, EC-11 to EC-13, INV-6
TESTS: tests/features/grok_host/test_grok_host_shared_contract.py
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from vidbyte.harnesses.serialization import HarnessRedactor
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.native_hosts import NativeHarness
from vidbyte.lib.enums.process import ProcessLaunchFailure
from vidbyte.lib.errors import ConfigurationError, McpProtocolError, NativeHostError

REDACTED = "<redacted>"
_LABELS: Mapping[NativeHarness, str] = MappingProxyType(
    {
        NativeHarness.GROK: "Grok Build",
        NativeHarness.OPENCODE: "opencode",
        NativeHarness.MUSE: "Muse Code",
        NativeHarness.CLAUDE_CODE: "Claude Code",
        NativeHarness.CODEX: "Codex",
    }
)
_EXITED_REASONS = frozenset({"process_exited", "closed", "stdin_write_failed", "reader_failed", "process_unavailable"})
_SEPARATOR = ", "


class NativeErrorFactory:
    """Builds scrubbed NativeHostError values for one harness."""

    def __init__(self, harness: NativeHarness) -> None:
        self._harness = harness
        self._label = _LABELS[harness]
        self._secrets: set[str] = set()
        self._redactor = HarnessRedactor()

    @property
    def harness(self) -> NativeHarness:
        # The harness whose codes this factory builds.
        return self._harness

    def register_secret(self, value: str) -> None:
        # @intent native-errors-scrub-injected-secrets
        # Every value the host injected (server password, API keys, MCP env
        # and header values) is replaced in all vendor text, because a vendor
        # may echo it back in an error.
        if isinstance(value, str) and value:
            self._secrets.add(value)

    def scrub(self, text: str) -> str:
        # @intent native-errors-redact-before-cap
        # Registered values go first, on the full text, so the cap cannot cut
        # one in half; then the shared redactor scrubs credential assignments
        # and the result is capped at NATIVE_VENDOR_MESSAGE_MAX_CHARS.
        limit = native_host_constants.NATIVE_VENDOR_MESSAGE_MAX_CHARS
        for secret in sorted(self._secrets, key=len, reverse=True):
            text = text.replace(secret, REDACTED)
        if not text.strip():
            return text[:limit]
        return self._redactor.safe_error_message(text, max_chars=limit)

    @staticmethod
    def listing(items: Iterable[str]) -> str:
        # Joins ids or names for a context value, keeping the first NATIVE_CONTEXT_LIST_MAX_ITEMS in their given order.
        kept = [str(item) for item in items][: native_host_constants.NATIVE_CONTEXT_LIST_MAX_ITEMS]
        return _SEPARATOR.join(kept)

    def code(self, problem: str) -> FailureCode:
        # The "<harness>.<problem>" member, for example grok.not_installed.
        return FailureCode(f"{self._harness.value}.{problem}")

    def build(self, code: FailureCode, message: str, *, operation: str, next_step: str | None = None, context: Mapping[str, str] | None = None) -> NativeHostError:
        # Scrubs the message and every context value, then builds the error; never raises.
        safe_context = {key: self.scrub(str(value)) for key, value in (context or {}).items()}
        return NativeHostError(self.scrub(message), failure_code=code, operation=operation, next_step=next_step, context=safe_context)

    def invalid_argument(self, field: str, message: str, *, operation: str, next_step: str | None = None) -> NativeHostError:
        # An argument failed its check before any I/O (EC-1): the next step
        # names the argument, which is the row's required token, unless the
        # row gives its own text; context["field"] carries the name too.
        step = next_step or native_host_constants.NATIVE_INVALID_ARGUMENT_NEXT_STEP.format(field=field)
        return self.build(FailureCode.CONFIGURATION_INVALID_ARGUMENT, message, operation=operation, next_step=step, context={"field": field})

    def from_configuration_error(self, exc: ConfigurationError, *, operation: str) -> NativeHostError:
        # A validator or record refusal names its field in details["field"]
        # ("GrokTurnRequest.model" names the argument "model"); the message is
        # the SDK's own text, which quotes only short non-secret values.
        field = str(exc.details.get("field", "argument")).rsplit(".", 1)[-1]
        next_step = native_host_constants.NATIVE_INVALID_ARGUMENT_NEXT_STEP.format(field=field)
        return self.build(FailureCode.CONFIGURATION_INVALID_ARGUMENT, exc.message, operation=operation, next_step=next_step, context={"field": field})

    def from_unexpected(self, exc: Exception, *, operation: str) -> NativeHostError:
        # @intent native-errors-defects-name-only-the-class
        # A defect reports only the exception's class name; its text may hold
        # paths, payloads or secrets and is never copied into the error.
        error_type = type(exc).__name__
        message = f"{operation} failed with an unexpected {error_type}."
        return NativeHostError(message, failure_code=FailureCode.RUNTIME_ERROR, operation=operation, error_type=error_type, context={"error_type": error_type})

    def from_launch_failure(self, failure: ProcessLaunchFailure, *, operation: str) -> NativeHostError:
        # A missing executable means not installed; any other launch failure means the process could not run.
        if failure is ProcessLaunchFailure.NOT_FOUND:
            return self.build(self.code("not_installed"), f"The {self._label} executable was not found.", operation=operation)
        return self.build(self.code("process_exited"), f"The {self._label} executable could not be started ({failure.value}).", operation=operation, context={"reason": failure.value})

    def from_protocol_error(self, exc: McpProtocolError, *, operation: str) -> NativeHostError:
        # @intent native-errors-transport-reason-to-row
        # A timeout means the peer did not answer in time (server_unreachable);
        # a closed or dead pipe means it stopped (process_exited). A vendor
        # error answer is normally mapped by the host's wire codec first.
        details = exc.details
        reason = str(details.get("reason", ""))
        if reason == "timeout":
            return self.build(self.code("server_unreachable"), f"The {self._label} process did not answer in time.", operation=operation, context={"reason": reason})
        if reason in _EXITED_REASONS:
            return self.build(self.code("process_exited"), f"The {self._label} process stopped before it answered.", operation=operation, context={"reason": reason})
        vendor = details.get("error")
        if isinstance(vendor, Mapping):
            return self.build(self.code("api_error"), f"{self._label} answered with an error.", operation=operation, context={"vendor_code": str(vendor.get("code", "")), "vendor_error": str(vendor.get("message", ""))})
        return self.build(self.code("protocol_mismatch"), f"{self._label} sent an answer this SDK cannot read.", operation=operation, context={"reason": reason or "invalid_answer"})


__all__ = ["REDACTED", "NativeErrorFactory"]
