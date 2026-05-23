from __future__ import annotations

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts


def agentic_loop_prompt() -> str:
    """Return the shared prompt fragment that explains the runtime loop."""
    return Prompts().get(Prompt.AGENTIC_LOOP_CONTEXT_PROMPT)


def append_agentic_loop_prompt(system_prompt: str | None) -> str:
    """Append the shared agentic-loop prompt after a system prompt."""
    loop_prompt = agentic_loop_prompt()
    if system_prompt and system_prompt.strip():
        return f"{system_prompt.strip()}\n\n{loop_prompt}"
    return loop_prompt


__all__ = [
    "agentic_loop_prompt",
    "append_agentic_loop_prompt",
]
