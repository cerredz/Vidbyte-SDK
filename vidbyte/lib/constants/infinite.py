"""FILE: vidbyte/lib/constants/infinite.py

PURPOSE: Defines every named default, limit, pattern, tool name, workspace file name, and short label of the InfiniteMemory agent: the delegation caps, the workspace caps, the entry and card sizes, the history cap, the run-id and verdict formats, the map's fixed labels, the run events' caps, key rule, and summary templates, the reply metadata keys, and the run handoff's file suffix and caps.
ROLE IN CODEBASE: Read by the settings and every module in vidbyte/agents/infinite/ (InfiniteEvents in events.py reads the event caps and templates), by the records in vidbyte/lib/dataclasses/infinite.py, by InfiniteHandoff (vidbyte/context/handoff/infinite.py), and by InfiniteMemoryAgentTools (vidbyte/tools/toolsets/infinite.py). The feature tests import the labels and caps to check output against them.
ARCHITECTURE NOTE: Immutable constants only; behavior lives in the workspace, journal, memory, launch, and runtime modules. The limits are generous on purpose, because this agent exists to take on work that outgrows one context: each one only stops a runaway run, and the context caps are sized for a 128,000-token model: the role prompt, the tool descriptions, the map, and the trimmed history take about 105,000 tokens, which leaves room for the developer's own prompt and the reply. Patterns are raw strings compiled where they are used, and the label templates are filled with str.format.
FUNCTION INVENTORY: No functions; defaults (INFINITE_DEFAULT_*), limits, patterns (INFINITE_*_PATTERN), tool names (INFINITE_*_TOOL_NAME and INFINITE_RESERVED_TOOL_NAMES), workspace layout names, labels, event caps (INFINITE_EVENT_*_MAX_*, the key digest, the byte bound, and the time factors), event summary templates (INFINITE_EVENT_*_SUMMARY), reply metadata keys (INFINITE_*_METADATA_KEY), and handoff caps (INFINITE_HANDOFF_*).
COMMON MODIFICATION PATTERNS: Change a cap or label here, never at its use site, so the settings, the tools, the tests, and the folder README stay in step. Add a named constant here before writing another InfiniteMemory policy literal. A new event kind adds one summary template here; a new details field adds its cap here and its worst case to the table in docs/spec/infinite-memory-events/spec.md section 9.1.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from any layer above vidbyte/lib. 2. Do not put model-facing sentences here; they belong in vidbyte/prompts/prompts/infinite_memory/. The event summaries are developer-facing display lines, and the handoff wording lives in vidbyte/context/handoff/infinite.py. 3. Do not rename a workspace file name; workspaces already on disk use it. 4. Do not tie an event cap to a setting; only fixed caps bound an event at any settings value.
KNOWN EDGE CASES: Every token figure is TokenEstimate's characters-divided-by-four estimate, not a real tokenizer count. The verdict pattern accepts Markdown emphasis and a trailing period, and the last matching line wins. Grep's file-size cap is derived from max_tokens with INFINITE_UTF8_MAX_BYTES_PER_CHAR, so no workspace file is too large to search.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 8.5, 9.1, and 9.3); docs/spec/infinite-memory-events/spec.md (section 9.1); vidbyte/agents/infinite/README.md
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

# Run event caps, in characters. Every event is bounded by these fixed
# caps at any settings value, never by a setting. The arithmetic takes
# the worst JSON escaping, 12 bytes per character: json.dumps with
# ensure_ascii writes a character outside the Basic Multilingual Plane
# as two \uXXXX escapes, which also covers ensure_ascii=False (at most
# 6 bytes, for an escaped control character). The largest details
# record, subagent_finished, holds 2,060 capped characters (24,720
# bytes) plus 2,295 bytes of keys, numbers, enums, and JSON syntax:
# 27,015 bytes, under the 32,768-byte bound, which is half of the
# backend's 65,536-byte details cap. Its envelope adds at most 4,076.
INFINITE_EVENT_SUMMARY_MAX_CHARS = 280
INFINITE_EVENT_TEXT_MAX_CHARS = 500
INFINITE_EVENT_PATH_MAX_CHARS = 500
INFINITE_EVENT_LINE_MAX_CHARS = 120
INFINITE_EVENT_LABEL_MAX_CHARS = 64
INFINITE_EVENT_MAX_DETAILS_BYTES = 32_768

# Items per list in one event; the rest are counted in the list's
# *_omitted field, so a cut list is never lost silently. 5 items of the
# 500-character text cap stay inside the byte bound above.
INFINITE_EVENT_MAX_ITEMS = 5

# The largest count an event carries, 2**63 - 1, so a backend can store
# every count as a 64-bit integer; a larger setting is reported at it.
INFINITE_EVENT_MAX_COUNT = 9_223_372_036_854_775_807

# The key rule. Every key in an event is ASCII and at most 512
# characters, the backend's context-reference cap. A pair key longer
# than 512 - len("/gen") = 508 characters becomes the mark, the first
# 16 hexadecimal digits of its SHA-256, "/", and its last 490
# characters: 1 + 16 + 1 + 490 = 508. The agent key then adds "/gen" or
# "/ver" and stays within 512. 16 digits keep two keys apart unless
# their digests collide in 64 bits.
INFINITE_EVENT_KEY_MAX_CHARS = 512
INFINITE_EVENT_KEY_DIGEST_CHARS = 16
INFINITE_EVENT_KEY_DIGEST_MARK = "~"

# Event times are stamped to the millisecond, and a generator's
# duration is reported in milliseconds.
INFINITE_EVENT_MILLISECONDS_PER_SECOND = 1_000
INFINITE_EVENT_MICROSECONDS_PER_MILLISECOND = 1_000

# Event summaries: one developer-facing display line each, filled with
# str.format, collapsed to one line, and cut to the summary cap. {agent}
# is "root" or the last two segments of the agent's key. FILE_CREATED
# is used for a created note that has a description, FILE_WRITTEN for
# every other write.
INFINITE_EVENT_RUN_STARTED_SUMMARY = "Run started: {task}"
INFINITE_EVENT_RUN_RESUMED_SUMMARY = "Run resumed: {finished} tasks done earlier, {interrupted} will run again"
INFINITE_EVENT_RUN_FINISHED_SUMMARY = "Run finished ({stop_reason}): {answer}"
INFINITE_EVENT_RUN_STOPPED_SUMMARY = "Run stopped ({reason}): {error_type}; resume it to continue"
INFINITE_EVENT_REFUSED_SUMMARY = "{tool} refused for {agent}: {problem}"
INFINITE_EVENT_SUBAGENT_LAUNCHED_SUMMARY = "{agent} launched {name}: {goal}"
INFINITE_EVENT_SUBAGENT_REPLAYED_SUMMARY = "{agent}: {name} already finished; its result is reused"
INFINITE_EVENT_GENERATOR_FINISHED_SUMMARY = "{agent}: {status}: {summary}"
INFINITE_EVENT_SUBAGENT_FINISHED_SUMMARY = "{name}: {verdict}, {committed} memories saved, {dropped} dropped, {files} files"
INFINITE_EVENT_MEMORY_SAVED_SUMMARY = "Memory #{id} ({kind}): {text}"
INFINITE_EVENT_MEMORY_STAGED_SUMMARY = "{agent} proposed {key} ({kind}): {text}"
INFINITE_EVENT_MEMORY_DROPPED_SUMMARY = "{agent} dropped {key}: {text}"
INFINITE_EVENT_FILE_WRITTEN_SUMMARY = "{agent} {change} {path}"
INFINITE_EVENT_FILE_CREATED_SUMMARY = "{agent} created {path}: {description}"

# Reply metadata keys: the run id this package adds, and the three the
# agent runtime sets, which events read the stop reason, tool calls,
# and usage from.
INFINITE_RUN_ID_METADATA_KEY = "infinite_run_id"
INFINITE_STOP_REASON_METADATA_KEY = "stop_reason"
INFINITE_TOOL_CALLS_METADATA_KEY = "tool_call_count"
INFINITE_USAGE_METADATA_KEY = "usage_rollup"

# The run handoff, written as .runs/<run_id>.handoff.md. Its caps fit
# the backend's 24 sections of 16,000 characters however the text is
# split: every list line at most 1,000 characters, Outcome at most
# 239,000 (15 sections, leaving 15 x 16,000 - 239,000 = 1,000 for its
# heading), and each of the other eight at most 15,900 (one section
# each, leaving 100). With the title, headings, and separators (300),
# the whole text is at most 239,000 + 8 x 15,900 + 300 = 366,500
# characters, 23 sections of 16,000.
INFINITE_HANDOFF_SUFFIX = ".handoff.md"
INFINITE_HANDOFF_OUTCOME_MAX_CHARS = 239_000
INFINITE_HANDOFF_SECTION_MAX_CHARS = 15_900
INFINITE_HANDOFF_LINE_MAX_CHARS = 1_000

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
    "INFINITE_EVENT_FILE_CREATED_SUMMARY",
    "INFINITE_EVENT_FILE_WRITTEN_SUMMARY",
    "INFINITE_EVENT_GENERATOR_FINISHED_SUMMARY",
    "INFINITE_EVENT_KEY_DIGEST_CHARS",
    "INFINITE_EVENT_KEY_DIGEST_MARK",
    "INFINITE_EVENT_KEY_MAX_CHARS",
    "INFINITE_EVENT_LABEL_MAX_CHARS",
    "INFINITE_EVENT_LINE_MAX_CHARS",
    "INFINITE_EVENT_MAX_COUNT",
    "INFINITE_EVENT_MAX_DETAILS_BYTES",
    "INFINITE_EVENT_MAX_ITEMS",
    "INFINITE_EVENT_MEMORY_DROPPED_SUMMARY",
    "INFINITE_EVENT_MEMORY_SAVED_SUMMARY",
    "INFINITE_EVENT_MEMORY_STAGED_SUMMARY",
    "INFINITE_EVENT_MICROSECONDS_PER_MILLISECOND",
    "INFINITE_EVENT_MILLISECONDS_PER_SECOND",
    "INFINITE_EVENT_PATH_MAX_CHARS",
    "INFINITE_EVENT_REFUSED_SUMMARY",
    "INFINITE_EVENT_RUN_FINISHED_SUMMARY",
    "INFINITE_EVENT_RUN_RESUMED_SUMMARY",
    "INFINITE_EVENT_RUN_STARTED_SUMMARY",
    "INFINITE_EVENT_RUN_STOPPED_SUMMARY",
    "INFINITE_EVENT_SUBAGENT_FINISHED_SUMMARY",
    "INFINITE_EVENT_SUBAGENT_LAUNCHED_SUMMARY",
    "INFINITE_EVENT_SUBAGENT_REPLAYED_SUMMARY",
    "INFINITE_EVENT_SUMMARY_MAX_CHARS",
    "INFINITE_EVENT_TEXT_MAX_CHARS",
    "INFINITE_FILES_FILE",
    "INFINITE_FINISHED_PAIR_LINE",
    "INFINITE_FIRST_ENTRY_ID",
    "INFINITE_GENERATOR_KEY",
    "INFINITE_HANDOFF_LINE_MAX_CHARS",
    "INFINITE_HANDOFF_OUTCOME_MAX_CHARS",
    "INFINITE_HANDOFF_SECTION_MAX_CHARS",
    "INFINITE_HANDOFF_SUFFIX",
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
    "INFINITE_RUN_ID_METADATA_KEY",
    "INFINITE_RUN_ID_PATTERN",
    "INFINITE_RUN_ID_TIME_FORMAT",
    "INFINITE_SEED_DIRNAME",
    "INFINITE_SEED_LABEL",
    "INFINITE_STAGED_KEY_PATTERN",
    "INFINITE_STOP_REASON_METADATA_KEY",
    "INFINITE_SUPERSEDED_FILE",
    "INFINITE_TAG_PATTERN",
    "INFINITE_TASK_NAME_PATTERN",
    "INFINITE_TOOL_CALLS_METADATA_KEY",
    "INFINITE_TOOL_RESULT_MAX_CHARS",
    "INFINITE_TRUNCATION_MARKER",
    "INFINITE_UNCOUNTED_DIRNAMES",
    "INFINITE_USAGE_METADATA_KEY",
    "INFINITE_UTF8_MAX_BYTES_PER_CHAR",
    "INFINITE_VERDICT_PATTERN",
    "INFINITE_VERIFIER_KEY",
    "INFINITE_WRITE_NOTE_TOOL_NAME",
]
