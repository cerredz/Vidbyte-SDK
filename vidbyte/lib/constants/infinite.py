"""FILE: vidbyte/lib/constants/infinite.py

PURPOSE: Defines every named default, limit, pattern, tool name, workspace file name, and short label of the InfiniteMemory agent: the delegation caps, the workspace caps, the entry and card sizes, the history cap, the run-id and verdict formats, and the map's fixed labels.
ROLE IN CODEBASE: Read by the settings and every module in vidbyte/agents/infinite/, by the records in vidbyte/lib/dataclasses/infinite.py, and by InfiniteMemoryAgentTools (vidbyte/tools/toolsets/infinite.py). The feature tests import the labels and caps to check output against them.
ARCHITECTURE NOTE: Immutable constants only; behavior lives in the workspace, journal, memory, launch, and runtime modules. The limits are generous on purpose, because this agent exists to take on work that outgrows one context: each one only stops a runaway run, and the context caps are sized for a 128,000-token model: the role prompt, the tool descriptions, the map, and the trimmed history take about 105,000 tokens, which leaves room for the developer's own prompt and the reply. Patterns are raw strings compiled where they are used, and the label templates are filled with str.format.
FUNCTION INVENTORY: No functions; defaults (INFINITE_DEFAULT_*), limits, patterns (INFINITE_*_PATTERN), tool names (INFINITE_*_TOOL_NAME and INFINITE_RESERVED_TOOL_NAMES), workspace layout names, and labels.
COMMON MODIFICATION PATTERNS: Change a cap or label here, never at its use site, so the settings, the tools, the tests, and the folder README stay in step. Add a named constant here before writing another InfiniteMemory policy literal.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from any layer above vidbyte/lib. 2. Do not put model-facing sentences here; they belong in vidbyte/prompts/prompts/infinite_memory/. 3. Do not rename a workspace file name; workspaces already on disk use it.
KNOWN EDGE CASES: Every token figure is TokenEstimate's characters-divided-by-four estimate, not a real tokenizer count. The verdict pattern accepts Markdown emphasis and a trailing period, and the last matching line wins. Grep's file-size cap is derived from max_tokens with INFINITE_UTF8_MAX_BYTES_PER_CHAR, so no workspace file is too large to search.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 8.5, 9.1, and 9.3); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py and the rest of tests/features/infinite_memory_agent/
"""

from __future__ import annotations

# Delegation defaults: how deep pairs may nest, how many tasks one
# launch_subagent call carries, and how many agents one run may start.
# DelegationLimitsMiddleware enforces the first two on every agent.
INFINITE_DEFAULT_MAX_DEPTH = 20
INFINITE_DEFAULT_MAX_PARALLEL = 20
INFINITE_DEFAULT_MAX_AGENTS = 1_000

# One generator and one verifier: the smallest team, so a run must
# allow at least one pair, and each new pair counts as this many agents.
INFINITE_MIN_AGENTS = 2

# The smallest value of every workspace cap and of the depth and batch
# caps, so no cap can be switched off by setting it to 0.
INFINITE_MIN_CAP = 1

# Entry ids start at the first number, and no file or token count may
# go below the second.
INFINITE_FIRST_ENTRY_ID = 1
INFINITE_MIN_COUNT = 0

# The root agent's depth, and how much deeper each pair's generator is
# than the agent that launched it.
INFINITE_ROOT_DEPTH = 0
INFINITE_DEPTH_STEP = 1

# How long a pair waits between its generator and its verifier: no
# time at all, only a turn for the sibling pairs of its batch.
INFINITE_PAIR_TURN_SECONDS = 0

# Workspace defaults: total files, total tokens, tokens per note or
# seed, tokens per entry or file description, and accepted remember
# calls per agent.
INFINITE_DEFAULT_MAX_FILES = 2_000
INFINITE_DEFAULT_MAX_TOKENS = 2_000_000
INFINITE_DEFAULT_MAX_FILE_TOKENS = 100_000
INFINITE_DEFAULT_MAX_ENTRY_TOKENS = 150
INFINITE_DEFAULT_MAX_ENTRIES_PER_AGENT = 25

# The default loop for every agent in the tree: at most 500 iterations,
# and every ordinary tool result cut at 200,000 characters, about
# 50,000 tokens, so one result never takes more than about half of
# the history cap below.
INFINITE_DEFAULT_MAX_ITERATIONS = 500
INFINITE_TOOL_RESULT_MAX_CHARS = 200_000

# Fixed limits: new files per agent, tags and refs per entry, items in
# a task card's context, and the token caps of a card's summary and
# review, the workspace map, and every agent's message history. A full
# batch of cards, each with four texts at the card cap, takes about
# 64,000 tokens, so it fits inside the history cap.
INFINITE_NEW_FILES_PER_AGENT = 10
INFINITE_MAX_TAGS = 8
INFINITE_MAX_REFS = 8
INFINITE_CONTEXT_MAX_ITEMS = 100
INFINITE_CARD_TEXT_MAX_TOKENS = 800
INFINITE_MAP_MAX_TOKENS = 8_000
INFINITE_HISTORY_MAX_TOKENS = 90_000

# The most bytes one character takes in UTF-8, so a byte cap derived
# from a token cap never skips a file the token cap allows.
INFINITE_UTF8_MAX_BYTES_PER_CHAR = 4

# Formats of a task name, an entry tag, a staged entry key, the
# verifier's verdict line, and a run id.
INFINITE_TASK_NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"
INFINITE_TAG_PATTERN = r"^[a-z0-9][a-z0-9-]{0,39}$"
INFINITE_STAGED_KEY_PATTERN = r"^s[1-9][0-9]*$"
INFINITE_VERDICT_PATTERN = r"(?im)^[\s*_`]*VERDICT[\s*_`]*:[\s*_`]*(passed|fixed|failed)[\s*_`.]*$"
INFINITE_RUN_ID_PATTERN = r"^\d{8}T\d{6}Z-[0-9a-f]{8}$"
INFINITE_RUN_ID_TIME_FORMAT = "%Y%m%dT%H%M%SZ"

# The model-facing names of the run-bound tools, which each run adds to
# its agents, and the name of the launch tool's task list. The reserved
# names add the three preset tools, so no developer tool may take any
# of them.
INFINITE_LAUNCH_TOOL_NAME = "launch_subagent"
INFINITE_LAUNCH_TASKS_ARGUMENT = "tasks"
INFINITE_REMEMBER_TOOL_NAME = "remember"
INFINITE_WRITE_NOTE_TOOL_NAME = "write_note"
INFINITE_EDIT_FILE_TOOL_NAME = "edit_file"
INFINITE_DROP_ENTRY_TOOL_NAME = "drop_entry"
INFINITE_RUN_BOUND_TOOL_NAMES = (
    INFINITE_LAUNCH_TOOL_NAME,
    INFINITE_REMEMBER_TOOL_NAME,
    INFINITE_WRITE_NOTE_TOOL_NAME,
    INFINITE_EDIT_FILE_TOOL_NAME,
    INFINITE_DROP_ENTRY_TOOL_NAME,
)
INFINITE_RESERVED_TOOL_NAMES = (
    *INFINITE_RUN_BOUND_TOOL_NAMES,
    "bash",
    "grep",
    "read_lines",
)

# Agent keys and workspace layout: the root's key, the last part of a
# pair's generator and verifier keys, the journal and seed folders, the
# three bookkeeping files, the suffixes a note may have, and the id of
# the map item in every agent's context.
INFINITE_ROOT_KEY = "root"
INFINITE_GENERATOR_KEY = "gen"
INFINITE_VERIFIER_KEY = "ver"
INFINITE_RUNS_DIRNAME = ".runs"
INFINITE_SEED_DIRNAME = "seed"
INFINITE_ENTRIES_FILE = "entries.jsonl"
INFINITE_SUPERSEDED_FILE = "superseded.jsonl"
INFINITE_FILES_FILE = "files.jsonl"
INFINITE_NOTE_SUFFIXES = (".md", ".txt", ".json", ".jsonl")
# Top-level folders whose files never count toward the workspace caps.
INFINITE_UNCOUNTED_DIRNAMES = (INFINITE_RUNS_DIRNAME,)
INFINITE_MAP_PRIMITIVE_ID = "infinite_memory_map"

# Short fixed labels: the map's title, the end of cut card text, the
# map's word for a file with no description or a seed, the line that
# replaces map lines past its cap, and one finished pair in a briefing.
INFINITE_MAP_TITLE = "Workspace map"
INFINITE_TRUNCATION_MARKER = " … [cut]"
INFINITE_NO_DESCRIPTION = "(no description)"
INFINITE_SEED_LABEL = "(seed file, read-only)"
INFINITE_MORE_FILES = "… and {count} more files"
INFINITE_FINISHED_PAIR_LINE = "- {name}: {status}, verdict {verdict}, entries {entries}"

__all__ = [
    "INFINITE_CARD_TEXT_MAX_TOKENS",
    "INFINITE_CONTEXT_MAX_ITEMS",
    "INFINITE_DEFAULT_MAX_AGENTS",
    "INFINITE_DEFAULT_MAX_DEPTH",
    "INFINITE_DEFAULT_MAX_ENTRIES_PER_AGENT",
    "INFINITE_DEFAULT_MAX_ENTRY_TOKENS",
    "INFINITE_DEFAULT_MAX_FILES",
    "INFINITE_DEFAULT_MAX_FILE_TOKENS",
    "INFINITE_DEFAULT_MAX_ITERATIONS",
    "INFINITE_DEFAULT_MAX_PARALLEL",
    "INFINITE_DEFAULT_MAX_TOKENS",
    "INFINITE_DEPTH_STEP",
    "INFINITE_DROP_ENTRY_TOOL_NAME",
    "INFINITE_EDIT_FILE_TOOL_NAME",
    "INFINITE_ENTRIES_FILE",
    "INFINITE_FILES_FILE",
    "INFINITE_FINISHED_PAIR_LINE",
    "INFINITE_FIRST_ENTRY_ID",
    "INFINITE_GENERATOR_KEY",
    "INFINITE_HISTORY_MAX_TOKENS",
    "INFINITE_LAUNCH_TASKS_ARGUMENT",
    "INFINITE_LAUNCH_TOOL_NAME",
    "INFINITE_MAP_MAX_TOKENS",
    "INFINITE_MAP_PRIMITIVE_ID",
    "INFINITE_MAP_TITLE",
    "INFINITE_MAX_REFS",
    "INFINITE_MAX_TAGS",
    "INFINITE_MIN_AGENTS",
    "INFINITE_MIN_CAP",
    "INFINITE_MIN_COUNT",
    "INFINITE_MORE_FILES",
    "INFINITE_NEW_FILES_PER_AGENT",
    "INFINITE_NOTE_SUFFIXES",
    "INFINITE_NO_DESCRIPTION",
    "INFINITE_PAIR_TURN_SECONDS",
    "INFINITE_REMEMBER_TOOL_NAME",
    "INFINITE_RESERVED_TOOL_NAMES",
    "INFINITE_ROOT_DEPTH",
    "INFINITE_ROOT_KEY",
    "INFINITE_RUNS_DIRNAME",
    "INFINITE_RUN_BOUND_TOOL_NAMES",
    "INFINITE_RUN_ID_PATTERN",
    "INFINITE_RUN_ID_TIME_FORMAT",
    "INFINITE_SEED_DIRNAME",
    "INFINITE_SEED_LABEL",
    "INFINITE_STAGED_KEY_PATTERN",
    "INFINITE_SUPERSEDED_FILE",
    "INFINITE_TAG_PATTERN",
    "INFINITE_TASK_NAME_PATTERN",
    "INFINITE_TOOL_RESULT_MAX_CHARS",
    "INFINITE_TRUNCATION_MARKER",
    "INFINITE_UNCOUNTED_DIRNAMES",
    "INFINITE_UTF8_MAX_BYTES_PER_CHAR",
    "INFINITE_VERDICT_PATTERN",
    "INFINITE_VERIFIER_KEY",
    "INFINITE_WRITE_NOTE_TOOL_NAME",
]
