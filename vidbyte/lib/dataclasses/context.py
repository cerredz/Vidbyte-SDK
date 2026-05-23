"""Context Protocol Header

Description:
    Defines structured context state data contracts for compaction tools and execution strategies.
Purpose:
    Lets compaction operate on a small protocol instead of binding to a concrete
    agent loop or provider message format, and defines shared context for harnesses/agents.
Architecture:
    - ContextMessage: Generic message record.
    - ProgressLog: Structured progress preserved during aggressive compaction.
    - ContextState: Protocol for conversation state stores.
    - ContextBudget: Model call, token, and cost budget restrictions.
    - ContextPermissions: Flagset for allowed tool/file system actions.
    - ContextToolCall: Structured record of a tool call.
    - ContextResponse: Structured model/agent response.
    - ContextArtifact: File or text intermediate product for strategies.
    - BaseContext: Baseline context with formatting capabilities.
    - StrategyContext: Pipeline strategy execution context.
    - VMAOContext: Context for verified multi-agent orchestration.
Relations:
    Used by agents, strategies, harnesses, and compaction utilities.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from vidbyte.lib.enums import BudgetPreset, PermissionPreset


@dataclass(frozen=True, slots=True)
class ContextMessage:
    """Generic message record used by compaction tools."""

    role: str
    content: str
    kind: str = "message"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextBudget:
    """Optional execution budget for strategy fanout and tool usage."""

    preset: BudgetPreset | None = None
    max_model_calls: int | None = None
    max_tokens: int | None = None
    max_latency_ms: int | None = None
    max_cost_usd: float | None = None
    max_tool_calls: int | None = None

    @classmethod
    def from_preset(cls, preset: BudgetPreset) -> "ContextBudget":
        if preset is BudgetPreset.TIGHT:
            return cls(preset=preset, max_model_calls=3, max_tokens=4000, max_latency_ms=30_000, max_tool_calls=2)
        if preset is BudgetPreset.BALANCED:
            return cls(preset=preset, max_model_calls=8, max_tokens=16_000, max_latency_ms=120_000, max_tool_calls=8)
        if preset is BudgetPreset.EXPLORATORY:
            return cls(preset=preset, max_model_calls=20, max_tokens=64_000, max_latency_ms=300_000, max_tool_calls=20)
        return cls(preset=preset)


@dataclass(frozen=True, slots=True)
class ContextPermissions:
    """Optional permissions visible to context-building strategies."""

    preset: PermissionPreset | None = None
    can_read_files: bool = False
    can_call_tools: bool = False
    can_write_files: bool = False
    can_access_network: bool = False
    can_expose_file_contents: bool = False

    @classmethod
    def from_preset(cls, preset: PermissionPreset) -> "ContextPermissions":
        if preset is PermissionPreset.READ_ONLY:
            return cls(preset=preset, can_read_files=True, can_expose_file_contents=True)
        if preset is PermissionPreset.TOOLS_ONLY:
            return cls(preset=preset, can_call_tools=True)
        if preset is PermissionPreset.TRUSTED:
            return cls(
                preset=preset,
                can_read_files=True,
                can_call_tools=True,
                can_write_files=True,
                can_access_network=True,
                can_expose_file_contents=True,
            )
        return cls(preset=preset)


@dataclass(frozen=True, slots=True)
class ContextToolCall:
    """Structured record of a tool call that is separate from model responses."""

    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    output: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProgressLog:
    """Structured progress preserved during aggressive compaction."""

    completed_tasks: tuple[str, ...] = ()
    touched_files: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()

    def to_markdown(self) -> str:
        """Render the progress log as compact Markdown."""
        sections = (
            ("Completed Tasks", self.completed_tasks),
            ("Touched Files", self.touched_files),
            ("Decisions", self.decisions),
            ("Errors", self.errors),
            ("Next Steps", self.next_steps),
        )
        lines = ["# Compacted Progress Log"]
        for title, items in sections:
            lines.append(f"\n## {title}")
            if items:
                lines.extend(f"- {item}" for item in items)
            else:
                lines.append("- N/A")
        return "\n".join(lines)


class ContextState(Protocol):
    """Protocol for mutable conversation state stores."""

    def messages(self) -> Sequence[ContextMessage]:
        """Return the current message sequence."""

    def replace_messages(self, messages: Sequence[ContextMessage]) -> None:
        """Replace the current message sequence."""


@dataclass(frozen=True, slots=True)
class ContextResponse:
    """Structured model or agent response stored separately from tool calls."""

    content: str
    sender: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextArtifact:
    """Existing output or intermediate product that a strategy should consider."""

    name: str
    content: str
    artifact_type: str = "text"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BaseContext:
    """Default context object shared by harnesses, agents, and strategies."""

    system_prompt: str | None = None
    agent_name: str | None = None
    role: str | None = None
    history: Sequence[object] = ()
    file_paths: Sequence[str] = ()
    strategy_metadata: Mapping[str, Any] = field(default_factory=dict)
    tool_calls: Sequence[ContextToolCall] = ()
    responses: Sequence[ContextResponse] = ()
    budget: ContextBudget | None = None
    artifacts: Sequence[ContextArtifact] = ()
    memory: str | None = None
    permissions: ContextPermissions | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def build_context(self) -> str:
        parts: list[str] = []
        if self.system_prompt:
            parts.append(f"System prompt:\n{self.system_prompt}")
        if self.memory:
            parts.append(f"Memory summary:\n{self.memory}")
        if self.history:
            parts.append("History:\n" + "\n".join(str(item) for item in self.history))
        if self.metadata:
            parts.append(f"Run metadata:\n{self.metadata}")
        if self.budget:
            parts.append(f"Budget:\n{self.budget}")
        if self.artifacts:
            parts.append("Artifacts:\n" + "\n\n".join(f"{artifact.name} ({artifact.artifact_type}):\n{artifact.content}" for artifact in self.artifacts))
        if self.responses:
            parts.append("Responses:\n" + "\n\n".join(response.content for response in self.responses))
        if self.tool_calls:
            parts.append("Tool calls:\n" + "\n".join(f"{call.name}: args={dict(call.arguments)} output={call.output}" for call in self.tool_calls))
        file_context = self._build_file_context()
        if file_context:
            parts.append(file_context)
        return "\n\n".join(parts)

    def _build_file_context(self) -> str:
        if not self.file_paths:
            return ""
        permissions = self.permissions or ContextPermissions()
        if not (permissions.can_read_files and permissions.can_expose_file_contents):
            return "File paths requested but file content exposure is not permitted:\n" + "\n".join(self.file_paths)
        sections: list[str] = []
        for raw_path in self.file_paths:
            path = Path(raw_path)
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as exc:
                content = f"<unable to read file: {type(exc).__name__}>"
            sections.append(f"File: {raw_path}\n{content}")
        return "Files:\n\n" + "\n\n".join(sections)


@dataclass(frozen=True, slots=True)
class StrategyContext(BaseContext):
    """Per-run context passed through strategies and agents."""


@dataclass(frozen=True, slots=True)
class BaseAgentContext(StrategyContext):
    """Context object built by BaseAgent before delegating to a strategy or runner."""


@dataclass(frozen=True, slots=True)
class VMAOContext(StrategyContext):
    """Context used by verified multi-agent orchestration loops."""

    round_index: int | None = None
    planner_notes: str | None = None
    verifier_notes: str | None = None
