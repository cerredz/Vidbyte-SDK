"""FILE: vidbyte/agents/jev/alignment/result.py

PURPOSE: Defines the immutable records JevAgentAlignment returns for one run: prompt gaps, edits, owner actions, and the prompt that ran; and, for tool alignment, the needs, attached tools, rejected candidates, and the live attachment.
ROLE IN CODEBASE: JevRuntime attaches one JevAlignmentResult under "jev_alignment" and one JevToolAlignmentResult under "jev_tool_alignment" to the main agent's result metadata; JevToolAttachment carries the live tools and MCP sessions for exactly one run.
ARCHITECTURE NOTE: Records hold only run-local evidence; nothing here is written back to JevAgentSettings or later runs.
COMMON MODIFICATION PATTERNS: Add a status member only with a matching branch in JevAgentAlignment.align and a test.
KNOWN EDGE CASES: A non-ALIGNED status always carries the original prompt; usage is None when no Jev call reported usage. JevToolAttachment owns open MCP sessions, so JevRuntime must hand it back to JevAgentAlignment.release_tools() when the run ends, including on failure.
RELATED DOCS: docs/design/jev-agent-alignment.md.
TESTS: tests/test_jev_alignment.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from vidbyte.agents.jev.alignment.questions import JevAlignmentRole, JevPromptSection
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.enums.tool_catalogs import ToolCatalogName, ToolInstallKind
from vidbyte.tools.base import BaseTool
from vidbyte.tools.mcp.types import McpServerHandle


class JevAlignmentStatus(StrEnum):
    """Outcome of one alignment pass."""

    ALIGNED = "aligned"  # at least one verified edit is in the prompt that ran
    NO_GAPS = "no_gaps"  # nothing the editor may fix was missing
    OUT_OF_SCOPE = "out_of_scope"  # a fit gate failed, so the prompt was left alone
    EDITS_REJECTED = "edits_rejected"  # the editor made no edit, or verification reverted every edit
    UNAVAILABLE = "unavailable"  # Jev or the editor failed; the original prompt ran
    SKIPPED = "skipped"  # the caller supplied its own context system prompt


@dataclass(frozen=True, slots=True)
class JevAlignmentGap:
    """One "no" answer that points at a prompt section."""

    question: str
    section: JevPromptSection
    role: JevAlignmentRole
    probability: float
    fix: str


@dataclass(frozen=True, slots=True)
class JevPromptEdit:
    """One additive edit the editor proposed for a section, and whether verification kept it."""

    section: JevPromptSection
    content: str
    fixes: tuple[str, ...]
    kept: bool = False


@dataclass(frozen=True, slots=True)
class JevAlignmentResult:
    """Everything one alignment pass decided, attached to the main agent's result metadata."""

    status: JevAlignmentStatus
    system_prompt: str
    gaps: tuple[JevAlignmentGap, ...] = ()
    edits: tuple[JevPromptEdit, ...] = ()
    owner_actions: tuple[str, ...] = ()
    probabilities: Mapping[str, float] = field(default_factory=dict)
    usage: JevUsage | None = None
    detail: str | None = None


class JevToolAlignmentStatus(StrEnum):
    """Outcome of one tool-alignment pass."""

    ATTACHED = "attached"  # at least one catalog tool was attached for this run
    NOT_NEEDED = "not_needed"  # Jev found no outside action in the request
    COVERED = "covered"  # every need is performed by a tool the agent already has
    NO_MATCH = "no_match"  # needs were uncovered, but no candidate passed the facts and Jev's checks
    OUT_OF_SCOPE = "out_of_scope"  # the request does not fit the agent, so no tool may widen it
    UNAVAILABLE = "unavailable"  # Jev, the scout, or the time budget failed; the original tools ran


class JevToolEffect(StrEnum):
    """What a tool does to outside systems, from Jev's choice and the server's declared hints."""

    READS = "reads"
    WRITES = "writes"
    SENDS_OR_DELETES = "sends_or_deletes"
    UNCLEAR = "unclear"


class JevToolRejection(StrEnum):
    """Why a proposed catalog tool was not attached."""

    NO_INSTALL = "no_install"  # the entry lists no way to run it
    INSTALL_NOT_ALLOWED = "install_not_allowed"  # its only installs are kinds the owner did not allow
    INSTALL_UNSUPPORTED = "install_unsupported"  # an OpenAPI description, which cannot be attached yet
    UNPINNED = "unpinned"  # a package with no version, so a later publish could change what runs
    MISSING_CREDENTIAL = "missing_credential"  # a required secret or credential is not configured
    CONNECT_FAILED = "connect_failed"  # the server or platform refused or failed the connection
    UNKNOWN_TOOL = "unknown_tool"  # the live server does not list the proposed tool
    NAME_CONFLICT = "name_conflict"  # the exposed name collides with a tool the agent already has
    INSTRUCTIONS_IN_DESCRIPTION = "instructions_in_description"  # the description instructs the AI beyond describing the tool
    NOT_PERFORMS_NEED = "not_performs_need"  # the description does not do the needed action
    NOT_SERVING_REQUEST = "not_serving_request"  # the request does not ask for what the tool does
    WRONG_SYSTEM = "wrong_system"  # the user named a system this tool does not work with
    EFFECT_NOT_ALLOWED = "effect_not_allowed"  # it writes, sends, or deletes without the request or owner allowing it
    LOWER_RANKED = "lower_ranked"  # another entry passed for the same need and ranked higher
    OVER_LIMIT = "over_limit"  # attaching it would exceed max_attached_tools


@dataclass(frozen=True, slots=True)
class JevToolNeed:
    """One outside action the scout wrote down for the request, and whether an existing tool already performs it."""

    need_id: str
    action: str
    object: str
    system: str | None
    sentence: str
    covered_by: tuple[str, ...] = ()
    asks_change: float = 0.0  # P(the request asks the agent to change something for this need)
    names_system: float = 0.0  # P(the request itself names `system` for this need)

    @property
    def covered(self) -> bool:
        """Return True when an existing tool already performs this need."""
        return bool(self.covered_by)


@dataclass(frozen=True, slots=True)
class JevToolCandidate:
    """One catalog tool that was judged or rejected for one need, with the evidence behind the decision."""

    need_id: str
    catalog: ToolCatalogName
    entry_id: str
    entry_name: str
    tool_name: str
    description: str = ""
    effect: JevToolEffect | None = None
    rejection: JevToolRejection | None = None
    detail: str | None = None
    probabilities: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class JevAttachedTool:
    """One catalog tool attached to this run, and where it came from, so users can see what was added."""

    name: str  # the name the main model calls it by
    original_name: str  # the name the server or platform uses
    description: str
    need_id: str
    need: str
    catalog: ToolCatalogName
    entry_id: str
    entry_name: str
    version: str | None
    install_kind: ToolInstallKind
    location: str  # the URL, image, package, or platform reference that runs it
    effect: JevToolEffect


@dataclass(frozen=True, slots=True)
class JevToolAlignmentResult:
    """Everything one tool-alignment pass decided, attached to the main agent's result metadata."""

    status: JevToolAlignmentStatus
    needs: tuple[JevToolNeed, ...] = ()
    attached: tuple[JevAttachedTool, ...] = ()
    rejected: tuple[JevToolCandidate, ...] = ()
    owner_actions: tuple[str, ...] = ()
    provider_errors: Mapping[str, str] = field(default_factory=dict)
    probabilities: Mapping[str, float] = field(default_factory=dict)
    usage: JevUsage | None = None
    detail: str | None = None

    def summary(self) -> str:
        """Return the plain-text list of added tools that JevRuntime appends to the output; empty when nothing was added."""
        if not self.attached:
            return ""
        lines = ["Tools added for this request:"]
        for tool in self.attached:
            version = f"@{tool.version}" if tool.version else ""
            lines.append(f"- {tool.name}: {tool.entry_name} ({tool.catalog.value}, {tool.entry_id}{version}, {tool.install_kind.value}) for: {tool.need}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class JevToolAttachment:
    """The live result of tool alignment for one run: the tools to add and the MCP sessions that serve them."""

    result: JevToolAlignmentResult
    tools: tuple[BaseTool, ...] = ()
    handles: tuple[McpServerHandle, ...] = ()


__all__ = [
    "JevAlignmentGap",
    "JevAlignmentResult",
    "JevAlignmentStatus",
    "JevAttachedTool",
    "JevPromptEdit",
    "JevToolAlignmentResult",
    "JevToolAlignmentStatus",
    "JevToolAttachment",
    "JevToolCandidate",
    "JevToolEffect",
    "JevToolNeed",
    "JevToolRejection",
]
