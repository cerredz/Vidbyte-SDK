"""FILE: vidbyte/lib/enums/native_threads.py

PURPOSE: Defines the closed vocabularies of the harness thread functions: which harness a call drives (NativeHarness), the verb and public function it is (NativeThreadVerb, NativeThreadOperation), the problems a call can fail with (NativeThreadProblem), the Grok permission modes and reasoning efforts, the Muse reasoning efforts, every command-line flag the SDK passes to grok, opencode, muse and wsl.exe (GrokFlag, OpencodeFlag, MuseFlag, WslFlag), the child environment variable names (NativeEnvironmentVariable), the Muse serve methods (MuseMethod) and the opencode event types the SDK reads (OpencodeEventType).
ROLE IN CODEBASE: Imported by the records in vidbyte/lib/dataclasses/native_threads.py, by the texts in vidbyte/lib/constants/native_threads.py, by NativeThreadError in vidbyte/lib/errors/base.py and by the thread functions under vidbyte/harnesses/native/. Exported from vidbyte/lib/enums/__init__.py; GrokPermissionMode, GrokReasoningEffort and MuseReasoningEffort are also re-exported from vidbyte.harnesses.native.
ARCHITECTURE NOTE: Every enum here is a StrEnum, so str(member) and an f-string give the value; Python 3.11 formats a (str, Enum) member as Class.MEMBER, which would corrupt argv and environment entries. Flag values are the exact spellings of grok 1.0.52, opencode 1.18.31 and Muse Code 1.0.1.
FUNCTION INVENTORY: No functions. NativeHarness, NativeThreadVerb, NativeThreadOperation, NativeThreadProblem, GrokPermissionMode, GrokReasoningEffort, MuseReasoningEffort, GrokFlag, OpencodeFlag, MuseFlag, WslFlag, NativeEnvironmentVariable, MuseMethod and OpencodeEventType.
COMMON MODIFICATION PATTERNS: Add a member only when the vendor CLI adds the value, and use it in the harness module that builds the argv or reads the output in the same change. A new problem also needs its FailureCode members and its texts in vidbyte/lib/constants/native_threads.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not add an approve-everything member (bypassPermissions, --yolo, --auto, --always-approve); the SDK never approves everything. 2. Do not import anything from vidbyte; enums sit at the bottom layer. 3. Do not turn an enum here back into a (str, Enum).
KNOWN EDGE CASES: NativeEnvironmentVariable values equal their names. MuseFlag.END_OF_OPTIONS is the bare "--" operand that keeps the Muse prompt from being read as a flag. WSL_UNAVAILABLE is a Muse-only problem.
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
    """The public thread function a call or an error belongs to."""

    RUN_GROK_THREAD = "run_grok_thread"
    CONTINUE_GROK_THREAD = "continue_grok_thread"
    FORK_GROK_THREAD = "fork_grok_thread"
    RUN_OPENCODE_THREAD = "run_opencode_thread"
    CONTINUE_OPENCODE_THREAD = "continue_opencode_thread"
    FORK_OPENCODE_THREAD = "fork_opencode_thread"
    RUN_MUSE_THREAD = "run_muse_thread"
    CONTINUE_MUSE_THREAD = "continue_muse_thread"
    FORK_MUSE_THREAD = "fork_muse_thread"


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
    """The grok options the Grok thread functions pass, each joined to its value."""

    SINGLE = "--single"
    OUTPUT_FORMAT = "--output-format"
    CWD = "--cwd"
    PERMISSION_MODE = "--permission-mode"
    MODEL = "--model"
    REASONING_EFFORT = "--reasoning-effort"
    RESUME = "--resume"
    FORK_SESSION = "--fork-session"


class OpencodeFlag(StrEnum):
    """The opencode run options the opencode thread functions pass, each joined to its value."""

    FORMAT = "--format"
    DIR = "--dir"
    MODEL = "--model"
    AGENT = "--agent"
    VARIANT = "--variant"
    SESSION = "--session"
    FORK = "--fork"


class MuseFlag(StrEnum):
    """The muse exec options the Muse thread functions pass as separate elements, and the end-of-options operand."""

    JSON = "--json"
    PROVIDER = "--provider"
    WORKSPACE = "--workspace"
    SESSION_ID = "--session-id"
    MODEL = "--model"
    REASONING_EFFORT = "--reasoning-effort"
    USER_INPUT_AUTO_RESOLVE = "--user-input-auto-resolve"
    END_OF_OPTIONS = "--"


class WslFlag(StrEnum):
    """The wsl.exe options the Muse WSL mode passes: the distro, the program to run, and the quiet distro listing."""

    DISTRIBUTION = "-d"
    EXEC = "-e"
    LIST = "-l"
    QUIET = "-q"


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


class MuseMethod(StrEnum):
    """The Muse serve (MSP) methods the Muse continue and fork functions send."""

    INITIALIZE = "initialize"
    INITIALIZED = "initialized"
    SESSION_READ = "session/read"
    SESSION_FORK = "session/fork"


class OpencodeEventType(StrEnum):
    """The opencode run --format json event types the opencode thread functions read."""

    TEXT = "text"
    ERROR = "error"


__all__ = [
    "GrokFlag",
    "GrokPermissionMode",
    "GrokReasoningEffort",
    "MuseFlag",
    "MuseMethod",
    "MuseReasoningEffort",
    "NativeEnvironmentVariable",
    "NativeHarness",
    "NativeThreadOperation",
    "NativeThreadProblem",
    "NativeThreadVerb",
    "OpencodeEventType",
    "OpencodeFlag",
    "WslFlag",
]
