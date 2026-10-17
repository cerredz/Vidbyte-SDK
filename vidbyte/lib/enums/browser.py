"""FILE: vidbyte/lib/enums/browser.py

PURPOSE: Defines the five closed vocabularies of the BrowserAgent: the role a browser MCP server plays, how one episode ended, the goal-card section patch_goal may change, a recheck's verdict, and the kind of a progress event.
ROLE IN CODEBASE: Typed fields of the records in vidbyte/lib/dataclasses/browser.py and of the settings, tools, goal, episode, events, and runtime modules in vidbyte/agents/browser/. Re-exported from vidbyte/lib/enums/__init__.py.
ARCHITECTURE NOTE: Every value is the member name in lowercase. The outcome, section, and verdict values are model-facing words: they appear in the worker's and the recheck's output schemas and in the patch_goal schema, so a value is a contract with the model as well as with the developer.
FUNCTION INVENTORY: No functions; five str Enums: BrowserToolRole, BrowserEpisodeOutcome, BrowserGoalSection, BrowserVerdict, and BrowserEventKind.
COMMON MODIFICATION PATTERNS: A new event is one more BrowserEventKind member and one emit call where it happens. A new patchable section is one more BrowserGoalSection member, one field on BrowserGoalCard, and one case in BrowserGoal.patch.
WHAT NOT TO DO IN THIS FILE: 1. Do not change a value; event sinks and schemas already carry it. 2. Do not add behavior or methods. 3. Do not add a section for goal or done_when; both are fixed for a run.
KNOWN EDGE CASES: READY_TO_SUBMIT is reported by a worker and never acted on by code. A recheck that fails has no verdict at all, so there is no "unavailable" member.
RELATED DOCS: docs/spec/browser-agent/spec.md (sections 8.5 and 9.1); vidbyte/agents/browser/README.md
TESTS: tests/features/browser_agent/test_browser_agent_contract.py
"""

from __future__ import annotations

from enum import Enum


class BrowserToolRole(str, Enum):
    """Which agent gets a server's tools: ACTION tools go to episode workers only, SEARCH and FETCH tools to the orchestrator."""

    ACTION = "action"
    SEARCH = "search"
    FETCH = "fetch"


class BrowserEpisodeOutcome(str, Enum):
    """How one episode ended, as the worker reports it or as code records a worker that stopped without a card."""

    DONE = "done"
    STUCK = "stuck"
    BLOCKED = "blocked"
    READY_TO_SUBMIT = "ready_to_submit"


class BrowserGoalSection(str, Enum):
    """The three goal-card sections patch_goal may change; goal and done_when are fixed for a run."""

    PLAN = "plan"
    PROGRESS = "progress"
    BLOCKERS = "blockers"


class BrowserVerdict(str, Enum):
    """A recheck's judgment of the run against its goal and done criteria."""

    CONTINUE = "continue"
    DONE = "done"
    STALLED = "stalled"


class BrowserEventKind(str, Enum):
    """The kinds of progress event a run sends to on_event, in the order a run usually emits them."""

    RUN_STARTED = "run_started"
    GOAL_SET = "goal_set"
    EPISODE_STARTED = "episode_started"
    EPISODE_FINISHED = "episode_finished"
    GOAL_PATCHED = "goal_patched"
    GOAL_RECHECKED = "goal_rechecked"
    RECIPE_RECORDED = "recipe_recorded"
    CONTEXT_REBUILT = "context_rebuilt"
    RUN_FINISHED = "run_finished"
    RUN_STOPPED = "run_stopped"


__all__ = ["BrowserEpisodeOutcome", "BrowserEventKind", "BrowserGoalSection", "BrowserToolRole", "BrowserVerdict"]
