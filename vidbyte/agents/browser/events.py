"""FILE: vidbyte/agents/browser/events.py

PURPOSE: Defines BrowserAgentEvents, which numbers each BrowserAgent run's events, builds a BrowserEvent for each one, and hands it to the developer's sync on_event sink, so that a failing sink never breaks the run.
ROLE IN CODEBASE: BrowserAgent builds one per agent (vidbyte/agents/browser/agent.py) and hands it to every run-local runtime, which calls start() when a run begins; the runtime, the episode tool, and the goal card call emit() at each step. The events are the BrowserEvent records of vidbyte/lib/dataclasses/browser.py.
ARCHITECTURE NOTE: The same pattern as the MultiAgent ledger controller's _emit_event: the sink runs in line, an Exception it raises is recorded by type name on errors (which the response copies), and a BaseException such as cancellation propagates (lint S019). Details are cut to one line of BROWSER_EVENT_DETAIL_MAX_CHARS, so a long task or summary never floods a log; callers never put a key or a typed value in a detail.
FUNCTION INVENTORY: start resets the sequence and the errors for a new run; emit builds one event and delivers it.
COMMON MODIFICATION PATTERNS: A new event adds a BrowserEventKind member (vidbyte/lib/enums/browser.py) and one emit call where it happens.
WHAT NOT TO DO IN THIS FILE: 1. Do not catch BaseException or CancelledError. 2. Do not await the sink; settings refuse an async one. 3. Do not store events; the sink owns them.
KNOWN EDGE CASES: With no sink, events are still numbered, so sequence numbers stay the same whether or not a sink is set. Two overlapping runs on one agent share this object and interleave their numbers (spec EC-21).
RELATED DOCS: docs/spec/browser-agent/spec.md (sections 6.1 INV-20, 8.1 D-18, and 8.5); vidbyte/agents/browser/README.md
TESTS: tests/features/browser_agent/test_browser_agent_observability.py
"""

from __future__ import annotations

import itertools
from collections.abc import Callable

from vidbyte.lib.constants.browser import (
    BROWSER_EVENT_DETAIL_MAX_CHARS,
    BROWSER_FIRST_INDEX,
    BROWSER_MIN_COUNT,
)
from vidbyte.lib.dataclasses.browser import BrowserEvent
from vidbyte.lib.enums.browser import BrowserEventKind


class BrowserAgentEvents:
    """Numbers a run's events and delivers each one to the developer's sink, recording any Exception the sink raises."""

    def __init__(self, sink: Callable[[BrowserEvent], None] | None) -> None:
        # The sink is checked by BrowserAgentSettings; None means the
        # events are numbered and dropped.
        self._sink = sink
        self._numbers = itertools.count(BROWSER_FIRST_INDEX)
        self.errors: list[str] = []

    def start(self) -> None:
        """Begin a new run: number its events from one again and clear the recorded sink errors."""
        self._numbers = itertools.count(BROWSER_FIRST_INDEX)
        self.errors = []

    def emit(self, kind: BrowserEventKind, detail: str = "", *, episode: int = BROWSER_MIN_COUNT) -> None:
        """Build the next event, with its detail cut to one short line, and hand it to the sink."""
        line = " ".join(detail.split())[:BROWSER_EVENT_DETAIL_MAX_CHARS]
        event = BrowserEvent(kind=kind, sequence=next(self._numbers), episode=episode, detail=line)
        if self._sink is None:
            return
        # @intent a-sink-error-never-breaks-the-run
        # The sink is the developer's code; an error in it is recorded
        # by type name for agent.response.event_errors, and the run
        # goes on. Cancellation and other BaseExceptions propagate.
        try:
            self._sink(event)
        except Exception as exc:
            self.errors.append(type(exc).__name__)


__all__ = ["BrowserAgentEvents"]
