"""Context Protocol Header

Description:
    Defines the typed data contracts and settings for the context-minimal fanout
    paradigm: environment context, split prompts, split plan, per-branch output,
    the final result, and the harness settings object.
Purpose:
    Keeps all frozen dataclasses and validation for the four-stage pipeline in one
    place so the orchestrator stays thin.
Architecture:
    - EnvironmentContext / ContextFile: compressed output of the context agent.
    - SplitPrompt / PromptSplitPlan: structured splitter/adversarial output.
    - ImplementationOutput / ContextMinimalFanoutResult: fanout results.
    - ContextMinimalFanoutSettings: per-role configuration for the four stages.
Relations:
    Consumed by vidbyte.paradigms.context_minimal_fanout.paradigm and built from
    OutputSchemaBuilder snapshots.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    # Avoids a runtime circular import; ContextManager is only used as a type hint
    # and inside from_manager where it is imported lazily.
    from vidbyte.context.manager import ContextManager


@dataclass(frozen=True, slots=True)
class ContextFile:
    """One repository file the context agent judged relevant."""

    path: str
    notes: str = ""
    content: str = ""
    model_comments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Normalizes and validates the file path.
        if not self.path.strip():
            raise ConfigurationError("ContextFile path cannot be empty.")
        object.__setattr__(self, "path", self.path.strip())
        object.__setattr__(self, "notes", self.notes.strip())
        object.__setattr__(self, "content", self.content.strip())
        object.__setattr__(self, "model_comments", _text_tuple(self.model_comments))

    @classmethod
    def from_value(cls, value: Any) -> "ContextFile | None":
        # Builds a ContextFile from a mapping or a bare path string.
        if isinstance(value, Mapping):
            path = str(value.get("path", "")).strip()
            if not path:
                return None
            notes = str(value.get("notes", value.get("excerpt", ""))).strip()
            content = str(value.get("content", value.get("full_file", value.get("full_text", "")))).strip()
            comments = value.get("model_comments", value.get("comments", ()))
            return cls(path=path, notes=notes, content=content, model_comments=_text_tuple(comments))
        text = str(value).strip()
        return cls(path=text) if text else None


@dataclass(frozen=True, slots=True)
class EnvironmentSummary:
    """Domain-neutral summary of the environment and request shape."""

    overview: str
    objective: str = ""
    domain: str = ""
    major_details: tuple[str, ...] = ()
    connections: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    additional: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes all summary subfields while preserving unknown summary details.
        object.__setattr__(self, "overview", self.overview.strip())
        object.__setattr__(self, "objective", self.objective.strip())
        object.__setattr__(self, "domain", self.domain.strip())
        object.__setattr__(self, "major_details", _entry_tuple(self.major_details))
        object.__setattr__(self, "connections", _entry_tuple(self.connections))
        object.__setattr__(self, "constraints", _entry_tuple(self.constraints))
        object.__setattr__(self, "open_questions", _entry_tuple(self.open_questions))
        object.__setattr__(self, "additional", dict(self.additional))

    @classmethod
    def from_value(cls, value: Any, *, fallback_text: str = "") -> "EnvironmentSummary":
        # Builds an EnvironmentSummary from either a mapping or a legacy scalar summary.
        if isinstance(value, Mapping):
            known = {"overview", "summary", "objective", "domain", "major_details", "connections", "constraints", "open_questions"}
            overview = str(value.get("overview", value.get("summary", ""))).strip() or fallback_text.strip()
            additional = {str(key): raw for key, raw in value.items() if str(key) not in known}
            return cls(
                overview=overview,
                objective=str(value.get("objective", "")).strip(),
                domain=str(value.get("domain", "")).strip(),
                major_details=_entry_tuple(value.get("major_details")),
                connections=_entry_tuple(value.get("connections")),
                constraints=_entry_tuple(value.get("constraints")),
                open_questions=_entry_tuple(value.get("open_questions")),
                additional=additional,
            )
        overview = str(value or "").strip() or fallback_text.strip()
        return cls(overview=overview)


@dataclass(frozen=True, slots=True)
class EnvironmentContext:
    """Compressed structured context extracted by the context agent."""

    summary: EnvironmentSummary
    files: tuple[ContextFile, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Normalizes the summary, file list, and notes.
        summary = self.summary if isinstance(self.summary, EnvironmentSummary) else EnvironmentSummary.from_value(self.summary)
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "files", tuple(self.files))
        object.__setattr__(self, "notes", _text_tuple(self.notes))

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Any], *, fallback_text: str = "") -> "EnvironmentContext":
        # Maps an OutputSchemaBuilder snapshot into typed environment context.
        values = dict(snapshot.get("values", {}))
        summary = EnvironmentSummary.from_value(values.get("summary"), fallback_text=fallback_text)
        files = tuple(f for f in (ContextFile.from_value(item) for item in _as_list(values.get("files"))) if f is not None)
        notes = [*_text_tuple(values.get("notes"))]
        for name, value in values.items():
            if name not in {"summary", "files", "notes"}:
                notes.extend(f"{name}: {entry}" for entry in _entry_tuple(value))
        return cls(
            summary=summary,
            files=files,
            notes=tuple(notes),
        )

    @classmethod
    def from_manager(cls, manager: ContextManager, *, fallback_text: str = "") -> "EnvironmentContext":
        # Builds an EnvironmentContext from a ContextManager's primitives.
        from vidbyte.context.primitives import (
            FileContextItem,
            MemoryContextItem,
            TextContextItem,
        )
        items = list(manager.items())
        files = tuple(
            ContextFile(
                path=item.path,
                notes=getattr(item, "excerpt", "") or "",
                content=getattr(item, "content", None) or "",
                model_comments=_text_tuple(getattr(item, "metadata", {}).get("model_comments", ())),
            )
            for item in items
            if isinstance(item, FileContextItem)
        )
        notes = tuple(item.to_context_text() for item in items if isinstance(item, MemoryContextItem))
        summary_text = fallback_text
        extra_notes: list[str] = []
        for item in items:
            if isinstance(item, TextContextItem):
                kind = item.kind
                text = item.to_context_text()
                if kind == "summary":
                    summary_text = summary_text or text
                else:
                    extra_notes.append(f"{kind}: {text}")
        return cls(
            summary=EnvironmentSummary.from_value(summary_text),
            files=files,
            notes=(*notes, *extra_notes),
        )

    def to_prompt_block(self) -> str:
        # Renders the environment context as a stable prompt block for later agents.
        lines = ["<environment_context>"]
        lines.extend(self._render_summary_section())
        lines.extend(self._render_files_section())
        lines.extend(self._render_text_section("notes", self.notes))
        lines.append("</environment_context>")
        return "\n".join(lines)

    def _render_summary_section(self) -> list[str]:
        # Renders the structured summary subfields as a tagged block.
        lines = ["<summary>", "<overview>", self.summary.overview or "N/A", "</overview>", ""]
        if self.summary.objective:
            lines.extend(["<objective>", self.summary.objective, "</objective>", ""])
        if self.summary.domain:
            lines.extend(["<domain>", self.summary.domain, "</domain>", ""])
        lines.extend(self._render_text_section("major_details", self.summary.major_details))
        lines.extend(self._render_text_section("connections", self.summary.connections))
        lines.extend(self._render_text_section("constraints", self.summary.constraints))
        lines.extend(self._render_text_section("open_questions", self.summary.open_questions))
        for name, value in self.summary.additional.items():
            lines.extend(self._render_text_section(name, _entry_tuple(value)))
        lines.extend(["</summary>", ""])
        return lines

    def _render_files_section(self) -> list[str]:
        # Renders each relevant file with model comments and captured content.
        lines = ["<files>"]
        if self.files:
            for item in self.files:
                lines.append(f"<file path=\"{_escape_attr(item.path)}\">")
                if item.notes:
                    lines.extend(["<notes>", item.notes, "</notes>"])
                lines.extend(self._render_text_section("model_comments", item.model_comments))
                lines.extend(["<content>", item.content or "N/A", "</content>"])
                lines.append("</file>")
            lines.extend(["</files>", ""])
            return lines
        lines.append("- N/A")
        lines.extend(["</files>", ""])
        return lines

    @staticmethod
    def _render_text_section(tag: str, entries: tuple[str, ...]) -> list[str]:
        # Renders a text-entry tuple as a tagged bullet list.
        if not entries:
            return [f"<{tag}>", "- N/A", f"</{tag}>", ""]
        lines = [f"<{tag}>"]
        lines.extend(f"- {entry}" for entry in entries)
        lines.extend([f"</{tag}>", ""])
        return lines


@dataclass(frozen=True, slots=True)
class SplitPrompt:
    """One implementation prompt emitted by the splitter or adversarial agent."""

    id: str
    title: str
    prompt: str
    owned_paths: tuple[str, ...] = ()
    read_only_paths: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Normalizes sequence fields and validates required text fields.
        if not self.id.strip():
            raise ConfigurationError("SplitPrompt id cannot be empty.")
        if not self.title.strip():
            raise ConfigurationError("SplitPrompt title cannot be empty.")
        if not self.prompt.strip():
            raise ConfigurationError("SplitPrompt prompt cannot be empty.")
        object.__setattr__(self, "id", self.id.strip())
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "prompt", self.prompt.strip())
        object.__setattr__(self, "owned_paths", _text_tuple(self.owned_paths))
        object.__setattr__(self, "read_only_paths", _text_tuple(self.read_only_paths))
        object.__setattr__(self, "commands", _text_tuple(self.commands))
        object.__setattr__(self, "notes", _text_tuple(self.notes))

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SplitPrompt":
        # Builds one split prompt from a structured object emitted by an agent.
        return cls(
            id=str(raw.get("id", "")),
            title=str(raw.get("title", "")),
            prompt=str(raw.get("prompt", "")),
            owned_paths=_text_tuple(raw.get("owned_paths", ())),
            read_only_paths=_text_tuple(raw.get("read_only_paths", ())),
            commands=_text_tuple(raw.get("commands", ())),
            notes=_text_tuple(raw.get("notes", ())),
        )


@dataclass(frozen=True, slots=True)
class PromptSplitPlan:
    """Structured split plan produced before fanout execution."""

    goal: str
    global_instructions: str
    non_overlap_requirements: tuple[str, ...]
    prompts: tuple[SplitPrompt, ...]

    def __post_init__(self) -> None:
        # Normalizes plan fields and rejects missing high-level instructions.
        if not self.goal.strip():
            raise ConfigurationError("PromptSplitPlan goal cannot be empty.")
        if not self.global_instructions.strip():
            raise ConfigurationError("PromptSplitPlan global_instructions cannot be empty.")
        object.__setattr__(self, "goal", self.goal.strip())
        object.__setattr__(self, "global_instructions", self.global_instructions.strip())
        object.__setattr__(self, "non_overlap_requirements", _text_tuple(self.non_overlap_requirements))
        object.__setattr__(self, "prompts", tuple(self.prompts))

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Any]) -> "PromptSplitPlan":
        # Builds a split plan from an OutputSchemaBuilder snapshot.
        values = dict(snapshot.get("values", {}))
        prompt_items = _as_list(values.get("prompts"))
        prompts = tuple(SplitPrompt.from_mapping(item) for item in prompt_items if isinstance(item, Mapping))
        if len(prompts) != len(prompt_items):
            raise ConfigurationError("Every splitter prompt entry must be a structured object.")
        return cls(
            goal=str(values.get("goal", "")),
            global_instructions=str(values.get("global_instructions", "")),
            non_overlap_requirements=_text_tuple(values.get("non_overlap_requirements", ())),
            prompts=prompts,
        )

    def with_prompts(self, prompts: Sequence[SplitPrompt]) -> "PromptSplitPlan":
        # Returns a copy of the plan carrying a replacement prompt list.
        return replace(self, prompts=tuple(prompts))

    def validate(self, *, max_prompt_count: int) -> None:
        # Enforces prompt count, unique ids, and unique owned path assignments.
        if not self.prompts:
            raise ConfigurationError("Prompt split plan must contain at least one implementation prompt.")
        if len(self.prompts) > max_prompt_count:
            raise ConfigurationError(f"Prompt split plan has {len(self.prompts)} prompts; maximum is {max_prompt_count}.")
        self._validate_unique_ids()
        self._validate_owned_paths_do_not_overlap()

    def overlap_conflicts(self) -> tuple[str, ...]:
        # Returns human-readable owned-path conflicts without raising.
        owners: dict[str, str] = {}
        conflicts: list[str] = []
        for prompt in self.prompts:
            for path in prompt.owned_paths:
                normalized = _normalize_path(path)
                previous = owners.get(normalized)
                if previous is not None and previous != prompt.id:
                    conflicts.append(f"{path} owned by both {previous} and {prompt.id}")
                owners[normalized] = prompt.id
        return tuple(conflicts)

    def to_markdown(self) -> str:
        # Renders the split plan into the Markdown artifact shape used by agents.
        lines = [
            "# Context Minimal Fanout Split Plan",
            "",
            "## Goal",
            self.goal,
            "",
            "## Instructions",
            self.global_instructions,
            "",
            "## Non-Overlap Requirements",
        ]
        lines.extend(_bullet_lines(self.non_overlap_requirements))
        lines.extend(["", "## Implementation Prompts"])
        for prompt in self.prompts:
            lines.extend(self._prompt_markdown(prompt))
        return "\n".join(lines).rstrip() + "\n"

    def _validate_unique_ids(self) -> None:
        # Rejects duplicate prompt identifiers before agents are launched.
        seen: set[str] = set()
        duplicates: list[str] = []
        for prompt in self.prompts:
            if prompt.id in seen:
                duplicates.append(prompt.id)
            seen.add(prompt.id)
        if duplicates:
            raise ConfigurationError(f"Duplicate split prompt ids: {', '.join(sorted(set(duplicates)))}")

    def _validate_owned_paths_do_not_overlap(self) -> None:
        # Rejects duplicate ownership of the same normalized path.
        conflicts = self.overlap_conflicts()
        if conflicts:
            raise ConfigurationError(f"Split prompt owned_paths overlap: {', '.join(conflicts)}")

    @classmethod
    def _prompt_markdown(cls, prompt: SplitPrompt) -> list[str]:
        # Renders one implementation prompt section into Markdown lines.
        return [
            "",
            f"### {prompt.id}: {prompt.title}",
            "",
            "#### Prompt",
            prompt.prompt,
            "",
            "#### Owned Paths",
            *_bullet_lines(prompt.owned_paths),
            "",
            "#### Read-Only Paths",
            *_bullet_lines(prompt.read_only_paths),
            "",
            "#### Commands",
            *_bullet_lines(prompt.commands),
            "",
            "#### Notes",
            *_bullet_lines(prompt.notes),
        ]


@dataclass(frozen=True, slots=True)
class ImplementationOutput:
    """One implementation branch output or captured branch error."""

    prompt_id: str
    title: str
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ContextMinimalFanoutResult:
    """Structured result returned by the context-minimal fanout paradigm."""

    plan: PromptSplitPlan
    plan_markdown: str
    environment: EnvironmentContext
    outputs: tuple[ImplementationOutput, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentRoleSettings:
    """Per-role configuration for one pipeline stage agent."""

    name: str = ""
    system_prompt: str | None = None
    runner: object | None = None
    provider: str | None = None
    model_name: str | Sequence[str] | None = None
    api_key: str | None = None
    temperature: float | None = None
    tools: tuple[object, ...] = ()
    middleware: tuple[object, ...] = ()
    agent_options: Mapping[str, Any] = field(default_factory=dict)
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        # Normalizes tuple and mapping fields.
        object.__setattr__(self, "tools", _object_tuple(self.tools))
        object.__setattr__(self, "middleware", _object_tuple(self.middleware))
        object.__setattr__(self, "agent_options", dict(self.agent_options))

    def with_overrides(self, **overrides: Any) -> "AgentRoleSettings":
        # Returns a new settings object with per-run overrides applied.
        clean = {key: value for key, value in overrides.items() if value is not None}
        return replace(self, **clean)


@dataclass(frozen=True, slots=True)
class ContextMinimalFanoutSettings:
    """Per-role configuration for the four-stage context-minimal fanout pipeline."""

    # Per-role agent settings.
    context: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="context-minimal-context"))
    splitter: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="context-minimal-splitter"))
    adversarial: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="context-minimal-adversarial"))
    implementation: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="context-minimal-implementation"))

    # Adversarial loop control.
    max_adversarial_rounds: int = 2

    # Shared toolset controls.
    include_minimal_toolset: bool = True
    default_tool_root: str | Path = "."
    include_execution_tool: bool = True
    implementation_include_write: bool = True

    # Fanout shape, budgets, behavior.
    max_prompt_count: int = 8
    max_concurrency: int = 4
    max_cost_usd: float | None = None
    cost_per_million_tokens: float | None = None
    return_exceptions: bool = True
    plan_output_path: str | Path | None = None

    def __post_init__(self) -> None:
        # Validates numeric limits and normalizes the default_tool_root path.
        if self.max_prompt_count <= 0:
            raise ConfigurationError("max_prompt_count must be greater than zero.")
        if self.max_concurrency <= 0:
            raise ConfigurationError("max_concurrency must be greater than zero.")
        if self.max_adversarial_rounds <= 0:
            raise ConfigurationError("max_adversarial_rounds must be greater than zero.")
        if (self.max_cost_usd is None) != (self.cost_per_million_tokens is None):
            raise ConfigurationError("max_cost_usd and cost_per_million_tokens must be provided together.")

    def with_overrides(self, **overrides: Any) -> "ContextMinimalFanoutSettings":
        # Returns a new settings object with per-run overrides applied.
        clean = {key: value for key, value in overrides.items() if value is not None}
        return replace(self, **clean)


def _text_tuple(value: object) -> tuple[str, ...]:
    # Converts strings or sequences into a clean tuple of non-empty strings.
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, Sequence):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def _render_mapping(m: Mapping[str, Any]) -> str:
    # Renders a mapping as a readable "key: value — key: value" string.
    return " — ".join(f"{k}: {v}" for k, v in m.items() if str(v).strip())


def _entry_tuple(value: object) -> tuple[str, ...]:
    # Converts strings, sequences, or mappings into a clean tuple of rendered strings.
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, Mapping):
        rendered = _render_mapping(value)
        return (rendered,) if rendered else ()
    if isinstance(value, Sequence):
        entries: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                rendered = _render_mapping(item)
                if rendered:
                    entries.append(rendered)
            else:
                text = str(item).strip()
                if text:
                    entries.append(text)
        return tuple(entries)
    return (str(value).strip(),) if str(value).strip() else ()


def _as_list(value: object) -> tuple[Any, ...]:
    # Normalizes a possibly-scalar snapshot value into a tuple of items.
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)


def _bullet_lines(items: Sequence[str]) -> list[str]:
    # Builds Markdown bullet lines, preserving an explicit empty marker.
    if not items:
        return ["- N/A"]
    return [f"- {item}" for item in items]


def _normalize_path(path: str) -> str:
    # Normalizes path ownership keys for duplicate detection.
    return path.strip().replace("\\", "/").lower()


def _escape_attr(value: str) -> str:
    # Escapes the small subset needed for XML-style attribute rendering.
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def _object_tuple(value: object) -> tuple[object, ...]:
    # Normalizes single objects, sequences, and Tools-like catalogs into tuples.
    if value is None:
        return ()
    all_items = getattr(value, "all", None)
    if callable(all_items):
        return tuple(all_items())
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


__all__ = [
    "AgentRoleSettings",
    "ContextFile",
    "ContextMinimalFanoutResult",
    "ContextMinimalFanoutSettings",
    "EnvironmentContext",
    "EnvironmentSummary",
    "ImplementationOutput",
    "PromptSplitPlan",
    "SplitPrompt",
]
