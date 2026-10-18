"""FILE: vidbyte/lib/constants/native_compose.py

PURPOSE: Holds every fixed value and text of the composite thread functions: count and size bounds, the stage decision for each thread problem, the field set of each prompt file and caller template, the prompt folder and spliced-text values, the git program, settings, subcommands, cleared variables and folder prefixes, the argument names compose reports, and the texts (a summary, likely cause and next step for each ThreadComposeProblem, the message and observation templates, the answer problems sent back to a model, and the refusal templates).
ROLE IN CODEBASE: Imported by the records in vidbyte/lib/dataclasses/native_compose.py and native_ensemble.py, and by every module under vidbyte/harnesses/native/compose/.
ARCHITECTURE NOTE: The compose modules hold no literals of their own (base spec INV-15): every git flag, prompt file and placeholder is an enum member in vidbyte/lib/enums/native_compose.py, and every other value they need lives here. Compose reads these names through this module object at call time (native_compose.COMPOSE_DIFF_MAX_CHARS), never through a from-import, so a patch here reaches every user. Each character cap is a base constant from vidbyte/lib/constants/native_threads.py or at least as large as the base's broad cap.
FUNCTION INVENTORY: No functions. Constants grouped as counts, size caps, git bounds, reader and Grok rules, stage decisions, prompt fields, prompt files and spliced texts, git words, folders and argument names, then the error texts, the answer problems and the refusal templates.
COMMON MODIFICATION PATTERNS: A value a compose module needs is added here under the COMPOSE_, STAGE_, ENSEMBLE_ or THREAD_COMPOSE_ prefix and used by name (lint A007, base INV-15). A new ThreadComposeProblem adds its own text to THREAD_COMPOSE_SUMMARIES, THREAD_COMPOSE_LIKELY_CAUSES and THREAD_COMPOSE_NEXT_STEPS. A new prompt file adds its COMPOSE_PROMPT_FIELDS entry with its ComposePrompt member.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte above vidbyte.lib.constants and vidbyte.lib.enums. 2. Do not name a constant with a password, token or secret word and give it a string (lint S054). 3. Do not add a caret to a git word; cmd.exe strips it when git is a batch launcher (spec D-24). 4. Do not share one likely cause or next step between two problems, and do not format anything into them.
KNOWN EDGE CASES: The texts must not contain a credential word followed by ":" or "=", because HarnessRedactor would rewrite such a phrase. Templates are filled with str.format by name, so a literal brace in a template is doubled. COMPOSE_GIT_CLEARED_VARIABLES includes GIT_INDEX_FILE: CliRunner removes the env_remove names before it applies the overlay, so a snapshot's own GIT_INDEX_FILE survives.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_surface.py, tests/features/harness_compose/test_harness_compose_git.py
"""

from __future__ import annotations

from types import MappingProxyType

from vidbyte.lib.constants.native_threads import (
    NATIVE_NAME_MAX_CHARS,
    NATIVE_RESULT_TEXT_MAX_CHARS,
)
from vidbyte.lib.enums.native_compose import (
    ComposeField,
    ComposePrompt,
    StageDecision,
    ThreadComposeProblem,
)
from vidbyte.lib.enums.native_threads import GrokPermissionMode, NativeThreadProblem

# Counts: chain steps, verifiers, stages, retries, ladder rungs,
# proposers and the approaches each proposer writes. Each floor is
# named beside its cap, even when it is 0 or 1 (lint A007).
COMPOSE_MIN_CHAIN_STEPS = 2
COMPOSE_MAX_STEPS = 25
COMPOSE_MIN_VERIFIERS = 1
COMPOSE_MAX_VERIFIERS = 10
COMPOSE_MIN_STAGES = 1
COMPOSE_MAX_STAGES = 25
STAGE_DEFAULT_RETRIES = 1
STAGE_MIN_RETRIES = 0
STAGE_MAX_RETRIES = 3
# Rung 0 is the step's own config; rung n is ladder item n.
STAGE_MIN_RUNG = 0
STAGE_MAX_LADDER = 4
ENSEMBLE_MIN_PROPOSERS = 1
ENSEMBLE_MAX_PROPOSERS = 10
# A proposal's number is its proposer's 1-based position.
ENSEMBLE_MIN_PROPOSAL_NUMBER = 1
# A narrowing round keeps at most one proposal in five, rounded up.
ENSEMBLE_NARROWING_FACTOR = 5
ENSEMBLE_MIN_APPROACHES = 2
ENSEMBLE_MAX_APPROACHES = 5

# Size caps. Each character cap is a base constant or at least as
# large as the base's broad cap (strict-config-dataclasses.md).
ENSEMBLE_ROLE_NAME_MAX_CHARS = NATIVE_NAME_MAX_CHARS
COMPOSE_ANSWER_TEXT_MAX_CHARS = NATIVE_RESULT_TEXT_MAX_CHARS
COMPOSE_VERDICT_MAX_FINDINGS = 50
COMPOSE_JSON_REPAIR_TURNS = 2
COMPOSE_PROBLEM_MAX_CHARS = 2000
COMPOSE_DIFF_MAX_CHARS = NATIVE_RESULT_TEXT_MAX_CHARS
COMPOSE_DIFF_MAX_FILES = 2000

# Git bounds: every git child is bounded in time and output (D-22).
COMPOSE_GIT_TIMEOUT_SECONDS = 120.0
COMPOSE_GIT_MAX_OUTPUT_BYTES = 16777216
COMPOSE_GIT_MESSAGE_MAX_CHARS = 2000
COMPOSE_MESSAGE_MAX_FILES = 10

# Readers and the Grok lock: the permission modes a Grok reader may
# use (INV-10), and the slots of each per-workspace semaphore (D-5).
COMPOSE_READER_GROK_MODES = frozenset({GrokPermissionMode.PLAN, GrokPermissionMode.DEFAULT})
COMPOSE_GROK_MAX_CONCURRENT_CALLS = 1

# What a staged run does after an attempt failed with each problem
# (D-14); an error that carries no problem ends the stage.
STAGE_DECISIONS: MappingProxyType[NativeThreadProblem, StageDecision] = MappingProxyType(
    {
        NativeThreadProblem.NOT_INSTALLED: StageDecision.ABORT,
        NativeThreadProblem.LAUNCHER_REFUSED: StageDecision.ABORT,
        NativeThreadProblem.KEY_REJECTED: StageDecision.ABORT,
        NativeThreadProblem.THREAD_NOT_FOUND: StageDecision.ABORT,
        NativeThreadProblem.WSL_UNAVAILABLE: StageDecision.ABORT,
        NativeThreadProblem.LAUNCH_FAILED: StageDecision.RETRY,
        NativeThreadProblem.TIMED_OUT: StageDecision.RETRY,
        NativeThreadProblem.OUTPUT_TOO_LARGE: StageDecision.RETRY,
        NativeThreadProblem.PROTOCOL_MISMATCH: StageDecision.RETRY,
        NativeThreadProblem.RUN_FAILED: StageDecision.RAISE_EFFORT,
    }
)
STAGE_UNCLASSIFIED_DECISION = StageDecision.ABORT

# The placeholders of each prompt file (spec §9.2); the loader
# requires every one and refuses any other.
COMPOSE_PROMPT_FIELDS: MappingProxyType[ComposePrompt, frozenset[ComposeField]] = MappingProxyType(
    {
        ComposePrompt.PLANNER_SYSTEM: frozenset({ComposeField.ROLES}),
        ComposePrompt.PLANNER_TURN: frozenset({ComposeField.TASK, ComposeField.ROLES}),
        ComposePrompt.PLAN_SCHEMA: frozenset({ComposeField.ROLES}),
        ComposePrompt.ROLE_SYSTEM: frozenset(
            {
                ComposeField.ROLE_NAME,
                ComposeField.IDENTITY,
                ComposeField.PERSONALITY,
                ComposeField.EXPERTISE,
                ComposeField.KNOWLEDGE,
                ComposeField.SKILLS,
                ComposeField.GOAL,
                ComposeField.MINIMUM,
                ComposeField.MAXIMUM,
            }
        ),
        ComposePrompt.ROLE_TURN: frozenset(
            {
                ComposeField.TASK,
                ComposeField.TASK_ANALYSIS,
                ComposeField.ROSTER_STRATEGY,
                ComposeField.COVERAGE_SUMMARY,
                ComposeField.MINIMUM,
                ComposeField.MAXIMUM,
            }
        ),
        ComposePrompt.FORK_TURN: frozenset({ComposeField.INSTRUCTIONS, ComposeField.TURN}),
        ComposePrompt.SELECTOR_SYSTEM: frozenset(),
        ComposePrompt.SELECTOR_ROUND_TURN: frozenset({ComposeField.TASK, ComposeField.ROUND, ComposeField.SURVIVING, ComposeField.TARGET, ComposeField.CANDIDATES}),
        ComposePrompt.SELECTOR_FINAL_TURN: frozenset({ComposeField.TASK, ComposeField.ROUND, ComposeField.SURVIVING, ComposeField.CANDIDATES}),
        ComposePrompt.ROUND_SCHEMA: frozenset({ComposeField.TARGET}),
        ComposePrompt.SELECTION_SCHEMA: frozenset(),
        ComposePrompt.PROPOSAL_BLOCK: frozenset({ComposeField.NUMBER, ComposeField.ROLE_NAME, ComposeField.TEXT}),
        ComposePrompt.IMPLEMENTER_SYSTEM: frozenset(),
        ComposePrompt.IMPLEMENTER_TURN: frozenset({ComposeField.TASK, ComposeField.ROLE_NAME, ComposeField.PROPOSAL, ComposeField.APPROACH, ComposeField.RATIONALE, ComposeField.GUIDANCE}),
        ComposePrompt.CHAIN_TURN: frozenset({ComposeField.PROMPT, ComposeField.PREVIOUS, ComposeField.DIFF}),
        ComposePrompt.VERIFY_TURN: frozenset({ComposeField.PROMPT, ComposeField.FILES, ComposeField.DIFF}),
        ComposePrompt.VERDICT_SCHEMA: frozenset(),
        ComposePrompt.HANDOFF_SUMMARY: frozenset(),
        ComposePrompt.HANDOFF_SEED: frozenset({ComposeField.SUMMARY}),
        ComposePrompt.JSON_ANSWER: frozenset({ComposeField.PROMPT, ComposeField.SCHEMA}),
        ComposePrompt.JSON_REPAIR: frozenset({ComposeField.PROBLEM, ComposeField.SCHEMA}),
        ComposePrompt.TRUNCATION_NOTE: frozenset({ComposeField.OMITTED}),
    }
)

# The fields a caller template may use: a chain template must splice
# the previous answer, and a stage template may use nothing else.
CHAIN_TEMPLATE_FIELDS = frozenset({ComposeField.PROMPT, ComposeField.PREVIOUS, ComposeField.DIFF})
CHAIN_REQUIRED_FIELDS = frozenset({ComposeField.PREVIOUS})
STAGE_TEMPLATE_FIELDS = frozenset({ComposeField.PREVIOUS})

# Prompt files and spliced texts: where the files live, the separator
# between a system file and a turn, the probe prompt a step is checked
# with (never sent), and what stands in for a bound key (D-28).
COMPOSE_PROMPTS_FOLDER = "prompts"
COMPOSE_PROMPT_SUFFIX = ".md"
COMPOSE_PROMPT_ENCODING = "utf-8"
COMPOSE_PROMPT_SEPARATOR = "\n\n"
COMPOSE_PROBE_PROMPT = "…"
COMPOSE_REDACTED_KEY = "[redacted]"
COMPOSE_NUL = "\x00"
# Counting a prompt as the Windows command line does (EC-36): a double
# quote is sent as a backslash and a quote and doubles the backslashes
# right before it, and a character past U+FFFF takes two UTF-16 units.
COMPOSE_QUOTE = '"'
COMPOSE_BACKSLASH = "\\"
COMPOSE_BMP_MAX_CODE_POINT = 0xFFFF

# Git words (INV-26). Every command starts with the program, the
# no-optional-locks flag and the two settings; HEAD is named alone,
# never with a caret (D-24).
COMPOSE_GIT_PROGRAM = "git"
COMPOSE_GIT_SETTINGS = ("core.fsmonitor=false", "core.safecrlf=false")
COMPOSE_GIT_REV_PARSE = "rev-parse"
COMPOSE_GIT_READ_TREE = "read-tree"
COMPOSE_GIT_ADD = "add"
COMPOSE_GIT_WRITE_TREE = "write-tree"
COMPOSE_GIT_DIFF = "diff"
COMPOSE_GIT_WORKTREE = "worktree"
COMPOSE_GIT_WORKTREE_ADD = "add"
COMPOSE_GIT_WORKTREE_REMOVE = "remove"
COMPOSE_GIT_HEAD = "HEAD"
# rev-parse --verify --quiet HEAD exits with 1 when there is no commit.
COMPOSE_GIT_UNBORN_EXIT_CODE = 1
COMPOSE_GIT_INDEX_VARIABLE = "GIT_INDEX_FILE"
COMPOSE_GIT_INDEX_FILE_NAME = "index"
# The names git rev-parse --local-env-vars prints, removed from every
# git child so the caller's environment cannot move compose to another
# repository or index (spec §9.3).
COMPOSE_GIT_CLEARED_VARIABLES = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CONFIG",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
    "GIT_OBJECT_DIRECTORY",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_GRAFT_FILE",
    "GIT_INDEX_FILE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_REPLACE_REF_BASE",
    "GIT_PREFIX",
    "GIT_SHALLOW_FILE",
    "GIT_COMMON_DIR",
)

# Temporary folders: a reader's worktree and a snapshot's index.
COMPOSE_WORKTREE_PREFIX = "vidbyte-compose-worktree-"
COMPOSE_INDEX_PREFIX = "vidbyte-compose-index-"

# Argument names compose reports in details["field"], and the two
# shapes of an argument path: an item of a list and a member of a
# record ("stages[2].step", "roster.proposers[0]").
COMPOSE_PROMPT_PARAMETER = "prompt"
COMPOSE_WRITER_PARAMETER = "writer"
COMPOSE_FUNCTION_ARGUMENT = "function"
COMPOSE_THREAD_ID_ARGUMENT = "thread_id"
COMPOSE_WORKSPACE_ARGUMENT = "workspace"
COMPOSE_STEPS_ARGUMENT = "steps"
COMPOSE_TEMPLATE_ARGUMENT = "template"
COMPOSE_VERIFIERS_ARGUMENT = "verifiers"
COMPOSE_FROM_THREAD_ARGUMENT = "from_thread"
COMPOSE_TO_STEP_ARGUMENT = "to_step"
COMPOSE_STAGES_ARGUMENT = "stages"
COMPOSE_ROSTER_ARGUMENT = "roster"
COMPOSE_STEP_ARGUMENT = "step"
COMPOSE_SCHEMA_ARGUMENT = "schema"
COMPOSE_PARSE_ARGUMENT = "parse"
COMPOSE_PLANNER_MEMBER = "planner"
COMPOSE_PROPOSERS_MEMBER = "proposers"
COMPOSE_SELECTOR_MEMBER = "selector"
COMPOSE_IMPLEMENTER_MEMBER = "implementer"
COMPOSE_ITEM_ARGUMENT = "{name}[{index}]"
COMPOSE_MEMBER_ARGUMENT = "{name}.{member}"

# ThreadComposeError texts. Each problem has its own summary, likely
# cause and next step; the likely cause and next step are sent
# verbatim (INV-6).
THREAD_COMPOSE_SUMMARIES: MappingProxyType[ThreadComposeProblem, str] = MappingProxyType(
    {
        ThreadComposeProblem.NOT_A_GIT_REPOSITORY: "The workspace is not inside a git repository, and this call needs git to snapshot it.",
        ThreadComposeProblem.GIT_UNAVAILABLE: "Git could not be found or started, and this call needs it to snapshot the workspace.",
        ThreadComposeProblem.GIT_FAILED: "A git command that compose runs to snapshot or compare the workspace failed.",
        ThreadComposeProblem.WORKTREE_FAILED: "Compose could not add, fill or remove the disposable worktree a reader runs in.",
        ThreadComposeProblem.READER_CHANGED_WORKSPACE: "A step that may only read changed the workspace during its read-only phase.",
    }
)
THREAD_COMPOSE_LIKELY_CAUSES: MappingProxyType[ThreadComposeProblem, str] = MappingProxyType(
    {
        ThreadComposeProblem.NOT_A_GIT_REPOSITORY: "The workspace folder is outside every git repository, or git refuses the repository because another user owns it (git's safe.directory check).",
        ThreadComposeProblem.GIT_UNAVAILABLE: "Git is not installed or its folder is not on PATH, or the operating system refused to start the git program that was found.",
        ThreadComposeProblem.GIT_FAILED: "Git reported an error or ran past its time bound, for example because the disk is full, the repository is damaged or the working tree is very large.",
        ThreadComposeProblem.WORKTREE_FAILED: "The repository has no commit yet, or the temporary worktree folder could not be created, filled or deleted, for example because a path is too long or a file is locked.",
        ThreadComposeProblem.READER_CHANGED_WORKSPACE: "A reader step edited files in the workspace, or another program or person changed them while the read-only phase ran.",
    }
)
THREAD_COMPOSE_NEXT_STEPS: MappingProxyType[ThreadComposeProblem, str] = MappingProxyType(
    {
        ThreadComposeProblem.NOT_A_GIT_REPOSITORY: "Run git init and commit in the workspace, or bind the steps to a folder inside a repository; if git reports dubious ownership, add the folder with git config --global --add safe.directory.",
        ThreadComposeProblem.GIT_UNAVAILABLE: "Install git 2.17 or later, put its folder on PATH and retry.",
        ThreadComposeProblem.GIT_FAILED: "Read git's text in this message, repair the repository or free disk space, and retry.",
        ThreadComposeProblem.WORKTREE_FAILED: "Commit at least once before a reader runs in a worktree; otherwise run git worktree prune, delete the named folder and retry.",
        ThreadComposeProblem.READER_CHANGED_WORKSPACE: "Review the change with git diff and restore what you want to keep; bind Grok readers in plan or default permission mode, and keep other programs out of the workspace during the call.",
    }
)
# The snapshot's add exits non-zero for two reasons git gives (EC-73).
THREAD_COMPOSE_ADD_LIKELY_CAUSE = "git add -A refused the working tree: an untracked folder inside it is a git repository with no commit, or git could not read one of its files because another program holds it open or its permissions forbid reading."
THREAD_COMPOSE_ADD_NEXT_STEP = "Commit in that folder, list it in .git/info/exclude or remove its .git folder; or close the program that holds the file, or fix its permissions; then retry."

# Message sentences, in the INV-6 order: what failed, what compose
# observed, git's text, the likely cause and the next step.
THREAD_COMPOSE_MESSAGE_HEAD = "Compose failed with {problem}."
THREAD_COMPOSE_WORKSPACE_SENTENCE = "The workspace was {workspace}."
THREAD_COMPOSE_EXIT_OBSERVATION = "git {subcommand} exited with status {exit_code}."
THREAD_COMPOSE_TIMEOUT_OBSERVATION = "git {subcommand} did not finish within {seconds} seconds."
THREAD_COMPOSE_LAUNCH_OBSERVATION = "Starting git from {program} failed with {failure}."
THREAD_COMPOSE_MISSING_OBSERVATION = "No {program} program was found in the folders on PATH."
THREAD_COMPOSE_FOLDER_OBSERVATION = "Compose could not create or remove the folder {folder} ({error_type})."
THREAD_COMPOSE_CHANGED_FILES_OBSERVATION = "The read-only phase changed {files}."
THREAD_COMPOSE_MORE_FILES = "{names} and {count} more"
THREAD_COMPOSE_GIT_TEXT_SENTENCE = 'git printed: "{git_message}".'
THREAD_COMPOSE_LIKELY_CAUSE_SENTENCE = "Likely cause: {likely_cause}"
THREAD_COMPOSE_NEXT_STEP_SENTENCE = "Next step: {next_step}"

# Answer problems: why an answer was not accepted, sent back to the
# model in a repair turn (INV-19, INV-23).
COMPOSE_TRUNCATED_PROBLEM = "The answer was cut at the length limit, so it was not read. Answer again with a shorter JSON object."
COMPOSE_EXTRA_MEMBERS_PROBLEM = "The JSON object has members the schema does not allow: {members}."
COMPOSE_MISSING_MEMBERS_PROBLEM = "The JSON object lacks members the schema requires: {members}."
COMPOSE_ROLE_COUNT_PROBLEM = "The plan must list exactly {expected} roles, one for each proposer; it lists {actual}."
COMPOSE_KEPT_PROBLEM = "kept must hold at most {target} of the offered numbers {offered}; it holds {kept}."
COMPOSE_PROPOSAL_PROBLEM = "proposal must be one of the offered numbers {offered}; it is {proposal}."

# Refusals compose raises as ConfigurationError (INV-2, INV-3, INV-5,
# INV-9, INV-10, INV-18, INV-24). None quotes a caller value.
COMPOSE_BIND_THREAD_RULE = "function must be run_grok_thread, run_opencode_thread, run_muse_thread, fork_grok_thread, fork_opencode_thread or fork_muse_thread; got a value of type {type_name}. A continue_ function is bound with bind_continue."
COMPOSE_BIND_CONTINUE_RULE = "function must be continue_grok_thread, continue_opencode_thread, continue_muse_thread, fork_grok_thread, fork_opencode_thread or fork_muse_thread; got a value of type {type_name}. A run_ function is bound with bind_thread."
COMPOSE_UNKNOWN_STEP_FUNCTION = "{argument} holds a function that is not one of the nine thread functions; build the step with bind_thread or bind_continue."
COMPOSE_STEP_MISMATCH = "{argument} says harness {harness} and verb {verb}, but its function is the {function_verb} function of {function_harness}; build the step with bind_thread or bind_continue."
COMPOSE_UNANCHORED_FORK_CALL = "thread_id is missing: this fork step has no thread to fork, so it cannot be called by itself. Bind it with bind_continue and a thread id, or give it to run_ensemble, which forks the planner's thread."
COMPOSE_COUNT_RULE = "{argument} must hold {minimum} to {maximum} items; got {count}."
COMPOSE_UNANCHORED_FORK_RULE = "{argument} is a fork step with no thread id, and there is no thread to fork here; bind it with bind_continue and a thread id."
COMPOSE_FORK_ROLE_RULE = "{argument} is a fork step with no thread id; run_ensemble forks only a Grok planner's thread, for a Grok step on the planner's workspace, so bind a run step or use a Grok planner."
COMPOSE_FROM_THREAD_RULE = "{argument} must continue or fork an existing thread; a run step starts a new thread with nothing to summarize. Bind it with bind_continue and a thread id."
COMPOSE_WORKTREE_READER_RULE = "{argument} must be a run step: an opencode or Muse reader runs in a disposable worktree, where the thread it would continue or fork is not reachable. Bind it with bind_thread and a run_ function."
COMPOSE_GROK_READER_RULE = "{argument} is a Grok reader in permission mode {mode}, which lets it edit files; compose never changes a step's config, so bind it with a GrokThreadConfig whose permission mode is plan or default."
COMPOSE_WORKSPACE_RULE = "{argument} has another workspace than {reference}; every step of this call must share one workspace."
COMPOSE_PROMPT_TOO_LONG = "{argument} is too long for {receiver}: with the fixed prompt text, the longest prompt that step can receive needs {needed} {units}, and it takes at most {cap}."
COMPOSE_CHARACTER_UNITS = "characters"
COMPOSE_COMMAND_LINE_UNITS = "UTF-16 command-line units"
COMPOSE_ALIAS_HARNESS_RULE = "{argument} must be a step on {expected}; got a step on {actual}."
COMPOSE_FIRST_STAGE_RULE = "{argument} must not use {{previous}}: the first stage has no earlier answer to splice."
COMPOSE_NOT_CALLABLE = "{argument} must be callable; got a value of type {type_name}."
