"""FILE: tests/features/grok_host/test_grok_host_shared_contract.py

PURPOSE: The contract shared by all three native hosts and the backends: the 53 new FailureCode members and their place (INV-20), NATIVE_HOST_NEXT_STEPS verbatim (AC-17, INV-8), NativeHostError (D-6), NativeErrorFactory scrubbing and mapping (INV-6, EC-5, EC-12, EC-13), NativeTurnTable reservation and eviction (EC-9, EC-149, INV-17), the 13 enums, the §9.3 constants, the fixed native/__init__.py bytes (INV-19), and fresh-interpreter imports (AC-18, AC-20, INV-21).
ROLE IN CODEBASE: Start here when a code, a default next step, an enum member or a constant drifts from the spec, or when an import order breaks. Host-specific behaviour lives in each host's own pack.
ARCHITECTURE NOTE: The catalog below is copied from spec §6.3.1 so the test fails on any wording drift; markdown backticks are ignored when comparing, because the spec table renders them as code spans. Fresh-interpreter checks run `python -c` with PYTHONPATH set to this checkout.
FUNCTION INVENTORY: CATALOG is §6.3.1; BASELINE_FAILURE_CODES_SHA256 fingerprints the members that existed at base_commit; ENUMS and CONSTANTS are §9.1 and §9.3; run_fresh runs Python code in a new interpreter; the test_* functions are one contract each.
COMMON MODIFICATION PATTERNS: A spec change to §6.3.1, §9.1 or §9.3 is copied here verbatim in the same edit.
WHAT NOT TO DO IN THIS FILE: 1. Do not regenerate the baseline fingerprint from a branch that changed existing members; it pins INV-20. 2. Do not import a host module at file level; collection must not depend on the feature.
KNOWN EDGE CASES: INV-19 hashes LF-normalised bytes so a CRLF checkout still compares. The AC-18 audit hook watches process-creation events only.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.1, §8.5, §9.1, §9.3, INV-19 to INV-21, AC-16 to AC-20
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_host_shared_contract.py
"""

from __future__ import annotations

import asyncio
import enum
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FRESH_TIMEOUT_SECONDS = 180
INV19_SHA256 = "0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a"
BASELINE_MEMBER_COUNT = 120
BASELINE_CODEX_CODES = 12
BASELINE_FAILURE_CODES_SHA256 = "ec044137a9ccd44982b705d0686cfe7c62b0b17736ae6299c89624afab6905eb"
SECRET_VALUE = "injected-value-7f3a9c"
CATALOG: dict[str, tuple[str, str]] = {
    "grok.not_installed": ("Install Grok Build 1.0.13 or newer, or set GrokHostSettings.grok_command.", "GrokHostSettings.grok_command"),
    "grok.version_unsupported": ("Update Grok Build to 1.0.13 or newer with `grok update`.", "grok update"),
    "grok.not_signed_in": ("Run `grok login` in a terminal, then retry.", "grok login"),
    "grok.model_unknown": ("Pick a model id returned by list_grok_models.", "list_grok_models"),
    "grok.capability_missing": ("Update Grok Build with `grok update`, or pick an option that list_grok_models shows for this model.", "list_grok_models"),
    "grok.session_not_found": ("Use list_grok_sessions to find a session id in this host's workspace.", "list_grok_sessions"),
    "grok.session_busy": ("Wait for or interrupt the live turn with wait_grok_turn or interrupt_grok_turn, then retry.", "interrupt_grok_turn"),
    "grok.api_error": ("Retry later; if it repeats, report error.context['vendor_code'] to xAI support.", "vendor_code"),
    "grok.process_exited": ("Run check_grok_ready; if the host was closed, open a new GrokHost.", "check_grok_ready"),
    "grok.protocol_mismatch": ("Run check_grok_ready and use a Grok Build release this SDK supports (1.0.13 or newer).", "check_grok_ready"),
    "grok.server_unreachable": ("Retry, or raise GrokHostSettings.control_timeout_seconds if the machine is slow.", "control_timeout_seconds"),
    "grok.turn_timed_out": ("The turn is still running: call wait_grok_turn again or interrupt_grok_turn.", "wait_grok_turn"),
    "grok.turn_not_found": ("Use a handle returned by this host's spawn_grok_session or continue_grok_session; finished turns are kept for the last 64 turns only.", "spawn_grok_session"),
    "opencode.not_installed": ("Install opencode 1.18.31 or newer, or set OpencodeHostSettings.opencode_command.", "opencode_command"),
    "opencode.version_unsupported": ("Upgrade opencode to 1.18.31 or newer with `opencode upgrade`.", "opencode upgrade"),
    "opencode.not_signed_in": ("Connect a provider with `opencode auth login`, or check server_username and server_password for an attached server.", "opencode auth login"),
    "opencode.model_unknown": ("Pick a provider/model id returned by list_opencode_models.", "list_opencode_models"),
    "opencode.session_not_found": ("Use list_opencode_sessions to find a session id on this server.", "list_opencode_sessions"),
    "opencode.message_not_found": ("Use get_opencode_session_messages to find a message id in this session.", "get_opencode_session_messages"),
    "opencode.session_busy": ("Wait for or interrupt the running turn with wait_opencode_turn or interrupt_opencode_turn, then retry.", "interrupt_opencode_turn"),
    "opencode.usage_limited": ("The provider rate-limited or capped this account; wait for the limit to reset, then retry.", "reset"),
    "opencode.billing_error": ("Add credit or fix billing with the model provider, then retry.", "billing"),
    "opencode.api_error": ("Retry later; if it repeats, inspect error.context['vendor_error'].", "vendor_error"),
    "opencode.mcp_server_failed": ("Fix the MCP server command or URL and add it again; servers that need OAuth are not supported here.", "OAuth"),
    "opencode.process_exited": ("The opencode server stopped; open a new OpencodeHost.", "OpencodeHost"),
    "opencode.protocol_mismatch": ("Run check_opencode_ready and use opencode 1.18.31 or newer.", "check_opencode_ready"),
    "opencode.server_unreachable": ("Check that the opencode server is running, or raise OpencodeHostSettings.request_timeout_seconds.", "request_timeout_seconds"),
    "opencode.turn_timed_out": ("The turn is still running: call wait_opencode_turn again or interrupt_opencode_turn.", "wait_opencode_turn"),
    "opencode.turn_not_found": ("Use a handle returned by this host's spawn_opencode_session or continue_opencode_session; finished turns are kept for the last 64 turns only.", "spawn_opencode_session"),
    "muse.not_installed": ("Install Muse Code 1.0.1 or newer in the distro, or set MuseHostSettings.muse_path.", "muse_path"),
    "muse.wsl_unavailable": ("Install WSL and the Muse distro, then set MuseHostSettings.wsl_distro to a name from `wsl.exe -l -q`.", "wsl_distro"),
    "muse.version_unsupported": ("Upgrade Muse Code to 1.0.1 or newer.", "1.0.1"),
    "muse.model_unknown": ("Pick a model id returned by list_muse_models.", "list_muse_models"),
    "muse.capability_missing": ("This Muse Code release lacks the method; upgrade Muse Code.", "upgrade"),
    "muse.session_not_found": ("Use list_muse_sessions to find a session id in this workspace.", "list_muse_sessions"),
    "muse.session_busy": ("Wait for or interrupt the running turn with wait_muse_turn or interrupt_muse_turn, then retry.", "interrupt_muse_turn"),
    "muse.budget_exhausted": ("The turn hit Muse's step limit; continue the session with continue_muse_session and a narrower prompt.", "continue_muse_session"),
    "muse.sandbox_not_ready": ("Run `muse sandbox` inside the distro to check the OS sandbox, then retry.", "muse sandbox"),
    "muse.api_error": ("Retry later; if it repeats, inspect error.context['vendor_error'].", "vendor_error"),
    "muse.process_exited": ("Run check_muse_ready; if the host was closed, open a new MuseHost.", "check_muse_ready"),
    "muse.protocol_mismatch": ("Run check_muse_ready and use Muse Code 1.0.1 or newer.", "check_muse_ready"),
    "muse.server_unreachable": ("Retry, or raise MuseHostSettings.control_timeout_seconds; WSL start-up can be slow.", "control_timeout_seconds"),
    "muse.turn_timed_out": ("The turn is still running: call wait_muse_turn again or interrupt_muse_turn.", "wait_muse_turn"),
    "muse.turn_not_found": ("Use a handle returned by this host's spawn_muse_session or continue_muse_session; finished turns are kept for the last 64 turns only.", "spawn_muse_session"),
    "backend.not_signed_in": ("Set the backend's API key environment variable (GLM_API_KEY or DEEPSEEK_API_KEY) to a valid key.", "API key"),
    "backend.model_unknown": ("Pick a model listed in HarnessBackend.claude_models from list_harness_backends.", "list_harness_backends"),
    "backend.feature_unsupported": ("Remove the listed features from the request or pick another backend; this endpoint silently ignores them.", "features"),
    "backend.harness_not_allowed": ("Use this backend only with a harness in HarnessBackend.allowed_harnesses.", "allowed_harnesses"),
    "backend.billing_error": ("Top up the DeepSeek account balance, then retry.", "balance"),
    "backend.usage_limited": ("Wait for the provider's rate limit to reset, then retry.", "reset"),
    "backend.api_error": ("Retry later; if it repeats, inspect error.context['vendor_error'].", "vendor_error"),
    "backend.server_unreachable": ("Check network access to the backend endpoint, then retry.", "network"),
    "backend.protocol_mismatch": ("The endpoint returned an unexpected response; check the backend's API status.", "API status"),
}
# Two §6.3.1 cells end with a note to the implementer; whether it is part of the text is ambiguous, so both forms pass.
CELL_NOTES = {
    "grok.turn_timed_out": "(One-shot rows override this.)",
    "backend.not_signed_in": "(Rows put the backend's own variable first.)",
}
REUSED = {
    "configuration.invalid_argument": "Fix the argument named in the message and call again.",
    "runtime.error": "This is a defect in the SDK host; report it with error.context['error_type'].",
}
ENUMS: dict[str, dict[str, str]] = {
    "NativeHarness": {"CLAUDE_CODE": "claude_code", "CODEX": "codex", "OPENCODE": "opencode", "GROK": "grok", "MUSE": "muse"},
    "NativeTurnStatus": {"RUNNING": "running", "COMPLETED": "completed", "INTERRUPTED": "interrupted", "FAILED": "failed"},
    "InterruptSource": {"CALLER": "caller", "DEADLINE": "deadline", "HOST_CLOSED": "host_closed", "POLICY": "policy"},
    "ApprovalOutcome": {"ALLOWED": "allowed", "REJECTED": "rejected", "CANCELLED": "cancelled", "NOT_SUPPORTED": "not_supported"},
    "AcpToolKind": {
        "READ": "read", "EDIT": "edit", "DELETE": "delete", "MOVE": "move", "SEARCH": "search", "EXECUTE": "execute", "THINK": "think", "FETCH": "fetch",
        "SWITCH_MODE": "switch_mode", "OTHER": "other",
    },
    "GrokPermissionMode": {"DEFAULT": "default", "ACCEPT_EDITS": "acceptEdits", "DONT_ASK": "dontAsk", "PLAN": "plan"},
    "OpencodePermissionAction": {"ALLOW": "allow", "ASK": "ask", "DENY": "deny"},
    "OpencodeMcpKind": {"LOCAL": "local", "REMOTE": "remote"},
    "MuseReasoningEffort": {"NONE": "none", "MINIMAL": "minimal", "LOW": "low", "MEDIUM": "medium", "HIGH": "high", "XHIGH": "xhigh", "ULTRA": "ultra"},
    "MuseViewDirection": {"FORWARD": "forward", "BACKWARD": "backward"},
    "HarnessBackendName": {"GLM": "glm", "DEEPSEEK": "deepseek"},
    "BackendFeature": {
        "MCP_SERVERS": "mcp_servers", "CACHE_CONTROL": "cache_control", "CONTAINER": "container", "TOP_K": "top_k", "SERVICE_TIER": "service_tier",
        "ANTHROPIC_BETA": "anthropic_beta", "DISABLE_PARALLEL_TOOL_USE": "disable_parallel_tool_use", "THINKING_BUDGET_TOKENS": "thinking_budget_tokens",
        "TOOL_RESULT_IS_ERROR": "tool_result_is_error", "DOCUMENT_BLOCKS": "document_blocks", "SEARCH_RESULT_BLOCKS": "search_result_blocks",
    },
    "ProcessLaunchFailure": {"NOT_FOUND": "not_found", "PERMISSION_DENIED": "permission_denied", "OS_ERROR": "os_error"},
}
ENUM_MODULES = {
    "native_hosts": ("NativeHarness", "NativeTurnStatus", "InterruptSource", "ApprovalOutcome", "AcpToolKind", "GrokPermissionMode", "OpencodePermissionAction", "OpencodeMcpKind", "MuseReasoningEffort", "MuseViewDirection"),
    "harness_backends": ("HarnessBackendName", "BackendFeature"),
    "process": ("ProcessLaunchFailure",),
}
CONSTANTS: dict[str, Any] = {
    "NATIVE_CONTROL_TIMEOUT_SECONDS": 30.0, "NATIVE_CONTROL_TIMEOUT_MAX_SECONDS": 600.0, "NATIVE_TURN_DEFAULT_SECONDS": 1800.0, "NATIVE_TURN_MAX_SECONDS": 14400.0,
    "NATIVE_WAIT_DEFAULT_SECONDS": 60.0, "NATIVE_WAIT_MAX_SECONDS": 3600.0, "NATIVE_TOOL_WAIT_MAX_SECONDS": 240.0, "NATIVE_STOP_GRACE_SECONDS": 5.0,
    "NATIVE_KILL_WAIT_SECONDS": 1.0, "NATIVE_STDIO_MAX_WAIT_SECONDS": 86400.0, "NATIVE_MAX_LIVE_TURNS_DEFAULT": 4, "NATIVE_MAX_LIVE_TURNS_LIMIT": 16,
    "NATIVE_FINISHED_TURN_LIMIT": 64, "NATIVE_LIST_DEFAULT_LIMIT": 50, "NATIVE_LIST_MAX_LIMIT": 200, "NATIVE_CURSOR_MAX_CHARS": 512, "NATIVE_ID_MAX_CHARS": 128,
    "NATIVE_SESSION_ID_MAX_CHARS": 160, "NATIVE_VENDOR_ID_PATTERN": r"^[^\s-][^\s]*$", "NATIVE_PROMPT_MAX_CHARS": 200000, "NATIVE_RESULT_TEXT_MAX_CHARS": 100000,
    "NATIVE_MAX_RECORDED_DECISIONS": 100, "NATIVE_VENDOR_MESSAGE_MAX_CHARS": 1000, "NATIVE_CONTEXT_LIST_MAX_ITEMS": 20, "NATIVE_TOOL_OUTPUT_MAX_BYTES": 64000,
    "NATIVE_EVENT_MAX_CHARS": 8000, "GROK_MIN_VERSION": (1, 0, 13), "GROK_VERSION_PATTERN": r"grok (\d+)\.(\d+)\.(\d+)", "GROK_ACP_PROTOCOL_VERSION": 1,
    "GROK_SIGNED_OUT_LINE": "You are not authenticated.", "GROK_NOT_SIGNED_IN_MARKERS": ("not authenticated", "auth token is invalid or expired", "grok login"),
    "GROK_ARGV_PROMPT_MAX_CHARS": 24000, "GROK_CLI_MAX_OUTPUT_BYTES": 4194304, "NATIVE_PROCESS_MAX_OUTPUT_BYTES": 67108864, "GROK_LIST_MAX_PAGES": 20,
    "GROK_SEARCH_DEFAULT_LIMIT": 20, "GROK_SEARCH_MAX_LIMIT": 100, "GROK_QUERY_MAX_CHARS": 200, "GROK_MAX_RULES": 32, "GROK_RULE_MAX_CHARS": 200,
    "GROK_MAX_TURNS_LIMIT": 200, "OPENCODE_MIN_VERSION": (1, 18, 31), "OPENCODE_LISTENING_PATTERN": r"opencode server listening on (http://127\.0\.0\.1:\d+)",
    "OPENCODE_SERVER_LOGIN": "vidbyte", "OPENCODE_STARTUP_TIMEOUT_SECONDS": 20.0, "OPENCODE_REQUEST_TIMEOUT_SECONDS": 30.0, "OPENCODE_MAX_RESPONSE_BYTES": 8388608,
    "OPENCODE_POLL_INTERVAL_SECONDS": 1.0, "OPENCODE_IDLE_CONFIRMATIONS": 3, "OPENCODE_POLL_FAILURE_LIMIT": 5, "OPENCODE_TURN_MESSAGE_LIMIT": 1000,
    "OPENCODE_WATCH_MESSAGE_LIMIT": 50, "OPENCODE_MAX_SESSION_TREE": 64, "OPENCODE_RETRY_ATTEMPT_LIMIT": 5,
    "OPENCODE_RATE_LIMIT_MARKERS": ("rate limit", "rate_limit", "429", "too many requests", "quota", "usage limit"),
    "OPENCODE_SYSTEM_MAX_CHARS": 20000, "OPENCODE_PATCH_MAX_CHARS": 20000, "OPENCODE_MAX_PERMISSION_RULES": 64, "OPENCODE_RULE_MAX_CHARS": 200,
    "OPENCODE_MAX_MCP_SERVERS": 16, "OPENCODE_MCP_TIMEOUT_MAX_MS": 600000, "OPENCODE_SESSION_ID_PATTERN": r"^ses[0-9A-Za-z_-]{1,128}$",
    "OPENCODE_MESSAGE_ID_PATTERN": r"^msg[0-9A-Za-z_-]{1,128}$", "OPENCODE_PART_ID_PATTERN": r"^prt[0-9A-Za-z_-]{1,128}$",
    "OPENCODE_MCP_NAME_PATTERN": r"^[A-Za-z0-9_-]{1,64}$", "OPENCODE_ENV_KEY_PATTERN": r"^[A-Za-z_][A-Za-z0-9_-]{0,127}$", "MUSE_MIN_VERSION": (1, 0, 1),
    "MUSE_VERSION_PATTERN": r"Muse Code (\d+)\.(\d+)\.(\d+)", "MUSE_SCHEMA_VERSION": 1, "MUSE_CLIENT_NAME": "vidbyte_sdk",
    "MUSE_UUID_TIMESTAMP_MASK": (1 << 48) - 1, "MUSE_UUID_TIMESTAMP_SHIFT": 80, "MUSE_UUID_VERSION": 7, "MUSE_UUID_VERSION_SHIFT": 76, "MUSE_UUID_RAND_A_SHIFT": 64,
    "MUSE_UUID_VARIANT": 0b10, "MUSE_UUID_VARIANT_SHIFT": 62, "MUSE_UUID_RANDOM_BITS": 74, "MUSE_UUID_RAND_B_BITS": 62, "MUSE_UUID_RAND_B_MASK": (1 << 62) - 1,
    "MUSE_DEFAULT_PATH": "/usr/local/bin/muse", "MUSE_APPROVAL_MODE": "denyUnmatched", "MUSE_PAGE_MAX_LIMIT": 200, "MUSE_USAGE_MAX_PAGES": 10,
    "MUSE_PEER_MARK_VARIABLE": "VIDBYTE_PEER_MARK", "MUSE_PEER_MARK_PATTERN": r"^[0-9a-f]{32}$", "MUSE_REAP_TIMEOUT_SECONDS": 10.0,
    "BACKEND_HTTP_TIMEOUT_SECONDS": 15.0, "BACKEND_MAX_RESPONSE_BYTES": 65536,
}
FRESH_IMPORTS = (
    "vidbyte",
    "vidbyte.agents",
    "vidbyte.tools.toolsets",
    "vidbyte.harnesses.native.grok",
    "vidbyte.harnesses.native.opencode",
    "vidbyte.harnesses.native.muse",
    "vidbyte.harnesses.native.backends",
)
AUDIT_PROBE = """
import json, sys
spawned = []
def hook(event, args):
    if event in ("subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn", "os.exec", "os.fork", "os.forkpty", "os.startfile", "_winapi.CreateProcess"):
        spawned.append(event)
sys.addaudithook(hook)
import vidbyte
vendor = sorted(name for name in sys.modules if name.split(".")[0] in ("acp", "muse_code_sdk", "opencode_ai"))
wanted = ("vidbyte.tools.toolsets.grok", "vidbyte.tools.toolsets.opencode", "vidbyte.tools.toolsets.muse", "vidbyte.tools.toolsets.harness_backends")
print(json.dumps({"spawned": spawned, "vendor": vendor, "toolsets": [name for name in wanted if name in sys.modules]}))
"""


def without_backticks(text: str) -> str:
    # The spec table renders commands as code spans; the words, not the markdown, are the contract.
    return text.replace("`", "")


def failure_code() -> Any:
    return importlib.import_module("vidbyte.lib.enums.failure").FailureCode


def next_steps() -> Any:
    return importlib.import_module("vidbyte.lib.constants.native_hosts").NATIVE_HOST_NEXT_STEPS


def hostkit() -> Any:
    return importlib.import_module("vidbyte.harnesses.native.hostkit")


def run_fresh(code: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True, text=True, timeout=FRESH_TIMEOUT_SECONDS, check=False)


def test_the_53_new_members_follow_rule_evaluation_failed_in_catalog_order() -> None:
    # §12.3 row 4 / §6.3.1: appended after RULE_EVALUATION_FAILED, names are the upper-cased value with "." -> "_".
    codes = failure_code()
    members = list(codes)
    start = members.index(codes.RULE_EVALUATION_FAILED) + 1
    appended = members[start:start + len(CATALOG)]
    assert [member.value for member in appended] == list(CATALOG)
    assert [member.name for member in appended] == [value.upper().replace(".", "_") for value in CATALOG]
    assert len(CATALOG) == 53


def test_existing_failure_code_members_are_unchanged() -> None:
    # INV-20: no existing member, value or order changes.
    members = list(failure_code())[:BASELINE_MEMBER_COUNT]
    fingerprint = hashlib.sha256("".join(f"{member.name}={member.value}\n" for member in members).encode()).hexdigest()
    assert fingerprint == BASELINE_FAILURE_CODES_SHA256
    assert members[-1].name == "RULE_EVALUATION_FAILED"
    assert sum(member.category == "codex" for member in failure_code()) == BASELINE_CODEX_CODES, "INV-20: no codex.* code is added"
    assert len(list(failure_code())) >= BASELINE_MEMBER_COUNT + 53


def test_next_steps_hold_every_code_verbatim() -> None:
    # AC-17 / INV-8: a non-empty default for each of the 53 codes and both reused ones, verbatim from §6.3.1.
    steps = next_steps()
    assert set(steps) == set(CATALOG) | set(REUSED)
    for code, (text, token) in CATALOG.items():
        accepted = {without_backticks(text), without_backticks(f"{text} {CELL_NOTES[code]}")} if code in CELL_NOTES else {without_backticks(text)}
        assert without_backticks(steps[code]) in accepted, code
        assert token in without_backticks(steps[code]), code
    for code, text in REUSED.items():
        assert steps[code] == text, code
    assert all(isinstance(value, str) and value.strip() for value in steps.values())


def test_every_new_code_starts_with_its_host_prefix() -> None:
    # AC-17 / INV-8: read from the live vocabulary, not from the table above.
    prefixes = ("grok.", "opencode.", "muse.", "backend.")
    new_keys = [key for key in next_steps() if key not in REUSED]
    assert len(new_keys) == 53 and all(key.startswith(prefixes) for key in new_keys)
    live = [member.value for member in failure_code() if member.value.startswith(prefixes)]
    assert {prefix: sum(value.startswith(prefix) for value in live) for prefix in prefixes} == {"grok.": 13, "opencode.": 16, "muse.": 15, "backend.": 9}


def native_error(**overrides: Any) -> Any:
    error_type = importlib.import_module("vidbyte.lib.errors").NativeHostError
    fields = {"failure_code": failure_code().GROK_API_ERROR, "operation": "spawn_grok_session"}
    fields.update(overrides)
    return error_type("Grok reported an error.", **fields)


def test_native_host_error_defaults_its_next_step_from_the_catalog() -> None:
    # D-6: next_step=None -> NATIVE_HOST_NEXT_STEPS[failure_code.value]; str(error) is the message.
    error = native_error(failure_code=failure_code().GROK_NOT_INSTALLED)
    assert error.next_step == next_steps()["grok.not_installed"]
    assert str(error) == "Grok reported an error."
    assert error.operation == "spawn_grok_session"
    assert error.error_type == ""
    assert dict(error.context) == {}


def test_native_host_error_keeps_an_explicit_next_step_and_context() -> None:
    error = native_error(next_step="Pick a reasoning effort list_grok_models shows for this model.", context={"vendor_code": "-32603"})
    assert error.next_step == "Pick a reasoning effort list_grok_models shows for this model."
    assert error.context["vendor_code"] == "-32603"
    with pytest.raises(TypeError):
        error.context["vendor_code"] = "changed"


def test_native_host_error_falls_back_to_the_runtime_text_and_never_raises() -> None:
    # INV-8: a code with no catalog entry falls back to the runtime.error text, so next_step is never empty.
    error = native_error(failure_code=failure_code().MODEL_RATE_LIMITED)
    assert error.next_step == REUSED["runtime.error"]


def test_native_host_error_is_an_agent_execution_error_with_diagnostics() -> None:
    errors = importlib.import_module("vidbyte.lib.errors")
    assert issubclass(errors.NativeHostError, errors.AgentExecutionError)
    assert "NativeHostError" in errors.__all__
    assert errors.NativeHostError.DIAGNOSTIC_FIELDS == (
        "error_kind", "expected", "actual", "safe_runtime_details", "likely_causes", "repair_approaches", "related_docs", "relevant_tests",
    )
    error = native_error()
    assert set(errors.NativeHostError.DIAGNOSTIC_FIELDS) <= set(error.details)
    assert failure_code().from_exception(error) is failure_code().GROK_API_ERROR, "the session failure vocabulary reads the declared code"


def test_error_factory_scrubs_registered_values_and_caps_vendor_text(grok_api) -> None:
    # INV-6: every exact injected value becomes <redacted>; vendor text is capped at NATIVE_VENDOR_MESSAGE_MAX_CHARS.
    factory = hostkit().NativeErrorFactory(grok_api.NativeHarness.OPENCODE)
    factory.register_secret(SECRET_VALUE)
    scrubbed = factory.scrub(f"login failed for {SECRET_VALUE} at the server")
    assert SECRET_VALUE not in scrubbed and "<redacted>" in scrubbed
    assert len(factory.scrub("v" * 5000)) <= grok_api.constants.NATIVE_VENDOR_MESSAGE_MAX_CHARS
    built = factory.build(grok_api.FailureCode.OPENCODE_API_ERROR, f"server said {SECRET_VALUE}", operation="list_opencode_sessions", context={"vendor_error": f"echo {SECRET_VALUE}"})
    assert SECRET_VALUE not in str(built) and SECRET_VALUE not in built.context["vendor_error"]
    assert "<redacted>" in built.context["vendor_error"]
    assert built.next_step == next_steps()["opencode.api_error"]


def test_error_factory_from_unexpected_names_only_the_class(grok_api) -> None:
    # EC-5: runtime.error with context["error_type"] set to the class name only.
    factory = hostkit().NativeErrorFactory(grok_api.NativeHarness.GROK)
    error = factory.from_unexpected(KeyError("internal detail that must stay private"), operation="check_grok_ready")
    assert error.failure_code is grok_api.FailureCode.RUNTIME_ERROR
    assert error.error_type == "KeyError" and error.context["error_type"] == "KeyError"
    assert "internal detail" not in str(error) and "internal detail" not in json.dumps(dict(error.context))
    assert "error_type" in error.next_step and error.operation == "check_grok_ready"


@pytest.mark.parametrize(
    ("harness", "failure", "code"),
    [
        ("GROK", "NOT_FOUND", "grok.not_installed"),
        ("GROK", "PERMISSION_DENIED", "grok.process_exited"),
        ("GROK", "OS_ERROR", "grok.process_exited"),
        ("OPENCODE", "NOT_FOUND", "opencode.not_installed"),
        ("MUSE", "NOT_FOUND", "muse.not_installed"),
    ],
)
def test_error_factory_maps_launch_failures(harness: str, failure: str, code: str, grok_api) -> None:
    # EC-11 / EC-12: FileNotFoundError -> not_installed; any other OSError -> process_exited.
    launch = importlib.import_module("vidbyte.lib.enums.process").ProcessLaunchFailure
    factory = hostkit().NativeErrorFactory(grok_api.NativeHarness[harness])
    error = factory.from_launch_failure(launch[failure], operation="check_ready")
    assert error.failure_code.value == code


@pytest.mark.parametrize(
    ("reason", "code"),
    [("timeout", "grok.server_unreachable"), ("process_exited", "grok.process_exited"), ("closed", "grok.process_exited"), ("stdin_write_failed", "grok.process_exited"), ("reader_failed", "grok.process_exited")],
)
def test_error_factory_maps_transport_reasons(reason: str, code: str, grok_api) -> None:
    # EC-12 / EC-13: McpProtocolError reasons map to rows, with context["reason"] for process_exited.
    errors = importlib.import_module("vidbyte.lib.errors")
    factory = hostkit().NativeErrorFactory(grok_api.NativeHarness.GROK)
    error = factory.from_protocol_error(errors.McpProtocolError("transport failed", details={"reason": reason}), operation="list_grok_models")
    assert error.failure_code.value == code
    if code.endswith("process_exited"):
        assert error.context["reason"] == reason


def turn_table(grok_api: Any, max_live_turns: int = 2) -> Any:
    kit = hostkit()
    return kit.NativeTurnTable(grok_api.NativeHarness.GROK, max_live_turns=max_live_turns, errors=kit.NativeErrorFactory(grok_api.NativeHarness.GROK))


async def finished_task(grok_api: Any, handle_fields: dict[str, Any]) -> Any:
    handle = grok_api.NativeTurnHandle(**handle_fields)
    return grok_api.NativeTurnResult(handle=handle, status=grok_api.NativeTurnStatus.COMPLETED)


def test_turn_table_reserves_synchronously_and_refuses_a_busy_session(grok_api) -> None:
    # EC-9 / EC-29: reservation happens before any await, so a second reserve on the session fails at once.
    table = turn_table(grok_api)
    session = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b"
    turn_id = table.reserve(session, operation="continue_grok_session")
    assert re.fullmatch(r"[0-9a-f]{32}", turn_id)
    assert table.is_session_busy(session)
    with pytest.raises(grok_api.NativeHostError) as caught:
        table.reserve(session, operation="continue_grok_session")
    assert caught.value.failure_code is grok_api.FailureCode.GROK_SESSION_BUSY
    table.release(turn_id)
    assert not table.is_session_busy(session)
    assert table.reserve(session, operation="continue_grok_session") != turn_id


def test_turn_table_caps_live_turns_with_the_live_count(grok_api) -> None:
    # EC-24 / INV-16: the cap counts reservations too; context["live_turns"] is a str.
    table = turn_table(grok_api, max_live_turns=2)
    table.reserve(None, operation="spawn_grok_session")
    table.reserve(None, operation="spawn_grok_session")
    with pytest.raises(grok_api.NativeHostError) as caught:
        table.reserve(None, operation="spawn_grok_session")
    assert caught.value.failure_code is grok_api.FailureCode.GROK_SESSION_BUSY
    assert caught.value.context["live_turns"] == "2"
    assert "interrupt_grok_turn" in caught.value.next_step


@pytest.mark.asyncio
async def test_turn_table_evicts_the_oldest_finished_turn_after_64(grok_api) -> None:
    # EC-149 / INV-16: first in, first out; an evicted handle raises turn_not_found.
    table = turn_table(grok_api, max_live_turns=1)
    handles = []
    for index in range(grok_api.constants.NATIVE_FINISHED_TURN_LIMIT + 1):
        session = f"{index:08d}-0000-4000-8000-000000000000"
        turn_id = table.reserve(session, operation="spawn_grok_session")
        task = asyncio.ensure_future(finished_task(grok_api, {"harness": grok_api.NativeHarness.GROK, "session_id": session, "turn_id": turn_id}))
        handles.append(table.activate(turn_id, task))
        await task
        await asyncio.sleep(0)
    assert table.live_tasks() == ()
    with pytest.raises(grok_api.NativeHostError) as caught:
        table.lookup(handles[0], operation="wait_grok_turn")
    assert caught.value.failure_code is grok_api.FailureCode.GROK_TURN_NOT_FOUND
    assert table.lookup(handles[1], operation="wait_grok_turn").done()
    assert table.lookup(handles[-1], operation="wait_grok_turn").done()


@pytest.mark.asyncio
async def test_turn_table_binds_the_session_and_scopes_handles(grok_api) -> None:
    # Spawn learns the session id after session/new; a handle of another harness or turn is not found (INV-17).
    table = turn_table(grok_api)
    turn_id = table.reserve(None, operation="spawn_grok_session")
    session = "0c9b8a7d-6e5f-4a3b-9c2d-1e0f9a8b7c6d"
    table.bind_session(turn_id, session)
    assert table.is_session_busy(session)
    blocker = asyncio.Event()

    async def driver() -> Any:
        await blocker.wait()
        return grok_api.NativeTurnResult(handle=grok_api.NativeTurnHandle(harness=grok_api.NativeHarness.GROK, session_id=session, turn_id=turn_id), status=grok_api.NativeTurnStatus.COMPLETED)

    task = asyncio.ensure_future(driver())
    handle = table.activate(turn_id, task)
    assert (handle.harness, handle.session_id, handle.turn_id) == (grok_api.NativeHarness.GROK, session, turn_id)
    assert table.live_tasks() == (task,)
    foreign = grok_api.NativeTurnHandle(harness=grok_api.NativeHarness.MUSE, session_id=session, turn_id=turn_id)
    for wrong in (foreign, grok_api.NativeTurnHandle(harness=grok_api.NativeHarness.GROK, session_id=session, turn_id="f" * 32)):
        with pytest.raises(grok_api.NativeHostError) as caught:
            table.lookup(wrong, operation="wait_grok_turn")
        assert caught.value.failure_code is grok_api.FailureCode.GROK_TURN_NOT_FOUND
    blocker.set()
    await task
    await asyncio.sleep(0)
    assert not table.is_session_busy(session)


def test_child_environment_is_os_environ_plus_overlay(monkeypatch: pytest.MonkeyPatch) -> None:
    # D-18: os.environ plus the overlay; the overlay wins.
    monkeypatch.setenv("VIDBYTE_CONTRACT_PROBE", "caller")
    monkeypatch.setenv("VIDBYTE_CONTRACT_OVERRIDDEN", "caller")
    built = hostkit().NativeChildEnvironment.build({"VIDBYTE_CONTRACT_OVERRIDDEN": "overlay", "VIDBYTE_CONTRACT_NEW": "overlay"})
    assert built == {**os.environ, "VIDBYTE_CONTRACT_OVERRIDDEN": "overlay", "VIDBYTE_CONTRACT_NEW": "overlay"}
    assert os.environ["VIDBYTE_CONTRACT_OVERRIDDEN"] == "caller", "building never edits the caller's environment"


@pytest.mark.asyncio
async def test_a_peer_that_never_started_closes_without_raising(grok_api) -> None:
    # §8.5 NativePeer.close never raises.
    kit = hostkit()
    peer = kit.NativePeer((sys.executable, "-c", "pass"), env=dict(os.environ), control_timeout_seconds=1.0, errors=kit.NativeErrorFactory(grok_api.NativeHarness.GROK))
    assert await peer.close() is None


@pytest.mark.parametrize("module_name", sorted(ENUM_MODULES))
def test_enums_have_exactly_the_spec_members(module_name: str) -> None:
    # §9.1: all str, Enum; exact members; exported from vidbyte.lib.enums.
    module = importlib.import_module(f"vidbyte.lib.enums.{module_name}")
    package = importlib.import_module("vidbyte.lib.enums")
    for name in ENUM_MODULES[module_name]:
        enum_type = getattr(module, name)
        assert issubclass(enum_type, str) and issubclass(enum_type, enum.Enum), name
        assert {member.name: member.value for member in enum_type} == ENUMS[name], name
        assert name in package.__all__ and getattr(package, name) is enum_type, name


def test_grok_permission_mode_has_no_approve_everything_member() -> None:
    # INV-9: no auto or bypassPermissions member.
    mode = importlib.import_module("vidbyte.lib.enums.native_hosts").GrokPermissionMode
    assert not {"auto", "bypassPermissions"} & {member.value for member in mode}


def test_constants_have_the_spec_values() -> None:
    # §9.3: every constant, value for value; patterns compared by their source text.
    module = importlib.import_module("vidbyte.lib.constants.native_hosts")
    for name, expected in CONSTANTS.items():
        actual = getattr(module, name)
        actual = getattr(actual, "pattern", actual)
        if isinstance(expected, tuple):
            actual = tuple(actual)
        assert actual == expected, name


def test_reap_script_is_lf_only_and_targets_the_exact_mark() -> None:
    # §9.3 MUSE_REAP_SCRIPT: LF endings only; exact-entry match on /proc/<pid>/environ; PPid from status.
    script = importlib.import_module("vidbyte.lib.constants.native_hosts").MUSE_REAP_SCRIPT
    assert isinstance(script, str) and "\r" not in script
    assert 'grep -qxF "VIDBYTE_PEER_MARK=$1"' in script
    assert "/proc/" in script and "PPid:" in script and "kill -KILL" in script


def test_native_package_init_matches_the_fixed_bytes() -> None:
    # INV-19 / AC-16: SHA-256 of the LF-normalised bytes.
    path = REPO_ROOT / "vidbyte" / "harnesses" / "native" / "__init__.py"
    digest = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert digest == INV19_SHA256


def test_import_vidbyte_starts_no_process_and_loads_no_vendor_sdk(tmp_path: Path) -> None:
    # AC-18 / INV-21: no child process, no acp / muse_code_sdk / opencode_ai, and the new toolsets are imported.
    completed = run_fresh(AUDIT_PROBE, tmp_path)
    assert completed.returncode == 0, completed.stderr[-2000:]
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    assert report["spawned"] == []
    assert report["vendor"] == []
    assert len(report["toolsets"]) == 4, report["toolsets"]


@pytest.mark.parametrize("module_name", FRESH_IMPORTS)
def test_each_entry_module_imports_first_in_a_fresh_interpreter(module_name: str, tmp_path: Path) -> None:
    # AC-20 / D-3: whatever module enters the package chain first, it and then every other entry module import.
    others = [name for name in FRESH_IMPORTS if name != module_name]
    completed = run_fresh("; ".join(f"import {name}" for name in (module_name, *others)), tmp_path)
    assert completed.returncode == 0, completed.stderr[-2000:]


def test_all_entry_modules_import_in_reverse_order(tmp_path: Path) -> None:
    completed = run_fresh("; ".join(f"import {name}" for name in reversed(FRESH_IMPORTS)), tmp_path)
    assert completed.returncode == 0, completed.stderr[-2000:]


def test_records_and_enums_are_not_added_to_the_root_package() -> None:
    # D-15 / INV-22: nothing new in vidbyte.__all__.
    root = importlib.import_module("vidbyte")
    new_names = {"GrokHost", "OpencodeHost", "MuseHost", "NativeHostError", "GrokTools", "OpencodeTools", "MuseTools", "HarnessBackendTools", "NativeTurnHandle"}
    assert not new_names & set(getattr(root, "__all__", ())), new_names & set(root.__all__)
    assert importlib.import_module("vidbyte.tools.toolsets").GrokTools is not None

