"""FILE: vidbyte/agents/jev/prompts.py

PURPOSE: Registers every fixed JevAgent prompt by name and loads its text from the Markdown assets in vidbyte/prompts/jev/.
ROLE IN CODEBASE: JevSpecialistRouter and JevPreflightTools read their question and option text through JevPrompts.get instead of inlining strings.
ARCHITECTURE NOTE: The registry owns names and loading only; the prompt text lives in one .md file per JevPrompt member, shipped as vidbyte.prompts package data.
COMMON MODIFICATION PATTERNS: Add a JevPrompt member and a matching vidbyte/prompts/jev/<value>.md file in the same change; edit wording only in the .md file.
KNOWN EDGE CASES: Surrounding whitespace is stripped so a file's trailing newline never reaches Jev; a missing or blank asset raises ConfigurationError on first use.
RELATED DOCS: vidbyte/agents/jev/README.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py.
"""

from __future__ import annotations

from enum import StrEnum
from functools import cache
from importlib import resources

from vidbyte.lib.errors import ConfigurationError

_JEV_PROMPT_PACKAGE = "vidbyte.prompts"
_JEV_PROMPT_FOLDER = "jev"


class JevPrompt(StrEnum):
    """Names of the fixed JevAgent prompts; each value is its Markdown file stem."""

    SPECIALIST_QUESTION = "specialist_question"
    SPECIALIST_NO_MATCH = "specialist_no_match"
    TOOL_SELECTOR_QUESTION = "tool_selector_question"


class JevPrompts:
    """Registry that resolves a JevPrompt to its Markdown text."""

    @staticmethod
    def get(prompt: JevPrompt) -> str:
        """Return the stripped text of one registered Jev prompt."""
        if not isinstance(prompt, JevPrompt):
            raise ConfigurationError(f"JevPrompts.get() expects a JevPrompt member, got {type(prompt).__name__}.")
        return JevPrompts._load(prompt)

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
