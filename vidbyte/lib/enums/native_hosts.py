"""FILE: vidbyte/lib/enums/native_hosts.py

PURPOSE: Defines the closed value sets shared by the native Grok, opencode and Muse hosts: which harness a turn belongs to, a turn's status, who interrupted it, how an approval was answered, the ACP tool kinds, the Grok one-shot permission modes, the opencode permission actions and MCP kinds, and the Muse reasoning efforts and view directions.
ROLE IN CODEBASE: Imported by the records in vidbyte/lib/dataclasses/native_hosts.py, grok.py, opencode.py and muse.py, by the hosts under vidbyte/harnesses/native/, and by the tools under vidbyte/tools/builtins/{grok,opencode,muse}/. Exported from vidbyte/lib/enums/__init__.py.
ARCHITECTURE NOTE: Every enum is a str Enum so a record field holds a member while JSON output carries its value. Vendor vocabularies the hosts only pass through (stop reasons, session states, approval decisions) stay plain strings in the records and are not modelled here.
FUNCTION INVENTORY: No functions. NativeHarness, NativeTurnStatus, InterruptSource, ApprovalOutcome, AcpToolKind, GrokPermissionMode, OpencodePermissionAction, OpencodeMcpKind, MuseReasoningEffort and MuseViewDirection.
COMMON MODIFICATION PATTERNS: Add a member only when the vendor protocol adds the value; update the records that check it and the host that sends it in the same change.
WHAT NOT TO DO IN THIS FILE: 1. Do not add an auto or bypassPermissions member to GrokPermissionMode; the hosts never approve everything. 2. Do not import anything from vidbyte; enums sit at the bottom layer.
KNOWN EDGE CASES: A missing or unknown ACP tool kind is read as AcpToolKind.OTHER by the Grok wire parser. NativeHarness lists CLAUDE_CODE and CODEX so backend profiles can name them, although no native host here drives those two.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §9.1; vidbyte/harnesses/README.md
TESTS: tests/features/grok_host/test_grok_host_records.py, tests/features/muse_host/test_muse_host_records.py, tests/features/opencode_host/test_opencode_host_records.py
"""

from __future__ import annotations

from enum import Enum


class NativeHarness(str, Enum):
    """The coding-agent harness a handle, profile or tool result belongs to."""

    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    OPENCODE = "opencode"
    GROK = "grok"
    MUSE = "muse"


class NativeTurnStatus(str, Enum):
    """The lifecycle state of one native turn."""

    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class InterruptSource(str, Enum):
    """Who ended an interrupted turn; CALLER also covers an interruption from another client of the session."""

    CALLER = "caller"
    DEADLINE = "deadline"
    HOST_CLOSED = "host_closed"
    POLICY = "policy"


class ApprovalOutcome(str, Enum):
    """How the host answered one approval or question request during a turn."""

    ALLOWED = "allowed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    NOT_SUPPORTED = "not_supported"


class AcpToolKind(str, Enum):
    """The ACP ToolKind values a Grok permission request can carry."""

    READ = "read"
    EDIT = "edit"
    DELETE = "delete"
    MOVE = "move"
    SEARCH = "search"
    EXECUTE = "execute"
    THINK = "think"
    FETCH = "fetch"
    SWITCH_MODE = "switch_mode"
    OTHER = "other"


class GrokPermissionMode(str, Enum):
    """The Grok one-shot permission modes the SDK allows; there is no approve-everything mode."""

    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    DONT_ASK = "dontAsk"
    PLAN = "plan"


class OpencodePermissionAction(str, Enum):
    """The action of one opencode permission rule."""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class OpencodeMcpKind(str, Enum):
    """Whether an opencode MCP server runs as a local command or is reached at a URL."""

    LOCAL = "local"
    REMOTE = "remote"


class MuseReasoningEffort(str, Enum):
    """The closed MSP ReasoningEffort set a Muse turn may request."""

    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    ULTRA = "ultra"


class MuseViewDirection(str, Enum):
    """The closed MSP ViewPageDirection set for paging a Muse session's view."""

    FORWARD = "forward"
    BACKWARD = "backward"


__all__ = [
    "AcpToolKind",
    "ApprovalOutcome",
    "GrokPermissionMode",
    "InterruptSource",
    "MuseReasoningEffort",
    "MuseViewDirection",
    "NativeHarness",
    "NativeTurnStatus",
    "OpencodeMcpKind",
    "OpencodePermissionAction",
]
