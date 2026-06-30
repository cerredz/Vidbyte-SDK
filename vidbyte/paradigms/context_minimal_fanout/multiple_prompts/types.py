from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class SplitPrompt:
    """One implementation prompt emitted by the splitter."""

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
        object.__setattr__(self, "owned_paths", self._text_tuple(self.owned_paths))
        object.__setattr__(self, "read_only_paths", self._text_tuple(self.read_only_paths))
        object.__setattr__(self, "commands", self._text_tuple(self.commands))
        object.__setattr__(self, "notes", self._text_tuple(self.notes))

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SplitPrompt":
        # Builds one split prompt from a JSON object emitted by the splitter.
        return cls(
            id=str(raw.get("id", "")),
            title=str(raw.get("title", "")),
            prompt=str(raw.get("prompt", "")),
            owned_paths=cls._text_tuple(raw.get("owned_paths", ())),
            read_only_paths=cls._text_tuple(raw.get("read_only_paths", ())),
            commands=cls._text_tuple(raw.get("commands", ())),
            notes=cls._text_tuple(raw.get("notes", ())),
        )

    @staticmethod
    def _text_tuple(value: object) -> tuple[str, ...]:
        # Converts strings or sequences into a clean tuple of non-empty strings.
        if value is None:
            return ()
        if isinstance(value, str):
            return (value.strip(),) if value.strip() else ()
        if isinstance(value, Sequence):
            return tuple(str(item).strip() for item in value if str(item).strip())
        return (str(value).strip(),) if str(value).strip() else ()


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
        object.__setattr__(self, "non_overlap_requirements", SplitPrompt._text_tuple(self.non_overlap_requirements))
        object.__setattr__(self, "prompts", tuple(self.prompts))

    @classmethod
    def from_json_text(cls, text: str) -> "PromptSplitPlan":
        # Parses splitter output, accepting raw JSON or a fenced JSON block.
        raw_text = cls._extract_json_text(text)
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Splitter output is not valid JSON: {exc}") from exc
        if not isinstance(raw, Mapping):
            raise ConfigurationError("Splitter output must be a JSON object.")
        return cls.from_mapping(raw)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PromptSplitPlan":
        # Converts a validated JSON object into a typed split plan.
        prompt_items = raw.get("prompts", ())
        if not isinstance(prompt_items, Sequence) or isinstance(prompt_items, (str, bytes)):
            raise ConfigurationError("Splitter output field 'prompts' must be a list.")
        prompts = tuple(SplitPrompt.from_mapping(item) for item in prompt_items if isinstance(item, Mapping))
        if len(prompts) != len(prompt_items):
            raise ConfigurationError("Every splitter prompt item must be a JSON object.")
        return cls(
            goal=str(raw.get("goal", "")),
            global_instructions=str(raw.get("global_instructions", "")),
            non_overlap_requirements=SplitPrompt._text_tuple(raw.get("non_overlap_requirements", ())),
            prompts=prompts,
        )

    def validate(self, *, max_prompt_count: int) -> None:
        # Enforces prompt count, unique ids, and unique owned path assignments.
        if not self.prompts:
            raise ConfigurationError("Prompt split plan must contain at least one implementation prompt.")
        if len(self.prompts) > max_prompt_count:
            raise ConfigurationError(f"Prompt split plan has {len(self.prompts)} prompts; maximum is {max_prompt_count}.")
        self._validate_unique_ids()
        self._validate_owned_paths_do_not_overlap()

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
        lines.extend(self._bullet_lines(self.non_overlap_requirements))
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
        owners: dict[str, str] = {}
        conflicts: list[str] = []
        for prompt in self.prompts:
            for path in prompt.owned_paths:
                normalized = self._normalize_path(path)
                previous = owners.get(normalized)
                if previous is not None and previous != prompt.id:
                    conflicts.append(f"{path} ({previous}, {prompt.id})")
                owners[normalized] = prompt.id
        if conflicts:
            raise ConfigurationError(f"Split prompt owned_paths overlap: {', '.join(conflicts)}")

    @staticmethod
    def _extract_json_text(text: str) -> str:
        # Extracts a fenced JSON block when present, otherwise returns raw text.
        stripped = text.strip()
        if "```" not in stripped:
            return stripped
        parts = stripped.split("```")
        for index, part in enumerate(parts):
            content = part.strip()
            if not content:
                continue
            if content.startswith("json"):
                return content[4:].strip()
            if index > 0 and content.startswith("{"):
                return content
        return stripped

    @staticmethod
    def _normalize_path(path: str) -> str:
        # Normalizes path ownership keys for duplicate detection.
        return path.strip().replace("\\", "/").lower()

    @staticmethod
    def _bullet_lines(items: Sequence[str]) -> list[str]:
        # Builds Markdown bullet lines, preserving an explicit empty marker.
        if not items:
            return ["- N/A"]
        return [f"- {item}" for item in items]

    @classmethod
    def _prompt_markdown(cls, prompt: SplitPrompt) -> list[str]:
        # Renders one implementation prompt section into Markdown lines.
        lines = [
            "",
            f"### {prompt.id}: {prompt.title}",
            "",
            "#### Prompt",
            prompt.prompt,
            "",
            "#### Owned Paths",
            *cls._bullet_lines(prompt.owned_paths),
            "",
            "#### Read-Only Paths",
            *cls._bullet_lines(prompt.read_only_paths),
            "",
            "#### Commands",
            *cls._bullet_lines(prompt.commands),
            "",
            "#### Notes",
            *cls._bullet_lines(prompt.notes),
        ]
        return lines


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
    """Structured result returned by the multiple-prompts harness."""

    plan: PromptSplitPlan
    plan_markdown: str
    outputs: tuple[ImplementationOutput, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MultiplePromptFanoutSettings:
    """Configuration for the multiple-prompts fanout harness."""

    splitter_name: str = "context-minimal-splitter"
    implementation_name_prefix: str = "context-minimal-implementation"
    splitter_system_prompt: str | None = None
    implementation_system_prompt: str | None = None
    splitter_runner: object | None = None
    implementation_runner: object | None = None
    splitter_provider: str | None = None
    implementation_provider: str | None = None
    splitter_model_name: str | Sequence[str] | None = None
    implementation_model_name: str | Sequence[str] | None = None
    splitter_api_key: str | None = None
    implementation_api_key: str | None = None
    splitter_temperature: float | None = None
    implementation_temperature: float | None = None
    splitter_tools: tuple[object, ...] = ()
    implementation_tools: tuple[object, ...] = ()
    include_default_splitter_tools: bool = True
    default_tool_root: str | Path = "."
    splitter_middleware: tuple[object, ...] = ()
    implementation_middleware: tuple[object, ...] = ()
    splitter_agent_options: Mapping[str, Any] = field(default_factory=dict)
    implementation_agent_options: Mapping[str, Any] = field(default_factory=dict)
    max_prompt_count: int = 8
    max_concurrency: int = 4
    max_splitter_tokens: int | None = None
    max_implementation_tokens: int | None = None
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
        if (self.max_cost_usd is None) != (self.cost_per_million_tokens is None):
            raise ConfigurationError("max_cost_usd and cost_per_million_tokens must be provided together.")
        object.__setattr__(self, "splitter_tools", tuple(self.splitter_tools))
        object.__setattr__(self, "implementation_tools", tuple(self.implementation_tools))
        object.__setattr__(self, "splitter_middleware", tuple(self.splitter_middleware))
        object.__setattr__(self, "implementation_middleware", tuple(self.implementation_middleware))
        object.__setattr__(self, "splitter_agent_options", dict(self.splitter_agent_options))
        object.__setattr__(self, "implementation_agent_options", dict(self.implementation_agent_options))

    def with_overrides(self, **overrides: Any) -> "MultiplePromptFanoutSettings":
        # Returns a new settings object with per-run overrides applied.
        clean = {key: value for key, value in overrides.items() if value is not None}
        return replace(self, **clean)


__all__ = [
    "ContextMinimalFanoutResult",
    "ImplementationOutput",
    "MultiplePromptFanoutSettings",
    "PromptSplitPlan",
    "SplitPrompt",
]
