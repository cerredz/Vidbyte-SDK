"""FILE: vidbyte/lib/constants/native_threads.py

PURPOSE: Holds every fixed value and text of the harness thread functions and the canonical process helpers: time, size and count bounds, record patterns, program names, folder names, option values, JSON member names, vendor markers, tested vendor versions, the process reaper's fixed programs and script, and the error texts (harness labels, summary and observation templates, the failure code of each harness and problem, the record each operation returns, and one likely cause and one next step per failure code).
ROLE IN CODEBASE: Imported by the records in vidbyte/lib/dataclasses/native_threads.py, process.py and validation.py, by CliRunner and ProcessReaper in vidbyte/lib/process/, and by every module under vidbyte/harnesses/native/. The browser tools' own values live beside it in vidbyte/lib/constants/browser_tools.py.
ARCHITECTURE NOTE: The harness modules hold no literals of their own (spec INV-15): every flag is an enum member in vidbyte/lib/enums/native_threads.py, and every other value they need lives here, so a reviewer finds each vendor fact in one place. The timing knobs NATIVE_KILL_WAIT_SECONDS, MUSE_REAP_TIMEOUT_SECONDS and NATIVE_CONTROL_TIMEOUT_SECONDS, and the reaper's NATIVE_PS_PATHS, are read through this module object at call time, never bound by a from-import, so one patch reaches every user.
FUNCTION INVENTORY: No functions. Constants grouped as contract bounds, record patterns, process helper values (the process reaper's among them), programs and folders, option values and separators, JSON member names (the browser path's Grok stream, opencode tool_use and Muse task records among them), vendor markers, tested versions, then the error texts, the failure code table and NATIVE_THREAD_RESULT_RECORDS.
COMMON MODIFICATION PATTERNS: A value a harness module needs is added here under its feature prefix and used by name (lint A007, spec INV-15). A new failure code adds its pair to NATIVE_THREAD_FAILURE_CODES and its own texts to NATIVE_THREAD_LIKELY_CAUSES and NATIVE_THREAD_NEXT_STEPS. A new operation adds its row to NATIVE_THREAD_RESULT_RECORDS.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte above vidbyte.lib.enums. 2. Do not name a constant with a password, token or secret word and give it a string (lint S054). 3. Do not add a carriage return to MUSE_REAP_SCRIPT; sh in the distro reads it from stdin. 4. Do not share one likely cause or next step between two codes of a harness; each code gets text written for it.
KNOWN EDGE CASES: Patterns are applied with re.fullmatch, so each one describes the whole value. The texts must not contain a credential word followed by ":" or "=", because HarnessRedactor would rewrite such a phrase in vendor text. MUSE_REAP_SCRIPT runs with the caller's environment, which lacks the peer mark, so it never matches itself; NATIVE_REAP_POWERSHELL_SCRIPT reads its marker from the environment and skips its own process for the same reason. The four browser.* codes are shared by the three harnesses, so each has one text per code, not per harness. Five next steps that name a plain function also name its _with_browser sibling (spec D-22).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_surface.py, tests/features/harness_threads/test_harness_threads_errors.py, tests/features/harness_threads/test_harness_threads_browser_contract.py
"""

from __future__ import annotations

from types import MappingProxyType

from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.native_threads import (
    NativeHarness,
    NativeThreadOperation,
    NativeThreadProblem,
    NativeThreadResultRecord,
)

# Contract bounds: time limits, size caps and counts.
NATIVE_THREAD_DEFAULT_SECONDS = 1800.0
NATIVE_THREAD_MAX_SECONDS = 14400.0
NATIVE_CONTROL_TIMEOUT_SECONDS = 30.0
NATIVE_KILL_WAIT_SECONDS = 1.0
MUSE_REAP_TIMEOUT_SECONDS = 10.0
NATIVE_ARGV_PROMPT_MAX_CHARS = 24000
# A Windows command line holds at most 32,766 UTF-16 units (measured).
# A Grok or Muse prompt may take 30,000 of them once quoted; the 2,766
# left are for the program, options, paths and ids, whose measured
# worst case is 608 units.
NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS = 30000
NATIVE_PROMPT_MAX_CHARS = 200000
NATIVE_API_KEY_MAX_CHARS = 4096
NATIVE_THREAD_MAX_SKILLS = 32
NATIVE_RESULT_TEXT_MAX_CHARS = 100000
NATIVE_VENDOR_MESSAGE_MAX_CHARS = 1000
NATIVE_LISTING_MAX_ITEMS = 20
GROK_CLI_MAX_OUTPUT_BYTES = 4194304
NATIVE_PROCESS_MAX_OUTPUT_BYTES = 67108864
NATIVE_QUOTED_VALUE_MAX_CHARS = 80
NATIVE_MODEL_MAX_CHARS = 160
NATIVE_THREAD_ID_MAX_CHARS = 160
NATIVE_NAME_MAX_CHARS = 64
NATIVE_SKILL_NAME_MAX_CHARS = 64
MUSE_DISTRO_MAX_CHARS = 64
MUSE_PATH_MAX_CHARS = 4096
NATIVE_PROCESS_FLAG_MAX_CHARS = 64

# Record patterns (spec §9.1), each applied with re.fullmatch.
# The key pattern is printable ASCII without space, "{" or "}", so
# opencode can never read a key as an {env:...} or {file:...} token.
NATIVE_API_KEY_PATTERN = r"^[!-z|~]+$"
NATIVE_PROMPT_PATTERN = r"[^\x00]+"
NATIVE_MODEL_PATTERN = r"^[A-Za-z0-9]\S*$"
OPENCODE_MODEL_PATTERN = r"^[a-z0-9][a-z0-9._-]*/[A-Za-z0-9]\S*$"
NATIVE_THREAD_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
NATIVE_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
NATIVE_SKILL_NAME_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
MUSE_DISTRO_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
MUSE_PATH_PATTERN = r"^/[^\x00\r\n]*$"
NATIVE_PROCESS_FLAG_PATTERN = r"^-[^\s=]*$"
NATIVE_PROCESS_VALUE_PATTERN = r"[^\x00]*"

# The canonical process helpers.
NATIVE_PROCESS_READ_CHUNK_BYTES = 65536
# asyncio's own buffer limit for a child's stream readers.
NATIVE_PROCESS_STREAM_LIMIT_BYTES = 65536
NATIVE_PROCESS_TRUNCATION_PROBE_BYTES = 1
# How often a POSIX tree stop checks whether the killed group is gone,
# and the signal number that only checks a group exists (signal 0).
NATIVE_PROCESS_GROUP_POLL_SECONDS = 0.01
NATIVE_PROCESS_GROUP_PROBE_SIGNAL = 0
NATIVE_SUCCESS_EXIT_CODE = 0
# taskkill starts by its full path in the Windows system folder, so
# Windows never runs a taskkill.exe from the current folder.
NATIVE_SYSTEM_ROOT_VARIABLE = "SystemRoot"
NATIVE_WINDOWS_DEFAULT_SYSTEM_ROOT = "C:\\Windows"
NATIVE_TASKKILL_PATH_PARTS = ("System32", "taskkill.exe")
NATIVE_TASKKILL_ARGUMENTS = ("/T", "/F", "/PID")
NATIVE_STDOUT_TASK_NAME = "cli-runner-stdout"
NATIVE_STDERR_TASK_NAME = "cli-runner-stderr"
NATIVE_TEXT_ENCODING = "utf-8"
NATIVE_DECODE_REPLACE = "replace"
NATIVE_DECODE_IGNORE = "ignore"
NATIVE_WINDOWS_PLATFORM = "win32"
NATIVE_PATH_VARIABLE = "PATH"
NATIVE_PATHEXT_VARIABLE = "PATHEXT"
# Python's own fallback when PATHEXT is unset
# (shutil._WIN_DEFAULT_PATHEXT).
NATIVE_WINDOWS_DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD;.VBS;.JS;.WS;.MSC"
# Windows counts a command line in UTF-16 code units, and reports one
# past its limit as a missing file with this error number.
NATIVE_WINDOWS_COMMAND_LINE_ENCODING = "utf-16-le"
NATIVE_UTF16_UNIT_BYTES = 2
NATIVE_COMMAND_LINE_TOO_LONG_WINERROR = 206
# The process reaper (ProcessReaper, spec D-12). On Windows it runs the
# System32 PowerShell with a fixed script that reads the marker from
# VIDBYTE_REAP_MARKER, so the marker never sits on a command line it
# would match; it kills every other process whose command line holds
# the marker and prints how many it killed. On POSIX it lists processes
# with ps from a fixed absolute path, never from PATH.
NATIVE_POWERSHELL_PATH_PARTS = ("System32", "WindowsPowerShell", "v1.0", "powershell.exe")
NATIVE_POWERSHELL_ARGUMENTS = ("-NoProfile", "-NonInteractive", "-Command")
NATIVE_REAP_POWERSHELL_SCRIPT = "$marker = $env:VIDBYTE_REAP_MARKER; $count = 0; if ($marker) { Get-CimInstance -ClassName Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.IndexOf($marker, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; $count++ } catch { } } }; Write-Output $count"
NATIVE_PS_PATHS = ("/bin/ps", "/usr/bin/ps")
# Windows PowerShell creates an AppData Roaming folder in USERPROFILE when it
# starts, so the reaper's PowerShell runs without USERPROFILE and
# Windows takes the profile from the user's logon token: a redirected
# USERPROFILE never gets a folder written into it.
NATIVE_USER_PROFILE_VARIABLE = "USERPROFILE"
# The count ProcessReaper.reap returns when it cannot list or stop
# anything (no PowerShell or ps, a timeout, a defect): nothing that
# can be counted was reaped.
NATIVE_REAP_NONE_COUNT = 0
NATIVE_PS_ARGUMENTS = ("-A", "-ww", "-o", "pid=,args=")
NATIVE_REAP_COUNT_PATTERN = r"\s*(\d+)\s*"

# Programs, subcommands, files and folders.
GROK_PROGRAM = "grok"
OPENCODE_PROGRAM = "opencode"
MUSE_PROGRAM = "muse"
WSL_PROGRAM = "wsl.exe"
OPENCODE_RUN_COMMAND = "run"
MUSE_EXEC_COMMAND = "exec"
MUSE_SERVE_COMMAND = "serve"
MUSE_PROVIDER = "meta"
MUSE_DEFAULT_PATH = "/usr/local/bin/muse"
MUSE_REAP_SHELL = "sh"
GROK_HOME_FOLDERS = (".grok", "bin")
NATIVE_WINDOWS_EXECUTABLE_SUFFIX = ".exe"
NATIVE_BATCH_SUFFIXES = (".cmd", ".bat")
NATIVE_WINDOWS_DROPPED_TAIL = ". "
GROK_PRIVATE_HOMES_PARTS = (".vidbyte", "grok-homes")
GROK_HOME_KEY_HEX_CHARS = 16
GROK_SKILLS_DIR = "skills"
MUSE_CONFIG_SKILLS_PARTS = ("muse", "skills")
MUSE_AUTH_FILE_PARTS = ("muse", "auth.json")
MUSE_SETTINGS_PARTS = ("muse", "settings.json")
NATIVE_SKILL_FILE_NAME = "SKILL.md"
MUSE_WSL_MOUNT_ROOT = "/mnt"
MUSE_WINDOWS_DRIVE_PATTERN = r"[A-Za-z]:"
NATIVE_WINDOWS_ROOT = "\\"

# Fixed option values and separators.
GROK_JSON_OUTPUT_FORMAT = "json"
# Only the browser path streams, because tool calls and connected
# servers are visible only in the stream (spec D-8).
GROK_STREAMING_JSON_OUTPUT_FORMAT = "streaming-json"
OPENCODE_JSON_FORMAT = "json"
NATIVE_ENABLED_SWITCH = "1"
NATIVE_DISABLED_SWITCH = "0"
NATIVE_WSLENV_SEPARATOR = ":"
NATIVE_WSLENV_UNIX_FLAG = "/u"
NATIVE_PROCESS_OPTION_SEPARATOR = "="
NATIVE_LINE_SEPARATOR = "\n"
NATIVE_SENTENCE_SEPARATOR = " "
NATIVE_LISTING_SEPARATOR = ", "
OPENCODE_MODEL_PROVIDER_SEPARATOR = "/"
NATIVE_NUL_CHARACTER = "\x00"

# JSON member names of the vendor output and of the inputs the SDK
# sends.
GROK_TYPE_FIELD = "type"
GROK_ERROR_TYPE = "error"
GROK_MESSAGE_FIELD = "message"
GROK_TEXT_FIELD = "text"
GROK_SESSION_FIELD = "sessionId"
OPENCODE_TYPE_FIELD = "type"
OPENCODE_SESSION_FIELD = "sessionID"
OPENCODE_PART_FIELD = "part"
OPENCODE_TEXT_FIELD = "text"
OPENCODE_MESSAGE_ID_FIELD = "messageID"
OPENCODE_ERROR_FIELD = "error"
OPENCODE_ERROR_NAME_FIELD = "name"
OPENCODE_ERROR_DATA_FIELD = "data"
OPENCODE_ERROR_MESSAGE_FIELD = "message"
OPENCODE_STATUS_FIELD = "statusCode"
OPENCODE_CONFIG_PROVIDER_FIELD = "provider"
OPENCODE_CONFIG_OPTIONS_FIELD = "options"
OPENCODE_CONFIG_KEY_FIELD = "apiKey"
OPENCODE_CONFIG_SKILLS_FIELD = "skills"
OPENCODE_CONFIG_PATHS_FIELD = "paths"
MUSE_STREAM_FIELD = "stream"
MUSE_STREAM_KIND_FIELD = "kind"
MUSE_STREAM_ID_FIELD = "id"
MUSE_PAYLOAD_TYPE_FIELD = "payload_type"
MUSE_PAYLOAD_FIELD = "payload"
MUSE_TERMINAL_FIELD = "terminal"
MUSE_TEXT_FIELD = "text"
MUSE_REASON_FIELD = "reason"
MUSE_CLIENT_INFO_FIELD = "clientInfo"
MUSE_CLIENT_NAME_FIELD = "name"
MUSE_CLIENT_VERSION_FIELD = "version"
MUSE_SESSION_FIELD = "session"
MUSE_SESSION_ID_FIELD = "sessionId"
MUSE_EXCLUDE_ITEMS_FIELD = "excludeItems"
MUSE_COMMAND_ID_FIELD = "commandId"
# The Grok streaming-json events of a browser run (vendor facts section
# 2): the connected tools, text chunks between usage boundaries, each
# tool call and its updates, and the closing end event.
GROK_TEXT_EVENT = "text"
GROK_USAGE_EVENT = "usage"
GROK_END_EVENT = "end"
GROK_TOOL_CALL_EVENT = "tool_call"
GROK_TOOL_CALL_UPDATE_EVENT = "tool_call_update"
GROK_AVAILABLE_COMMANDS_EVENT = "available_commands"
GROK_DATA_FIELD = "data"
GROK_STOP_REASON_FIELD = "stopReason"
GROK_TOOL_CALL_ID_FIELD = "toolCallId"
GROK_TOOL_NAME_FIELD = "toolName"
GROK_RAW_INPUT_FIELD = "rawInput"
GROK_RAW_TOOL_NAME_FIELD = "tool_name"
GROK_STATUS_FIELD = "status"
GROK_TOOLS_FIELD = "tools"
GROK_USE_TOOL_NAME = "use_tool"
GROK_CANCELLED_STOP_REASON = "cancelled"
GROK_COMPLETED_STATUS = "completed"
# The opencode tool_use event of a call to a mounted server.
OPENCODE_TOOL_FIELD = "tool"
OPENCODE_STATE_FIELD = "state"
OPENCODE_STATE_STATUS_FIELD = "status"
OPENCODE_COMPLETED_STATUS = "completed"
# The Muse records of a call to a mounted server (spec A-1).
MUSE_TASK_PROPOSED_TYPE = "task.lifecycle.proposed"
MUSE_SIDE_EFFECT_INTENT_TYPE = "side_effect_intent"
MUSE_TASK_COMPLETED_TYPE = "task.lifecycle.completed"
MUSE_TASK_FAILED_TYPE = "task.lifecycle.failed"
MUSE_TASK_ID_FIELD = "task_id"
MUSE_TASK_KIND_FIELD = "task_kind"
MUSE_OPERATION_FIELD = "operation"
JSONRPC_VERSION_FIELD = "jsonrpc"
JSONRPC_VERSION = "2.0"
JSONRPC_ID_FIELD = "id"
JSONRPC_METHOD_FIELD = "method"
JSONRPC_PARAMS_FIELD = "params"
JSONRPC_RESULT_FIELD = "result"
JSONRPC_ERROR_FIELD = "error"
JSONRPC_CODE_FIELD = "code"
JSONRPC_MESSAGE_FIELD = "message"
MUSE_INITIALIZE_REQUEST_ID = 1
MUSE_SESSION_REQUEST_ID = 2
MUSE_CLIENT_NAME = "vidbyte_sdk"

# Vendor markers: texts, names and codes the vendors print.
GROK_NOT_SIGNED_IN_MARKERS = ("not signed in", "not authenticated", "auth token is invalid or expired")
OPENCODE_SESSION_NOT_FOUND_MARKER = "Session not found"
OPENCODE_KEY_REJECTED_ERROR_NAMES = frozenset({"ProviderAuthError"})
OPENCODE_KEY_REJECTED_STATUSES = frozenset({401, 403})
MUSE_KEY_REJECTED_MARKERS = ("authentication failed",)
MUSE_DISTRO_NOT_FOUND_MARKER = "WSL_E_DISTRO_NOT_FOUND"
MUSE_NO_SUCH_FILE_MARKER = "No such file or directory"
NATIVE_COMMAND_NOT_FOUND_EXIT_CODE = 127
MUSE_SESSION_NOT_FOUND_CODE = -32020
MUSE_TERMINAL_PREFIX = "run.terminal."
# The members a Muse protocol_mismatch names when they are missing.
MUSE_SESSION_STREAM_MEMBER = "stream.id"
MUSE_TERMINAL_RECORD_MEMBER = "run.terminal.*"
MUSE_FORK_SESSION_MEMBER = "result.session.sessionId"
MUSE_COMPLETED_TERMINAL = "completed"
MUSE_SESSION_STREAM_KIND = "session"
# Muse fails a whole run when any configured MCP server fails to start
# and names that server in its reason (vendor facts section 1).
MUSE_REQUIRED_SERVER_MARKER = "Required MCP server"

# Tested vendor versions: the releases these contracts were checked
# against, named in protocol_mismatch errors.
GROK_TESTED_VERSION = "1.0.52"
OPENCODE_TESTED_VERSION = "1.18.31"
MUSE_TESTED_VERSION = "1.0.1"
NATIVE_TESTED_VERSIONS: MappingProxyType[NativeHarness, str] = MappingProxyType(
    {
        NativeHarness.GROK: GROK_TESTED_VERSION,
        NativeHarness.OPENCODE: OPENCODE_TESTED_VERSION,
        NativeHarness.MUSE: MUSE_TESTED_VERSION,
    }
)

# UUIDv7 layout for the Muse session/fork commandId.
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
MUSE_MILLISECONDS_PER_SECOND = 1000

# The Muse WSL peer mark and the in-distro reap, read by `sh -s <mark>`
# from stdin. It finds every process whose environment holds the exact
# mark entry, adds their descendants from the PPid line of
# /proc/<pid>/status until a pass finds nothing new, kills them all
# except itself, and always exits 0.
MUSE_PEER_MARK_PATTERN = r"^[0-9a-f]{32}$"
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

# Error texts. Every NativeThreadError message is these sentences in
# order: the head, the summary, the workspace and thread id when known,
# the observations, the vendor text, the likely cause and the next
# step (spec INV-5).
NATIVE_HARNESS_LABELS: MappingProxyType[NativeHarness, str] = MappingProxyType(
    {
        NativeHarness.GROK: "Grok Build",
        NativeHarness.OPENCODE: "opencode",
        NativeHarness.MUSE: "Muse Code",
    }
)
NATIVE_REDACTED = "<redacted>"
NATIVE_FIELD_DETAIL_KEY = "field"
NATIVE_UNNAMED_ARGUMENT = "argument"
NATIVE_CONFIG_ARGUMENT = "config"
NATIVE_WORKSPACE_ARGUMENT = "workspace"
MUSE_WSL_WORKSPACE_RULE = "workspace must be an absolute Windows path on a drive letter; UNC and drive-less paths have no /mnt form inside WSL."
NATIVE_MESSAGE_HEAD = "{operation} failed with {code}."
NATIVE_WORKSPACE_SENTENCE = "The workspace was {workspace}."
NATIVE_THREAD_ID_SENTENCE = "The thread id was {thread_id}."
NATIVE_EXIT_STATUS_SENTENCE = "The process exited with status {exit_code}."
NATIVE_MISSING_MEMBER_SENTENCE = "The output has no {member} member."
NATIVE_VENDOR_TEXT_SENTENCE = 'The vendor printed: "{vendor_text}".'
NATIVE_LIKELY_CAUSE_SENTENCE = "Likely cause: {likely_cause}"
NATIVE_NEXT_STEP_SENTENCE = "Next step: {next_step}"
NATIVE_INVALID_ARGUMENT_SUMMARY = "The SDK refused an argument before starting {harness}."
NATIVE_INVALID_ARGUMENT_OBSERVATION = "The argument {argument} was refused: {rule}"
NATIVE_RUNTIME_ERROR_SUMMARY = "The SDK failed while driving {harness}."
NATIVE_RUNTIME_ERROR_OBSERVATION = "An unexpected {error_type} was raised inside the SDK; its text is left out because it can hold private data."
NATIVE_THREAD_SUMMARIES: MappingProxyType[NativeThreadProblem, str] = MappingProxyType(
    {
        NativeThreadProblem.NOT_INSTALLED: "{harness} could not be found.",
        NativeThreadProblem.LAUNCHER_REFUSED: "{harness} was not started because its launcher is a Windows batch file.",
        NativeThreadProblem.LAUNCH_FAILED: "{harness} could not be started.",
        NativeThreadProblem.KEY_REJECTED: "{harness} rejected the API key.",
        NativeThreadProblem.THREAD_NOT_FOUND: "{harness} could not find the requested thread.",
        NativeThreadProblem.TIMED_OUT: "{harness} did not finish in time.",
        NativeThreadProblem.OUTPUT_TOO_LARGE: "{harness} printed more output than the SDK reads.",
        NativeThreadProblem.PROTOCOL_MISMATCH: "{harness} answered in a form this SDK cannot read.",
        NativeThreadProblem.RUN_FAILED: "{harness} reported that the run failed.",
        NativeThreadProblem.WSL_UNAVAILABLE: "{harness} could not be reached through WSL.",
        NativeThreadProblem.MOUNT_UNSUPPORTED: "{harness} cannot mount the selected browser tools safely, so nothing was started.",
        NativeThreadProblem.RUNTIME_MISSING: "A program the selected browser tools need was not found, so {harness} was not started.",
        NativeThreadProblem.TOOL_INSTALL_FAILED: "A selected browser tool could not be installed into the tool cache, so {harness} was not started.",
        NativeThreadProblem.TOOLS_UNAVAILABLE: "{harness} finished, but its output does not show the mounted browser tools working.",
    }
)
NATIVE_THREAD_OBSERVATIONS: MappingProxyType[NativeThreadProblem, str] = MappingProxyType(
    {
        NativeThreadProblem.NOT_INSTALLED: "No launcher that the SDK could start was found.",
        NativeThreadProblem.LAUNCHER_REFUSED: "cmd.exe would re-read the arguments of a batch file as a command line, so the SDK never starts one.",
        NativeThreadProblem.LAUNCH_FAILED: "The SDK could not start the program or prepare its private folder.",
        NativeThreadProblem.KEY_REJECTED: "The vendor refused the key passed as api_key, and the SDK never falls back to a stored login.",
        NativeThreadProblem.THREAD_NOT_FOUND: "The vendor could not continue the requested thread, or answered on another one.",
        NativeThreadProblem.TIMED_OUT: "The SDK waited {seconds} seconds and then stopped the whole process tree, so the thread may hold a partial turn.",
        NativeThreadProblem.OUTPUT_TOO_LARGE: "Standard output passed the cap of {cap_bytes} bytes, so the SDK did not read it as an answer.",
        NativeThreadProblem.PROTOCOL_MISMATCH: "The output did not match what this SDK expects from {harness} {version}.",
        NativeThreadProblem.RUN_FAILED: "The vendor reported a failure of its own.",
        NativeThreadProblem.WSL_UNAVAILABLE: "Muse Code runs on Windows only inside a WSL distro.",
        NativeThreadProblem.MOUNT_UNSUPPORTED: "Before anything starts, the SDK checks each selected tool against what {harness} can carry without writing a key into a file.",
        NativeThreadProblem.RUNTIME_MISSING: "Before anything starts, the SDK checks for Node when a local tool is selected and for Chrome stable when a tool drives Chrome.",
        NativeThreadProblem.TOOL_INSTALL_FAILED: "Each local browser tool is installed once, at its pinned version, into the tool cache under ~/.vidbyte/tools before its first use.",
        NativeThreadProblem.TOOLS_UNAVAILABLE: "The SDK reads the vendor's own output for evidence that each mounted server connected or was used.",
    }
)
# Detail sentences the harness modules fill in and hand to the error
# factory as `searched`.
NATIVE_SEARCHED_PATH = "The SDK searched for {program} on PATH."
NATIVE_SEARCHED_PATH_AND_FALLBACK = "The SDK searched for {program} on PATH and at {fallback}."
NATIVE_SEARCHED_COMMAND = "The launcher {program} does not exist."
NATIVE_REFUSED_LAUNCHER = "The refused launcher is {program}."
NATIVE_LAUNCH_FAILURE_DETAIL = "Starting {program} failed with {kind}."
GROK_HOME_FAILURE_DETAIL = "The private Grok home {home} could not be prepared ({error_type}: {reason})."
GROK_HOME_UNKNOWN_DETAIL = "The user home folder, where the private Grok home lives, could not be determined ({error_type}); set HOME (POSIX) or USERPROFILE (Windows) for this process."
MUSE_CONFIG_FAILURE_DETAIL = "The private Muse config folder could not be prepared ({error_type}: {reason})."
MUSE_NO_WSL_DETAIL = "Neither wsl_distro nor muse_command was set, and on Windows the SDK runs Muse Code only through one of them."
MUSE_NO_WSL_PROGRAM_DETAIL = "The SDK searched for {program} on PATH and found none."
MUSE_DISTRO_MISSING_DETAIL = "WSL has no distro named {distro}; {program} lists {distros}."
MUSE_NOT_IN_DISTRO_DETAIL = "The SDK looked for {muse_path} inside the WSL distro {distro}."
NATIVE_FORK_RETURNED_SOURCE_DETAIL = "The fork answered with its source thread, so the vendor continued the source thread instead of forking it."
NATIVE_OTHER_THREAD_DETAIL = "The vendor answered on thread {answered} instead of {requested}."
GROK_STOP_REASON_DETAIL = "Grok Build ended the turn with stop reason {reason}; a headless run cancels the turn when the agent calls a tool that no rule allows."
# The detail of each wrong-thread problem of a Grok or opencode answer;
# both are formatted with the answered and the requested id.
NATIVE_WRONG_THREAD_DETAILS: MappingProxyType[NativeThreadProblem, str] = MappingProxyType(
    {
        NativeThreadProblem.THREAD_NOT_FOUND: NATIVE_OTHER_THREAD_DETAIL,
        NativeThreadProblem.PROTOCOL_MISMATCH: NATIVE_FORK_RETURNED_SOURCE_DETAIL,
    }
)
# The vendor text of an opencode error event: its name, its HTTP
# status when it has one, and its message.
OPENCODE_ERROR_EVENT_TEXT = "{name}: {message}"
OPENCODE_ERROR_EVENT_STATUS_TEXT = "{name} (status {status}): {message}"

# The failure code of each harness and problem, a closed table, so the
# error factory never builds a code from text.
NATIVE_THREAD_FAILURE_CODES: MappingProxyType[tuple[NativeHarness, NativeThreadProblem], FailureCode] = MappingProxyType(
    {
        (NativeHarness.GROK, NativeThreadProblem.NOT_INSTALLED): FailureCode.GROK_NOT_INSTALLED,
        (NativeHarness.GROK, NativeThreadProblem.LAUNCHER_REFUSED): FailureCode.GROK_LAUNCHER_REFUSED,
        (NativeHarness.GROK, NativeThreadProblem.LAUNCH_FAILED): FailureCode.GROK_LAUNCH_FAILED,
        (NativeHarness.GROK, NativeThreadProblem.KEY_REJECTED): FailureCode.GROK_KEY_REJECTED,
        (NativeHarness.GROK, NativeThreadProblem.THREAD_NOT_FOUND): FailureCode.GROK_THREAD_NOT_FOUND,
        (NativeHarness.GROK, NativeThreadProblem.TIMED_OUT): FailureCode.GROK_TIMED_OUT,
        (NativeHarness.GROK, NativeThreadProblem.OUTPUT_TOO_LARGE): FailureCode.GROK_OUTPUT_TOO_LARGE,
        (NativeHarness.GROK, NativeThreadProblem.PROTOCOL_MISMATCH): FailureCode.GROK_PROTOCOL_MISMATCH,
        (NativeHarness.GROK, NativeThreadProblem.RUN_FAILED): FailureCode.GROK_RUN_FAILED,
        (NativeHarness.OPENCODE, NativeThreadProblem.NOT_INSTALLED): FailureCode.OPENCODE_NOT_INSTALLED,
        (NativeHarness.OPENCODE, NativeThreadProblem.LAUNCHER_REFUSED): FailureCode.OPENCODE_LAUNCHER_REFUSED,
        (NativeHarness.OPENCODE, NativeThreadProblem.LAUNCH_FAILED): FailureCode.OPENCODE_LAUNCH_FAILED,
        (NativeHarness.OPENCODE, NativeThreadProblem.KEY_REJECTED): FailureCode.OPENCODE_KEY_REJECTED,
        (NativeHarness.OPENCODE, NativeThreadProblem.THREAD_NOT_FOUND): FailureCode.OPENCODE_THREAD_NOT_FOUND,
        (NativeHarness.OPENCODE, NativeThreadProblem.TIMED_OUT): FailureCode.OPENCODE_TIMED_OUT,
        (NativeHarness.OPENCODE, NativeThreadProblem.OUTPUT_TOO_LARGE): FailureCode.OPENCODE_OUTPUT_TOO_LARGE,
        (NativeHarness.OPENCODE, NativeThreadProblem.PROTOCOL_MISMATCH): FailureCode.OPENCODE_PROTOCOL_MISMATCH,
        (NativeHarness.OPENCODE, NativeThreadProblem.RUN_FAILED): FailureCode.OPENCODE_RUN_FAILED,
        (NativeHarness.MUSE, NativeThreadProblem.NOT_INSTALLED): FailureCode.MUSE_NOT_INSTALLED,
        (NativeHarness.MUSE, NativeThreadProblem.LAUNCHER_REFUSED): FailureCode.MUSE_LAUNCHER_REFUSED,
        (NativeHarness.MUSE, NativeThreadProblem.LAUNCH_FAILED): FailureCode.MUSE_LAUNCH_FAILED,
        (NativeHarness.MUSE, NativeThreadProblem.KEY_REJECTED): FailureCode.MUSE_KEY_REJECTED,
        (NativeHarness.MUSE, NativeThreadProblem.THREAD_NOT_FOUND): FailureCode.MUSE_THREAD_NOT_FOUND,
        (NativeHarness.MUSE, NativeThreadProblem.TIMED_OUT): FailureCode.MUSE_TIMED_OUT,
        (NativeHarness.MUSE, NativeThreadProblem.OUTPUT_TOO_LARGE): FailureCode.MUSE_OUTPUT_TOO_LARGE,
        (NativeHarness.MUSE, NativeThreadProblem.PROTOCOL_MISMATCH): FailureCode.MUSE_PROTOCOL_MISMATCH,
        (NativeHarness.MUSE, NativeThreadProblem.RUN_FAILED): FailureCode.MUSE_RUN_FAILED,
        (NativeHarness.MUSE, NativeThreadProblem.WSL_UNAVAILABLE): FailureCode.MUSE_WSL_UNAVAILABLE,
        # The browser tools: one shared code per problem, because the
        # cause is the tool, not the harness (spec D-13).
        (NativeHarness.GROK, NativeThreadProblem.MOUNT_UNSUPPORTED): FailureCode.BROWSER_MOUNT_UNSUPPORTED,
        (NativeHarness.GROK, NativeThreadProblem.RUNTIME_MISSING): FailureCode.BROWSER_RUNTIME_MISSING,
        (NativeHarness.GROK, NativeThreadProblem.TOOL_INSTALL_FAILED): FailureCode.BROWSER_TOOL_INSTALL_FAILED,
        (NativeHarness.GROK, NativeThreadProblem.TOOLS_UNAVAILABLE): FailureCode.BROWSER_TOOLS_UNAVAILABLE,
        (NativeHarness.OPENCODE, NativeThreadProblem.MOUNT_UNSUPPORTED): FailureCode.BROWSER_MOUNT_UNSUPPORTED,
        (NativeHarness.OPENCODE, NativeThreadProblem.RUNTIME_MISSING): FailureCode.BROWSER_RUNTIME_MISSING,
        (NativeHarness.OPENCODE, NativeThreadProblem.TOOL_INSTALL_FAILED): FailureCode.BROWSER_TOOL_INSTALL_FAILED,
        (NativeHarness.OPENCODE, NativeThreadProblem.TOOLS_UNAVAILABLE): FailureCode.BROWSER_TOOLS_UNAVAILABLE,
        (NativeHarness.MUSE, NativeThreadProblem.MOUNT_UNSUPPORTED): FailureCode.BROWSER_MOUNT_UNSUPPORTED,
        (NativeHarness.MUSE, NativeThreadProblem.RUNTIME_MISSING): FailureCode.BROWSER_RUNTIME_MISSING,
        (NativeHarness.MUSE, NativeThreadProblem.TOOL_INSTALL_FAILED): FailureCode.BROWSER_TOOL_INSTALL_FAILED,
        (NativeHarness.MUSE, NativeThreadProblem.TOOLS_UNAVAILABLE): FailureCode.BROWSER_TOOLS_UNAVAILABLE,
    }
)

# The record each operation returns, named by NativeThreadError.expected
# (spec D-15): the plain functions return a NativeThreadResult and the
# browser functions a BrowserThreadResult.
NATIVE_THREAD_RESULT_RECORDS: MappingProxyType[NativeThreadOperation, NativeThreadResultRecord] = MappingProxyType(
    {
        NativeThreadOperation.RUN_GROK_THREAD: NativeThreadResultRecord.NATIVE_THREAD_RESULT,
        NativeThreadOperation.CONTINUE_GROK_THREAD: NativeThreadResultRecord.NATIVE_THREAD_RESULT,
        NativeThreadOperation.FORK_GROK_THREAD: NativeThreadResultRecord.NATIVE_THREAD_RESULT,
        NativeThreadOperation.RUN_OPENCODE_THREAD: NativeThreadResultRecord.NATIVE_THREAD_RESULT,
        NativeThreadOperation.CONTINUE_OPENCODE_THREAD: NativeThreadResultRecord.NATIVE_THREAD_RESULT,
        NativeThreadOperation.FORK_OPENCODE_THREAD: NativeThreadResultRecord.NATIVE_THREAD_RESULT,
        NativeThreadOperation.RUN_MUSE_THREAD: NativeThreadResultRecord.NATIVE_THREAD_RESULT,
        NativeThreadOperation.CONTINUE_MUSE_THREAD: NativeThreadResultRecord.NATIVE_THREAD_RESULT,
        NativeThreadOperation.FORK_MUSE_THREAD: NativeThreadResultRecord.NATIVE_THREAD_RESULT,
        NativeThreadOperation.RUN_GROK_WITH_BROWSER: NativeThreadResultRecord.BROWSER_THREAD_RESULT,
        NativeThreadOperation.CONTINUE_GROK_WITH_BROWSER: NativeThreadResultRecord.BROWSER_THREAD_RESULT,
        NativeThreadOperation.FORK_GROK_WITH_BROWSER: NativeThreadResultRecord.BROWSER_THREAD_RESULT,
        NativeThreadOperation.RUN_OPENCODE_WITH_BROWSER: NativeThreadResultRecord.BROWSER_THREAD_RESULT,
        NativeThreadOperation.CONTINUE_OPENCODE_WITH_BROWSER: NativeThreadResultRecord.BROWSER_THREAD_RESULT,
        NativeThreadOperation.FORK_OPENCODE_WITH_BROWSER: NativeThreadResultRecord.BROWSER_THREAD_RESULT,
        NativeThreadOperation.RUN_MUSE_WITH_BROWSER: NativeThreadResultRecord.BROWSER_THREAD_RESULT,
        NativeThreadOperation.CONTINUE_MUSE_WITH_BROWSER: NativeThreadResultRecord.BROWSER_THREAD_RESULT,
        NativeThreadOperation.FORK_MUSE_WITH_BROWSER: NativeThreadResultRecord.BROWSER_THREAD_RESULT,
    }
)

# One likely cause per failure code, written for that code.
NATIVE_THREAD_LIKELY_CAUSES: MappingProxyType[FailureCode, str] = MappingProxyType(
    {
        FailureCode.GROK_NOT_INSTALLED: "Grok Build is not on PATH and has no ~/.grok/bin install, or the grok_command you passed names a file that does not exist.",
        FailureCode.GROK_LAUNCHER_REFUSED: "The grok found first is a Windows .cmd or .bat shim, such as the npm grok.cmd, and cmd.exe would re-read the prompt as a command line.",
        FailureCode.GROK_LAUNCH_FAILED: "The operating system refused to start grok, or the SDK could not create the private Grok home under ~/.vidbyte/grok-homes; concurrent Grok calls in one workspace with different skill sets can also collide while its skills folder is rebuilt.",
        FailureCode.GROK_KEY_REJECTED: "xAI rejected the API key passed as api_key because it is wrong, revoked or lacks access, and the SDK never falls back to a stored grok login.",
        FailureCode.GROK_THREAD_NOT_FOUND: "Grok answered on a different session than the thread_id you passed, so the requested thread was not continued.",
        FailureCode.GROK_TIMED_OUT: "The Grok run needed more than timeout_seconds, often because it waited for an approval that a headless run cannot give, or because the task is large.",
        FailureCode.GROK_OUTPUT_TOO_LARGE: "Grok printed more than GROK_CLI_MAX_OUTPUT_BYTES on a plain call, or more than NATIVE_PROCESS_MAX_OUTPUT_BYTES on a call with browser tools, so its answer could not be read whole.",
        FailureCode.GROK_PROTOCOL_MISMATCH: "The grok CLI printed output this SDK cannot read, or a fork returned its source thread; the installed Grok Build may differ from the release this SDK was checked against.",
        FailureCode.GROK_RUN_FAILED: "Grok Build reported a failure of its own, such as an unknown thread id, a model or API error, or a refused action.",
        FailureCode.OPENCODE_NOT_INSTALLED: "opencode is not on PATH, or the opencode_command you passed names a file that does not exist.",
        FailureCode.OPENCODE_LAUNCHER_REFUSED: "The opencode found first is a Windows .cmd or .bat shim, such as the npm opencode.cmd, and cmd.exe would re-read its arguments as a command line.",
        FailureCode.OPENCODE_LAUNCH_FAILED: "The operating system refused to start opencode, for example because the file lacks execute permission or is not a program.",
        FailureCode.OPENCODE_KEY_REJECTED: "The provider named in model rejected the API key passed as api_key (opencode reported ProviderAuthError or status 401 or 403); the key may be wrong, revoked or meant for another provider.",
        FailureCode.OPENCODE_THREAD_NOT_FOUND: "opencode has no session with that id in its store for this user, or it answered on another session.",
        FailureCode.OPENCODE_TIMED_OUT: "The opencode run needed more than timeout_seconds, often because the task is large or a tool waited on a permission prompt.",
        FailureCode.OPENCODE_OUTPUT_TOO_LARGE: "opencode printed more than NATIVE_PROCESS_MAX_OUTPUT_BYTES of events, so the stream could not be read whole.",
        FailureCode.OPENCODE_PROTOCOL_MISMATCH: "opencode printed no readable JSON events or no sessionID, or a fork returned its source session; the installed opencode may differ from the release this SDK was checked against.",
        FailureCode.OPENCODE_RUN_FAILED: "opencode or its provider reported a failure, such as an unknown provider or model, a rate limit or a provider error.",
        FailureCode.MUSE_NOT_INSTALLED: "Muse Code is not where the SDK looked: not on PATH, not at muse_path inside the WSL distro, or not at the muse_command you passed.",
        FailureCode.MUSE_LAUNCHER_REFUSED: "The muse_command you passed is a Windows .cmd or .bat file, and cmd.exe would re-read the prompt as a command line.",
        FailureCode.MUSE_LAUNCH_FAILED: "The operating system refused to start muse, or the SDK could not create the private Muse config folder in the temp folder.",
        FailureCode.MUSE_KEY_REJECTED: "Meta rejected the API key passed as api_key (Muse printed authentication failed), and the SDK never falls back to a saved Muse login.",
        FailureCode.MUSE_THREAD_NOT_FOUND: "Muse has no session with that id (muse serve answered not found), or muse exec answered on another session.",
        FailureCode.MUSE_TIMED_OUT: "The Muse run needed more than timeout_seconds, or muse serve did not answer within NATIVE_CONTROL_TIMEOUT_SECONDS; a slow WSL start-up adds to both.",
        FailureCode.MUSE_OUTPUT_TOO_LARGE: "Muse printed more than NATIVE_PROCESS_MAX_OUTPUT_BYTES of JSON records, so the stream could not be read whole.",
        FailureCode.MUSE_PROTOCOL_MISMATCH: "muse printed no terminal record or no session stream, or muse serve answered a fork with its source id; the installed Muse Code may differ from the release this SDK was checked against.",
        FailureCode.MUSE_RUN_FAILED: "Muse Code reported a failure of its own: a terminal state other than completed, a muse serve error, or a non-zero exit.",
        FailureCode.MUSE_WSL_UNAVAILABLE: "On Windows Muse Code runs only inside WSL, and WSL is missing, the named distro does not exist, or neither wsl_distro nor muse_command was set.",
        FailureCode.CONFIGURATION_INVALID_ARGUMENT: "An argument failed its check before anything started; the message names the argument and the rule it broke.",
        FailureCode.RUNTIME_ERROR: "An unexpected exception inside the SDK, which is a defect in the SDK rather than a vendor failure.",
        FailureCode.BROWSER_MOUNT_UNSUPPORTED: "The selected tools ask for something this harness cannot carry safely: a keyed remote tool on Grok, a keyed or narrowed tool on Muse, a local tool on Muse in WSL mode, or more Grok allow and deny rules than fit on its command line.",
        FailureCode.BROWSER_RUNTIME_MISSING: "Node 22.12.0 or later is not on PATH, the node found first is a Windows batch file, or a selected tool that drives Chrome found no Chrome stable install.",
        FailureCode.BROWSER_TOOL_INSTALL_FAILED: "npm could not install a pinned tool package: the registry was unreachable, the install timed out, the npm that ships with Node is missing, the user home is unknown, or an earlier install left a broken folder.",
        FailureCode.BROWSER_TOOLS_UNAVAILABLE: "A mounted tool server did not start or connect in time, or the agent used none of the mounted tools; opencode prints no per-server status, so there the two cannot be told apart.",
    }
)

# One next step per failure code, written for that code.
NATIVE_THREAD_NEXT_STEPS: MappingProxyType[FailureCode, str] = MappingProxyType(
    {
        FailureCode.GROK_NOT_INSTALLED: "Install Grok Build, or pass the full path of its executable in GrokThreadConfig(grok_command=(...,)).",
        FailureCode.GROK_LAUNCHER_REFUSED: "Pass the real grok.exe in GrokThreadConfig(grok_command=(...,)), or install Grok Build's own binary under ~/.grok/bin.",
        FailureCode.GROK_LAUNCH_FAILED: "Check that grok runs from a terminal and that ~/.vidbyte/grok-homes is a writable folder, then retry; run concurrent Grok calls in one workspace only with a skill set an earlier call already prepared.",
        FailureCode.GROK_KEY_REJECTED: "Pass a valid xAI API key as api_key and retry.",
        FailureCode.GROK_THREAD_NOT_FOUND: "Continue a Grok thread only from the workspace that created it, with the thread_id that run_grok_thread, fork_grok_thread, run_grok_with_browser or fork_grok_with_browser returned.",
        FailureCode.GROK_TIMED_OUT: "Raise GrokThreadConfig.timeout_seconds, narrow the prompt, or choose a permission_mode that lets the run proceed; continue the thread to finish a partial turn.",
        FailureCode.GROK_OUTPUT_TOO_LARGE: "Ask Grok for a shorter answer, for example by having it write long results to a file in the workspace.",
        FailureCode.GROK_PROTOCOL_MISMATCH: "Run grok --version and install the Grok Build release named in this message, then retry.",
        FailureCode.GROK_RUN_FAILED: "Read the vendor text in this message; a Grok thread can be continued only from the workspace that created it, and API errors usually clear on retry.",
        FailureCode.OPENCODE_NOT_INSTALLED: "Install opencode, or pass the full path of its executable in OpencodeThreadConfig(opencode_command=(...,)).",
        FailureCode.OPENCODE_LAUNCHER_REFUSED: "Pass the opencode executable itself (opencode.exe) in OpencodeThreadConfig(opencode_command=(...,)).",
        FailureCode.OPENCODE_LAUNCH_FAILED: "Check that opencode runs from a terminal as the same user, then retry.",
        FailureCode.OPENCODE_KEY_REJECTED: "Pass a valid API key for the provider before the slash in model, for example a DeepSeek key for deepseek/deepseek-v4-pro, and retry.",
        FailureCode.OPENCODE_THREAD_NOT_FOUND: "Pass a thread_id that run_opencode_thread, fork_opencode_thread, run_opencode_with_browser or fork_opencode_with_browser returned for this user and machine.",
        FailureCode.OPENCODE_TIMED_OUT: "Raise OpencodeThreadConfig.timeout_seconds or narrow the prompt; continue the session to finish a partial turn.",
        FailureCode.OPENCODE_OUTPUT_TOO_LARGE: "Ask for a shorter answer, or split the task across several continue_opencode_thread or continue_opencode_with_browser calls.",
        FailureCode.OPENCODE_PROTOCOL_MISMATCH: "Run opencode --version and install the opencode release named in this message, then retry.",
        FailureCode.OPENCODE_RUN_FAILED: "Read the vendor text in this message, check that model names a provider and model that opencode knows, and retry.",
        FailureCode.MUSE_NOT_INSTALLED: "Install Muse Code, set MuseThreadConfig.muse_path to its path inside the distro, or pass its full path as muse_command.",
        FailureCode.MUSE_LAUNCHER_REFUSED: "Run Muse through WSL with MuseThreadConfig(wsl_distro=...), or pass a real executable as muse_command.",
        FailureCode.MUSE_LAUNCH_FAILED: "Check that muse runs from a terminal and that the system temp folder is writable, then retry.",
        FailureCode.MUSE_KEY_REJECTED: "Pass a valid Meta API key as api_key and retry.",
        FailureCode.MUSE_THREAD_NOT_FOUND: "Pass a thread_id that run_muse_thread, fork_muse_thread, run_muse_with_browser or fork_muse_with_browser returned for this user and machine.",
        FailureCode.MUSE_TIMED_OUT: "Raise MuseThreadConfig.timeout_seconds or narrow the prompt; in WSL mode check that the distro starts quickly from a terminal.",
        FailureCode.MUSE_OUTPUT_TOO_LARGE: "Ask for a shorter answer, or split the task across several continue_muse_thread or continue_muse_with_browser calls.",
        FailureCode.MUSE_PROTOCOL_MISMATCH: "Run muse --version and install the Muse Code release named in this message, then retry.",
        FailureCode.MUSE_RUN_FAILED: "Read the vendor text in this message; a muse serve error usually clears once no other client holds the session.",
        FailureCode.MUSE_WSL_UNAVAILABLE: "Install WSL and a distro that holds Muse Code, then pass MuseThreadConfig(wsl_distro=...) with a name that wsl.exe -l -q lists.",
        FailureCode.CONFIGURATION_INVALID_ARGUMENT: "Fix the argument named in this message and call again; nothing ran and nothing was written.",
        FailureCode.RUNTIME_ERROR: "Report the defect with the exception class named in this message; a retry may succeed if the cause was transient.",
        FailureCode.BROWSER_MOUNT_UNSUPPORTED: "Choose tools this harness can mount, as the observation in this message describes, or run the same tools on a harness that can mount them.",
        FailureCode.BROWSER_RUNTIME_MISSING: "Install Node 22.12.0 or later as a real node executable on PATH, and Google Chrome stable for playwright or chromedevtools, then call again.",
        FailureCode.BROWSER_TOOL_INSTALL_FAILED: "Check network access to registry.npmjs.org and that the user home is writable, delete any broken folder this message names under ~/.vidbyte/tools, then call again.",
        FailureCode.BROWSER_TOOLS_UNAVAILABLE: "Read the servers and the vendor text this message names, check each tool's key, and continue the thread with the same tools to try again.",
    }
)
