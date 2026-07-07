"""
FILE: vidbyte/middleware/compaction/trace_render.py

PURPOSE:
    Pure renderer that turns a continual-trace artifact dict into bounded Markdown. Lets trace-backed compaction inject a readable, size-bounded trace summary into the context window without coupling the rendering logic to any runtime state.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/compaction/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.middleware.compaction.base: imported by this file.

FUNCTION INVENTORY:
    - TraceArtifactRenderer (class): public or navigational symbol owned here.
    - TraceArtifactRenderer (export): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - ValueError: raised, returned, or imported by this file. Keep context safe and grepable.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; scripts/test-security-middleware.py and compaction-related scripts when changing middleware behavior.

CONCURRENCY MODEL:
    - No explicit concurrency primitive; keep future mutable state local to calls unless documented here.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.middleware.compaction.base import TokenCounter


class TraceArtifactRenderer:
    """Deterministically renders a trace artifact dict to bounded Markdown text."""

    def __init__(self, *, fields: Sequence[str] | None = None, max_chars: int | None = None, array_head: int | None = None, array_tail: int | None = None, max_tokens: int | None = None, token_counter: TokenCounter | None = None, title: str = "Continual Trace") -> None:
        # Stores render bounds and validates that all numeric limits are non-negative.
        self.fields = tuple(fields) if fields is not None else None
        self.max_chars = max_chars
        self.array_head = array_head
        self.array_tail = array_tail
        self.max_tokens = max_tokens
        self.token_counter = token_counter
        self.title = title
        self._validate_bounds()

    def render(self, artifact: Mapping[str, Any]) -> str:
        # Renders the artifact into a titled Markdown document under the configured bounds.
        items = self._ordered_items(artifact)
        items = self._apply_token_budget(items)
        body = self._render_items(items)
        return self._apply_char_limit(body)

    @staticmethod
    def is_empty(artifact: Mapping[str, Any] | None) -> bool:
        # Returns True when the artifact is missing or every field is empty (cold-start guard).
        if not isinstance(artifact, Mapping) or not artifact:
            return True
        return not any(TraceArtifactRenderer._has_content(value) for value in artifact.values())

    @staticmethod
    def _has_content(value: Any) -> bool:
        # Returns True when a single field value carries any renderable content.
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, Mapping):
            return any(TraceArtifactRenderer._has_content(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(TraceArtifactRenderer._has_content(item) for item in value)
        return True

    def _validate_bounds(self) -> None:
        # Raises ValueError when any configured numeric bound is negative.
        for name, value in (("max_chars", self.max_chars), ("array_head", self.array_head), ("array_tail", self.array_tail), ("max_tokens", self.max_tokens)):
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative.")

    def _ordered_items(self, artifact: Mapping[str, Any]) -> list[tuple[str, Any]]:
        # Selects/order fields (subset when configured) and copies arrays so they can be trimmed.
        names = self.fields if self.fields is not None else tuple(artifact.keys())
        items: list[tuple[str, Any]] = []
        for name in names:
            if name not in artifact:
                continue
            value = artifact[name]
            items.append((name, list(value) if isinstance(value, (list, tuple, set)) else value))
        return items

    def _apply_token_budget(self, items: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
        # Drops oldest array entries first until the rendered text fits the token budget.
        if self.max_tokens is None:
            return items
        while self._token_count(self._render_items(items)) > self.max_tokens:
            if not self._drop_oldest_array_entry(items):
                break
        return items

    def _drop_oldest_array_entry(self, items: list[tuple[str, Any]]) -> bool:
        # Removes the first entry of the first non-empty array field; False when no arrays remain.
        for _, value in items:
            if isinstance(value, list) and value:
                value.pop(0)
                return True
        return False

    def _render_items(self, items: Sequence[tuple[str, Any]]) -> str:
        # Renders ordered (name, value) items into a titled Markdown document.
        lines = [f"# {self.title}"]
        for name, value in items:
            lines.append(f"\n## {name}")
            lines.extend(self._render_value(value))
        return "\n".join(lines)

    def _render_value(self, value: Any) -> list[str]:
        # Renders one field value as a bullet array, nested key/value lines, or a scalar line.
        if isinstance(value, list):
            return self._render_array(value)
        if isinstance(value, Mapping):
            return [f"- {key}: {self._scalar(item)}" for key, item in value.items()] or ["- N/A"]
        return [self._scalar(value)]

    def _render_array(self, items: Sequence[Any]) -> list[str]:
        # Renders array entries as bullets, eliding the middle when head/tail bounds are set.
        if not items:
            return ["- N/A"]
        if self.array_head is None and self.array_tail is None:
            return [f"- {self._scalar(item)}" for item in items]
        head = self.array_head or 0
        tail = self.array_tail or 0
        if len(items) <= head + tail:
            return [f"- {self._scalar(item)}" for item in items]
        omitted = len(items) - head - tail
        lines = [f"- {self._scalar(item)}" for item in items[:head]]
        lines.append(f"- ...[{omitted} omitted]...")
        lines.extend(f"- {self._scalar(item)}" for item in (items[-tail:] if tail else ()))
        return lines

    def _apply_char_limit(self, text: str) -> str:
        # Truncates rendered text to max_chars including an omitted-count marker, never exceeding the bound.
        if self.max_chars is None or len(text) <= self.max_chars:
            return text
        template = "\n...[trace truncated {count} chars]"
        marker_overhead = len(template.replace("{count}", str(len(text))))
        keep = max(0, self.max_chars - marker_overhead)
        marker = template.replace("{count}", str(len(text) - keep))
        return (text[:keep] + marker)[: self.max_chars]

    def _token_count(self, text: str) -> int:
        # Counts tokens via the injected counter or a deterministic char-based estimate.
        if self.token_counter is None:
            return max(1, math.ceil(len(text) / 4)) if text else 0
        return max(0, int(self.token_counter(text)))

    @staticmethod
    def _scalar(value: Any) -> str:
        # Renders a scalar value, mapping None to a stable placeholder.
        return "N/A" if value is None else str(value)


__all__ = [
    "TraceArtifactRenderer",
]
