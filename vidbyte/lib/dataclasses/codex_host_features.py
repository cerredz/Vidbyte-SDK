"""FILE: vidbyte/lib/dataclasses/codex_host_features.py

PURPOSE: Defines the eleven validated records of CodexHost's first-class features: CodexThreadSettingsUpdate, the settings change a developer builds for update_codex_thread_settings, and the records the host returns from Codex's answers: one streamed turn event with its plan steps, MCP servers and their page, the memory status, a created worktree, background terminals and their page, and thread search hits and their page.
ROLE IN CODEBASE: The feature data layer under vidbyte/harnesses/native/codex/. CodexFeatureResponseTranslator (feature_wire.py) and CodexTurnEventTranslator (turn_stream.py) build the output records from Codex's answers, CodexThreadMethods builds CodexWorktree, and the tools under vidbyte/tools/builtins/codex/ serialize them for the model.
ARCHITECTURE NOTE: Every record is frozen with slots and checks itself in __post_init__ through RecordFieldValidator and RecordFieldConverter, naming the field as "<owner> <field>". It imports codex_host for the handle, snapshot and thread records and codex_host_modes for the collaboration mode, which import nothing from here, so there is no cycle (first-class D-5, D-30). No record has a dict encoder: the wire params live in CodexFeatureParamsTranslator.
COMMON MODIFICATION PATTERNS: A new field adds its check to the same record's __post_init__; a new output record is added here and to the literal __all__, and its translator method goes in feature_wire.py. A new thread setting adds its field to CodexThreadSettingsUpdate, its default to the empty-update check (which reads the dataclass defaults) and its wire key to CodexFeatureParamsTranslator.thread_settings.
KNOWN EDGE CASES: Every record but CodexThreadSettingsUpdate and CodexWorktree is built by a translator from a Codex answer, so a failed check there surfaces as codex.protocol_mismatch inside the call (first-class INV-6). A settings update with every field at its default is refused, and an empty disabled_plugin_ids tuple counts as a change because it clears the list. A CodexTurnEvent carries a snapshot exactly when its kind is ENDED, an item only for the two item kinds, and a dropped count of at least 1 exactly when its kind is GAP. A search snippet and a plan step may be empty text, because Codex sends them as plain strings.
RELATED DOCS: docs/spec/codex-host-first-class/spec.md (sections 8.5 and 9.1); vidbyte/lib/dataclasses/validation.py
TESTS: tests/features/codex_host/test_codex_host_feature_records.py
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, fields

from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_SETTINGS_EMPTY_MESSAGE,
    CODEX_HOST_SETTINGS_MODE_MODEL_MESSAGE,
    CODEX_HOST_SETTINGS_NETWORK_ACCESS_MESSAGE,
    CODEX_HOST_SETTINGS_WRITABLE_ROOTS_MESSAGE,
    CODEX_HOST_TIER_CLEAR_CONFLICT_MESSAGE,
)
from vidbyte.lib.dataclasses.codex import CodexItem, CodexUsage
from vidbyte.lib.dataclasses.codex_host import CodexThreadInfo, CodexTurnHandle, CodexTurnSnapshot
from vidbyte.lib.dataclasses.codex_host_modes import CodexCollaborationMode
from vidbyte.lib.dataclasses.validation import RecordFieldConverter, RecordFieldValidator
from vidbyte.lib.enums.codex import (
    CodexApprovalPolicy,
    CodexApprovalsReviewer,
    CodexHostOperation,
    CodexMcpAuthStatus,
    CodexMcpConnectionStatus,
    CodexPlanStepStatus,
    CodexReasoningEffort,
    CodexReasoningSummary,
    CodexSandbox,
    CodexTurnEventKind,
)
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class CodexThreadSettingsUpdate:
    """The thread settings update_codex_thread_settings changes; every field left at its default stays as Codex has it.

    Codex applies the change to the thread's later turns, not to a turn
    already running. ``clear_service_tier`` removes the thread's tier,
    ``disabled_plugin_ids=()`` clears the disabled list, and ``None``
    leaves it unchanged. ``network_access`` needs a READ_ONLY or
    WORKSPACE_WRITE ``sandbox`` and ``writable_roots`` needs
    WORKSPACE_WRITE. A ``collaboration_mode`` needs a model, in the mode
    or in ``model``, because Codex requires one with every mode.
    """

    model: str = ""
    effort: CodexReasoningEffort = CodexReasoningEffort.PROVIDER_DEFAULT
    summary: CodexReasoningSummary = CodexReasoningSummary.PROVIDER_DEFAULT
    service_tier: str = ""
    clear_service_tier: bool = False
    cwd: str = ""
    approval_policy: CodexApprovalPolicy = CodexApprovalPolicy.PROVIDER_DEFAULT
    approvals_reviewer: CodexApprovalsReviewer = CodexApprovalsReviewer.PROVIDER_DEFAULT
    sandbox: CodexSandbox = CodexSandbox.PROVIDER_DEFAULT
    network_access: bool | None = None
    writable_roots: tuple[str, ...] = ()
    collaboration_mode: CodexCollaborationMode | None = None
    disabled_plugin_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        # Check each field's type first, so every later rule can trust
        # the values it compares.
        self._reject_bad_types()

        # An update that changes nothing would still be sent, so it is
        # refused here with the field named settings.
        self._reject_empty_update()

        # A tier cannot be set and cleared at once, and the sandbox
        # overrides need the sandbox policy that carries them.
        self._reject_tier_conflict()
        self._reject_bad_sandbox_fields()

        # A collaboration mode needs a model and must agree with the
        # update's own model and effort (first-class EC-7, INV-14).
        self._reject_bad_mode()

    def _reject_bad_types(self) -> None:
        owner = CodexHostOperation.UPDATE_CODEX_THREAD_SETTINGS.value
        RecordFieldValidator.require_text(self.model, f"{owner} model", allow_blank=True, one_line=True)
        RecordFieldValidator.require_enum(self.effort, CodexReasoningEffort, f"{owner} effort")
        RecordFieldValidator.require_enum(self.summary, CodexReasoningSummary, f"{owner} summary")
        RecordFieldValidator.require_text(self.service_tier, f"{owner} service_tier", allow_blank=True, one_line=True)
        RecordFieldValidator.require_bool(self.clear_service_tier, f"{owner} clear_service_tier")
        RecordFieldValidator.require_text(self.cwd, f"{owner} cwd", allow_blank=True, one_line=True)
        if self.cwd and not os.path.isabs(self.cwd):
            raise ConfigurationError(f"{owner} cwd must be blank or an absolute path.", details={"field": f"{owner} cwd"})
        RecordFieldValidator.require_enum(self.approval_policy, CodexApprovalPolicy, f"{owner} approval_policy")
        RecordFieldValidator.require_enum(self.approvals_reviewer, CodexApprovalsReviewer, f"{owner} approvals_reviewer")
        RecordFieldValidator.require_enum(self.sandbox, CodexSandbox, f"{owner} sandbox")
        RecordFieldConverter.require_instance(self.collaboration_mode, f"{owner} collaboration_mode", CodexCollaborationMode, optional=True)
        if self.disabled_plugin_ids is not None:
            # The list is one field to the caller, so a bad entry is
            # reported under the field's own name.
            try:
                RecordFieldValidator.require_text_items(self.disabled_plugin_ids, f"{owner} disabled_plugin_ids", one_line=True)
            except ConfigurationError as error:
                raise ConfigurationError(str(error), details={"field": f"{owner} disabled_plugin_ids"}) from None

    def _reject_empty_update(self) -> None:
        if all(getattr(self, item.name) == item.default for item in fields(self)):
            message = CODEX_HOST_SETTINGS_EMPTY_MESSAGE.format(operation=CodexHostOperation.UPDATE_CODEX_THREAD_SETTINGS.value)
            raise ConfigurationError(message, details={"field": "settings"})

    def _reject_tier_conflict(self) -> None:
        if self.service_tier and self.clear_service_tier:
            message = CODEX_HOST_TIER_CLEAR_CONFLICT_MESSAGE.format(operation=CodexHostOperation.UPDATE_CODEX_THREAD_SETTINGS.value)
            raise ConfigurationError(message, details={"field": "clear_service_tier"})

    def _reject_bad_sandbox_fields(self) -> None:
        # @intent settings-sandbox-overrides-need-their-sandbox
        # Both fields are sent inside the sandbox policy, and only some
        # policies have them, so a sandbox without the setting is
        # refused here rather than by Codex.
        if self.network_access is not None:
            RecordFieldValidator.require_bool(self.network_access, "update_codex_thread_settings network_access")
            if self.sandbox not in (CodexSandbox.READ_ONLY, CodexSandbox.WORKSPACE_WRITE):
                raise ConfigurationError(CODEX_HOST_SETTINGS_NETWORK_ACCESS_MESSAGE.format(sandbox=self.sandbox.name), details={"field": "network_access"})
        roots = self.writable_roots
        if roots == ():
            return
        bad_roots = not isinstance(roots, tuple) or any(not isinstance(root, str) or not root or not os.path.isabs(root) for root in roots)
        if bad_roots or self.sandbox is not CodexSandbox.WORKSPACE_WRITE:
            raise ConfigurationError(CODEX_HOST_SETTINGS_WRITABLE_ROOTS_MESSAGE, details={"field": "writable_roots"})

    def _reject_bad_mode(self) -> None:
        mode = self.collaboration_mode
        if mode is None:
            return
        if not (mode.model or self.model):
            raise ConfigurationError(CODEX_HOST_SETTINGS_MODE_MODEL_MESSAGE, details={"field": "collaboration_mode"})
        mode.reject_conflict(CodexHostOperation.UPDATE_CODEX_THREAD_SETTINGS.value, self.model, self.effort)


@dataclass(frozen=True, slots=True)
class CodexPlanStep:
    """One step of a turn's plan and its state."""

    step: str
    status: CodexPlanStepStatus

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.step, "Codex plan step step", allow_blank=True)
        RecordFieldValidator.require_enum(self.status, CodexPlanStepStatus, "Codex plan step status")


@dataclass(frozen=True, slots=True)
class CodexTurnEvent:
    """One streamed event of a live turn: a delta, an item, a plan or usage update, a gap in the stream, or its end.

    ``sequence`` counts from 1 per turn. ``text`` holds the delta, the
    diff or the plan explanation. ``usage`` is the turn's own usage so
    far. A ``GAP`` event says ``dropped`` events were lost because the
    reader fell behind, and ``ENDED`` carries the turn's final snapshot.
    """

    sequence: int
    kind: CodexTurnEventKind
    handle: CodexTurnHandle
    item_id: str = ""
    item_type: str = ""
    text: str = ""
    item: CodexItem | None = None
    usage: CodexUsage | None = None
    plan_steps: tuple[CodexPlanStep, ...] = ()
    snapshot: CodexTurnSnapshot | None = None
    dropped: int = 0

    def __post_init__(self) -> None:
        # Check each field's own type and range.
        RecordFieldValidator.require_int(self.sequence, "Codex turn event sequence", minimum=1)
        RecordFieldValidator.require_enum(self.kind, CodexTurnEventKind, "Codex turn event kind")
        RecordFieldConverter.require_instance(self.handle, "Codex turn event handle", CodexTurnHandle)
        RecordFieldValidator.require_text(self.item_id, "Codex turn event item_id", allow_blank=True)
        RecordFieldValidator.require_text(self.item_type, "Codex turn event item_type", allow_blank=True)
        RecordFieldValidator.require_text(self.text, "Codex turn event text", allow_blank=True)
        RecordFieldConverter.require_instance(self.item, "Codex turn event item", CodexItem, optional=True)
        RecordFieldConverter.require_instance(self.usage, "Codex turn event usage", CodexUsage, optional=True)
        RecordFieldConverter.require_instance(self.snapshot, "Codex turn event snapshot", CodexTurnSnapshot, optional=True)
        object.__setattr__(self, "plan_steps", RecordFieldConverter.to_tuple(self.plan_steps, "Codex turn event plan_steps", item_type=CodexPlanStep))

        # Then the rules that tie a field to the event's kind.
        self._reject_fields_of_another_kind()

    def _reject_fields_of_another_kind(self) -> None:
        # @intent each-event-kind-carries-only-its-own-fields
        # The end carries the snapshot, an item event the item, and a
        # gap its count, so a reader can trust the kind alone.
        if (self.snapshot is not None) != (self.kind is CodexTurnEventKind.ENDED):
            raise ConfigurationError("Codex turn event snapshot must be set exactly when kind is ENDED.", details={"field": "Codex turn event snapshot"})
        if self.item is not None and self.kind not in (CodexTurnEventKind.ITEM_STARTED, CodexTurnEventKind.ITEM_COMPLETED):
            raise ConfigurationError("Codex turn event item may be set only when kind is ITEM_STARTED or ITEM_COMPLETED.", details={"field": "Codex turn event item"})
        gap = self.kind is CodexTurnEventKind.GAP
        RecordFieldValidator.require_int(self.dropped, "Codex turn event dropped", minimum=1 if gap else 0, maximum=None if gap else 0)


@dataclass(frozen=True, slots=True)
class CodexMcpServer:
    """One MCP server Codex runs: its sign-in and connection state, its tool names and its resource counts."""

    name: str
    auth_status: CodexMcpAuthStatus
    connection_status: CodexMcpConnectionStatus
    tool_names: tuple[str, ...]
    resource_count: int
    resource_template_count: int
    plugin_id: str = ""
    http_origin: str = ""
    tools_error: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.name, "Codex MCP server name")
        RecordFieldValidator.require_enum(self.auth_status, CodexMcpAuthStatus, "Codex MCP server auth_status")
        RecordFieldValidator.require_enum(self.connection_status, CodexMcpConnectionStatus, "Codex MCP server connection_status")
        RecordFieldValidator.require_text_items(self.tool_names, "Codex MCP server tool_names")
        RecordFieldValidator.require_int(self.resource_count, "Codex MCP server resource_count", minimum=0)
        RecordFieldValidator.require_int(self.resource_template_count, "Codex MCP server resource_template_count", minimum=0)
        for name in ("plugin_id", "http_origin", "tools_error", "version"):
            RecordFieldValidator.require_text(getattr(self, name), f"Codex MCP server {name}", allow_blank=True)


@dataclass(frozen=True, slots=True)
class CodexMcpServerPage:
    """One page of MCP servers, with the cursor of the next page, empty on the last."""

    servers: tuple[CodexMcpServer, ...]
    next_cursor: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "servers", RecordFieldConverter.to_tuple(self.servers, "Codex MCP server page servers", item_type=CodexMcpServer))
        RecordFieldValidator.require_text(self.next_cursor, "Codex MCP server page next_cursor", allow_blank=True, one_line=True)


@dataclass(frozen=True, slots=True)
class CodexMemoryStatus:
    """Codex's memory state: how many threads it has consolidated into memories, and whether they are ready."""

    consolidated_threads: int
    ready: bool

    def __post_init__(self) -> None:
        RecordFieldValidator.require_int(self.consolidated_threads, "Codex memory status consolidated_threads", minimum=0)
        RecordFieldValidator.require_bool(self.ready, "Codex memory status ready")


@dataclass(frozen=True, slots=True)
class CodexWorktree:
    """A git worktree create_codex_worktree made: its folder, its new branch, the ref it started from and its repository."""

    path: str
    branch: str
    base_ref: str
    repository: str

    def __post_init__(self) -> None:
        for name in ("path", "branch", "base_ref", "repository"):
            RecordFieldValidator.require_text(getattr(self, name), f"Codex worktree {name}")


@dataclass(frozen=True, slots=True)
class CodexBackgroundTerminal:
    """One background terminal a thread's commands left running, with its command, folder and process figures."""

    process_id: str
    item_id: str
    command: str
    cwd: str
    os_pid: int | None = None
    cpu_percent: float | None = None
    rss_kb: int | None = None

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.process_id, "Codex background terminal process_id")
        RecordFieldValidator.require_text(self.item_id, "Codex background terminal item_id")
        RecordFieldValidator.require_text(self.command, "Codex background terminal command", allow_blank=True)
        RecordFieldValidator.require_text(self.cwd, "Codex background terminal cwd", allow_blank=True)
        for name in ("os_pid", "rss_kb"):
            if getattr(self, name) is not None:
                RecordFieldValidator.require_int(getattr(self, name), f"Codex background terminal {name}", minimum=0)
        cpu = RecordFieldConverter.require_instance(self.cpu_percent, "Codex background terminal cpu_percent", (int, float), optional=True)
        if cpu is not None and not (math.isfinite(cpu) and cpu >= 0):
            raise ConfigurationError("Codex background terminal cpu_percent must be None or a finite number of at least 0.", details={"field": "Codex background terminal cpu_percent"})


@dataclass(frozen=True, slots=True)
class CodexBackgroundTerminalPage:
    """One page of background terminals, with the cursor of the next page, empty on the last."""

    terminals: tuple[CodexBackgroundTerminal, ...]
    next_cursor: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "terminals", RecordFieldConverter.to_tuple(self.terminals, "Codex background terminal page terminals", item_type=CodexBackgroundTerminal))
        RecordFieldValidator.require_text(self.next_cursor, "Codex background terminal page next_cursor", allow_blank=True, one_line=True)


@dataclass(frozen=True, slots=True)
class CodexThreadSearchHit:
    """One thread whose stored content matched a search, with the matching snippet."""

    thread: CodexThreadInfo
    snippet: str

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.thread, "Codex thread search hit thread", CodexThreadInfo)
        RecordFieldValidator.require_text(self.snippet, "Codex thread search hit snippet", allow_blank=True)


@dataclass(frozen=True, slots=True)
class CodexThreadSearchPage:
    """One page of thread search hits, with the cursors of the next and the previous page, empty at either end."""

    hits: tuple[CodexThreadSearchHit, ...]
    next_cursor: str
    backwards_cursor: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "hits", RecordFieldConverter.to_tuple(self.hits, "Codex thread search page hits", item_type=CodexThreadSearchHit))
        RecordFieldValidator.require_text(self.next_cursor, "Codex thread search page next_cursor", allow_blank=True, one_line=True)
        RecordFieldValidator.require_text(self.backwards_cursor, "Codex thread search page backwards_cursor", allow_blank=True, one_line=True)


__all__ = [
    "CodexBackgroundTerminal",
    "CodexBackgroundTerminalPage",
    "CodexMcpServer",
    "CodexMcpServerPage",
    "CodexMemoryStatus",
    "CodexPlanStep",
    "CodexThreadSearchHit",
    "CodexThreadSearchPage",
    "CodexThreadSettingsUpdate",
    "CodexTurnEvent",
    "CodexWorktree",
]
