"""FILE: vidbyte/lib/enums/native_threads.py

PURPOSE: Defines the closed vocabularies of the harness thread functions: which harness a call drives (NativeHarness), the verb and public function it is (NativeThreadVerb, NativeThreadOperation), the problems a call can fail with (NativeThreadProblem), the Grok permission modes and reasoning efforts, the Muse reasoning efforts, every command-line flag the SDK passes to grok, opencode, muse, wsl.exe and the reap's sh (GrokFlag, OpencodeFlag, MuseFlag, WslFlag, ShellFlag), the child environment variable names (NativeEnvironmentVariable), the Muse serve methods (MuseMethod), the opencode and grok event types the SDK reads (OpencodeEventType, GrokEventType), the Grok store scopes the thread helpers read (GrokThreadScope), the Grok bundled slash commands and agents the command functions run (GrokCommand, GrokAgent), the flags written inside a slash-command line (GrokCommandFlag) and the Muse bundled skill ids (MuseSkill).
ROLE IN CODEBASE: Imported by the records in vidbyte/lib/dataclasses/native_threads.py, by the texts in vidbyte/lib/constants/native_threads.py, by NativeThreadError in vidbyte/lib/errors/base.py and by the thread functions under vidbyte/harnesses/native/. Exported from vidbyte/lib/enums/__init__.py; GrokPermissionMode, GrokReasoningEffort, MuseReasoningEffort, GrokThreadScope and GrokCommand are also re-exported from vidbyte.harnesses.native.
ARCHITECTURE NOTE: Every enum here is a StrEnum, so str(member) and an f-string give the value; Python 3.11 formats a (str, Enum) member as Class.MEMBER, which would corrupt argv and environment entries. Flag values are the exact spellings of grok 1.0.52, opencode 1.18.31 and Muse Code 1.0.1.
FUNCTION INVENTORY: No functions. NativeHarness, NativeThreadVerb, NativeThreadOperation, NativeThreadProblem, GrokPermissionMode, GrokReasoningEffort, MuseReasoningEffort, GrokFlag, OpencodeFlag, MuseFlag, WslFlag, ShellFlag, NativeEnvironmentVariable, MuseMethod, OpencodeEventType, GrokThreadScope, GrokCommand, GrokAgent, GrokCommandFlag, GrokEventType and MuseSkill.
COMMON MODIFICATION PATTERNS: Append members only, never reorder them (the order is part of the contract). Add a member only when the vendor CLI adds the value, and use it in the harness module that builds the argv or reads the output in the same change. A new problem also needs its FailureCode members and its texts in vidbyte/lib/constants/native_threads.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not add an approve-everything member (bypassPermissions, --yolo, --auto, --always-approve); the SDK never approves everything. 2. Do not import anything from vidbyte; enums sit at the bottom layer. 3. Do not turn an enum here back into a (str, Enum).
KNOWN EDGE CASES: NativeEnvironmentVariable values equal their names. MuseFlag.END_OF_OPTIONS is the bare "--" operand that keeps the Muse prompt from being read as a flag. WSL_UNAVAILABLE is a Muse-only problem and STORE_UNREADABLE a Grok-only one. GrokCommandFlag values are written inside the --single line, never as argv elements. MuseSkill values carry the bundled: prefix of the Muse skill registry.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_surface.py, tests/features/harness_threads/test_harness_threads_argv.py
"""

from __future__ import annotations

from enum import StrEnum


class NativeHarness(StrEnum):
    """The coding harness a thread function drives."""

    GROK = "grok"
    OPENCODE = "opencode"
    MUSE = "muse"


class NativeThreadVerb(StrEnum):
    """What a thread function does to a thread: start one, continue one, or copy one into a new one."""

    RUN = "run"
    CONTINUE = "continue"
    FORK = "fork"


class NativeThreadOperation(StrEnum):
    """The public thread function, helper or skill function a call or an error belongs to; each value is the function name."""

    RUN_GROK_THREAD = "run_grok_thread"
    CONTINUE_GROK_THREAD = "continue_grok_thread"
    FORK_GROK_THREAD = "fork_grok_thread"
    RUN_OPENCODE_THREAD = "run_opencode_thread"
    CONTINUE_OPENCODE_THREAD = "continue_opencode_thread"
    FORK_OPENCODE_THREAD = "fork_opencode_thread"
    RUN_MUSE_THREAD = "run_muse_thread"
    CONTINUE_MUSE_THREAD = "continue_muse_thread"
    FORK_MUSE_THREAD = "fork_muse_thread"
    LIST_GROK_THREADS = "list_grok_threads"
    LIST_RECENT_GROK_THREADS = "list_recent_grok_threads"
    LIST_GROK_THREADS_SINCE = "list_grok_threads_since"
    GET_GROK_THREAD = "get_grok_thread"
    READ_GROK_THREAD = "read_grok_thread"
    GET_GROK_THREAD_LINEAGE = "get_grok_thread_lineage"
    SEARCH_GROK_THREADS = "search_grok_threads"
    DELETE_GROK_THREAD = "delete_grok_thread"
    LIST_OPENCODE_THREADS = "list_opencode_threads"
    LIST_RECENT_OPENCODE_THREADS = "list_recent_opencode_threads"
    LIST_OPENCODE_THREADS_SINCE = "list_opencode_threads_since"
    GET_OPENCODE_THREAD = "get_opencode_thread"
    READ_OPENCODE_THREAD = "read_opencode_thread"
    GET_OPENCODE_THREAD_LINEAGE = "get_opencode_thread_lineage"
    SEARCH_OPENCODE_THREADS = "search_opencode_threads"
    DELETE_OPENCODE_THREAD = "delete_opencode_thread"
    LIST_MUSE_THREADS = "list_muse_threads"
    LIST_RECENT_MUSE_THREADS = "list_recent_muse_threads"
    LIST_MUSE_THREADS_SINCE = "list_muse_threads_since"
    GET_MUSE_THREAD = "get_muse_thread"
    READ_MUSE_THREAD = "read_muse_thread"
    GET_MUSE_THREAD_LINEAGE = "get_muse_thread_lineage"
    RUN_GROK_COMMAND = "run_grok_command"
    RUN_GROK_GOAL = "run_grok_goal"
    RUN_GROK_IMPLEMENT = "run_grok_implement"
    RUN_GROK_DESIGN = "run_grok_design"
    RUN_GROK_EXECUTE_PLAN = "run_grok_execute_plan"
    RUN_GROK_REVIEW = "run_grok_review"
    RUN_GROK_CODE_REVIEW = "run_grok_code_review"
    RUN_GROK_RESUME_CLAUDE = "run_grok_resume_claude"
    RUN_GROK_RESUME_CODEX = "run_grok_resume_codex"
    RUN_GROK_RESUME_CURSOR = "run_grok_resume_cursor"
    RUN_GROK_IMAGINE = "run_grok_imagine"
    RUN_GROK_IMAGINE_VIDEO = "run_grok_imagine_video"
    RUN_GROK_PLAN = "run_grok_plan"
    RUN_GROK_EXPLORE = "run_grok_explore"
    RUN_OPENCODE_COMMAND = "run_opencode_command"
    RUN_OPENCODE_REVIEW = "run_opencode_review"
    RUN_OPENCODE_INIT = "run_opencode_init"
    RUN_OPENCODE_PLAN = "run_opencode_plan"
    RUN_MUSE_SKILL = "run_muse_skill"
    RUN_MUSE_GOAL = "run_muse_goal"
    RUN_MUSE_PLAN = "run_muse_plan"
    RUN_MUSE_IMPORT = "run_muse_import"
    RUN_MUSE_SCAFFOLD = "run_muse_scaffold"
    RUN_MUSE_BROWSER_APP = "run_muse_browser_app"
    INIT_MUSE_WORKSPACE = "init_muse_workspace"


class NativeThreadProblem(StrEnum):
    """Why a thread function failed, in the order the functions check for it."""

    NOT_INSTALLED = "not_installed"
    LAUNCHER_REFUSED = "launcher_refused"
    LAUNCH_FAILED = "launch_failed"
    KEY_REJECTED = "key_rejected"
    THREAD_NOT_FOUND = "thread_not_found"
    TIMED_OUT = "timed_out"
    OUTPUT_TOO_LARGE = "output_too_large"
    PROTOCOL_MISMATCH = "protocol_mismatch"
    RUN_FAILED = "run_failed"
    WSL_UNAVAILABLE = "wsl_unavailable"
    COMMAND_NOT_RUN = "command_not_run"
    STORE_UNREADABLE = "store_unreadable"


class GrokPermissionMode(StrEnum):
    """The Grok headless permission modes the SDK allows; there is no approve-everything mode."""

    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    DONT_ASK = "dontAsk"
    PLAN = "plan"


class GrokReasoningEffort(StrEnum):
    """The reasoning efforts grok --reasoning-effort accepts."""

    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class MuseReasoningEffort(StrEnum):
    """The reasoning efforts muse exec --reasoning-effort accepts."""

    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    ULTRA = "ultra"


class GrokFlag(StrEnum):
    """The grok options the Grok thread and command functions pass, each joined to its value."""

    SINGLE = "--single"
    OUTPUT_FORMAT = "--output-format"
    CWD = "--cwd"
    PERMISSION_MODE = "--permission-mode"
    MODEL = "--model"
    REASONING_EFFORT = "--reasoning-effort"
    RESUME = "--resume"
    FORK_SESSION = "--fork-session"
    AGENT = "--agent"
    SESSION_ID = "--session-id"


class OpencodeFlag(StrEnum):
    """The opencode run and session list options the opencode functions pass, each joined to its value."""

    FORMAT = "--format"
    DIR = "--dir"
    MODEL = "--model"
    AGENT = "--agent"
    VARIANT = "--variant"
    SESSION = "--session"
    FORK = "--fork"
    COMMAND = "--command"
    MAX_COUNT = "--max-count"


class MuseFlag(StrEnum):
    """The muse exec, export and init options the Muse functions pass as separate elements, and the end-of-options operand."""

    JSON = "--json"
    PROVIDER = "--provider"
    WORKSPACE = "--workspace"
    SESSION_ID = "--session-id"
    MODEL = "--model"
    REASONING_EFFORT = "--reasoning-effort"
    USER_INPUT_AUTO_RESOLVE = "--user-input-auto-resolve"
    END_OF_OPTIONS = "--"
    SESSION = "--session"
    OUT = "--out"
    DRY_RUN = "--dry-run"


class WslFlag(StrEnum):
    """The wsl.exe options the Muse WSL mode passes: the distro, the program to run, and the quiet distro listing."""

    DISTRIBUTION = "-d"
    EXEC = "-e"
    LIST = "-l"
    QUIET = "-q"


class ShellFlag(StrEnum):
    """The sh options the Muse WSL reap passes: read the script from standard input."""

    READ_STDIN = "-s"


class NativeEnvironmentVariable(StrEnum):
    """The environment variables the SDK sets in a vendor child; each value equals its name."""

    XAI_API_KEY = "XAI_API_KEY"
    GROK_CODE_XAI_API_KEY = "GROK_CODE_XAI_API_KEY"
    GROK_HOME = "GROK_HOME"
    GROK_DISABLE_AUTOUPDATER = "GROK_DISABLE_AUTOUPDATER"
    OPENCODE_CONFIG_CONTENT = "OPENCODE_CONFIG_CONTENT"
    OPENCODE_DISABLE_AUTOUPDATE = "OPENCODE_DISABLE_AUTOUPDATE"
    META_API_KEY = "META_API_KEY"
    MUSE_NO_AUTO_UPDATE = "MUSE_NO_AUTO_UPDATE"
    MUSE_AUTH_PATH = "MUSE_AUTH_PATH"
    XDG_CONFIG_HOME = "XDG_CONFIG_HOME"
    WSLENV = "WSLENV"
    VIDBYTE_PEER_MARK = "VIDBYTE_PEER_MARK"
    GROK_WORKFLOWS = "GROK_WORKFLOWS"
    PWD = "PWD"


class MuseMethod(StrEnum):
    """The Muse serve (MSP) methods the Muse thread functions and helpers send."""

    INITIALIZE = "initialize"
    INITIALIZED = "initialized"
    SESSION_READ = "session/read"
    SESSION_FORK = "session/fork"
    SESSION_LIST = "session/list"


class OpencodeEventType(StrEnum):
    """The opencode run --format json event types the opencode thread functions read."""

    TEXT = "text"
    ERROR = "error"


class GrokThreadScope(StrEnum):
    """Which Grok store the Grok thread helpers read: the SDK's private home for the workspace, or the user's own ~/.grok."""

    SDK = "sdk"
    USER = "user"


class GrokCommand(StrEnum):
    """The Grok bundled slash commands the Grok command functions run; each value is the command name without its slash."""

    GOAL = "goal"
    IMPLEMENT = "implement"
    DESIGN = "design"
    EXECUTE_PLAN = "execute-plan"
    REVIEW = "review"
    CODE_REVIEW = "code-review"
    RESUME_CLAUDE = "resume-claude"
    RESUME_CODEX = "resume-codex"
    RESUME_CURSOR = "resume-cursor"
    IMAGINE = "imagine"
    IMAGINE_VIDEO = "imagine-video"


class GrokAgent(StrEnum):
    """The Grok bundled agents run_grok_plan and run_grok_explore pass to grok --agent."""

    PLAN = "plan"
    EXPLORE = "explore"


class GrokCommandFlag(StrEnum):
    """The option flags written inside a Grok slash-command line (not on argv)."""

    BUDGET = "--budget"
    EFFORT = "--effort"
    CONCURRENCY = "--concurrency"
    DRY_RUN = "--dry-run"
    AUTO_PR = "--auto-pr"
    LOCAL = "--local"
    BRANCH = "--branch"
    PR = "--pr"


class GrokEventType(StrEnum):
    """The grok --output-format streaming-json event types the Grok command functions read."""

    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_CALL_UPDATE = "tool_call_update"
    END = "end"
    ERROR = "error"


class MuseSkill(StrEnum):
    """The Muse bundled skill ids the named Muse skill functions ask the model to load."""

    PLAN = "bundled:plan"
    IMPORT = "bundled:import"
    SCAFFOLD = "bundled:greenfield-project-scaffolding"
    BROWSER_APP = "bundled:browser-app-delivery"


__all__ = [
    "GrokAgent",
    "GrokCommand",
    "GrokCommandFlag",
    "GrokEventType",
    "GrokFlag",
    "GrokPermissionMode",
    "GrokReasoningEffort",
    "GrokThreadScope",
    "MuseFlag",
    "MuseMethod",
    "MuseReasoningEffort",
    "MuseSkill",
    "NativeEnvironmentVariable",
    "NativeHarness",
    "NativeThreadOperation",
    "NativeThreadProblem",
    "NativeThreadVerb",
    "OpencodeEventType",
    "OpencodeFlag",
    "ShellFlag",
    "WslFlag",
]
