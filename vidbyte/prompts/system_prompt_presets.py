"""FILE: vidbyte/prompts/system_prompt_presets.py

PURPOSE: Renders the text of a system-prompt preset and composes enabled presets into an agent's system prompt.
ROLE IN CODEBASE: BaseAgent._runtime calls SystemPromptPresetComposer.compose once per runtime it builds, so every runtime type receives the composed prompt; developers call it directly to see the exact prompt an agent sends, or to attach a preset to a facade that only takes a system prompt string (CodexHarnessAgent).
ARCHITECTURE NOTE: Sits beside agentic_loop.py, the other system-prompt fragment. A preset's text is the `system_prompt` leaf of the prompt family named by the preset's value, read through the Prompts catalog, so no preset text is ever inlined in code.
COMMON MODIFICATION PATTERNS: A new preset needs a SystemPromptPreset member and a family directory; nothing here changes.
KNOWN EDGE CASES: With no presets (an empty list or None) the prompt is returned unchanged, byte for byte. A preset whose text already appears in the prompt, even with different line wrapping, is not appended again. Presets compose in SystemPromptPreset declaration order, whatever order the caller gave, so the composed prompt is stable.
RELATED DOCS: docs/design/working-principles-preset.md.
TESTS: tests/features/system_prompt_presets/test_system_prompt_presets_units.py.
"""

from __future__ import annotations

from collections.abc import Iterable

from vidbyte.lib.enums.prompts import Prompt, SystemPromptPreset
from vidbyte.prompts.catalog import Prompts


class SystemPromptPresetComposer:
    """Renders system-prompt preset text and composes it into an agent's system prompt."""

    @staticmethod
    def text(preset: SystemPromptPreset) -> str:
        """Return the exact text a preset adds, from the `system_prompt` leaf of its prompt family."""
        return Prompts().get(Prompt(f"{SystemPromptPreset(preset).value}.system_prompt")).strip()

    @classmethod
    def compose(cls, system_prompt: str | None, presets: Iterable[SystemPromptPreset] | None) -> str:
        """Return the system prompt with each enabled preset's text appended once, in preset declaration order."""
        enabled = frozenset(presets or ())
        # With nothing enabled the prompt goes out exactly as before.
        if not enabled:
            return system_prompt or ""
        # Append each enabled preset after the agent's own prompt, in a
        # fixed order, so the same set always produces the same prompt.
        composed = (system_prompt or "").strip()
        for preset in SystemPromptPreset:
            if preset not in enabled:
                continue
            text = cls.text(preset)
            # A prompt that already carries this text, for example one a
            # parent pasted into a child, does not get a second copy.
            if cls._collapsed(text) in cls._collapsed(composed):
                continue
            composed = f"{composed}\n\n{text}" if composed else text
        return composed

    @staticmethod
    def _collapsed(text: str) -> str:
        # Collapses every run of whitespace, so re-wrapped copies still match.
        return " ".join(text.split())


__all__ = ["SystemPromptPresetComposer"]
