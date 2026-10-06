"""FILE: vidbyte/agents/jev/compute/states.py

PURPOSE: Build bounded shared dynamic-compute state from the request, verified brief, exact facts, and recent numbered events.
ROLE IN CODEBASE: JevComputeRecognizer sends this mapping with all enabled option questions in one Jev request.
ARCHITECTURE NOTE: Every option reads the same state; only the newest bounded event-log tail is included.
COMMON MODIFICATION PATTERNS: Keep the state keys shared with question records in vidbyte/lib/jev/compute/.
KNOWN EDGE CASES: The request and each recent event are clipped with an omitted-character marker; only the latest twelve events are retained.
RELATED DOCS: docs/design/jev-compute-situations.md.
TESTS: tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

from collections.abc import Mapping

from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.lib.constants.jev import (
    JEV_RUN_BRIEF_CLIP_HEAD_SHARE,
    JEV_RUN_BRIEF_REQUEST_MAX_CHARS,
)
from vidbyte.lib.dataclasses.jev import JevRunBrief, JevRunFacts

ComputeState = Mapping[str, object]
_RECENT_EVENT_COUNT = 12
_RECENT_EVENT_MAX_CHARS = 2_000
_CLIP_MIN_AVAILABLE_CHARS = 0
_CLIP_MARKER_RESERVE_CHARS = 32
_CLIP_NO_OVERFLOW = 0


class JevComputeStates:
    """Render request, verified brief, exact facts, and a bounded event-log tail."""

    @classmethod
    def build(cls, request: str, brief: JevRunBrief, facts: JevRunFacts, events: JevRunEventLog) -> ComputeState:
        """Return the single shared evidence mapping used for every enabled option."""
        # @intent every-option-reads-the-same-bounded-evidence
        # The verified brief and exact fact fields stay intact, while request and recent event text have explicit size bounds.
        event_lines = tuple(line for line in events.lines if not line.partition(" ")[2].startswith("USER: "))
        recent = "\n".join(cls._clip(line, _RECENT_EVENT_MAX_CHARS) for line in event_lines[-_RECENT_EVENT_COUNT:])
        return {
            "request": cls._clip(request, JEV_RUN_BRIEF_REQUEST_MAX_CHARS),
            "brief": brief.render(),
            "facts": {
                "iteration": facts.iteration,
                "tool_calls": facts.tool_calls,
                "error_streak": facts.error_streak,
                "tokens_used": facts.tokens_used,
            },
            "recent": recent,
        }

    @staticmethod
    def _clip(text: str, limit: int) -> str:
        """Keep a bounded head and tail and show how many characters were omitted."""
        if len(text) <= limit:
            return text
        available = max(_CLIP_MIN_AVAILABLE_CHARS, limit - _CLIP_MARKER_RESERVE_CHARS)
        head = int(available * JEV_RUN_BRIEF_CLIP_HEAD_SHARE)
        tail = available - head
        while True:
            marker = f" [...] {len(text) - head - tail} chars omitted [...] "
            overflow = head + tail + len(marker) - limit
            if overflow <= _CLIP_NO_OVERFLOW:
                return f"{text[:head]}{marker}{text[-tail:] if tail else ''}"
            reduction = min(overflow, tail)
            tail -= reduction
            head -= overflow - reduction


__all__ = ["JevComputeStates"]
