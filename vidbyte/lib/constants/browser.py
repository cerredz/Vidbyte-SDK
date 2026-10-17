"""FILE: vidbyte/lib/constants/browser.py

PURPOSE: Defines every named default, cap, tool and argument name, marker, and name template of the BrowserAgent: the orchestrator loop and its rebuild trigger, the per-episode caps, the recheck cadence and stall stop, the server timeouts, the goal-card and result-card caps, and the names of the run-bound tools and the agents a run starts.
ROLE IN CODEBASE: Read by the settings and every module in vidbyte/agents/browser/ and by the records in vidbyte/lib/dataclasses/browser.py. The feature tests import the caps and names to check behavior against them.
ARCHITECTURE NOTE: Immutable constants only; behavior lives in vidbyte/agents/browser/. The caps are sized for a 128,000-token model, counted in TokenEstimate tokens. The orchestrator's call is about 115,800 tokens at its caps: rules and developer prompt about 3,000; the goal card about 30,800 (plan 2,000, progress 24,000, blockers 2,000, criteria 2,500, and the verdict, gap, and last-episode lines 300); the goal about 2,000 (assumed); tool schemas about 4,000 (assumed); the stored history at most 60,000 at each check, because a rebuild runs after every tool iteration and every refused finish that passes it, unless the newest group alone is larger (assumed, with what a refused finish appends after its check); and 16,000 for the reply. A worker's call is about 60,000 tokens: rules and developer prompt 3,000, the task 1,000, the ACTION tool schemas about 8,000 (assumed), the outgoing history at most BROWSER_WORKER_HISTORY_MAX_TOKENS whatever the number of tools, and 16,000 for the reply. The progress section holds about 480 to 800 one-line facts at 120 to 200 characters each.
FUNCTION INVENTORY: No functions; loop and rebuild caps, episode caps, recheck caps, server timeouts, card and text caps, tool and argument names, the card's primitive id and title, markers, and agent and server name templates.
COMMON MODIFICATION PATTERNS: Change a cap here, never at its use site, so the settings, the records, the tests, and the folder README stay in step. When a cap that feeds a model call changes, recount the budget sums above. Add a named constant here before writing another BrowserAgent policy literal.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from any layer above vidbyte/lib. 2. Do not put model-facing sentences here; they belong in vidbyte/prompts/prompts/browser_agent/. 3. Do not rename a tool, argument, or primitive id; models, sinks, and tests bind to them.
KNOWN EDGE CASES: Every token figure is TokenEstimate's characters-divided-by-four estimate, not a real tokenizer count. The goal is rendered verbatim on every orchestrator call without a cap, so a very long task makes every call larger. A worker's max_iterations is max_actions plus BROWSER_EPISODE_REPLY_TURNS: one final reply and the three schema repairs AgentLoopSettings allows by default.
RELATED DOCS: docs/spec/browser-agent/spec.md (sections 9.1 and 9.3); vidbyte/agents/browser/README.md
TESTS: tests/features/browser_agent/test_browser_agent_contract.py and the rest of tests/features/browser_agent/
"""

from __future__ import annotations

# The orchestrator's default loop: at most 1,000 iterations, and every
# ordinary tool result cut at 20,000 characters, about 5,000 tokens.
BROWSER_DEFAULT_MAX_ITERATIONS = 1_000
BROWSER_TOOL_RESULT_MAX_CHARS = 20_000

# The orchestrator's stored conversation is rebuilt to its newest
# call/result group once it passes this many tokens.
BROWSER_HISTORY_MAX_TOKENS = 60_000

# Episode defaults: browser calls per episode, executed calls per
# screenshot tool, and full observations kept per tool.
BROWSER_DEFAULT_MAX_ACTIONS = 30
BROWSER_DEFAULT_MAX_SCREENSHOTS = 5
BROWSER_DEFAULT_KEEP_OBSERVATIONS = 2

# An older observation is cut to this many characters, and a stuck
# card's evidence is the newest successful result cut the same way.
BROWSER_STALE_OBSERVATION_CHARS = 400

# A worker's outgoing history is trimmed to this many tokens at
# provider boundaries, whatever the number of tools it used.
BROWSER_WORKER_HISTORY_MAX_TOKENS = 32_000

# The model turns a worker gets beyond its action cap: one final
# reply plus the three schema repairs the loop allows by default.
BROWSER_EPISODE_REPLY_TURNS = 4

# Recheck defaults: a periodic recheck after this many finished
# episodes, and a stall stop after this many stalled rechecks.
BROWSER_DEFAULT_RECHECK_EVERY = 5
BROWSER_DEFAULT_MAX_STALLS = 3

# The smallest value of every cap, so none can be switched off by
# setting it to 0.
BROWSER_MIN_CAP = 1

# The done-when and recheck agents get one answer plus one schema
# repair.
BROWSER_CHECK_MAX_ITERATIONS = 2

# The per-request MCP timeout of a server, and the most it may be.
BROWSER_DEFAULT_SERVER_TIMEOUT_SECONDS = 30.0
BROWSER_MAX_SERVER_TIMEOUT_SECONDS = 600.0

# Card and text caps: the result card the orchestrator reads, a card's
# summary, one item, the items per list, the done criteria, the plan,
# the blockers, the whole progress section, and one event detail.
BROWSER_CARD_MAX_TOKENS = 800
BROWSER_SUMMARY_MAX_CHARS = 2_000
BROWSER_ITEM_MAX_CHARS = 500
BROWSER_MAX_ITEMS = 50
BROWSER_MAX_CRITERIA = 20
BROWSER_PLAN_MAX_CHARS = 8_000
BROWSER_BLOCKERS_MAX_CHARS = 8_000
BROWSER_PROGRESS_MAX_CHARS = 96_000
BROWSER_EVENT_DETAIL_MAX_CHARS = 500

# The run-bound tools the runtime adds to the orchestrator, and their
# argument names; no developer or MCP tool may take these names.
BROWSER_EPISODE_TOOL_NAME = "run_episode"
BROWSER_PATCH_TOOL_NAME = "patch_goal"
BROWSER_RESERVED_TOOL_NAMES = (BROWSER_EPISODE_TOOL_NAME, BROWSER_PATCH_TOOL_NAME)
BROWSER_EPISODE_TASK_ARGUMENT = "task"
BROWSER_EPISODE_DONE_WHEN_ARGUMENT = "done_when"
BROWSER_PATCH_SECTION_ARGUMENT = "section"
BROWSER_PATCH_TEXT_ARGUMENT = "text"

# The goal card's fixed context item, the word that marks a screenshot
# tool, and the marker that ends a card cut at its token cap.
BROWSER_GOAL_PRIMITIVE_ID = "browser_goal_card"
BROWSER_GOAL_TITLE = "Goal card"
BROWSER_SCREENSHOT_MARKER = "screenshot"
BROWSER_CARD_CUT_MARKER = "\n[card cut at its size cap]"

# Name templates for the servers and the agents a run starts.
BROWSER_SERVER_NAME_TEMPLATE = "browser-{role}-{index}"
BROWSER_EPISODE_AGENT_NAME = "{name}-episode-{index}"
BROWSER_RECHECK_AGENT_NAME = "{name}-recheck"
BROWSER_DONE_WHEN_AGENT_NAME = "{name}-done-when"

# Episodes, rechecks, events, and servers are numbered from the first
# value, and no count may go below the second.
BROWSER_FIRST_INDEX = 1
BROWSER_MIN_COUNT = 0

__all__ = [
    "BROWSER_BLOCKERS_MAX_CHARS",
    "BROWSER_CARD_CUT_MARKER",
    "BROWSER_CARD_MAX_TOKENS",
    "BROWSER_CHECK_MAX_ITERATIONS",
    "BROWSER_DEFAULT_KEEP_OBSERVATIONS",
    "BROWSER_DEFAULT_MAX_ACTIONS",
    "BROWSER_DEFAULT_MAX_ITERATIONS",
    "BROWSER_DEFAULT_MAX_SCREENSHOTS",
    "BROWSER_DEFAULT_MAX_STALLS",
    "BROWSER_DEFAULT_RECHECK_EVERY",
    "BROWSER_DEFAULT_SERVER_TIMEOUT_SECONDS",
    "BROWSER_DONE_WHEN_AGENT_NAME",
    "BROWSER_EPISODE_AGENT_NAME",
    "BROWSER_EPISODE_DONE_WHEN_ARGUMENT",
    "BROWSER_EPISODE_REPLY_TURNS",
    "BROWSER_EPISODE_TASK_ARGUMENT",
    "BROWSER_EPISODE_TOOL_NAME",
    "BROWSER_EVENT_DETAIL_MAX_CHARS",
    "BROWSER_FIRST_INDEX",
    "BROWSER_GOAL_PRIMITIVE_ID",
    "BROWSER_GOAL_TITLE",
    "BROWSER_HISTORY_MAX_TOKENS",
    "BROWSER_ITEM_MAX_CHARS",
    "BROWSER_MAX_CRITERIA",
    "BROWSER_MAX_ITEMS",
    "BROWSER_MAX_SERVER_TIMEOUT_SECONDS",
    "BROWSER_MIN_CAP",
    "BROWSER_MIN_COUNT",
    "BROWSER_PATCH_SECTION_ARGUMENT",
    "BROWSER_PATCH_TEXT_ARGUMENT",
    "BROWSER_PATCH_TOOL_NAME",
    "BROWSER_PLAN_MAX_CHARS",
    "BROWSER_PROGRESS_MAX_CHARS",
    "BROWSER_RECHECK_AGENT_NAME",
    "BROWSER_RESERVED_TOOL_NAMES",
    "BROWSER_SCREENSHOT_MARKER",
    "BROWSER_SERVER_NAME_TEMPLATE",
    "BROWSER_STALE_OBSERVATION_CHARS",
    "BROWSER_SUMMARY_MAX_CHARS",
    "BROWSER_TOOL_RESULT_MAX_CHARS",
    "BROWSER_WORKER_HISTORY_MAX_TOKENS",
]
