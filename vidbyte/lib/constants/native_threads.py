"""FILE: vidbyte/lib/constants/native_threads.py

PURPOSE: Holds every fixed value and text of the harness thread functions, the thread helpers, the command and skill functions and the canonical process helpers: time, size and count bounds, record patterns, program names, subcommand words, folder names, option values, JSON member names, vendor markers, evidence tool names and fragments, prompt templates, the per-operation argument tables, tested vendor versions, and the error texts (harness labels, summary and observation templates, detail sentences, the failure code of each harness and problem, and one likely cause and one next step per failure code).
ROLE IN CODEBASE: Imported by the records in vidbyte/lib/dataclasses/native_threads.py (NativeThreadRequest, NativeHelperRequest, GrokCommandArguments and the rest), process.py and validation.py, by CliRunner in vidbyte/lib/process/runner.py, and by every module under vidbyte/harnesses/native/.
ARCHITECTURE NOTE: The harness modules hold no literals of their own (spec INV-15): every flag is an enum member in vidbyte/lib/enums/native_threads.py, and every other value they need lives here, so a reviewer finds each vendor fact in one place. The timing knobs NATIVE_KILL_WAIT_SECONDS, MUSE_REAP_TIMEOUT_SECONDS and NATIVE_CONTROL_TIMEOUT_SECONDS are read through this module object at call time, never bound by a from-import, so one patch reaches every user.
FUNCTION INVENTORY: No functions. Constants grouped as contract bounds, helper and command bounds, record patterns, process helper values, programs and folders, helper subcommands and store names, option values and separators, JSON member names, vendor markers, evidence and templates, the operation tables, tested versions, then the error texts and detail sentences.
COMMON MODIFICATION PATTERNS: A value a harness module needs is added here under its feature prefix and used by name (lint A007, spec INV-15). A new failure code adds its pair to NATIVE_THREAD_FAILURE_CODES and its own texts to NATIVE_THREAD_LIKELY_CAUSES and NATIVE_THREAD_NEXT_STEPS. A new helper or command operation joins the operation tables (NATIVE_HELPER_OPERATIONS and the rest) that decide which arguments it takes; a new Grok command adds its evidence rows to GROK_EVIDENCE_TOOLS and GROK_EVIDENCE_FRAGMENTS.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte above vidbyte.lib.enums. 2. Do not name a constant with a password, token or secret word and give it a string (lint S054). 3. Do not add a carriage return to MUSE_REAP_SCRIPT; sh in the distro reads it from stdin. 4. Do not share one likely cause or next step between two codes of a harness; each code gets text written for it.
KNOWN EDGE CASES: Patterns are applied with re.fullmatch, so each one describes the whole value. The texts must not contain a credential word followed by ":" or "=", because HarnessRedactor would rewrite such a phrase in vendor text. MUSE_REAP_SCRIPT runs with the caller's environment, which lacks the peer mark, so it never matches itself. The evidence fragments use forward slashes because evidence text is matched after every run of backslashes is folded to one slash. OPENCODE_COMMAND_NOT_FOUND_TEXT is a prefix: opencode appends the list of commands it has. OPENCODE_SESSION_QUERY may only ever be filled with a thread id that passed NATIVE_THREAD_ID_PATTERN.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_surface.py, tests/features/harness_threads/test_harness_threads_errors.py
"""

from __future__ import annotations

from datetime import timedelta
from types import MappingProxyType

from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.native_threads import (
    GrokCommand,
    GrokCommandFlag,
    NativeEnvironmentVariable,
    NativeHarness,
    NativeThreadOperation,
    NativeThreadProblem,
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

# Thread helper and command bounds (helpers spec §9.3).
NATIVE_LIST_DEFAULT_LIMIT = 20
NATIVE_RECENT_DEFAULT_LIMIT = 10
NATIVE_LIST_MIN_LIMIT = 1
NATIVE_LIST_MAX_LIMIT = 200
NATIVE_SINCE_MAX = timedelta(days=3650)
NATIVE_QUERY_MAX_CHARS = 1000
NATIVE_TITLE_MAX_CHARS = 4096
NATIVE_TOOL_NAME_MAX_CHARS = 256
NATIVE_COMMAND_MAX_CHARS = 128
NATIVE_LINEAGE_MAX_DEPTH = 64
# Room the built prompt keeps for the slash line and its options, so a
# command text at its cap still fits the argv prompt caps (D-25).
NATIVE_COMMAND_RESERVED_CHARS = 1024
NATIVE_COMMAND_TEXT_MAX_CHARS = NATIVE_ARGV_PROMPT_MAX_CHARS - NATIVE_COMMAND_RESERVED_CHARS
NATIVE_WINDOWS_COMMAND_TEXT_MAX_UNITS = NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS - NATIVE_COMMAND_RESERVED_CHARS
# opencode session list stops at 100 rows unless asked for more; a
# list of exactly this many may be cut (D-19, EC-75).
NATIVE_OPENCODE_SCAN_MAX = 10000
# The latest epoch millisecond a datetime holds (9999-12-31T23:59:59.999Z).
NATIVE_EPOCH_MS_MIN = 0
NATIVE_EPOCH_MS_MAX = 253402300799999
OPENCODE_MILLISECONDS_PER_SECOND = 1000
GROK_SUMMARY_MAX_BYTES = 1048576
GROK_CWD_MAX_BYTES = 65536
# A store whose session folders all lack summary.json is a renamed
# layout once its newest folder is older than this (D-31, EC-67).
GROK_SUMMARY_GRACE_SECONDS = 60
GROK_COMMAND_MIN_VALUE = 1
GROK_GOAL_MAX_BUDGET_TOKENS = 100000000
GROK_IMPLEMENT_MAX_EFFORT = 5
GROK_EXECUTE_PLAN_MAX_EFFORT = 2
GROK_EXECUTE_PLAN_MAX_CONCURRENCY = 8
GROK_BRANCH_MAX_CHARS = 255
GROK_PR_MAX_CHARS = 2048
GROK_PR_MAX_NUMBER = 999999999

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
# Command and skill names, Grok branch names and pull requests, and the
# text of a command (which may be empty for some commands).
NATIVE_COMMAND_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/:-]*$"
NATIVE_COMMAND_TEXT_PATTERN = r"[^\x00]*"
GROK_BRANCH_PATTERN = r"^[^\s\x00-][^\s\x00]*$"
GROK_PR_PATTERN = r"^([1-9][0-9]*|https://\S+)$"
# Evidence text is matched after each run of backslashes becomes "/",
# so a Windows path matches the forward-slash fragments.
NATIVE_BACKSLASH_RUN_PATTERN = r"\\+"
NATIVE_FORWARD_SLASH = "/"

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
NATIVE_SKILL_FILE_NAME = "SKILL.md"
MUSE_WSL_MOUNT_ROOT = "/mnt"
MUSE_WINDOWS_DRIVE_PATTERN = r"[A-Za-z]:"
NATIVE_WINDOWS_ROOT = "\\"

# Thread helper subcommands and the Grok store layout
# (<home>/sessions/<url-encoded cwd>/<id>/summary.json, beside
# <group>/.cwd).
GROK_EXPORT_COMMAND = "export"
GROK_SESSIONS_COMMAND = "sessions"
GROK_DELETE_COMMAND = "delete"
OPENCODE_SESSION_COMMAND = "session"
OPENCODE_LIST_COMMAND = "list"
OPENCODE_DELETE_COMMAND = "delete"
OPENCODE_EXPORT_COMMAND = "export"
OPENCODE_DB_COMMAND = "db"
OPENCODE_REVIEW_COMMAND = "review"
OPENCODE_INIT_COMMAND = "init"
OPENCODE_PLAN_AGENT = "plan"
MUSE_EXPORT_COMMAND = "export"
MUSE_INIT_COMMAND = "init"
GROK_SESSIONS_DIR = "sessions"
GROK_SUMMARY_FILE = "summary.json"
GROK_CWD_FILE = ".cwd"
GROK_USER_HOME_PARTS = (".grok",)
MUSE_EXPORT_PARTS = ("export", "thread.json")

# Fixed option values and separators.
GROK_JSON_OUTPUT_FORMAT = "json"
OPENCODE_JSON_FORMAT = "json"
NATIVE_ENABLED_SWITCH = "1"
NATIVE_WSLENV_SEPARATOR = ":"
NATIVE_WSLENV_UNIX_FLAG = "/u"
NATIVE_PROCESS_OPTION_SEPARATOR = "="
NATIVE_LINE_SEPARATOR = "\n"
NATIVE_SENTENCE_SEPARATOR = " "
NATIVE_LISTING_SEPARATOR = ", "
OPENCODE_MODEL_PROVIDER_SEPARATOR = "/"
NATIVE_NUL_CHARACTER = "\x00"
GROK_STREAMING_OUTPUT_FORMAT = "streaming-json"
# GROK_WORKFLOWS=0 runs /goal in-turn with the update_goal driver
# instead of the background engine; only goal runs set it.
GROK_WORKFLOWS_OFF = "0"
NATIVE_COMMAND_PART_SEPARATOR = " "

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
# Grok summary.json members (§9.1) and streaming-json event members.
GROK_CREATED_AT_FIELD = "created_at"
GROK_UPDATED_AT_FIELD = "updated_at"
GROK_TITLE_FIELD = "generated_title"
GROK_SESSION_SUMMARY_FIELD = "session_summary"
GROK_LAST_TURN_SUMMARY_FIELD = "last_turn_summary"
GROK_PARENT_FIELD = "parent_session_id"
GROK_MODEL_FIELD = "current_model_id"
GROK_AGENT_NAME_FIELD = "agent_name"
GROK_DATA_FIELD = "data"
GROK_TOOL_NAME_FIELD = "toolName"
GROK_RAW_INPUT_FIELD = "rawInput"
GROK_END_MEMBER = "end"
# opencode session list rows and the OPENCODE_SESSION_QUERY columns.
OPENCODE_ID_FIELD = "id"
OPENCODE_TITLE_FIELD = "title"
OPENCODE_CREATED_FIELD = "created"
OPENCODE_UPDATED_FIELD = "updated"
OPENCODE_DIRECTORY_FIELD = "directory"
OPENCODE_TIME_CREATED_COLUMN = "time_created"
OPENCODE_TIME_UPDATED_COLUMN = "time_updated"
OPENCODE_PARENT_COLUMN = "parent_id"
# Muse MSP session/list and session/read members and history modes.
MUSE_WORKSPACE_ROOT_FIELD = "workspaceRoot"
MUSE_LIMIT_FIELD = "limit"
MUSE_UPDATED_AFTER_FIELD = "updatedAfter"
MUSE_SESSIONS_FIELD = "sessions"
MUSE_CREATED_AT_FIELD = "createdAt"
MUSE_UPDATED_AT_FIELD = "updatedAt"
MUSE_FORKED_FROM_FIELD = "forkedFrom"
MUSE_MODEL_ID_FIELD = "modelId"
MUSE_HISTORY_FIELD = "history"
MUSE_HISTORY_MODE_FIELD = "mode"
MUSE_ITEMS_FIELD = "items"
MUSE_SNAPSHOT_FIELD = "snapshot"
MUSE_STATE_FIELD = "state"
MUSE_NONE_REASON_FIELD = "noneReason"
MUSE_ITEM_KIND_FIELD = "kind"
MUSE_TOOL_FIELD = "tool"
MUSE_ARGS_FIELD = "args"
MUSE_TOOL_CALL_KIND = "toolCall"
MUSE_HISTORY_INLINE = "inline"
MUSE_HISTORY_SNAPSHOT = "snapshot"
MUSE_HISTORY_ANCHORED = "anchoredSnapshot"
MUSE_HISTORY_NONE = "none"
# The record fields a reader names, as the vendor spells them, when a
# NativeThreadSummary refuses one (INV-6).
GROK_SUMMARY_MEMBERS: MappingProxyType[str, str] = MappingProxyType(
    {
        "thread_id": "session folder name",
        "title": GROK_TITLE_FIELD,
        "created_at": GROK_CREATED_AT_FIELD,
        "updated_at": GROK_UPDATED_AT_FIELD,
        "parent_thread_id": GROK_PARENT_FIELD,
        "model": GROK_MODEL_FIELD,
        "search_text": GROK_SESSION_SUMMARY_FIELD,
        "agent_name": GROK_AGENT_NAME_FIELD,
    }
)
OPENCODE_LIST_MEMBERS: MappingProxyType[str, str] = MappingProxyType(
    {
        "thread_id": OPENCODE_ID_FIELD,
        "title": OPENCODE_TITLE_FIELD,
        "created_at": OPENCODE_CREATED_FIELD,
        "updated_at": OPENCODE_UPDATED_FIELD,
    }
)
OPENCODE_ROW_MEMBERS: MappingProxyType[str, str] = MappingProxyType(
    {
        "thread_id": OPENCODE_ID_FIELD,
        "title": OPENCODE_TITLE_FIELD,
        "created_at": OPENCODE_TIME_CREATED_COLUMN,
        "updated_at": OPENCODE_TIME_UPDATED_COLUMN,
        "parent_thread_id": OPENCODE_PARENT_COLUMN,
    }
)
MUSE_SESSION_MEMBERS: MappingProxyType[str, str] = MappingProxyType(
    {
        "thread_id": MUSE_SESSION_ID_FIELD,
        "created_at": MUSE_CREATED_AT_FIELD,
        "updated_at": MUSE_UPDATED_AT_FIELD,
        "parent_thread_id": MUSE_FORKED_FROM_FIELD,
        "model": MUSE_MODEL_ID_FIELD,
    }
)

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
GROK_SESSION_NOT_FOUND_TEXT = "Session '{thread_id}' not found."
OPENCODE_COMMAND_NOT_FOUND_TEXT = 'Command not found: "{command}"'
MUSE_METHOD_NOT_FOUND_CODE = -32601
# The one opencode db query; its only variable is a thread id that
# passed NATIVE_THREAD_ID_PATTERN (D-26, T-9).
OPENCODE_SESSION_QUERY = "SELECT id, title, time_created, time_updated, parent_id, directory FROM session WHERE id = '{thread_id}'"

# Command and skill evidence (§9.2, INV-8): the tool a run must call and
# the text its arguments must hold, matched after backslash folding.
GROK_UPDATE_GOAL_TOOL = "update_goal"
GROK_READ_FILE_TOOL = "read_file"
GROK_IMAGE_TOOLS = ("image_gen", "image_edit")
GROK_IMAGE_TO_VIDEO_TOOL = "image_to_video"
GROK_IMPLEMENTER_PERSONA = "shared/personas/implementer.md"
GROK_DESIGN_PERSONA = "shared/personas/design-doc-writer.md"
GROK_REVIEWER_PERSONA = "shared/personas/reviewer.md"
GROK_RESUME_CORE = "shared/resume-session/CORE.md"
# A sentence of the code-review skill's Core Prompt; only the expanded
# skill puts it in the run's own export (D-28).
GROK_CODE_REVIEW_FRAGMENT = "deep code quality audit of the current branch's changes"
MUSE_READ_SKILL_TOOL = "read_skill"
MUSE_CREATE_GOAL_TOOL = "create_goal"
GROK_EVIDENCE_TOOLS: MappingProxyType[GrokCommand, tuple[str, ...]] = MappingProxyType(
    {
        GrokCommand.GOAL: (GROK_UPDATE_GOAL_TOOL,),
        GrokCommand.IMPLEMENT: (GROK_READ_FILE_TOOL,),
        GrokCommand.DESIGN: (GROK_READ_FILE_TOOL,),
        GrokCommand.EXECUTE_PLAN: (GROK_READ_FILE_TOOL,),
        GrokCommand.REVIEW: (GROK_READ_FILE_TOOL,),
        GrokCommand.RESUME_CLAUDE: (GROK_READ_FILE_TOOL,),
        GrokCommand.RESUME_CODEX: (GROK_READ_FILE_TOOL,),
        GrokCommand.RESUME_CURSOR: (GROK_READ_FILE_TOOL,),
        GrokCommand.IMAGINE: GROK_IMAGE_TOOLS,
        GrokCommand.IMAGINE_VIDEO: (GROK_IMAGE_TO_VIDEO_TOOL,),
    }
)
GROK_EVIDENCE_FRAGMENTS: MappingProxyType[GrokCommand, str] = MappingProxyType(
    {
        GrokCommand.IMPLEMENT: GROK_IMPLEMENTER_PERSONA,
        GrokCommand.DESIGN: GROK_DESIGN_PERSONA,
        GrokCommand.EXECUTE_PLAN: GROK_IMPLEMENTER_PERSONA,
        GrokCommand.REVIEW: GROK_REVIEWER_PERSONA,
        GrokCommand.RESUME_CLAUDE: GROK_RESUME_CORE,
        GrokCommand.RESUME_CODEX: GROK_RESUME_CORE,
        GrokCommand.RESUME_CURSOR: GROK_RESUME_CORE,
    }
)
# The option flags each named Grok wrapper's text may not carry (D-30,
# R-19); a command absent here refuses none.
GROK_TEXT_OPTION_FLAGS: MappingProxyType[GrokCommand, tuple[GrokCommandFlag, ...]] = MappingProxyType(
    {
        GrokCommand.GOAL: (GrokCommandFlag.BUDGET,),
        GrokCommand.IMPLEMENT: (GrokCommandFlag.EFFORT,),
    }
)
# The /goal subcommands, refused as a whole objective (D-30).
GROK_GOAL_RESERVED_WORDS = frozenset({"status", "pause", "resume", "clear"})
GROK_SLASH_TEMPLATE = "/{command}"
GROK_FLAG_JOIN = "="
MUSE_SKILL_PROMPT_TEMPLATE = "Use the `{skill}` skill.\n\n{prompt}"
MUSE_GOAL_PROMPT_TEMPLATE = "Use the create_goal tool to set this goal, then work until it is met.\n\n{prompt}"

# The key variables no helper or evidence child may inherit (INV-2).
NATIVE_HELPER_REMOVED_VARIABLES = (
    NativeEnvironmentVariable.XAI_API_KEY.value,
    NativeEnvironmentVariable.GROK_CODE_XAI_API_KEY.value,
    NativeEnvironmentVariable.OPENCODE_CONFIG_CONTENT.value,
    NativeEnvironmentVariable.META_API_KEY.value,
)

# Which arguments each helper and command operation takes (D-1, D-25).
_Op = NativeThreadOperation
NATIVE_HELPER_OPERATIONS: MappingProxyType[NativeHarness, frozenset[NativeThreadOperation]] = MappingProxyType(
    {
        NativeHarness.GROK: frozenset(
            {
                _Op.LIST_GROK_THREADS, _Op.LIST_RECENT_GROK_THREADS, _Op.LIST_GROK_THREADS_SINCE, _Op.GET_GROK_THREAD,
                _Op.READ_GROK_THREAD, _Op.GET_GROK_THREAD_LINEAGE, _Op.SEARCH_GROK_THREADS, _Op.DELETE_GROK_THREAD,
            }
        ),
        NativeHarness.OPENCODE: frozenset(
            {
                _Op.LIST_OPENCODE_THREADS, _Op.LIST_RECENT_OPENCODE_THREADS, _Op.LIST_OPENCODE_THREADS_SINCE, _Op.GET_OPENCODE_THREAD,
                _Op.READ_OPENCODE_THREAD, _Op.GET_OPENCODE_THREAD_LINEAGE, _Op.SEARCH_OPENCODE_THREADS, _Op.DELETE_OPENCODE_THREAD,
            }
        ),
        NativeHarness.MUSE: frozenset(
            {
                _Op.LIST_MUSE_THREADS, _Op.LIST_RECENT_MUSE_THREADS, _Op.LIST_MUSE_THREADS_SINCE, _Op.GET_MUSE_THREAD,
                _Op.READ_MUSE_THREAD, _Op.GET_MUSE_THREAD_LINEAGE, _Op.INIT_MUSE_WORKSPACE,
            }
        ),
    }
)
NATIVE_THREAD_ID_OPERATIONS = frozenset(
    {
        _Op.GET_GROK_THREAD, _Op.READ_GROK_THREAD, _Op.GET_GROK_THREAD_LINEAGE, _Op.DELETE_GROK_THREAD,
        _Op.GET_OPENCODE_THREAD, _Op.READ_OPENCODE_THREAD, _Op.GET_OPENCODE_THREAD_LINEAGE, _Op.DELETE_OPENCODE_THREAD,
        _Op.GET_MUSE_THREAD, _Op.READ_MUSE_THREAD, _Op.GET_MUSE_THREAD_LINEAGE,
    }
)
NATIVE_SINCE_REQUIRED_OPERATIONS = frozenset({_Op.LIST_GROK_THREADS_SINCE, _Op.LIST_OPENCODE_THREADS_SINCE, _Op.LIST_MUSE_THREADS_SINCE})
NATIVE_SINCE_OPTIONAL_OPERATIONS = frozenset({_Op.LIST_GROK_THREADS, _Op.LIST_OPENCODE_THREADS, _Op.LIST_MUSE_THREADS})
NATIVE_LIMIT_OPERATIONS = frozenset(
    {
        _Op.LIST_GROK_THREADS, _Op.LIST_RECENT_GROK_THREADS, _Op.LIST_GROK_THREADS_SINCE, _Op.SEARCH_GROK_THREADS,
        _Op.LIST_OPENCODE_THREADS, _Op.LIST_RECENT_OPENCODE_THREADS, _Op.LIST_OPENCODE_THREADS_SINCE, _Op.SEARCH_OPENCODE_THREADS,
        _Op.LIST_MUSE_THREADS, _Op.LIST_RECENT_MUSE_THREADS, _Op.LIST_MUSE_THREADS_SINCE,
    }
)
NATIVE_QUERY_OPERATIONS = frozenset({_Op.SEARCH_GROK_THREADS, _Op.SEARCH_OPENCODE_THREADS})
# The public name of each command or skill function's text argument.
NATIVE_TEXT_ARGUMENTS: MappingProxyType[NativeThreadOperation, str] = MappingProxyType(
    {
        _Op.RUN_GROK_COMMAND: "arguments",
        _Op.RUN_GROK_GOAL: "objective",
        _Op.RUN_GROK_IMPLEMENT: "task",
        _Op.RUN_GROK_DESIGN: "description",
        _Op.RUN_GROK_RESUME_CLAUDE: "session",
        _Op.RUN_GROK_RESUME_CODEX: "session",
        _Op.RUN_GROK_RESUME_CURSOR: "session",
        _Op.RUN_GROK_IMAGINE: "description",
        _Op.RUN_GROK_IMAGINE_VIDEO: "description",
        _Op.RUN_GROK_PLAN: "task",
        _Op.RUN_GROK_EXPLORE: "question",
        _Op.RUN_OPENCODE_COMMAND: "arguments",
        _Op.RUN_OPENCODE_REVIEW: "target",
        _Op.RUN_OPENCODE_PLAN: "task",
        _Op.RUN_MUSE_SKILL: "prompt",
        _Op.RUN_MUSE_GOAL: "objective",
        _Op.RUN_MUSE_PLAN: "task",
        _Op.RUN_MUSE_IMPORT: "session_ref",
        _Op.RUN_MUSE_SCAFFOLD: "description",
        _Op.RUN_MUSE_BROWSER_APP: "description",
    }
)
# The text arguments that may be empty: raw command arguments and an
# optional review target.
NATIVE_BLANK_TEXT_OPERATIONS = frozenset({_Op.RUN_GROK_COMMAND, _Op.RUN_OPENCODE_COMMAND, _Op.RUN_OPENCODE_REVIEW})
# The public name of NativeThreadRequest.command per harness.
NATIVE_COMMAND_ARGUMENTS: MappingProxyType[NativeHarness, str] = MappingProxyType(
    {
        NativeHarness.OPENCODE: "command",
        NativeHarness.MUSE: "skill",
    }
)
del _Op

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
        NativeThreadProblem.COMMAND_NOT_RUN: "{harness} did not run the requested command or skill.",
        NativeThreadProblem.STORE_UNREADABLE: "{harness} keeps a thread store that the SDK could not read.",
    }
)
NATIVE_THREAD_OBSERVATIONS: MappingProxyType[NativeThreadProblem, str] = MappingProxyType(
    {
        NativeThreadProblem.NOT_INSTALLED: "No launcher that the SDK could start was found.",
        NativeThreadProblem.LAUNCHER_REFUSED: "cmd.exe would re-read the arguments of a batch file as a command line, so the SDK never starts one.",
        NativeThreadProblem.LAUNCH_FAILED: "The SDK could not start the program or prepare its private folder.",
        NativeThreadProblem.KEY_REJECTED: "The vendor refused the key passed as api_key, and the SDK never falls back to a stored login.",
        NativeThreadProblem.THREAD_NOT_FOUND: "The vendor has no thread with the requested id, could not continue it, or answered on another one.",
        NativeThreadProblem.TIMED_OUT: "The SDK waited {seconds} seconds and then stopped the whole process tree, so the thread may hold a partial turn.",
        NativeThreadProblem.OUTPUT_TOO_LARGE: "Standard output passed the cap of {cap_bytes} bytes, so the SDK did not read it as an answer.",
        NativeThreadProblem.PROTOCOL_MISMATCH: "The output did not match what this SDK expects from {harness} {version}.",
        NativeThreadProblem.RUN_FAILED: "The vendor reported a failure of its own.",
        NativeThreadProblem.WSL_UNAVAILABLE: "Muse Code runs on Windows only inside a WSL distro.",
        NativeThreadProblem.COMMAND_NOT_RUN: "The SDK looked for the evidence of the command in the run's own record and did not find it.",
        NativeThreadProblem.STORE_UNREADABLE: "The SDK reads the Grok store files itself, and a read failed.",
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
# Detail sentences of the thread helpers and the command and skill
# functions, handed to the error factory as `searched`.
GROK_STORE_HOME_UNKNOWN_DETAIL = "The user home folder, under which the Grok store lives, could not be determined ({error_type})."
GROK_STORE_PATH_DETAIL = "Reading {path} raised {error_type}."
GROK_SUMMARY_MEMBER_DETAIL = "The {member} of {path} is missing or unusable."
GROK_SUMMARY_SHAPE_DETAIL = "The file {path} does not hold one JSON object in UTF-8."
GROK_SUMMARY_OVERSIZE_DETAIL = "The file {path} holds {size} bytes, more than GROK_SUMMARY_MAX_BYTES ({cap} bytes)."
GROK_STORE_LAYOUT_DETAIL = "No session folder under {home} holds a summary.json in the layout sessions/<group>/<id>/summary.json that this SDK reads, and the newest folder is older than {seconds} seconds."
GROK_SCOPE_SEARCHED_DETAIL = "The SDK searched the {scope} scope, whose Grok store is {home}."
GROK_DELETE_LEFT_DETAIL = "grok sessions delete exited 0, but the session folder {folder} still exists."
GROK_SESSION_ID_MISMATCH_DETAIL = "The end event names the sessionId {answered} instead of the requested {requested}."
GROK_THREAD_MAY_NOT_EXIST_DETAIL = "The run failed before Grok reported the session, so the thread may not exist."
NATIVE_EVIDENCE_TOOLS_DETAIL = "The run made no call to {tools}, the evidence that the command ran; it called {seen}."
NATIVE_EVIDENCE_FRAGMENT_DETAIL = "The run made no call to {tools} whose arguments name {fragment}, the evidence that the command ran; it called {seen}."
NATIVE_NO_TOOLS_SEEN = "no tools"
NATIVE_EVIDENCE_VALUE_DETAIL = "The run's record holds {actual} as its {member}, but the evidence that the command ran is {expected}."
NATIVE_EVIDENCE_NO_VALUE_DETAIL = "The run's record holds no {member}, but the evidence that the command ran is the {member} {expected}."
NATIVE_EVIDENCE_TEXT_DETAIL = "The run's transcript does not contain {fragment}, the evidence that the command ran."
NATIVE_LINEAGE_CYCLE_DETAIL = "The thread {thread_id} appears twice among the parents, so the parent links form a cycle."
NATIVE_LINEAGE_DEPTH_DETAIL = "The chain of parents is longer than NATIVE_LINEAGE_MAX_DEPTH ({depth}) threads."
OPENCODE_SCAN_CAP_DETAIL = "opencode session list returned NATIVE_OPENCODE_SCAN_MAX ({cap}) root sessions, the most the SDK asks for, so the list may be cut."
OPENCODE_SHAPE_DETAIL = "opencode printed output that is not a JSON array of objects."
OPENCODE_MEMBER_DETAIL = "The member {member} of an opencode session row is missing or unusable."
OPENCODE_ROWS_DETAIL = "opencode db returned {count} rows for one exact session id."
MUSE_METHOD_NOT_FOUND_DETAIL = "muse serve does not know the method {method}."
MUSE_MEMBER_DETAIL = "The member {member} of a Muse session is missing or unusable."
MUSE_HISTORY_NONE_DETAIL = "Muse returned the thread's history without items (mode none, noneReason {reason})."
MUSE_EXPORT_FILE_MISSING_DETAIL = "muse export exited 0 but wrote no file at {path}."
# Refusal rules of the command records, named in invalid_argument.
GROK_TEXT_FLAG_RULE = "{field} may not hold the token {flag}, which the slash command would read as its own option."
GROK_GOAL_RESERVED_RULE = "{field} may not be the /goal subcommand {word}."
GROK_DESIGN_DOC_SPACE_RULE = "design_doc may not contain whitespace, because the slash command splits its arguments at whitespace."

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
        (NativeHarness.GROK, NativeThreadProblem.COMMAND_NOT_RUN): FailureCode.GROK_COMMAND_NOT_RUN,
        (NativeHarness.OPENCODE, NativeThreadProblem.COMMAND_NOT_RUN): FailureCode.OPENCODE_COMMAND_NOT_RUN,
        (NativeHarness.MUSE, NativeThreadProblem.COMMAND_NOT_RUN): FailureCode.MUSE_COMMAND_NOT_RUN,
        (NativeHarness.GROK, NativeThreadProblem.STORE_UNREADABLE): FailureCode.GROK_STORE_UNREADABLE,
    }
)

# One likely cause per failure code, written for that code.
NATIVE_THREAD_LIKELY_CAUSES: MappingProxyType[FailureCode, str] = MappingProxyType(
    {
        FailureCode.GROK_NOT_INSTALLED: "Grok Build is not on PATH and has no ~/.grok/bin install, or the grok_command you passed names a file that does not exist.",
        FailureCode.GROK_LAUNCHER_REFUSED: "The grok found first is a Windows .cmd or .bat shim, such as the npm grok.cmd, and cmd.exe would re-read the prompt as a command line.",
        FailureCode.GROK_LAUNCH_FAILED: "The operating system refused to start grok, or the SDK could not create the private Grok home under ~/.vidbyte/grok-homes; concurrent Grok calls in one workspace with different skill sets can also collide while its skills folder is rebuilt.",
        FailureCode.GROK_KEY_REJECTED: "xAI rejected the API key passed as api_key because it is wrong, revoked or lacks access, and the SDK never falls back to a stored grok login.",
        FailureCode.GROK_THREAD_NOT_FOUND: "Grok has no session with that id in the store the call searched, or it answered on a different session than the thread_id you passed, so the requested thread was not continued.",
        FailureCode.GROK_TIMED_OUT: "The Grok run needed more than timeout_seconds, often because it waited for an approval that a headless run cannot give, or because the task is large; a thread helper's grok child (export or sessions delete) has the fixed NATIVE_CONTROL_TIMEOUT_SECONDS instead, which config does not change.",
        FailureCode.GROK_OUTPUT_TOO_LARGE: "Grok printed more than GROK_CLI_MAX_OUTPUT_BYTES for run_grok_thread, continue_grok_thread or fork_grok_thread, so its one JSON answer could not be read whole, or more than NATIVE_PROCESS_MAX_OUTPUT_BYTES for a command run's event stream or a grok export transcript, which cannot be returned whole.",
        FailureCode.GROK_PROTOCOL_MISMATCH: "The grok CLI printed output this SDK cannot read, or a fork returned its source thread; the installed Grok Build may differ from the release this SDK was checked against.",
        FailureCode.GROK_RUN_FAILED: "Grok Build reported a failure of its own, such as an unknown thread id, a model or API error, or a refused action.",
        FailureCode.OPENCODE_NOT_INSTALLED: "opencode is not on PATH, or the opencode_command you passed names a file that does not exist.",
        FailureCode.OPENCODE_LAUNCHER_REFUSED: "The opencode found first is a Windows .cmd or .bat shim, such as the npm opencode.cmd, and cmd.exe would re-read its arguments as a command line.",
        FailureCode.OPENCODE_LAUNCH_FAILED: "The operating system refused to start opencode, for example because the file lacks execute permission or is not a program.",
        FailureCode.OPENCODE_KEY_REJECTED: "The provider named in model rejected the API key passed as api_key (opencode reported ProviderAuthError or status 401 or 403); the key may be wrong, revoked or meant for another provider.",
        FailureCode.OPENCODE_THREAD_NOT_FOUND: "opencode has no session with that id in its store for this user (a run, db, export or session delete found none), or it answered on another session.",
        FailureCode.OPENCODE_TIMED_OUT: "The opencode run needed more than timeout_seconds, often because the task is large or a tool waited on a permission prompt; a thread helper's opencode child (session list, db, export or session delete) has the fixed NATIVE_CONTROL_TIMEOUT_SECONDS instead.",
        FailureCode.OPENCODE_OUTPUT_TOO_LARGE: "opencode printed more than NATIVE_PROCESS_MAX_OUTPUT_BYTES of events, so the stream could not be read whole, or an opencode export transcript or session list passed that cap and cannot be returned whole.",
        FailureCode.OPENCODE_PROTOCOL_MISMATCH: "opencode printed no readable JSON events, rows or sessionID, a fork returned its source session, or the project has NATIVE_OPENCODE_SCAN_MAX or more root sessions so session list may be cut; the installed opencode may differ from the release this SDK was checked against.",
        FailureCode.OPENCODE_RUN_FAILED: "opencode or its provider reported a failure, such as an unknown provider or model, a rate limit or a provider error.",
        FailureCode.MUSE_NOT_INSTALLED: "Muse Code is not where the SDK looked: not on PATH, not at muse_path inside the WSL distro, or not at the muse_command you passed.",
        FailureCode.MUSE_LAUNCHER_REFUSED: "The muse_command you passed is a Windows .cmd or .bat file, and cmd.exe would re-read the prompt as a command line.",
        FailureCode.MUSE_LAUNCH_FAILED: "The operating system refused to start muse, or the SDK could not create the private Muse config folder in the temp folder.",
        FailureCode.MUSE_KEY_REJECTED: "Meta rejected the API key passed as api_key (Muse printed authentication failed), and the SDK never falls back to a saved Muse login.",
        FailureCode.MUSE_THREAD_NOT_FOUND: "Muse has no session with that id (muse serve answered not found to a run or a thread helper), or muse exec answered on another session.",
        FailureCode.MUSE_TIMED_OUT: "The Muse run needed more than timeout_seconds, or muse serve, muse export or muse init did not finish within the fixed NATIVE_CONTROL_TIMEOUT_SECONDS that thread helpers and evidence reads use; a slow WSL start-up adds to both.",
        FailureCode.MUSE_OUTPUT_TOO_LARGE: "Muse printed more than NATIVE_PROCESS_MAX_OUTPUT_BYTES of JSON records, so the stream could not be read whole, or a muse export transcript passed that cap and cannot be returned whole.",
        FailureCode.MUSE_PROTOCOL_MISMATCH: "muse printed no terminal record or no session stream, or muse serve answered a fork with its source id; the installed Muse Code may differ from the release this SDK was checked against.",
        FailureCode.MUSE_RUN_FAILED: "Muse Code reported a failure of its own: a terminal state other than completed, a muse serve error, or a non-zero exit.",
        FailureCode.MUSE_WSL_UNAVAILABLE: "On Windows Muse Code runs only inside WSL, and WSL is missing, the named distro does not exist, or neither wsl_distro nor muse_command was set.",
        FailureCode.GROK_COMMAND_NOT_RUN: "Grok ran the prompt as ordinary text because it did not expand the slash command or the --agent; or a same-named skill or command replaced the bundled one, from the workspace (.grok, .claude, .agents or .cursor), from ~/.claude or ~/.grok, or from skills=; or the skill left no trace, as /imagine-video does when video tools are off (features.video_gen).",
        FailureCode.OPENCODE_COMMAND_NOT_RUN: "opencode has no command of that name in this workspace or in the user config, so it refused the run.",
        FailureCode.MUSE_COMMAND_NOT_RUN: "muse exec sends slash commands as plain text and the model did not call read_skill or create_goal, the thread's history could not be read back, or the run compacted and its transcript lacks the call.",
        FailureCode.GROK_STORE_UNREADABLE: "A folder or file under the Grok home could not be read, because of its permissions or a lock held by another process, or the user home folder could not be determined.",
        FailureCode.CONFIGURATION_INVALID_ARGUMENT: "An argument failed its check before anything started; the message names the argument and the rule it broke.",
        FailureCode.RUNTIME_ERROR: "An unexpected exception inside the SDK, which is a defect in the SDK rather than a vendor failure.",
    }
)

# One next step per failure code, written for that code.
NATIVE_THREAD_NEXT_STEPS: MappingProxyType[FailureCode, str] = MappingProxyType(
    {
        FailureCode.GROK_NOT_INSTALLED: "Install Grok Build, or pass the full path of its executable in GrokThreadConfig(grok_command=(...,)).",
        FailureCode.GROK_LAUNCHER_REFUSED: "Pass the real grok.exe in GrokThreadConfig(grok_command=(...,)), or install Grok Build's own binary under ~/.grok/bin.",
        FailureCode.GROK_LAUNCH_FAILED: "Check that grok runs from a terminal and that ~/.vidbyte/grok-homes is a writable folder, then retry; run concurrent Grok calls in one workspace only with a skill set an earlier call already prepared.",
        FailureCode.GROK_KEY_REJECTED: "Pass a valid xAI API key as api_key and retry.",
        FailureCode.GROK_THREAD_NOT_FOUND: "Pass a thread_id that a Grok function or list_grok_threads returned for the same workspace and scope; a Grok thread can be continued only from the workspace that created it.",
        FailureCode.GROK_TIMED_OUT: "For a run, raise GrokThreadConfig.timeout_seconds, narrow the prompt, or choose a permission_mode that lets the run proceed, and continue the thread to finish a partial turn; for a thread helper, retry, or run grok export directly.",
        FailureCode.GROK_OUTPUT_TOO_LARGE: "For a run, ask Grok for a shorter answer, for example by having it write long results to a file in the workspace; for a read, export the transcript with grok export yourself.",
        FailureCode.GROK_PROTOCOL_MISMATCH: "Run grok --version and install the Grok Build release named in this message, then retry.",
        FailureCode.GROK_RUN_FAILED: "Read the vendor text in this message; a Grok thread can be continued only from the workspace that created it, and API errors usually clear on retry.",
        FailureCode.OPENCODE_NOT_INSTALLED: "Install opencode, or pass the full path of its executable in OpencodeThreadConfig(opencode_command=(...,)).",
        FailureCode.OPENCODE_LAUNCHER_REFUSED: "Pass the opencode executable itself (opencode.exe) in OpencodeThreadConfig(opencode_command=(...,)).",
        FailureCode.OPENCODE_LAUNCH_FAILED: "Check that opencode runs from a terminal as the same user, then retry.",
        FailureCode.OPENCODE_KEY_REJECTED: "Pass a valid API key for the provider before the slash in model, for example a DeepSeek key for deepseek/deepseek-v4-pro, and retry.",
        FailureCode.OPENCODE_THREAD_NOT_FOUND: "Pass a thread_id that an opencode function or list_opencode_threads returned for this user and machine.",
        FailureCode.OPENCODE_TIMED_OUT: "For a run, raise OpencodeThreadConfig.timeout_seconds or narrow the prompt, and continue the session to finish a partial turn; for a thread helper, retry, or run opencode session list or opencode export directly.",
        FailureCode.OPENCODE_OUTPUT_TOO_LARGE: "For a run, ask for a shorter answer or split the task across several continue_opencode_thread calls; for a read, export the transcript with opencode export yourself.",
        FailureCode.OPENCODE_PROTOCOL_MISMATCH: "Run opencode --version and install the opencode release named in this message, then retry; when the message names the scan cap, narrow the list with list_opencode_threads_since or archive old sessions.",
        FailureCode.OPENCODE_RUN_FAILED: "Read the vendor text in this message, check that model names a provider and model that opencode knows, and retry.",
        FailureCode.MUSE_NOT_INSTALLED: "Install Muse Code, set MuseThreadConfig.muse_path to its path inside the distro, or pass its full path as muse_command.",
        FailureCode.MUSE_LAUNCHER_REFUSED: "Run Muse through WSL with MuseThreadConfig(wsl_distro=...), or pass a real executable as muse_command.",
        FailureCode.MUSE_LAUNCH_FAILED: "Check that muse runs from a terminal and that the system temp folder is writable, then retry.",
        FailureCode.MUSE_KEY_REJECTED: "Pass a valid Meta API key as api_key and retry.",
        FailureCode.MUSE_THREAD_NOT_FOUND: "Pass a thread_id that a Muse function or list_muse_threads returned for this user and machine.",
        FailureCode.MUSE_TIMED_OUT: "For a run, raise MuseThreadConfig.timeout_seconds or narrow the prompt; for a thread helper, retry; in WSL mode check that the distro starts quickly from a terminal.",
        FailureCode.MUSE_OUTPUT_TOO_LARGE: "For a run, ask for a shorter answer or split the task across several continue_muse_thread calls; for a read, export the transcript with muse export yourself.",
        FailureCode.MUSE_PROTOCOL_MISMATCH: "Run muse --version and install the Muse Code release named in this message, then retry.",
        FailureCode.MUSE_RUN_FAILED: "Read the vendor text in this message; a muse serve error usually clears once no other client holds the session.",
        FailureCode.MUSE_WSL_UNAVAILABLE: "Install WSL and a distro that holds Muse Code, then pass MuseThreadConfig(wsl_distro=...) with a name that wsl.exe -l -q lists.",
        FailureCode.GROK_COMMAND_NOT_RUN: "Read the thread with read_grok_thread(error.thread_id, workspace) to see what ran; run grok inspect --json and look for collidesWith to find a shadowing skill; check that Grok Build is the tested release 1.0.52, or run the command in the Grok TUI.",
        FailureCode.OPENCODE_COMMAND_NOT_RUN: "Pass the name of a command that opencode has, such as init or review, or add the command to the workspace's opencode config first.",
        FailureCode.MUSE_COMMAND_NOT_RUN: "Read the thread with read_muse_thread to see what ran, then name the skill in the prompt and call again.",
        FailureCode.GROK_STORE_UNREADABLE: "Fix the permissions of the path named in this message, or set HOME (POSIX) or USERPROFILE (Windows) for this process, then retry.",
        FailureCode.CONFIGURATION_INVALID_ARGUMENT: "Fix the argument named in this message and call again; nothing ran and nothing was written.",
        FailureCode.RUNTIME_ERROR: "Report the defect with the exception class named in this message; a retry may succeed if the cause was transient.",
    }
)
