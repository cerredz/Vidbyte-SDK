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
from typing import Any

from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class ContextFile:
    """One repository file the context agent judged relevant."""

    path: str
    notes: str = ""

    def __post_init__(self) -> None:
        # Normalizes and validates the file path.
        if not self.path.strip():
            raise ConfigurationError("ContextFile path cannot be empty.")
        object.__setattr__(self, "path", self.path.strip())
        object.__setattr__(self, "notes", self.notes.strip())

    @classmethod
    def from_value(cls, value: Any) -> "ContextFile | None":
        # Builds a ContextFile from a mapping or a bare path string.
        if isinstance(value, Mapping):
            path = str(value.get("path", "")).strip()
            if not path:
                return None
            notes = str(value.get("notes", value.get("excerpt", ""))).strip()
            return cls(path=path, notes=notes)
        text = str(value).strip()
        return cls(path=text) if text else None


@dataclass(frozen=True, slots=True)
class EnvironmentContext:
    """Compressed structured context extracted by the context agent."""

    summary: str
    files: tuple[ContextFile, ...] = ()
    notes: tuple[str, ...] = ()
    entries: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes the summary and freezes the entries mapping.
        object.__setattr__(self, "summary", self.summary.strip())
        object.__setattr__(self, "files", tuple(self.files))
        object.__setattr__(self, "notes", _text_tuple(self.notes))
        object.__setattr__(self, "entries", dict(self.entries))

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Any], *, fallback_text: str = "") -> "EnvironmentContext":
        # Maps an OutputSchemaBuilder snapshot into typed environment context.
        values = dict(snapshot.get("values", {}))
        summary = str(values.get("summary") or "").strip() or fallback_text.strip()
        files = tuple(f for f in (ContextFile.from_value(item) for item in _as_list(values.get("files"))) if f is not None)
        notes = _text_tuple(values.get("notes"))
        return cls(summary=summary, files=files, notes=notes, entries=values)

    def to_prompt_block(self) -> str:
        # Renders the environment context as a stable prompt block for later agents.
        lines = ["<environment_context>", "<summary>", self.summary or "N/A", "</summary>", "", "<files>"]
        if self.files:
            for item in self.files:
                suffix = f" — {item.notes}" if item.notes else ""
                lines.append(f"- {item.path}{suffix}")
        else:
            lines.append("- N/A")
        lines.extend(["</files>", "", "<notes>"])
        lines.extend([f"- {note}" for note in self.notes] or ["- N/A"])
        lines.append("</notes>")
        lines.append("</environment_context>")
        return "\n".join(lines)


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
class ContextMinimalFanoutSettings:
    """Per-role configuration for the four-stage context-minimal fanout pipeline."""

    # Context agent.
    context_agent_name: str = "context-minimal-context"
    context_system_prompt: str | None = None
    context_runner: object | None = None
    context_provider: str | None = None
    context_model_name: str | Sequence[str] | None = None
    context_api_key: str | None = None
    context_temperature: float | None = None
    context_tools: tuple[object, ...] = ()
    context_middleware: tuple[object, ...] = ()
    context_agent_options: Mapping[str, Any] = field(default_factory=dict)
    max_context_tokens: int | None = None

    # Splitter agent.
    splitter_name: str = "context-minimal-splitter"
    splitter_system_prompt: str | None = None
    splitter_runner: object | None = None
    splitter_provider: str | None = None
    splitter_model_name: str | Sequence[str] | None = None
    splitter_api_key: str | None = None
    splitter_temperature: float | None = None
    splitter_tools: tuple[object, ...] = ()
    splitter_middleware: tuple[object, ...] = ()
    splitter_agent_options: Mapping[str, Any] = field(default_factory=dict)
    max_splitter_tokens: int | None = None

    # Adversarial agent.
    adversarial_name: str = "context-minimal-adversarial"
    adversarial_system_prompt: str | None = None
    adversarial_runner: object | None = None
    adversarial_provider: str | None = None
    adversarial_model_name: str | Sequence[str] | None = None
    adversarial_api_key: str | None = None
    adversarial_temperature: float | None = None
    adversarial_tools: tuple[object, ...] = ()
    adversarial_middleware: tuple[object, ...] = ()
    adversarial_agent_options: Mapping[str, Any] = field(default_factory=dict)
    max_adversarial_tokens: int | None = None
    max_adversarial_rounds: int = 2

    # Implementation agents.
    implementation_name_prefix: str = "context-minimal-implementation"
    implementation_system_prompt: str | None = None
    implementation_runner: object | None = None
    implementation_provider: str | None = None
    implementation_model_name: str | Sequence[str] | None = None
    implementation_api_key: str | None = None
    implementation_temperature: float | None = None
    implementation_tools: tuple[object, ...] = ()
    implementation_middleware: tuple[object, ...] = ()
    implementation_agent_options: Mapping[str, Any] = field(default_factory=dict)
    max_implementation_tokens: int | None = None

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
        # Normalizes tuple-like settings and validates numeric limits.
        if self.max_prompt_count <= 0:
            raise ConfigurationError("max_prompt_count must be greater than zero.")
        if self.max_concurrency <= 0:
            raise ConfigurationError("max_concurrency must be greater than zero.")
        if self.max_adversarial_rounds <= 0:
            raise ConfigurationError("max_adversarial_rounds must be greater than zero.")
        if (self.max_cost_usd is None) != (self.cost_per_million_tokens is None):
            raise ConfigurationError("max_cost_usd and cost_per_million_tokens must be provided together.")
        for tuple_field in ("context_tools", "splitter_tools", "adversarial_tools", "implementation_tools", "context_middleware", "splitter_middleware", "adversarial_middleware", "implementation_middleware"):
            object.__setattr__(self, tuple_field, _object_tuple(getattr(self, tuple_field)))
        for map_field in ("context_agent_options", "splitter_agent_options", "adversarial_agent_options", "implementation_agent_options"):
            object.__setattr__(self, map_field, dict(getattr(self, map_field)))

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
    "ContextFile",
    "ContextMinimalFanoutResult",
    "ContextMinimalFanoutSettings",
    "EnvironmentContext",
    "ImplementationOutput",
    "PromptSplitPlan",
    "SplitPrompt",
]
