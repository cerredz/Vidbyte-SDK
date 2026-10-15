"""FILE: vidbyte/lib/constants/infinite.py

PURPOSE: Defines every named default, limit, pattern, tool name, workspace file name, and short label of the InfiniteMemory agent: the delegation caps, the workspace caps, the entry and card sizes, the history cap, the run-id and verdict formats, and the map's fixed labels.
ROLE IN CODEBASE: Read by the settings and every module in vidbyte/agents/infinite/, by the records in vidbyte/lib/dataclasses/infinite.py, and by InfiniteMemoryAgentTools (vidbyte/tools/toolsets/infinite.py). The feature tests import the labels and caps to check output against them.
ARCHITECTURE NOTE: Immutable constants only; behavior lives in the workspace, journal, memory, launch, and runtime modules. Defaults follow the request's proposed numbers. Patterns are raw strings compiled where they are used, and the label templates are filled with str.format.
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
INFINITE_DEFAULT_MAX_DEPTH = 10
INFINITE_DEFAULT_MAX_PARALLEL = 10
INFINITE_DEFAULT_MAX_AGENTS = 200

# One generator and one verifier: the smallest team, so a run must
# allow at least one pair, and each new pair counts as this many agents.
INFINITE_MIN_AGENTS = 2

# The root agent's depth, and how much deeper each pair's generator is
# than the agent that launched it.
INFINITE_ROOT_DEPTH = 0
INFINITE_DEPTH_STEP = 1

# Workspace defaults: total files, total tokens, tokens per note or
# seed, tokens per entry or file description, and accepted remember
# calls per agent.
INFINITE_DEFAULT_MAX_FILES = 200
INFINITE_DEFAULT_MAX_TOKENS = 250_000
INFINITE_DEFAULT_MAX_FILE_TOKENS = 20_000
INFINITE_DEFAULT_MAX_ENTRY_TOKENS = 60
INFINITE_DEFAULT_MAX_ENTRIES_PER_AGENT = 5

# The default loop for every agent in the tree: at most 100 iterations,
# and every ordinary tool result cut at 100,000 characters.
INFINITE_DEFAULT_MAX_ITERATIONS = 100
INFINITE_TOOL_RESULT_MAX_CHARS = 100_000

# Fixed limits: new files per agent, tags and refs per entry, items in
# a task card's context, and the token caps of a card's summary and
# review, the workspace map, and every agent's message history.
INFINITE_NEW_FILES_PER_AGENT = 1
INFINITE_MAX_TAGS = 3
INFINITE_MAX_REFS = 3
INFINITE_CONTEXT_MAX_ITEMS = 20
INFINITE_CARD_TEXT_MAX_TOKENS = 400
INFINITE_MAP_MAX_TOKENS = 2_000
INFINITE_HISTORY_MAX_TOKENS = 60_000

# The most bytes one character takes in UTF-8, so a byte cap derived
# from a token cap never skips a file the token cap allows.
INFINITE_UTF8_MAX_BYTES_PER_CHAR = 4

# Formats of a task name, an entry tag, a staged entry key, the
# verifier's verdict line, and a run id.
INFINITE_TASK_NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{0,39}$"
INFINITE_TAG_PATTERN = r"^[a-z0-9][a-z0-9-]{0,23}$"
INFINITE_STAGED_KEY_PATTERN = r"^s[1-9][0-9]*$"
INFINITE_VERDICT_PATTERN = r"(?im)^[\s*_`]*VERDICT[\s*_`]*:[\s*_`]*(passed|fixed|failed)[\s*_`.]*$"
INFINITE_RUN_ID_PATTERN = r"^\d{8}T\d{6}Z-[0-9a-f]{8}$"
INFINITE_RUN_ID_TIME_FORMAT = "%Y%m%dT%H%M%SZ"

# The model-facing names of the run-bound tools. The reserved names add
# the three preset tools, so no developer tool may take any of them.
INFINITE_LAUNCH_TOOL_NAME = "launch_subagent"
INFINITE_REMEMBER_TOOL_NAME = "remember"
INFINITE_WRITE_NOTE_TOOL_NAME = "write_note"
INFINITE_EDIT_FILE_TOOL_NAME = "edit_file"
INFINITE_DROP_ENTRY_TOOL_NAME = "drop_entry"
INFINITE_RESERVED_TOOL_NAMES = (
    INFINITE_LAUNCH_TOOL_NAME,
    INFINITE_REMEMBER_TOOL_NAME,
    INFINITE_WRITE_NOTE_TOOL_NAME,
    INFINITE_EDIT_FILE_TOOL_NAME,
    INFINITE_DROP_ENTRY_TOOL_NAME,
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
    "INFINITE_GENERATOR_KEY",
    "INFINITE_HISTORY_MAX_TOKENS",
    "INFINITE_LAUNCH_TOOL_NAME",
    "INFINITE_MAP_MAX_TOKENS",
    "INFINITE_MAP_PRIMITIVE_ID",
    "INFINITE_MAP_TITLE",
    "INFINITE_MAX_REFS",
    "INFINITE_MAX_TAGS",
    "INFINITE_MIN_AGENTS",
    "INFINITE_MORE_FILES",
    "INFINITE_NEW_FILES_PER_AGENT",
    "INFINITE_NOTE_SUFFIXES",
    "INFINITE_NO_DESCRIPTION",
    "INFINITE_REMEMBER_TOOL_NAME",
    "INFINITE_RESERVED_TOOL_NAMES",
    "INFINITE_ROOT_DEPTH",
    "INFINITE_ROOT_KEY",
    "INFINITE_RUNS_DIRNAME",
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
    "INFINITE_UTF8_MAX_BYTES_PER_CHAR",
    "INFINITE_VERDICT_PATTERN",
    "INFINITE_VERIFIER_KEY",
    "INFINITE_WRITE_NOTE_TOOL_NAME",
]
