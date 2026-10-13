"""FILE: vidbyte/lib/constants/native_hosts.py

PURPOSE: Holds every bound, default, pattern and fixed text the native Grok, opencode and Muse hosts, the GLM and DeepSeek backend profiles, and the canonical process helpers use, including NATIVE_HOST_NEXT_STEPS, the default next step for each of the 53 native failure codes plus configuration.invalid_argument and runtime.error.
ROLE IN CODEBASE: Imported by the records in vidbyte/lib/dataclasses/, by NativeHostError in vidbyte/lib/errors/base.py, by vidbyte/lib/process/, by the McpStdioTransport extension in vidbyte/tools/mcp/transport.py, by the hosts under vidbyte/harnesses/native/ and by the tools under vidbyte/tools/builtins/.
ARCHITECTURE NOTE: Stdlib only, so the error module can import it without a cycle. The timing constants that tests shrink (NATIVE_STOP_GRACE_SECONDS, NATIVE_KILL_WAIT_SECONDS, OPENCODE_POLL_INTERVAL_SECONDS) are read through this module object at call time by their users, never bound by a from-import, so one patch reaches every user.
FUNCTION INVENTORY: No functions. Constants grouped as shared native bounds, NATIVE_HOST_NEXT_STEPS, the next steps every host words the same way (a {tool} slot takes the host's own tool name), the fixed texts and HTTP statuses more than one host reads, then Grok, opencode, Muse, and backend values.
COMMON MODIFICATION PATTERNS: A new bound is a feature-prefixed constant here, used by name everywhere (lint A007). A text or code that a second host or module needs moves here instead of being copied. A new failure code adds its default next step to NATIVE_HOST_NEXT_STEPS with its FailureCode value as the key, verbatim from the spec's code catalog.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte; vidbyte.lib.errors imports this module. 2. Do not name a constant with a password, token or secret word and give it a string (lint S054). 3. Do not add a carriage return to MUSE_REAP_SCRIPT; sh in the distro reads it from stdin.
KNOWN EDGE CASES: NATIVE_HOST_NEXT_STEPS is keyed by the FailureCode value string because this module may not import the enum package. Patterns are plain strings; callers compile them where they use them. MUSE_REAP_SCRIPT runs with the caller's environment, which lacks the peer mark, so it never matches itself.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.1, §9.3
TESTS: tests/features/grok_host/test_grok_host_shared_contract.py, tests/features/muse_host/test_muse_host_wsl.py, tests/features/native_backends/test_native_backends_profiles.py
"""

from __future__ import annotations

from types import MappingProxyType

# Shared native host bounds.
NATIVE_CONTROL_TIMEOUT_SECONDS = 30.0
NATIVE_CONTROL_TIMEOUT_MAX_SECONDS = 600.0
NATIVE_TURN_DEFAULT_SECONDS = 1800.0
NATIVE_TURN_MAX_SECONDS = 14400.0
NATIVE_WAIT_DEFAULT_SECONDS = 60.0
NATIVE_WAIT_MAX_SECONDS = 3600.0
NATIVE_TOOL_WAIT_MAX_SECONDS = 240.0
NATIVE_STOP_GRACE_SECONDS = 5.0
NATIVE_KILL_WAIT_SECONDS = 1.0
NATIVE_STDIO_MAX_WAIT_SECONDS = 86400.0
NATIVE_MAX_LIVE_TURNS_DEFAULT = 4
NATIVE_MAX_LIVE_TURNS_LIMIT = 16
NATIVE_MIN_LIVE_TURNS = 1
NATIVE_FINISHED_TURN_LIMIT = 64
NATIVE_LIST_MIN_LIMIT = 1
NATIVE_LIST_DEFAULT_LIMIT = 50
NATIVE_LIST_MAX_LIMIT = 200
NATIVE_CURSOR_MAX_CHARS = 512
NATIVE_ID_MAX_CHARS = 128
NATIVE_APPROVAL_TITLE_MAX_CHARS = 200
NATIVE_STEER_STATUS_MAX_CHARS = 64
NATIVE_URL_MAX_CHARS = 2048
NATIVE_QUOTED_VALUE_MAX_CHARS = 80
NATIVE_SESSION_ID_MAX_CHARS = 160
NATIVE_VENDOR_ID_PATTERN = r"^[^\s-][^\s]*$"
NATIVE_PROMPT_MAX_CHARS = 200000
NATIVE_RESULT_TEXT_MAX_CHARS = 100000
NATIVE_MAX_RECORDED_DECISIONS = 100
NATIVE_VENDOR_MESSAGE_MAX_CHARS = 1000
NATIVE_CONTEXT_LIST_MAX_ITEMS = 20
NATIVE_TOOL_OUTPUT_MAX_BYTES = 64000
NATIVE_EVENT_MAX_CHARS = 8000
NATIVE_PROCESS_MAX_OUTPUT_BYTES = 67108864
NATIVE_PROCESS_TRUNCATION_PROBE_BYTES = 1

# Default next step per failure code value, verbatim from the spec's code catalog.
NATIVE_HOST_NEXT_STEPS: MappingProxyType[str, str] = MappingProxyType(
    {
        "grok.not_installed": "Install Grok Build 1.0.13 or newer, or set GrokHostSettings.grok_command.",
        "grok.version_unsupported": "Update Grok Build to 1.0.13 or newer with grok update.",
        "grok.not_signed_in": "Run grok login in a terminal, then retry.",
        "grok.model_unknown": "Pick a model id returned by list_grok_models.",
        "grok.capability_missing": "Update Grok Build with grok update, or pick an option that list_grok_models shows for this model.",
        "grok.session_not_found": "Use list_grok_sessions to find a session id in this host's workspace.",
        "grok.session_busy": "Wait for or interrupt the live turn with wait_grok_turn or interrupt_grok_turn, then retry.",
        "grok.api_error": "Retry later; if it repeats, report error.context['vendor_code'] to xAI support.",
        "grok.process_exited": "Run check_grok_ready; if the host was closed, open a new GrokHost.",
        "grok.protocol_mismatch": "Run check_grok_ready and use a Grok Build release this SDK supports (1.0.13 or newer).",
        "grok.server_unreachable": "Retry, or raise GrokHostSettings.control_timeout_seconds if the machine is slow.",
        "grok.turn_timed_out": "The turn is still running: call wait_grok_turn again or interrupt_grok_turn.",
        "grok.turn_not_found": "Use a handle returned by this host's spawn_grok_session or continue_grok_session; finished turns are kept for the last 64 turns only.",
        "opencode.not_installed": "Install opencode 1.18.31 or newer, or set OpencodeHostSettings.opencode_command.",
        "opencode.version_unsupported": "Upgrade opencode to 1.18.31 or newer with opencode upgrade.",
        "opencode.not_signed_in": "Connect a provider with opencode auth login, or check server_username and server_password for an attached server.",
        "opencode.model_unknown": "Pick a provider/model id returned by list_opencode_models.",
        "opencode.session_not_found": "Use list_opencode_sessions to find a session id on this server.",
        "opencode.message_not_found": "Use get_opencode_session_messages to find a message id in this session.",
        "opencode.session_busy": "Wait for or interrupt the running turn with wait_opencode_turn or interrupt_opencode_turn, then retry.",
        "opencode.usage_limited": "The provider rate-limited or capped this account; wait for the limit to reset, then retry.",
        "opencode.billing_error": "Add credit or fix billing with the model provider, then retry.",
        "opencode.api_error": "Retry later; if it repeats, inspect error.context['vendor_error'].",
        "opencode.mcp_server_failed": "Fix the MCP server command or URL and add it again; servers that need OAuth are not supported here.",
        "opencode.process_exited": "The opencode server stopped; open a new OpencodeHost.",
        "opencode.protocol_mismatch": "Run check_opencode_ready and use opencode 1.18.31 or newer.",
        "opencode.server_unreachable": "Check that the opencode server is running, or raise OpencodeHostSettings.request_timeout_seconds.",
        "opencode.turn_timed_out": "The turn is still running: call wait_opencode_turn again or interrupt_opencode_turn.",
        "opencode.turn_not_found": "Use a handle returned by this host's spawn_opencode_session or continue_opencode_session; finished turns are kept for the last 64 turns only.",
        "muse.not_installed": "Install Muse Code 1.0.1 or newer in the distro, or set MuseHostSettings.muse_path.",
        "muse.wsl_unavailable": "Install WSL and the Muse distro, then set MuseHostSettings.wsl_distro to a name from wsl.exe -l -q.",
        "muse.version_unsupported": "Upgrade Muse Code to 1.0.1 or newer.",
        "muse.model_unknown": "Pick a model id returned by list_muse_models.",
        "muse.capability_missing": "This Muse Code release lacks the method; upgrade Muse Code.",
        "muse.session_not_found": "Use list_muse_sessions to find a session id in this workspace.",
        "muse.session_busy": "Wait for or interrupt the running turn with wait_muse_turn or interrupt_muse_turn, then retry.",
        "muse.budget_exhausted": "The turn hit Muse's step limit; continue the session with continue_muse_session and a narrower prompt.",
        "muse.sandbox_not_ready": "Run muse sandbox inside the distro to check the OS sandbox, then retry.",
        "muse.api_error": "Retry later; if it repeats, inspect error.context['vendor_error'].",
        "muse.process_exited": "Run check_muse_ready; if the host was closed, open a new MuseHost.",
        "muse.protocol_mismatch": "Run check_muse_ready and use Muse Code 1.0.1 or newer.",
        "muse.server_unreachable": "Retry, or raise MuseHostSettings.control_timeout_seconds; WSL start-up can be slow.",
        "muse.turn_timed_out": "The turn is still running: call wait_muse_turn again or interrupt_muse_turn.",
        "muse.turn_not_found": "Use a handle returned by this host's spawn_muse_session or continue_muse_session; finished turns are kept for the last 64 turns only.",
        "backend.not_signed_in": "Set the backend's API key environment variable (GLM_API_KEY or DEEPSEEK_API_KEY) to a valid key.",
        "backend.model_unknown": "Pick a model listed in HarnessBackend.claude_models from list_harness_backends.",
        "backend.feature_unsupported": "Remove the listed features from the request or pick another backend; this endpoint silently ignores them.",
        "backend.harness_not_allowed": "Use this backend only with a harness in HarnessBackend.allowed_harnesses.",
        "backend.billing_error": "Top up the DeepSeek account balance, then retry.",
        "backend.usage_limited": "Wait for the provider's rate limit to reset, then retry.",
        "backend.api_error": "Retry later; if it repeats, inspect error.context['vendor_error'].",
        "backend.server_unreachable": "Check network access to the backend endpoint, then retry.",
        "backend.protocol_mismatch": "The endpoint returned an unexpected response; check the backend's API status.",
        "configuration.invalid_argument": "Fix the argument named in the message and call again.",
        "runtime.error": "This is a defect in the SDK host; report it with error.context['error_type'].",
    }
)
# The configuration.invalid_argument next step with the argument's name filled in, so it holds the row's token (EC-1, EC-138).
NATIVE_INVALID_ARGUMENT_NEXT_STEP = "Fix the {field} argument and call again."
# Next steps every host gives in the same words. {tool} is the
# host's own tool, for example interrupt_grok_turn.
NATIVE_NOT_OPEN_NEXT_STEP = "Open the host with async with and call it inside the block."
NATIVE_REENTER_NEXT_STEP = "Create a new host object for each async with block."
NATIVE_AT_CAP_NEXT_STEP = "This host already runs its maximum number of live turns; wait for or interrupt one with {tool}, then retry."
NATIVE_STALE_CURSOR_NEXT_STEP = "Call {tool} without a cursor to start again."

# Fixed texts and status codes more than one host reads or writes.
NATIVE_TRUE_TEXT = "true"
NATIVE_FALSE_TEXT = "false"
NATIVE_SUCCESS_EXIT_CODE = 0
NATIVE_HTTP_SUCCESS_FIRST_STATUS = 200
NATIVE_HTTP_SUCCESS_END_STATUS = 300
NATIVE_HTTP_SIGNED_OUT_STATUSES = frozenset({401, 403})
NATIVE_HTTP_BILLING_STATUS = 402
NATIVE_HTTP_RATE_LIMIT_STATUS = 429

# Grok Build.
GROK_MIN_VERSION = (1, 0, 13)
GROK_VERSION_PATTERN = r"grok (\d+)\.(\d+)\.(\d+)"
GROK_ACP_PROTOCOL_VERSION = 1
GROK_SIGNED_OUT_LINE = "You are not authenticated."
GROK_NOT_SIGNED_IN_MARKERS = ("not authenticated", "auth token is invalid or expired", "grok login")
GROK_ARGV_PROMPT_MAX_CHARS = 24000
GROK_CLI_MAX_OUTPUT_BYTES = 4194304
GROK_LIST_MAX_PAGES = 20
GROK_SEARCH_DEFAULT_LIMIT = 20
GROK_SEARCH_MAX_LIMIT = 100
GROK_QUERY_MAX_CHARS = 200
GROK_MAX_RULES = 32
GROK_RULE_MAX_CHARS = 200
GROK_MAX_TURNS_LIMIT = 200
GROK_MIN_TURNS = 1
GROK_CLIENT_NAME = "vidbyte-sdk"
GROK_CLIENT_TITLE = "Vidbyte SDK"
GROK_TURN_OPERATION = "wait_grok_turn"

# opencode.
OPENCODE_MIN_VERSION = (1, 18, 31)
OPENCODE_LISTENING_PATTERN = r"opencode server listening on (http://127\.0\.0\.1:\d+)"
OPENCODE_SERVER_LOGIN = "vidbyte"
OPENCODE_STARTUP_TIMEOUT_SECONDS = 20.0
OPENCODE_REQUEST_TIMEOUT_SECONDS = 30.0
OPENCODE_MAX_RESPONSE_BYTES = 8388608
OPENCODE_POLL_INTERVAL_SECONDS = 1.0
OPENCODE_IDLE_CONFIRMATIONS = 3
OPENCODE_POLL_FAILURE_LIMIT = 5
OPENCODE_TURN_MESSAGE_LIMIT = 1000
OPENCODE_WATCH_MESSAGE_LIMIT = 50
OPENCODE_MAX_SESSION_TREE = 64
OPENCODE_RETRY_ATTEMPT_LIMIT = 5
OPENCODE_RATE_LIMIT_MARKERS = ("rate limit", "rate_limit", "429", "too many requests", "quota", "usage limit")
OPENCODE_SYSTEM_MAX_CHARS = 20000
OPENCODE_PATCH_MAX_CHARS = 20000
OPENCODE_MAX_PERMISSION_RULES = 64
OPENCODE_RULE_MAX_CHARS = 200
OPENCODE_MAX_MCP_SERVERS = 16
OPENCODE_MCP_TIMEOUT_MAX_MS = 600000
OPENCODE_MCP_TIMEOUT_MIN_MS = 1
OPENCODE_MCP_NAME_MAX_CHARS = 64
OPENCODE_MCP_MAP_MAX_ITEMS = 64
OPENCODE_PROVIDER_ID_MAX_CHARS = 64
OPENCODE_PROVIDER_MODEL_MAX_CHARS = 257
OPENCODE_CREDENTIAL_MAX_CHARS = 1024
OPENCODE_SESSION_ID_PATTERN = r"^ses[0-9A-Za-z_-]{1,128}$"
OPENCODE_MESSAGE_ID_PATTERN = r"^msg[0-9A-Za-z_-]{1,128}$"
OPENCODE_PART_ID_PATTERN = r"^prt[0-9A-Za-z_-]{1,128}$"
OPENCODE_MCP_NAME_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
OPENCODE_ENV_KEY_PATTERN = r"^[A-Za-z_][A-Za-z0-9_-]{0,127}$"
OPENCODE_TURN_OPERATION = "wait_opencode_turn"
OPENCODE_BUSY_STATES = frozenset({"busy", "retry"})
OPENCODE_RETRY_STATE = "retry"
OPENCODE_ASSISTANT_ROLE = "assistant"
OPENCODE_MODEL_ID_SPLITS = 1

# Muse Code.
MUSE_MIN_VERSION = (1, 0, 1)
MUSE_VERSION_PATTERN = r"Muse Code (\d+)\.(\d+)\.(\d+)"
MUSE_SCHEMA_VERSION = 1
MUSE_CLIENT_NAME = "vidbyte_sdk"
MUSE_UUID_TIMESTAMP_MASK = (1 << 48) - 1
MUSE_UUID_TIMESTAMP_SHIFT = 80
MUSE_UUID_VERSION = 7
MUSE_UUID_VERSION_SHIFT = 76
MUSE_UUID_RAND_A_SHIFT = 64
MUSE_UUID_VARIANT = 0b10
MUSE_UUID_VARIANT_SHIFT = 62
MUSE_UUID_RANDOM_BITS = 74
MUSE_UUID_RAND_B_BITS = 62
MUSE_UUID_RAND_B_MASK = (1 << 62) - 1
MUSE_DEFAULT_PATH = "/usr/local/bin/muse"
MUSE_PATH_MAX_CHARS = 4096
MUSE_DISTRO_MAX_CHARS = 64
MUSE_FRAME_POLL_SECONDS = 0.1
MUSE_APPROVAL_MODE = "denyUnmatched"
MUSE_FAILED_TERMINAL = "failed"
MUSE_TURN_OPERATION = "wait_muse_turn"
MUSE_PAGE_MAX_LIMIT = 200
MUSE_USAGE_MAX_PAGES = 10
MUSE_PEER_MARK_VARIABLE = "VIDBYTE_PEER_MARK"
MUSE_PEER_MARK_PATTERN = r"^[0-9a-f]{32}$"
MUSE_REAP_TIMEOUT_SECONDS = 10.0
# The in-distro reap, read by `sh -s <mark>` from stdin. It finds every
# process whose environment holds the exact mark entry, adds their
# descendants from the PPid line of /proc/<pid>/status until a pass finds
# nothing new, kills them all except itself, and always exits 0.
MUSE_REAP_SCRIPT = """targets=""
for d in /proc/[0-9]*; do
  p=${d#/proc/}
  if tr '\\0' '\\n' < /proc/$p/environ 2>/dev/null | grep -qxF "VIDBYTE_PEER_MARK=$1"; then
    targets="$targets $p"
  fi
done
changed=1
while [ "$changed" = 1 ]; do
  changed=0
  for d in /proc/[0-9]*; do
    p=${d#/proc/}
    case " $targets " in *" $p "*) continue ;; esac
    pp=$(sed -n 's/^PPid:[[:space:]]*//p' /proc/$p/status 2>/dev/null)
    [ -n "$pp" ] || continue
    case " $targets " in *" $pp "*) targets="$targets $p"; changed=1 ;; esac
  done
done
for p in $targets; do
  [ "$p" = "$$" ] && continue
  kill -KILL "$p" 2>/dev/null
done
exit 0
"""

# GLM and DeepSeek backend profiles.
BACKEND_HTTP_TIMEOUT_SECONDS = 15.0
BACKEND_MAX_RESPONSE_BYTES = 65536
BACKEND_ENV_NAME_MAX_CHARS = 64
BACKEND_CURRENCY_MAX_CHARS = 16
BACKEND_KEY_MISSING_NEXT_STEP = "Set {variable} in the environment to a valid key."
