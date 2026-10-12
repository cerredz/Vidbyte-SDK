"""FILE: vidbyte/lib/util/prompt_placement.py

PURPOSE: Finds where a separately delivered prompt belongs in a provider-shaped chat history.
ROLE IN CODEBASE: Called by the OpenAI-compatible, Anthropic, and OpenAI Responses providers.
ARCHITECTURE NOTE: Shape-agnostic; each provider passes its own call-turn and user-turn predicates.
FUNCTION INVENTORY: PromptPlacement.index(turns, is_call_turn, is_user_turn) -> int, plus the
    chat-shaped predicates is_chat_call_turn and is_chat_user_turn.
COMMON MODIFICATION PATTERNS: Keep the call-turn rule in step with GeminiProvider._prompt_index.
WHAT NOT TO DO: Do not import provider modules; predicates arrive as arguments. Do not move the
    prompt ahead of a leading assistant turn; only Gemini needs that, and it keeps its own rule.
KNOWN EDGE CASES: A history whose first call is already introduced by a user turn appends.
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
    def index(turns: Sequence[Turn], *, is_call_turn: Callable[[Turn], bool], is_user_turn: Callable[[Turn], bool]) -> int:
        # The runtime hands this run's tool exchange in the history and the prompt that provoked
        # it separately, so appending the prompt sends the task again after the work it caused
        # and the model restarts instead of finishing. Slot the prompt in front of the first
        # call turn that no user turn introduces; otherwise it appends. A caller's history that
        # opens with an assistant turn, such as a greeting, keeps it in front: unlike Gemini,
        # whose _prompt_index also moves the prompt ahead of a leading model turn, these
        # providers accept a history that starts with the assistant.
        # @intent prompt-opens-its-tool-exchange
        for position, turn in enumerate(turns):
            if is_call_turn(turn):
                return len(turns) if position and is_user_turn(turns[position - 1]) else position
        return len(turns)

    @staticmethod
    def is_chat_call_turn(turn: Turn) -> bool:
        # A chat-shaped assistant turn carrying tool_calls, or a Responses function_call item.
        return turn.get("type") == "function_call" or (turn.get("role") == "assistant" and bool(turn.get("tool_calls")))

    @staticmethod
    def is_chat_user_turn(turn: Turn) -> bool:
        # Chat-shaped tool results use role "tool", so a user role is always a user's own turn.
        return turn.get("role") == "user"
