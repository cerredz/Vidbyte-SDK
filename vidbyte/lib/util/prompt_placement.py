"""FILE: vidbyte/lib/util/prompt_placement.py

PURPOSE: Finds where a separately delivered prompt belongs in a provider-shaped chat history.
ROLE IN CODEBASE: Called by the OpenAI-compatible, Anthropic, and OpenAI Responses providers.
ARCHITECTURE NOTE: Shape-agnostic; each provider passes its own call-turn predicate.
FUNCTION INVENTORY: PromptPlacement.index(turns, is_call_turn, boundary) -> int, plus the chat-shaped
    predicate is_chat_call_turn.
COMMON MODIFICATION PATTERNS: Keep the call-turn rule in step with GeminiProvider._prompt_index.
WHAT NOT TO DO: Do not import provider modules; predicates arrive as arguments. Do not move the
    prompt ahead of a leading assistant turn; only Gemini needs that, and it keeps its own rule.
KNOWN EDGE CASES: A runtime boundary in range wins; without one, calls after a user turn or tool result
    are skipped, and with none left the prompt appends.
RELATED DOCS: vidbyte/providers/gemini.py (_prompt_index) applies the call-turn rule to Gemini contents.
TESTS: tests/test_prompt_opens_tool_exchange.py.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

Turn = Mapping[str, Any]


class PromptPlacement:
    """Places the run's prompt in front of the tool exchange it provoked."""

    @staticmethod
    def index(turns: Sequence[Turn], *, is_call_turn: Callable[[Turn], bool], boundary: int | None = None) -> int:
        # The runtime may say where the caller's history ends and this run's exchange begins. That wins,
        # because a rejected plain draft and its feedback look exactly like a caller's greeting and question.
        # @intent prompt-sits-at-the-run-boundary
        if boundary is not None and boundary <= len(turns):
            return boundary
        # The runtime hands this run's tool exchange in the history and the prompt that provoked
        # it separately, so appending the prompt sends the task again after the work it caused
        # and the model restarts instead of finishing. Slot the prompt in front of the first
        # call turn that nothing introduces: one that opens the history or follows an assistant
        # turn. A call right after a user turn or a tool result belongs to an exchange that is
        # already introduced (a replayed one, or a later round of this one), so scanning goes on
        # past it; with no such call the prompt appends. A caller's history that opens with an
        # assistant turn, such as a greeting, stays in front: unlike Gemini, whose _prompt_index
        # also moves the prompt ahead of a leading model turn, these providers accept it.
        # @intent prompt-opens-its-tool-exchange
        for position, turn in enumerate(turns):
            if is_call_turn(turn) and (position == 0 or turns[position - 1].get("role") == "assistant"):
                return position
        return len(turns)

    @staticmethod
    def is_chat_call_turn(turn: Turn) -> bool:
        # A chat-shaped assistant turn carrying tool_calls, or a Responses function_call item.
        return turn.get("type") == "function_call" or (turn.get("role") == "assistant" and bool(turn.get("tool_calls")))
