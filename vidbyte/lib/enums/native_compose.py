"""FILE: vidbyte/lib/enums/native_compose.py

PURPOSE: Defines the closed vocabularies of the composite thread functions: a verifier's decision (VerdictDecision), what a staged run does after a failed attempt (StageDecision), the ensemble stage that stopped a run (EnsembleStage), why compose itself failed (ThreadComposeProblem), the 22 prompt files and the 34 placeholder names they use (ComposePrompt, ComposeField), and every git flag compose passes (GitFlag).
ROLE IN CODEBASE: Imported by the records in vidbyte/lib/dataclasses/native_compose.py and native_ensemble.py, by the constants in vidbyte/lib/constants/native_compose.py, by ThreadComposeError in vidbyte/lib/errors/base.py and by the composites under vidbyte/harnesses/native/compose/. Exported from vidbyte/lib/enums/__init__.py; VerdictDecision, StageDecision, EnsembleStage and ThreadComposeProblem are also re-exported from vidbyte.harnesses.native.compose.
ARCHITECTURE NOTE: Every enum here is a StrEnum, so str(member) and an f-string give the value, as in vidbyte/lib/enums/native_threads.py. A ComposePrompt value is the stem of its Markdown file in the compose prompts folder, and a ComposeField value is the placeholder name inside those files, so the compose modules name files and fields without literals (base spec INV-15). GitFlag values are git's exact spellings.
FUNCTION INVENTORY: No functions. VerdictDecision, StageDecision, EnsembleStage, ThreadComposeProblem, ComposePrompt, ComposeField and GitFlag.
COMMON MODIFICATION PATTERNS: A new prompt file adds its ComposePrompt member and its COMPOSE_PROMPT_FIELDS entry in vidbyte/lib/constants/native_compose.py in the same change; a new placeholder adds its ComposeField member. A new git flag is added only when ComposeGit passes it.
WHAT NOT TO DO IN THIS FILE: 1. Do not import anything from vidbyte; enums sit at the bottom layer. 2. Do not add a git flag that changes the working tree, the real index, HEAD or a ref (spec INV-26). 3. Do not turn an enum here into a (str, Enum).
KNOWN EDGE CASES: GitFlag.CONFIG is git's -c switch, which takes the next argument as a setting; the two settings live in COMPOSE_GIT_SETTINGS. ThreadComposeProblem never covers a step's own failure, which stays a NativeThreadError recorded in the result.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_surface.py
"""

from __future__ import annotations

from enum import StrEnum


class VerdictDecision(StrEnum):
    """A verifier's decision about the writer's change."""

    APPROVE = "approve"
    REJECT = "reject"


class StageDecision(StrEnum):
    """What a staged run does after a failed attempt: try the same rung again, move to the next rung, or end the stage."""

    RETRY = "retry"
    RAISE_EFFORT = "raise_effort"
    ABORT = "abort"


class EnsembleStage(StrEnum):
    """The ensemble stage at which a run stopped."""

    PLAN = "plan"
    PROPOSE = "propose"
    SELECT = "select"
    IMPLEMENT = "implement"


class ThreadComposeProblem(StrEnum):
    """Why compose itself failed: git, a disposable worktree, or a reader that changed the workspace."""

    NOT_A_GIT_REPOSITORY = "not_a_git_repository"
    GIT_UNAVAILABLE = "git_unavailable"
    GIT_FAILED = "git_failed"
    WORKTREE_FAILED = "worktree_failed"
    READER_CHANGED_WORKSPACE = "reader_changed_workspace"


class ComposePrompt(StrEnum):
    """One prompt file of the compose prompts folder; the value is the file's stem."""

    PLANNER_SYSTEM = "planner_system"
    PLANNER_TURN = "planner_turn"
    PLAN_SCHEMA = "plan_schema"
    ROLE_SYSTEM = "role_system"
    ROLE_TURN = "role_turn"
    FORK_TURN = "fork_turn"
    SELECTOR_SYSTEM = "selector_system"
    SELECTOR_ROUND_TURN = "selector_round_turn"
    SELECTOR_FINAL_TURN = "selector_final_turn"
    ROUND_SCHEMA = "round_schema"
    SELECTION_SCHEMA = "selection_schema"
    PROPOSAL_BLOCK = "proposal_block"
    IMPLEMENTER_SYSTEM = "implementer_system"
    IMPLEMENTER_TURN = "implementer_turn"
    CHAIN_TURN = "chain_turn"
    VERIFY_TURN = "verify_turn"
    VERDICT_SCHEMA = "verdict_schema"
    HANDOFF_SUMMARY = "handoff_summary"
    HANDOFF_SEED = "handoff_seed"
    JSON_ANSWER = "json_answer"
    JSON_REPAIR = "json_repair"
    TRUNCATION_NOTE = "truncation_note"


class ComposeField(StrEnum):
    """One placeholder name the prompt files and caller templates use; the value is the name inside the braces."""

    ROLES = "roles"
    TASK = "task"
    ROLE_NAME = "role_name"
    IDENTITY = "identity"
    PERSONALITY = "personality"
    EXPERTISE = "expertise"
    KNOWLEDGE = "knowledge"
    SKILLS = "skills"
    GOAL = "goal"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    TASK_ANALYSIS = "task_analysis"
    ROSTER_STRATEGY = "roster_strategy"
    COVERAGE_SUMMARY = "coverage_summary"
    INSTRUCTIONS = "instructions"
    TURN = "turn"
    ROUND = "round"
    SURVIVING = "surviving"
    TARGET = "target"
    CANDIDATES = "candidates"
    NUMBER = "number"
    TEXT = "text"
    PROPOSAL = "proposal"
    APPROACH = "approach"
    RATIONALE = "rationale"
    GUIDANCE = "guidance"
    PROMPT = "prompt"
    PREVIOUS = "previous"
    DIFF = "diff"
    FILES = "files"
    SUMMARY = "summary"
    SCHEMA = "schema"
    PROBLEM = "problem"
    OMITTED = "omitted"


class GitFlag(StrEnum):
    """Every git flag compose passes, in git's exact spelling."""

    NO_OPTIONAL_LOCKS = "--no-optional-locks"
    CONFIG = "-c"
    SHOW_TOPLEVEL = "--show-toplevel"
    VERIFY = "--verify"
    QUIET = "--quiet"
    ALL = "-A"
    NAME_ONLY = "--name-only"
    NUL_TERMINATED = "-z"
    NO_RENAMES = "--no-renames"
    NO_COLOR = "--no-color"
    NO_EXT_DIFF = "--no-ext-diff"
    NO_TEXTCONV = "--no-textconv"
    DETACH = "--detach"
    NO_CHECKOUT = "--no-checkout"
    UPDATE = "-u"
    RESET = "--reset"
    FORCE = "--force"


__all__ = [
    "ComposeField",
    "ComposePrompt",
    "EnsembleStage",
    "GitFlag",
    "StageDecision",
    "ThreadComposeProblem",
    "VerdictDecision",
]
