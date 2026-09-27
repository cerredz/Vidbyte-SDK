"""FILE: vidbyte/agents/jev/prompts.py

PURPOSE: Registers Jev question assets and turns the profile-selection Markdown brief into a validated typed question brief and option criteria.
ROLE IN CODEBASE: `JevAgentRouter` reads the structured selection brief and criteria here; `JevPreflightTools` reads its fixed question text here.
ARCHITECTURE NOTE: The registry owns prompt names, resource loading, and the stable section-to-JevBrief mapping; all authored wording remains in packaged Markdown.
FUNCTION INVENTORY: `JevPrompts.get(prompt)` returns cached asset text; `brief(prompt)` validates the five JevBrief sections; `selection_criteria()` builds structured Choice option criteria. Errors are `ConfigurationError`.
COMMON MODIFICATION PATTERNS: Change wording only in the Markdown asset; when adding a prompt, add a `JevPrompt` member, packaged file, and an asset/brief test together.
WHAT NOT TO DO IN THIS FILE: 1. Do not make routing decisions; `vidbyte/agents/jev/specialists.py` owns selection policy. 2. Do not put provider JSON encoding here; the TypeSafe adapter owns the wire.
KNOWN EDGE CASES: Surrounding whitespace is stripped; missing, empty, duplicated, or incomplete sections fail before sending a Jev request.
RELATED DOCS: vidbyte/agents/jev/README.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py.
"""

from __future__ import annotations

from functools import cache
from importlib import resources
from typing import cast

from vidbyte.lib.dataclasses.jev import JevBrief, JevCriterion
from vidbyte.lib.enums.jev import JevPrompt
from vidbyte.lib.errors import ConfigurationError

_JEV_PROMPT_PACKAGE = "vidbyte.prompts"
_JEV_PROMPT_FOLDER = "jev"


class JevPrompts:
    """Registry that resolves a JevPrompt to its Markdown text."""

    @staticmethod
    def get(prompt: JevPrompt) -> str:
        """Return the stripped text of one registered Jev prompt."""
        if not isinstance(prompt, JevPrompt):
            raise ConfigurationError(f"JevPrompts.get() expects a JevPrompt member, got {type(prompt).__name__}.")
        return JevPrompts._load(prompt)

    @staticmethod
    def brief(prompt: JevPrompt) -> JevBrief:
        # Turns the checked Markdown sections into the typed brief the Jev question contract requires.
        sections = JevPrompts._sections(prompt)
        return JevBrief(
            introduction=cast(str, sections["introduction"]),
            state=cast(str, sections["state"]),
            definitions=cast(tuple[str, ...], sections["definitions"]),
            rules=cast(tuple[str, ...], sections["rules"]),
            question=cast(str, sections["question"]),
        )

    @staticmethod
    def selection_criteria() -> dict[str, object]:
        # Gives every candidate Choice option a mirrored, structured fit criterion.
        sections = JevPrompts._sections(JevPrompt.AGENT_SELECTION_QUESTION)
        return dict(JevCriterion(
            what=cast(str, sections["option_what"]),
            not_for=cast(str, sections["option_not_for"]),
            easy=(cast(str, sections["easy_example"]),),
            boundary=(cast(str, sections["boundary_example"]),),
        ).to_content())

    @staticmethod
    def _sections(prompt: JevPrompt) -> dict[str, str | tuple[str, ...]]:
        # Parses required heading names and rejects duplicate or missing sections before use.
        sections: dict[str, list[str]] = {}
        current = ""
        for line in JevPrompts.get(prompt).splitlines():
            if line.startswith("## "):
                current = line[3:].strip().lower().replace(" ", "_")
                if current in sections:
                    raise ConfigurationError(f"Jev prompt {prompt.name} repeats section {current!r}.")
                sections[current] = []
            elif current:
                sections[current].append(line)
        rendered: dict[str, str | tuple[str, ...]] = {name: "\n".join(lines).strip() for name, lines in sections.items()}
        required: tuple[str, ...] = ("introduction", "state", "definitions", "rules", "question")
        if prompt is JevPrompt.AGENT_SELECTION_QUESTION:
            required = (*required, "option_what", "option_not_for", "easy_example", "boundary_example")
        missing = tuple(name for name in required if not rendered.get(name))
        if missing:
            raise ConfigurationError(f"Jev prompt {prompt.name} is missing required sections: {missing}.")
        rendered["definitions"] = JevPrompts._bullet_values(cast(str, rendered["definitions"]))
        rendered["rules"] = JevPrompts._bullet_values(cast(str, rendered["rules"]))
        return rendered

    @staticmethod
    def _bullet_values(section: object) -> tuple[str, ...]:
        # Returns the non-empty bullet entries from one multi-value brief section.
        if not isinstance(section, str):
            raise ConfigurationError("Jev brief list sections must be strings.")
        lines = tuple(line.strip() for line in section.splitlines() if line.strip())
        if not lines or any(not line.startswith("- ") for line in lines):
            raise ConfigurationError("Jev brief definitions and rules must use non-empty Markdown bullet lines.")
        return tuple(line[2:].strip() for line in lines)

    @staticmethod
    @cache
    def _load(prompt: JevPrompt) -> str:
        # Reads one Markdown asset once per process; the text is immutable package data.
        asset = resources.files(_JEV_PROMPT_PACKAGE).joinpath(_JEV_PROMPT_FOLDER, f"{prompt.value}.md")
        if not asset.is_file():
            raise ConfigurationError(f"Jev prompt {prompt.name} has no asset at vidbyte/prompts/{_JEV_PROMPT_FOLDER}/{prompt.value}.md.")
        text = asset.read_text(encoding="utf-8").strip()
        if not text:
            raise ConfigurationError(f"Jev prompt asset vidbyte/prompts/{_JEV_PROMPT_FOLDER}/{prompt.value}.md is empty.")
        return text


__all__ = ["JevPrompt", "JevPrompts"]
